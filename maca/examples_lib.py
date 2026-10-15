"""
examples_lib —— 测试用样例计算书导出模块

历史问题：`tests/test_maca.py` 直接 `import examples_lib`，但该模块从未被创建，
导致单元测试在收集阶段就 `ModuleNotFoundError` 崩溃——评审拿到包后跑
`python tests/test_maca.py` 会直接报错，看不到任何测试结果。

修复方式：不改测试逻辑，只把既有样例文件 `design_book_sample.txt` 的内容
导出为 `SAMPLE`，让测试原有断言（跨度 6.0m / 荷载 20kN/m / 截面 200×300）
继续成立。

单独运行可自检：
    python examples_lib.py
"""

from pathlib import Path

# 样例计算书正文（与 tests/test_maca.py 的断言严格对应）
SAMPLE = (
    '# 某简支混凝土梁计算书（脱敏示例）\n'
    '\n'
    '## 1. 结构信息\n'
    '- 类型：钢筋混凝土简支梁，单跨\n'
    '- 材料：C30 混凝土\n'
    '- 纵向钢筋：HRB300，as_area = 1256 mm^2（4C18）\n'
    '- 跨度：6.0 m\n'
    '- 均布荷载（可变）：20 kN/m\n'
    '- 是否计入自重：是\n'
    '- 初始截面：200 x 300\n'
    '\n'
    '## 2. 设计要求\n'
    '- 承载能力利用率 ≤ 1.0\n'
    '- 服务性挠度限值：≤ 20 mm\n'
)

SAMPLE_PATH = Path(__file__).resolve().parent / 'examples' / 'design_book_sample.txt'


def load_sample():
    """从磁盘读取样例；文件缺失时回退到内置 SAMPLE。"""
    if SAMPLE_PATH.is_file():
        try:
            return SAMPLE_PATH.read_text(encoding='utf-8')
        except Exception:
            pass
    return SAMPLE


if __name__ == '__main__':
    text = load_sample()
    print(f'SAMPLE 字数      : {len(text)}')
    print(f'样例文件存在      : {SAMPLE_PATH.is_file()}  ({SAMPLE_PATH})')
    for kw in ('跨度', '6.0', '20 kN/m', '200 x 300'):
        print(f'  含 "{kw}": {kw in text}')
