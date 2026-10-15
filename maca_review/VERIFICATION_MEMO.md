# MACA 评审辅助核验备忘（只读，未改动任何核心文件）

日期：2026-10-14 · 角色：外部评估，仅读取 + 新增本目录文件
核心目录（`maca/` 内 AGNES 产物）：**零修改**

## 1. 真值表核验（新文件：`real_fea_table_165.json`）

- 来源：`勒勒车计算书.docx` 第 4 张表（表格3，一级加载工况），逐行 XML 解析，非 OCR。
- 165 数据行，节点号 1..208（中间号缺失 = 该工况未列出全部节点，与 PPT 208 节点口径自洽）。
- 独立复算结果 vs `strategy.json` / `real_fea_table.py` 声称值：

| 量 | 复算值 | 声称值 | 判定 |
|---|---|---|---|
| \|DZ\| max | 32.224528 mm | 32.22 | ✅ 吻合 |
| 最大节点 | 115 | 115 | ✅ |
| 合成位移 max | 32.2582 mm | 32.26 | ✅ 吻合 |
| DZ min | -11.8125 mm | -11.81 | ✅ |
| DZ mean | 6.7123 mm | 6.71 | ✅ |

**结论：M1 矛盾（正文 15mm vs 实测 32.22mm，缺口 2.148 倍）独立复核成立，且 32.22mm 的口径反推（L/250→8055mm、L/600→19332mm 均超车架尺度）数值验证无误。这是项目最硬的证据，可放心写进答辩。**

- L 口径反推（M1 裁决依据）：32.22mm ↔ L=250×32.22=8055mm / 600×32.22=19332mm；15mm ↔ 3750mm / 9000mm。四者均非 500mm 级车架外廓 → "L 口径写错"判定数据层面自洽。

## 2. 口径自洽性检查（未改代码，只指出给 AGNES 的收尾提示）

1. **duel_report.json 当前 `red_unavailable`，蓝军参数全占位**（L=0.13m、截面 20×20、q=1000 N/m、E=206 GPa）。蓝军数字无工程含义——需 AGNES 收尾时按 `strategy.json` 真口径灌参（E=6 GPa 依 PPT slide11/M2 open，截面号 1/2，跨度取轴网 768.8/736.2/500mm），并保留"占位参数→真参数"的来源标注。
2. **`duel_run.py` red_run 中 MATL 硬编码 Q355 钢（E=206 GPa）**，与 strategy.json 的竹材 6 GPa 不一致——红方在线态若照此建模，与蓝军 6 GPa 口径会系统性差 34 倍，`consistent` 判据失真。建议 AGNES 收尾前对齐（材料取 strategy 口径，标注 M2 open）。
3. **`calc_report.py` 注释写"无 JWT"**，`duel_run.py` 用的是 MAPI-Key 双 header（MAPI-Key + Bearer）——术语不统一，答辩被追问鉴权机制时统一说法。
4. **`real_fea_table.py` 只有聚合统计，没有逐节点明细**——本次已把 165 行明细落盘到本目录 `real_fea_table_165.json`，AGNES 收尾做"快照即真值"红方双态时可直接引用（新增引用，非改动其逻辑）。

## 3. 给 AGNES 的收尾任务令（判据可机器验证，避免总结式收尾）

"完成"定义：`run_duel` 全链路跑完后，`duel_report.json` 满足——
1. `red.available == true` 且 `red.source ∈ {"MIDAS实时", "表格3快照"}`（快照态引用本目录 165 行 JSON，报告标 `red_source`）；
2. `summary.verdict ∈ {consistent, divergent}`（不再出现 `red_unavailable`，除非 MIDAS 与会话确实无法建立且快照亦缺失）；
3. 报告含全链路分段计时 + 与 600s 预算的对比；
4. 由 AGH verifier 出 turn 级 pass 终态，不接受文本总结代替。

## 4. AGH 三步骤底座（评审举证素材，引诊断日志 seq）

| 步骤 | 机制 | 本会话实证 |
|---|---|---|
| 任务规划 | todo 台账 | 45 done / 48 pending，跨 54 turn |
| 能力调用 | effect/intent + tool/call | 1612 effect、790 tool 调用，replay:"never" 全程账本 |
| 反馈处理+验证 | verifier/signal 三级 + repair/decision | 1587 信号（1570 pass）、12 轮 repair、approval 链路完整 |
