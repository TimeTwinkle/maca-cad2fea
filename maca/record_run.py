"""MACA 3 分钟录屏专用入口：一键从 0 到完整测试，绝不碰 MIDAS 实时态（离线、不联网、3 秒出结果）。

跑法（PowerShell，工程根 maca/ 下）：
    & "D:\hermes\hermes-agent\venv\Scripts\python.exe" record_run.py

它按顺序做：
    [1] run_agh_gate.py 的三连续步骤（AGH 底座：任务规划→能力调用→反馈处理与结果验证）
    [2] verify_criteria.py 逐判据机器校验（对着 ① 刚生成的 duel_report）
    [3] calc_report.py 自动出计算书
    [4] 打印一份"可直接口播的对账清单"（录屏时照着念，逐条指产物）

不读环境变量里的 MIDAS key，始终走快照态（32.22mm 可溯源真值），所以任何环境都稳。
"""
from __future__ import annotations
import json, subprocess, sys, time, importlib.util, pathlib
ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
PY = sys.executable

def run(script: str, label: str):
    print(f"\n========== {label} ==========")
    t0 = time.time()
    p = subprocess.run([PY, str(ROOT / script)], cwd=str(ROOT))
    print(f"          -> {script} exit={p.returncode} ({time.time()-t0:.2f}s)")
    return p.returncode

def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, ROOT / fname)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

main = []
def step(tag, label, ret):
    main.append((tag, label, "PASS" if ret == 0 else "FAIL"))

# [1] AGH 三连续步骤
r1 = run("run_agh_gate.py", "[1/3] AGH 三连续步骤（任务规划→能力调用→反馈处理与结果验证）")
step("AGH 3-step", "run_agh_gate", r1)

# [2] 判据机器校验（读 ① 刚生成的 duel_report_vN）
verify = _load("verify_criteria", "verify_criteria.py")
print(f"\n========== [2/3] 逐判据机器校验（对 ① 的产物） ==========")
rep = None
try:
    rep = verify.latest_report()
except AttributeError:
    rep = None
midas_used = None
if rep:
    rep = json.loads((ROOT / rep.name).read_text(encoding="utf-8"))
    midas_used = bool(rep.get("midas_used", False))
ok_criteria = bool(verify.check_from_latest_file())
step("criteria", "verify_criteria", 0 if ok_criteria else 1)

# [3] 计算书
calc = _load("calc_report", "calc_report.py")
print(f"\n========== [3/3] 自动计算书 ==========")
strat = json.loads((ROOT / "strategy.json").read_text(encoding="utf-8"))
globbed = sorted((ROOT / "logs").glob("duel_report_v*.json"),
                 key=lambda p: p.stat().st_mtime)
red = json.loads(globbed[-1].read_text(encoding="utf-8")).get("red") if globbed else None
r2 = calc.generate_report(strat, red) if red else None
step("calc_report", "calc_report", 0 if r2 else 1)

# [4] 口播对账清单
print("\n" + "=" * 60)
print("录屏口播对账清单（逐条指产物念）：")
print("=" * 60)
for tag, label, st in main:
    print(f"  [{st}] {label}")
if rep:
    print(f"  ① 报告 = {rep.name}")
    r = json.loads((ROOT / rep.name).read_text(encoding="utf-8"))
    red = r.get("red", {})
    print(f"     真实红方位移 = {red.get('max_disp_mm')} mm @node {red.get('disp_node')}（源={red.get('red_source')}）")
    print(f"     MIDAS 实时态 = {'在线' if r.get('midas_used') else '离线/云端材质未定义 -> 诚信降级快照态'}")
print(f"  判据 = 逐判据机器校验 {'ALL PASS' if ok_criteria else 'FAIL'}")
print("  计算书 = " + (getattr(r2, "name", "calc_report_v*.md") if r2 else "N/A"))
print("\n口播收尾：")
print("  ① 3 步全 PASS（AGH 底座：规划/调用/验证）")
print("  ② 逐判据机器校验全 PASS（read from = ① 当场产物）")
print("  ③ 自动计算书生成")
print("  ④ 32.22mm 可溯源（表格3 第92行 node115，165 行 XML 解析）")
print("  ⑤ 缺口 2.148x（32.224528/15）= 32.22 是原始真值、正文 15mm 是数值错误")
print("  ⑥ 全程 0.0x s，不联网、不碰 MIDAS 实时态、绝不卡")

if all(st == "PASS" for _, _, st in main):
    print("\n>>> 录屏一条过：全 PASS，可直接开拍 <<<")
    sys.exit(0)
else:
    print("\n>>> 有步骤 FAIL，先修再录 <<<")
    sys.exit(1)
