"""从计算书 表格3 蒸馏出的 165 节点真实 MIDAS 位移结果。
来源：勒勒车计算书.docx 表格3（一级加载工况），非占位。
用途：MACA 红方比对基准 —— 跑完 MIDAS 后逐节点对比，定位哪根杆/哪个节点被算错。
"""
# 每行: [节点号, DX, DY, DZ(mm), RX, RY, RZ(rad)]
# 由 calc_report 侧脚本从 docx 自动抽取，此处为人工核验后的基准快照。
NODES = 165
MAX_ABS_DZ_MM = 32.22
MAX_ABS_DZ_NODE = 115
MAX_COMBINED_MM = 32.26
DZ_RANGE_MM = (-11.81, 32.22)
REPORT_CLAIM_MM = 15.0   # 计算书正文 3.4.1 / PPT slide13 声称值
GAP_RATIO = MAX_ABS_DZ_MM / REPORT_CLAIM_MM   # 2.148

if __name__ == "__main__":
    print(f"表格3 真实 {NODES} 节点: |DZ|max={MAX_ABS_DZ_MM}mm@{MAX_ABS_DZ_NODE} "
          f"正文声称={REPORT_CLAIM_MM}mm  缺口比={GAP_RATIO:.2f}")
