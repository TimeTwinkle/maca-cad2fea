"""交付清单自检：只编译 + 列文件 + 标可复现性。不做任何空转。"""
import py_compile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 成品模块（MACA 交付物，全需编译绿）
DELIVERABLES = [
    "cad_model.py",
    "duel_run.py",
    "duel_rules.py",
    "midas_importer.py",
    "cross_validate.py",
    "calc_report.py",
    "discrepancy.py",
    "real_fea_table.py",
    "maca_mcp.py",
    "project_llecar.py",
]

results = []
for f in DELIVERABLES:
    p = ROOT / f
    if not p.exists():
        results.append((f, "MISSING"))
        continue
    try:
        py_compile.compile(str(p), doraise=True)
        results.append((f, "OK"))
    except Exception as e:
        results.append((f, f"COMPILE_FAIL {e}"))

print("=== 编译自检 ===")
for f, r in results:
    print(f"  {f:20s} {r}")

# 数据资产（只读，确认在）
print("\n=== 数据资产（只读确认存在） ===")
DATA = ["strategy.json", "duel_rules.json",
        "logs/calc_report.md", "logs/structure_manifest.json",
        "logs/max_component.json", "logs/midas_import_trace.json"]
for f in DATA:
    p = ROOT / f
    print(f"  {f:30s} {'OK' if p.exists() else 'MISSING'}  "
          f"{p.stat().st_size if p.exists() else 0}B")

# 已删项确认
print("\n=== 已删除的空转产物 ===")
for f in ["mgbx_parser.py", "_audit_run.py"]:
    print(f"  {f:20s} {'GONE' if not (ROOT/f).exists() else 'STILL THERE'}")

# 退出码：编译失败或缺交付物 -> 1
bad = [r for r in results if r[1] != "OK"]
sys.exit(1 if bad else 0)
