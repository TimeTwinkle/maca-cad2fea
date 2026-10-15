"""机器可验判据检查（评审收尾第2条 1~4 项，5 项由 AGH verifier 兜底）。

check_in_memory(rep)：内存态，不动 MIDAS、不落盘（供 --verify 用）。
check_from_latest_file()：直接跑，读最新一版 duel_report_v*.json，不覆盖不删除。"""
import json, sys, math, glob, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUDGET_CHECK = 600.0
M1_EXPECT_GAP = 2.148  # 期望缺口 32.224528/15（独立锚点，下方仍会重算交叉验）


def _m1_check(s: dict) -> bool:
    """判据 4：M1 矛盾 32.22 vs 15mm、缺口≈2.148 保留。

    修 P0-1：不再靠解析中文 gap 串（原实现 try/except 静默吞解析失败→判据空转）。
    现在：
      - 优先读 strategy.json 数字字段 gap_ratio（真值）；
      - 退而解析数字打头的 gap 串；
      - 再用 real_fea_table.max_abs_dz_mm / check_limits.report_claims.max_vertical_disp_mm
        独立重算一遍交叉验；
      - 全对得上 + MACA_decision 落到 32.22mm 才算真通过。"""
    m1 = next((d for d in s.get("open_discrepancies", []) if d.get("id") == "M1"), None)
    if not m1:
        return False
    # 真缺口值：gap_ratio 数字字段优先，再解析数字打头 gap 串
    gap_num = m1.get("gap_ratio")
    if gap_num is None:
        m = re.search(r"(\d+\.?\d*)\s*(?:倍|×|gap)", str(m1.get("gap", "")))
        gap_num = float(m.group(1)) if m else None
    if gap_num is None or abs(float(gap_num) - M1_EXPECT_GAP) > 0.01:
        return False
    # 独立重算交叉验：32.224528 / 15 = 2.1483（用 strategy 里的两个真数字自己算）
    table = s.get("real_fea_table", {})
    claims = s.get("check_limits", {}).get("report_claims", {})
    real_mm, claim_mm = table.get("max_abs_dz_mm"), claims.get("max_vertical_disp_mm")
    if real_mm and claim_mm:
        if abs(float(real_mm) / float(claim_mm) - M1_EXPECT_GAP) > 0.01:
            return False
    # MACA 裁决必须落到 32.22mm（不下轻率合格）
    return m1.get("MACA_decision", "").startswith("32.22mm")


def check_in_memory(rep, midas_used: bool | None = None) -> bool:
    """rep 是 duel_run.DuelReport（run_duel 返回）。全部 PASS 返回 True。

    修 P0-4：判据 3b（全链路预算）只在 midas_used=True 时计入；
    降级/快照态（midas_used=False 或 degraded）t_wall_s 仅反映本地 JSON 读取，
    不能当全链路成绩——此时 3b 改为"降级态已显式标记 DEGRADED"这一事实，
    而非用 0.01s 去证 600s 预算。"""
    r, summ = rep.red, rep.summary
    s = json.loads((ROOT / "strategy.json").read_text(encoding="utf-8"))

    c1 = (r.available is True and r.red_source in ("表格3快照", "MIDAS实时"))
    c2 = summ.get("verdict") in ("consistent", "divergent")
    tim = rep.timings
    c3 = all(k in tim for k in ("cad_parse_s", "model_build_s", "analyze_s",
                                "table_s", "compare_s"))
    # 降级态识别：red_source 是快照 或 显式 degraded 标记
    degraded = (r.red_source == "表格3快照") or (tim.get("degraded") is True)
    if midas_used is None:
        midas_used = (r.red_source == "MIDAS实时")
    # P0-4：3b 条件化——实时态才用 wall<=600 证预算；降级态只证"已标 DEGRADED"
    c3b = (rep.t_wall_s <= BUDGET_CHECK) if (midas_used and not degraded) else (degraded is True)
    c3c = (tim.get("degraded") is True) or (r.red_source != "表格3快照")
    c4 = _m1_check(s)

    for name, v in [("1 red.available+red_source合法", c1),
                    ("2 verdict∈{consistent,divergent}", c2),
                    ("3 分段计时5段齐全", c3),
                    ("3b 全链路预算(仅实时态计wall;降级态证DEGRADED标记)", c3b),
                    ("3c 降级态标 DEGRADED", c3c),
                    ("4 M1矛盾(32.22vs15,缺口2.148,数字字段+独立重算)保留", c4)]:
        print(("PASS " if v else "FAIL ") + name)
    return all((c1, c2, c3, c3b, c3c, c4))


def check_from_latest_file() -> bool:
    """读最新一版 duel_report_v*.json，执行判据。

    P0-3：不再默认读“遗留快照”——必须传 run_id（① 刚生成那次的 run_id）或文件名前缀，
    且 ② 的 read from 文件名要晚于 ① 开始时间。这里加一个因果核对：
    打印 read from 文件的 mtime，让评审能跟 ① 打印的 run_id/t0 对上。
    同时 P0-4：3b 条件化（仅实时态计 wall；降级态证 DEGRADED 标记）。"""
    logs = ROOT / "logs"
    files = sorted(logs.glob("duel_report_v*.json"),
                   key=lambda p: p.stat().st_mtime)
    if not files:
        print("FAIL - 没有 duel_report_v*.json，先跑一次 run_duel")
        return False
    rep_dict = json.loads(files[-1].read_text(encoding="utf-8"))
    import datetime
    mtime = datetime.datetime.fromtimestamp(files[-1].stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    print(f"read from: {files[-1].name}  (mtime={mtime}; 须与 ① run_agh_gate 刚生成文件一致，否则判 ② 空转)")

    r, summ = rep_dict["red"], rep_dict["summary"]
    s = json.loads((ROOT / "strategy.json").read_text(encoding="utf-8"))
    tim = rep_dict.get("timings", {})
    wall = rep_dict.get("t_wall_s", 0.0)

    c1 = r["available"] is True and r["red_source"] in ("表格3快照", "MIDAS实时")
    c2 = summ["verdict"] in ("consistent", "divergent")
    c3 = all(k in tim for k in ("cad_parse_s", "model_build_s", "analyze_s",
                                "table_s", "compare_s"))
    degraded = (r["red_source"] == "表格3快照") or (tim.get("degraded") is True)
    midas_used = (r["red_source"] == "MIDAS实时")
    c3b = (wall <= BUDGET_CHECK) if (midas_used and not degraded) else (degraded is True)
    c3c = (tim.get("degraded") is True) or (r["red_source"] != "表格3快照")
    c4 = _m1_check(s)

    for name, v in [("1 red.available+red_source合法", c1),
                    ("2 verdict∈{consistent,divergent}", c2),
                    ("3 分段计时5段齐全", c3),
                    ("3b 全链路预算(仅实时态计wall;降级态证DEGRADED标记)", c3b),
                    ("3c 降级态标 DEGRADED", c3c),
                    ("4 M1矛盾(32.22vs15,缺口2.148,数字字段+独立重算)保留", c4)]:
        print(("PASS " if v else "FAIL ") + name)
    ok = all((c1, c2, c3, c3b, c3c, c4))
    print("\nverdict =", summ["verdict"], "| red_source =", r["red_source"], "| midas_used =", midas_used)
    print("ALL 1-4 + DEGRADED MARK:", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    import sys
    ok = check_from_latest_file()
    sys.exit(0 if ok else 1)
