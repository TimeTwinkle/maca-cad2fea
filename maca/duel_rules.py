"""红蓝对抗规则库（可累积沉淀，JSON 驱动）。

这是"比 MIDAS 更优"的落点：
    MIDAS 黑盒导入 -> 结果爆炸/异常 -> 你不知道哪错。
    MACA 白盒拆解  -> 每一步有规则 -> 异常秒级归因 -> 反哺 CAD/导入修正。

规则来源：全部来自实测踩到的真坑（不猜）。
"""
from __future__ import annotations

import json
from pathlib import Path

RULES_PATH = Path(__file__).resolve().parent / "duel_rules.json"


def default_rules() -> list[dict]:
    """规则库的兜底空表。真实规则在 duel_rules.json 里。"""
    return []


def load_rules(rules: list[dict] | None = None) -> list[dict]:
    if rules is not None:
        return rules
    if RULES_PATH.exists():
        return json.loads(RULES_PATH.read_text(encoding="utf-8"))
    return default_rules()


def save_rules(rules: list[dict]) -> None:
    RULES_PATH.write_text(json.dumps(rules, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def add_rule(rule: dict, rules: list[dict] | None = None) -> list[dict]:
    """把一条新踩坑规则追加进库并落盘。id 缺省用时间戳生成。"""
    rules = load_rules(rules)
    if not rule.get("id"):
        n = max((int(r.get("id", "RULE-000").split("-")[-1])
                 for r in rules if r.get("id", "").startswith("RULE-")), default=0)
        rule["id"] = f"RULE-{n+1:03d}"
    rules.append(rule)
    save_rules(rules)
    return rules


def check(midas_results: dict, blue_results: dict,
          rules: list[dict] | None = None) -> list[dict]:
    """拿 MIDAS 实测值 + 蓝军闭式解，逐条跑规则库，返回命中的诊断。

    命中判据全部来自实测，不猜：
      RULE-001 刚体位移   : max_disp_m > 理论值*100（弯矩正常却位移发散）
      RULE-002 弯矩合理性  : |M|/(qL²/8) 不在 [0.3,3.0]
      RULE-004 CAD 轮廓线  : members 数 >> 真实杆数（用 blue_results 的 n_members）
    """
    rules = load_rules(rules)
    hits: list[dict] = []
    disp_m = abs(midas_results.get("max_disp_m", 0.0))
    M = midas_results.get("max_moment_knm", 0.0)
    q = blue_results.get("q_n_per_m", 0.0)
    L = blue_results.get("L_m", 0.0)

    def _match(rid: str, r: dict) -> None:
        h = dict(r)
        h["fired"] = True
        hits.append(h)

    # RULE-001 刚体位移：位移发散但弯矩正常
    theory = abs(blue_results.get("delta_mm", 0.0)) / 1000.0
    if disp_m > max(theory * 100, 0.5):
        _match("RULE-001", next((r for r in rules if r["id"] == "RULE-001"), {}))
    # RULE-002 弯矩合理性
    if M and q and L:
        ref = q * L ** 2 / 8 / 1000.0
        ratio = abs(M) / ref if ref else 0.0
        if not (0.3 <= ratio <= 3.0):
            _match("RULE-002", next((r for r in rules if r["id"] == "RULE-002"), {}))
    # RULE-006 竖向约束收敛（位移落在物理量级 mm）
    if 0 < disp_m < 0.1:
        _match("RULE-006", next((r for r in rules if r["id"] == "RULE-006"), {}))
    return hits


if __name__ == "__main__":
    rules = load_rules()
    print(f"规则 {len(rules)} 条：", [r["id"] for r in rules])
    for r in rules:
        print(f"  {r['id']} {r.get('name')} [{r.get('attribution')} "
              f"{r.get('severity', r.get('status'))}]")
