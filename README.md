# MACA · 判断蒸馏与独立复核层

**AutoCAD → MIDAS GEN NX 结构计算自动化，并给建模结果装一层能挑错的复核。**

把"读图纸 → 在 MIDAS GEN NX 手工建模 → 有限元分析 → 出计算书"这条约 3 小时的人工流程做成可运行代码包，
并把工程师关于 MIDAS 的判断（用哪个截面、约束放哪、工况怎么组合、结果该信哪个数）蒸馏成机器可读配置。
在此之上增设一层**独立于建模过程的复核**：自动检出图纸断线、约束缺失与计算书自相矛盾。
**取不到实时真值时显式降级并标注，从不把 0 或缺测值当作实时结果。**

基于 **Agnes Harness（AGH）+ Agnes 3.0 Flash** 构建与执行，全程 stage 级留痕可审。

## 30 秒跑起来

```powershell
pip install ezdxf requests          # 仅两包，其余标准库；Python 3.10+
cd maca
python run_agh_gate.py              # ① AGH 三连续步骤（任务规划→能力调用→反馈处理与结果验证）
python verify_criteria.py           # ② 6 条判据机器校验（会打印所读文件与 mtime）
python calc_report.py               # ③ 自动计算书（M1 矛盾 RED FLAG + 不予合格结论）
```
不联网、不需要 MIDAS 授权即可跑通 ①②③（此时为快照态，显式标 `degraded=true`）。
配好凭证后自动尝试实时态：`. .\maca\setup_maca.ps1 <活JWT>` → `red_source=MIDAS实时`。

## 它检出了什么（全部来自本项目真实工程件，可独立复算）

| 检出 | 事实 | 复核依据 |
|---|---|---|
| **计算书自相矛盾** | 正文 3.4.1 与 PPT slide13 称"最大位移 15mm 满足要求"，而**同一文档表格3** 实测 `32.224528mm @ node115`，缺口 **2.1483 倍** | `maca_review/real_fea_table_165.json`（165 行逐行 XML 解析；`sha256(word/document.xml)=f78fb79f…` 可回源计算书原件复验） |
| **图纸不是结构** | 源图纸 891 实体 → 263 节点 / 371 杆，**散落 47 个互不相连连通分量**；直接导入即机构，位移发散至 1e10 m | `cad_model.py`、`maca/logs/structure_manifest.json`、RULE-004 |
| **约束缺竖向** | 平面 3 点固支只锁 XY → 位移发散；节点 1 改 `1111100`（含竖向）后收敛至 −0.53mm 量级 | RULE-001/006 |
| **人工全模型解本身奇异** | MIDAS 原生求解日志含 **265 条位移 `ABNORMAL`** + **234 个自由度 `MAY BE SINGULAR`**，且无任何 `.XOUT` 出现 32.22 | 原始求解日志属团队工程数据，随作品文件包提交；仓库内 `提交/05_运行证据/` 提供计数结果与复算方法 |

## 目录

```
maca/                代码包（CAD 解析 / 拓扑筛选 / MIDAS MAPI 建模 / 复核规则 / 计算书 / MCP server）
maca_review/         表格3 原始位移 165 行（独立锚点，含 sha256 与逐行数据）
提交/                交付面：按报名表必填项分槽（运行证据、测试样例、成员声明、公开内容、原件索引）
```
> 原始工程件（CAD 图纸 `.dxf/.dwg`、源计算书 docx、MIDAS `.mgbx/.XOUT` 求解日志）**不进公开仓库**，
> 随作品文件包提交给评审；仓库内保留可复算的派生证据与校验值（`maca_review/real_fea_table_165.json`、`maca/logs/`）。

## 三层结构

1. **判断蒸馏** `maca/strategy.json` —— 竹材 E=6GPa、208 节点、1.2恒+1.4活 / 1.0恒+1.0活、挠度限值 L/400·L/250·L/200、连通分量筛选、M1/M2/M3/M4 矛盾项
2. **过程复现** `cad_model.py` → `midas_importer.py` → `duel_run.py` —— 经 MIDAS 官方 REST MAPI 建模/分析/取数，15 步请求与状态码全留痕
3. **独立复核** `duel_rules.json`（6 条，一条实测坑换一条规则）+ `discrepancy.py` + `calc_report.py`

## 已知边界（不藏）

1. **MIDAS 实时求解态未通过**：15 步写入全 200/201，唯材质失败——`analyze` 回 `[错误] 材料 没有定义。`。
   两个候选变量待对照实验分辨：① 写入 `ELAST=6e9` 在本单位制（`FORCE:KN / DIST:M`，即 kPa）下等于 6000 GPa，超出可接受范围；
   ② 材质名含括号与逗号，而同实例历史成功并可读回的自定义 USER 材质名为 `Q355`、`ELAST=206000000`（=206 GPa）。
   修正后 `red_source` 可无缝翻为 `MIDAS实时`，计算书代码零改动。
2. 复刻对象是 CAD 最大连通分量（30 节点 / 46 杆），与表格3 的 208 节点全模型**跨口径不可比**；
   故当前 `verdict=divergent` 的语义是"口径不可比"，**不作为结构缺陷证据**，缺陷证据是 M1 矛盾本身。
3. 截面/材料/限值/荷载系数仍有待确认项（M2/M3 open），命令行使用兜底占位值。
4. 蓝军为闭式解（简支梁公式），仅适用局部构件；整体结构的双引擎对拍尚未完成。
5. MCP 工具注册受 AGH 侧 lifecycle 限制未生效，演示以 CLI 一条命令为准，不宣称 agent 自动调度。
6. 计时口径缺陷已记录：`t_wall_s` 未并入 MIDAS 侧真实耗时（trace 里 `analyze 9.0s`，而 `analyze_s=0.0`）。

## 许可与数据说明

CAD 图纸、计算书与 PPT 为团队真实工程产物，仅随作品文件包提交给评审用于成果验证，不在公开仓库内；MIDAS 为团队合法授权副本。
**仓库内不含任何有效凭证**：`setup_maca.ps1` 的 JWT 示例位已替换为占位符，密钥仅经环境变量注入。
