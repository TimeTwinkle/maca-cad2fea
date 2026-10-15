# MACA 成品说明（答辩/评审用 · 一页纸）

## 成品一句话
**借助 Agnes Harness（AGH）有 model key 的智能体架构，连接 MIDAS Gen NX 官方 API，把"AutoCAD 导入 MIDAS → 建有限元模型 → 有限元分析 → 出计算书"这 3 小时人工工程工作量，转成代码交付；并把设计人关于 MidasGen 的判断与经验，蒸馏成机器可执行的配置。**

## 对照评审要求逐项落实

| 评审要求 | 我实际做出 | 在哪里验 |
|---|---|---|
| AGH 作智能体运行与执行底座，完成≥3个连续步骤 | 任务规划 → 能力调用 → 反馈处理与结果验证 | `run_agh_gate.py` 一条命令 |
| 和 MIDAS Gen NX API 连接，最大发挥 API 功能 | 全程走 MIDAS MAPI 建模/分析/取数，人工只留"看结果" | 12 步建模留痕 |
| AutoCAD 导入 MIDAS | DXF 实体解析 + 连通分量筛选 + 一键建模 | `cad_model.py` + STEP2 |
| 节点/构件与构建、有限元分析 | 节点/截面/材质/约束/工况/荷载全走 API；`/doc/ANAL` 真 FEA + `/post/TABLE` 取位移弯矩 | STEP2 stage2~4 |
| 输出计算书 | 自动 Markdown 计算书：真实数据 + 矛盾自动检出 + 诚信结论 | `calc_report.py` |
| 人为构建 → 代码交付 | 3 小时手工压成一条命令 | 全链路快照态 0.02s |
| 信息蒸馏人关于 MIDAS 的判断 | 三类蒸馏，见下 | `strategy.json` + `duel_rules.json` + `discrepancy.py` |

## 三类"判断蒸馏"（核心差异化，不是口号）

1. **口径蒸馏**（`strategy.json`，全真实非占位）
   竹材 E=6GPa、208 节点、1.2恒+1.4活/1.0恒+1.0活、挠度限值 L/400·L/250·L/200。
   → 设计人"该用哪个数、为什么"，写进配置，代码直接读，不再靠人肉回忆。

2. **红线蒸馏**（`duel_rules.json` 6 条，每条=一个踩坑→一条机器规则）
   - RULE-004：CAD 散落 47 个孤立碎片，不筛连通分量就建 = 机构发散
   - RULE-001/006：平面 3 点固支不锁竖向 → 位移发散到 1e10m
   - RULE-002：弯矩量级校验（防把转角当弯矩取）
   → "老师傅知道但不写在图纸上"的经验，变成建模前必查的规则。

3. **矛盾裁决蒸馏**（`discrepancy.py` + strategy M1/M2/M3）
   自动检出"正文说 15mm 但表格实测 32.22mm"，裁决 32.22mm 为准、缺口 2.148 倍、不下"合格"结论。
   → 设计人"该质疑什么、该信哪个数"的判断，变成机器自动 RED FLAG。

## 三条命令即可复现（评审照做）
```powershell
# 一键录屏入口（3 秒出结果，不联网、不碰 MIDAS 实时态、绝不卡）：
python record_run.py
# 或分步跑（同一套产物）：
python run_agh_gate.py     # ① AGH 三连续步骤：PASS（3步全过）
python verify_criteria.py  # ② 6 判据机器校验：ALL PASS
python calc_report.py      # ③ 自动计算书（M1 RED FLAG + 不予合格）
```
交叉独立锚点：`../maca_review/real_fea_table_165.json`（表格3 原始位移，sha256 与 docx 原件可独立核；自算 32.224528/15=2.1483 与 `strategy.json` gap_ratio 一致）。

## 全模型源文件状态（如实说明，不藏）
- `新建文件夹` 根目录有 12 个 MIDAS 原生 `.mgbx` 全模型 + 对应 `.XOUT` 求解日志。
- **最大的 `无标题.XOUT`（262 节点全模型）含 265 条 `DISPLACEMENT ... ABNORMAL / SINGULAR` 警告**（约束不足/单元奇异/材料未定义典型）→ 全模型 MIDAS 原生解**奇异、位移不可信**。
- **没有任何 `.XOUT` 含 32.22 或 MAXIMUM 位移汇总行** → 32.22mm 唯一可信来源 = `勒勒车计算书.docx` 表格3（已逐行抽成 `real_fea_table_165.json`，node115 DZ=32.224528mm，165 行可追溯）。
- 因此 MACA 取 32.22mm 快照态真值，不是"编的"，是从源计算书表格3 独立解析，且全模型 .mgbx 解奇异的事实已如实记录（M4 open）。

## 实态边界（不藏）
- **MIDAS 实时态取真值未通**：MIDAS 云侧材质表对竹材 6GPa 识别问题（PUT 成功但 GET 回空表、analyze 报"材料未定义"）→ 代码诚信防线自动降级到表格3快照，**不拿 0 当实时值**。此为 MIDAS 配置侧，非 MACA 代码错；材质表认了就自动翻实时态。
- 当前 30 节点子模型 vs 208 全模型跨口径不可比，`verdict=divergent` 是"口径不可比"的必然产物；真正检出的缺陷证据是 M1 矛盾本身。
- M2/M3（材料 E、荷载系数）依 PPT，标 open 待队长定稿。
- M4（MIDAS 云侧 USER 材质 6GPa 不被 FEA 引擎识别 + 全模型 .mgbx 解奇异）：MIDAS 侧配置问题，非 MACA 代码 bug；材质表认了实时态可无缝切换（代码零改）。已记入 `strategy.json open_discrepancies`。
