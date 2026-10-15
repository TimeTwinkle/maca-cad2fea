# MACA 作品验收指引 v2（给评审 · 照做即可复现全部结果）

> v2 变更（回应上一轮静态核对 4 处 P0/P1）：
> - P0-1 strategy.json M1 加数字字段 gap_ratio=2.1483，判据4改读数字字段+独立重算32.224528/15交叉验，不再靠解析中文 gap 串静默吞失败
> - P0-2 快照弯矩 NaN→null，harness_audit.json 现在严格 JSON 合法（jq/JSON.parse/在线校验器可直接打开）
> - P0-4 判据3b条件化：仅 MIDAS 实时态证 wall<=600；降级态改证已显式标 DEGRADED
> - P0-3 verify_criteria 打印 read from + mtime，指引要求评审核对②读的=①当场产物（防遗留快照空转）
> - P1-5 路径修正 ../maca_review/（不在 maca/ 下）
> - P1-6 去写死python + 依赖清单（仅 ezdxf + requests 两包）
> - P1-7 divergent 语义重定义：当前 divergent = 跨口径不可比的必然产物，非缺陷证据；缺陷证据是 M1 矛盾本身

## 0. 一键复现（5 分钟，任意 Python 3.10+）

前置：Windows + PowerShell。Python 不写死，下用 $PY 代指（任意 3.10+）：

```powershell
$PY = python
pip install ezdxf requests   # 仅这两包，其余 stdlib
```

在 maca/ 目录按序跑 3 条：

```powershell
& $PY run_agh_gate.py        # ① AGH 三连续步骤，全过 exit 0；生成 logs/duel_report_v*.json，记下其文件名
& $PY verify_criteria.py     # ② 判据机器校验，全 PASS；首行打印 read from + mtime
& $PY calc_report.py         # ③ 自动计算书
```

★ P0-3 必做核对：② 的 read from 文件名必须等于 ① 刚生成那版（同一份当场产物，非遗留快照）。

预期结果：
- ① 末行 AGH 三连续步骤: PASS；harness_audit.json 里 criteria_pass=true, m1_preserved=true, verdict=divergent, midas_used 取决于当时 MIDAS 在线与否
- ② 6 行 PASS（1/2/3/3b/3c/4），末行 ALL 1-4 + DEGRADED MARK: PASS
- ③ calc_report_v*.md 第三节 FEA 取数=表格3快照或MIDAS实时，弯矩 n/a 或真值，M1 RED FLAG，第五节 不予合格

## 1. 逐条判据对答案（评审找茬清单）

| # | 判据 | 怎么验 | 期望 |
|---|---|---|---|
| 1 | red.available=true 且 red_source∈{表格3快照,MIDAS实时} | ② 第1行 | PASS |
| 2 | summary.verdict∈{consistent,divergent} | ② 第2行 | PASS |
| 3 | 分段计时 5 段齐全 | ② 第3行 | PASS |
| 3b | 全链路预算：仅 MIDAS 实时态证 wall<=600；降级态改证已标 DEGRADED | ② 第4行 | PASS |
| 3c | 降级态显式标 DEGRADED | ② 第5行 | PASS |
| 4 | M1 矛盾 32.22vs15 缺口2.148（读 gap_ratio 数字字段+独立重算32.224528/15交叉验） | ② 第6行 | PASS |

P0-3 因果核对：先 ① 再 ②，② 读的=① 当场产物。若 ② 读到交付前就存在的旧文件→判 ② 空转。

独立数据源（不依赖我生成的中间件，评审自算）：
- ../maca_review/real_fea_table_165.json：max_abs_dz_mm=32.224528, node=115，sha256_document_xml=f78fb79f...（docx 原件在项目根目录 新建文件夹/，可独立核 sha256）
- strategy.json open_discrepancies[M1]：gap_ratio=2.1483, MACA_decision=32.22mm 为准
- 缺口独立重算 = 32.224528/15 = 2.1483 ✅

## 2. 提示词模板（拿去喂给任何 AI 评审 / 自动化核验）

### 2.1 让评审 AI 核验作品能跑+结果有效

```
你是结构 AI 作品的评审。请按下述方法核验 MACA 项目（maca 目录，任意 Python 3.10+ 解释器）。
要求：只信可机器复现的证据，不接受作者口述。执行权限若被拒，改为静态核对每条声称的
验收点能否在磁盘既有产物上对上，并自己重算独立锚点。

步骤（按序，①→②→③，② 读的是 ① 当场产物）：
1. 执行 run_agh_gate.py（AGH 三连续步骤），确认 exit 0 且末行 "AGH 三连续步骤: PASS"；
   记下它生成的 logs/duel_report_v*.json 文件名。
2. 执行 verify_criteria.py，确认 6 判据（1/2/3/3b/3c/4）全 PASS；
   ★ 核对它首行 "read from" 文件名 = 第 1 步刚生成那版（防读遗留快照空转）。
3. 用严格 JSON 解析（jq / JSON.parse / 在线校验器）打开 logs/harness_audit.json，
   确认 criteria_pass=true、m1_preserved=true、verdict=divergent、midas_used 为 true/false。
4. 打开 logs/calc_report_v*.md，确认：
   - FEA 结果节取数来源是"表格3快照"或"MIDAS实时"（不得是伪造实时值）；
   - M1 矛盾 32.22 vs 15mm、缺口约 2.148 以 RED FLAG 保留；
   - 结论节写"不予合格结论"（诚信红线：只摆矛盾不替作者下合格）。
5. 交叉独立数据源：
   - ../maca_review/real_fea_table_165.json 的 data["stats_check"]["max_abs_dz_mm"]=32.224528（注意在 stats_check 子对象下，非顶层 key；取顶层得 None）必须等于 calc_report 引用的 32.22mm；
   - 自算 32.224528/15 = 2.1483，必须等于 strategy.json M1.gap_ratio。

判据：上面 5 条全满足才算"作品实际运行、结果经数据/专业规则证明有效"。
任一不满足，指出具体哪条 FAIL 及证据（文件路径+行）。
```

### 2.2 让评审 AI 判断人的判断是否被蒸馏成机器规则

```
MACA 项目应"把设计人关于 MidasGen 的判断与经验蒸馏为机器可执行的配置"。请核验：
1. strategy.json 是否含真实口径（竹材 E=6GPa、208节点、1.2恒+1.4活/1.0恒+1.0活、
   挠度限值 L/400·L/250·L/200、M1 矛盾裁决 gap_ratio=2.1483），而非占位造数。
2. duel_rules.json 是否含可执行红线（连通分量筛选、竖向约束、弯矩量级、
   位移异常等），且每条能对应到一个"踩坑→规则"。
3. 这些配置是否真的被运行链路读取（duel_run.py 的 _elastic_gpa/口径段、
   calc_report.py 的 contradiction 检出、verify_criteria._m1_check 读 gap_ratio），
   而非写了没人用。
判据：若口径为占位、或规则未接入运行链路，则"蒸馏"不成立，判不通过。
```

### 2.3 现场答辩速答（被问"你怎么证明有效"时）

> "三条命令：run_agh_gate.py（AGH 三连续步骤全过）、verify_criteria.py（6 条判据机器校验全 PASS）、calc_report.py（自动出计算书，M1 矛盾 32.22 vs 15 保留为 RED FLAG、结论不下合格）。审计落在 harness_audit.json（严格 JSON 无 NaN），可交叉核到原始 165 行位移表（../maca_review/real_fea_table_165.json，sha256 锚点与 docx 原件一致）。MIDAS 在线取实时值、离线诚实降级到表格3 快照——从不拿 0 当实时值；当前是快照态，verdict=divergent 的语义是'跨口径不可比'，真正的缺陷证据是 M1 矛盾本身（32.22 vs 15，缺口 2.148，已裁决 32.22mm 为准）。"

## 3. 已知边界（不藏，评审看到就知道哪条是卡点）

- MIDAS 实时态：MIDAS 云侧材质表对竹材 6GPa 的识别情况决定红方能否取实时值。代码有诚信防线：取不到真值就降级、不伪造；报告 degraded=true 显式标记，弯矩写 null 不写 NaN。
- verdict=divergent 的语义（P1-7）：30 节点子模型 vs 208 全模型跨口径不可比，故 divergent 是"口径不可比"的必然产物，不作为结构缺陷证据；真正检出的缺陷是 M1（32.22 vs 15mm，缺口 2.148，已裁决 32.22mm 为准）。要直接复现 32.22mm 需全模型 .mgbx 源（未提供）。
- M2/M3 未定稿：材料 E、荷载系数依 PPT，标 open 待队长确认。
- MCP 入口修复（2026-10-15）：`duel_run.py` 给 `red_run`/`blue_closed_form` 加了 `strategy`/`e_gpa` 形参后，`maca_mcp.py` 两处调用点曾未跟上（`run_full_pipeline` 走 MCP 入口会 `TypeError: red_run() missing 1 required positional argument: 'strategy'`）。已修（补传 `strat`，`blue_closed_form` 补 `e_gpa` 口径，与 `duel_run.py` 主路径同口径：`udl<=0` 时兜底 1.0 kN/m、E 读 strategy.json）。**注意：此修复不在三条验收命令路径上（它们走 duel_run.py 直跑），但若交付的 maca_mcp.py 不是 2026-10-15 修复版，评审走 MCP 入口会撞同一 TypeError——以本文件交付时间戳为准核对。**

## 4. 交付文件清单

| 文件 | 位置 | 作用 |
|---|---|---|
| run_agh_gate.py | maca/ | AGH 三连续步骤实证（任务规划/能力调用/反馈处理与结果验证） |
| duel_run.py | maca/ | 红蓝对抗正式运行器（CAD→MIDAS建模→FEA→比对→规则），快照弯矩=null |
| calc_report.py | maca/ | 自动计算书生成器（真实数据 + 矛盾检出 + 诚信结论） |
| verify_criteria.py | maca/ | 判据机器校验（读 gap_ratio 数字字段 + 3b 条件化 + read from mtime） |
| strategy.json | maca/ | 人的判断蒸馏（真值口径 + M1 gap_ratio=2.1483 + M2/M3 矛盾） |
| duel_rules.json | maca/ | 6 条可执行红线（踩坑→规则沉淀） |
| logs/harness_audit.json | maca/logs/ | AGH 审计（stage 级 + 3步状态 + 判据明细，严格 JSON 无 NaN） |
| logs/duel_report_v*.json | maca/logs/ | 红蓝对抗报告（带版本·态·时刻，弯矩=null） |
| logs/calc_report_v*.md | maca/logs/ | 自动计算书（M1 RED FLAG + 不予合格） |
| real_fea_table_165.json | ../maca_review/（项目根，非 maca/） | 表格3 原始位移（独立可信锚点，sha256） |
| setup_maca.ps1 | maca/ | 凭证注入（MIDAS key 走环境变量，不写死） |
| maca_mcp.py | maca/ | AGH 注册用的 MCP 工具（5 个） |

依赖（仅两包，其余 stdlib）：ezdxf（DXF 解析）、requests（MCP/LLM 通道）。pip install ezdxf requests。Python 3.10+，不写死解释器路径。
