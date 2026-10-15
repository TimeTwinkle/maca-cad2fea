# MACA · 多模式 AI 计算自动化引擎

**一句话**：用大模型作中枢，用**标准化接口**对接一切结构计算引擎（MIDAS / PyNite / 理论公式），把"读计算书 → 审查 → 自动调引擎验证 → 迭代截面"从人工数小时压到分钟级。

这是 2026 江苏省 AI+科学与工程创新实践黑客松（工程仿真与优化赛道）的参赛落地实现。

## 核心范式（三层解耦）

```
┌──────────────────────────────────────────────┐
│  输入层  计算书(自然语言/任意格式) → AI 泛化解析 → DesignParams(JSON) │
├──────────────────────────────────────────────┤
│  调度层  统一求解接口 solve(params) ← 可插拔适配器(注册表)          │
│          ├ 模式A  MIDAS Gen NX  (REST Open API, 商业)            │
│          ├ 模式B  PyNite        (开源 FEA)                        │
│          └ 模式C  FormulaEngine (纯 math, 对照基准, 永远可用)     │
├──────────────────────────────────────────────┤
│  迭代层  AI 评估(SolverResult) → Suggestion → 新 DesignParams → 再求解 │
└──────────────────────────────────────────────┘
```

**卖点**：AI 不绑定任何软件。MIDAS 只是适配器之一；没 MIDAS 授权也能用 PyNite/理论公式跑通完整闭环，**填入 MAPI-Key 即无缝迁移到商业软件**——这正是答辩话术里的"解耦与泛化"。

## 目录结构

```
maca/
├── core/
│   ├── models.py        DesignParams / SolverResult / Suggestion
│   ├── solver.py        SolverBase + 注册表（调度层灵魂）
│   └── agent.py         Agent 编排（迭代闭环）
├── adapters/
│   ├── formula_adapter.py     模式C：纯 math 理论解（零依赖）
│   ├── pynite_adapter.py      模式B：开源 FEA（PyniteFEA）
│   └── midas_mock_adapter.py  模式A：MIDAS Gen NX REST Open API
├── ai/
│   └── decider.py         AI 决策层：解析 + 出建议（Agnes 通道 + 规则 fallback）
├── ui/
│   └── app.py             Streamlit 三栏 Demo（左计算书/中日志/右折线+引擎对比）
├── mcp_bridge.py          把求解层暴露成 MCP 工具（AGH/Claude 可接入）
├── demo.py                CLI 闭环演示（无 UI 环境）
├── examples/design_book_sample.txt   示例计算书
└── tests/test_maca.py     单元测试（无网无 PyNite 也全过）
```

## 快速上手

```bash
cd maca

# 1. 依赖
pip install streamlit plotly requests
pip install PyniteFEA        # 可选：不装则 PyNite 自动回退理论解，闭环仍跑通

# 2. 跑测试（验证闭环）
python tests/test_maca.py

# 3. CLI 闭环（无需浏览器）
python demo.py --engine FormulaEngine
python demo.py --engine PyNite

# 4. Streamlit Demo
python -m streamlit run ui/app.py     # 浏览器 http://localhost:8501
```

## 三种引擎 & 接入

| 引擎 | 模式 | 状态 | 接入条件 |
|---|---|---|---|
| `FormulaEngine` | 理论公式 | 🟢 永远可用 | 无（纯 math，作为对照基准） |
| `PyNite` | 开源 FEA | 🟢 装 `PyniteFEA` | `pip install PyniteFEA`（未装自动回退） |
| `MIDAS(NX)` | 商业软件 | ⚪ 未接入 | 设 `MIDAS_API_URL` + `MIDAS_MAPI_KEY` |

## 接入 MIDAS Gen NX（3 步）

MIDAS 官方明确：Gen NX / Civil NX 走**开放式 REST API（HTTP/HTTPS + JSON）**，无需 COM/Excel VBA。

1. **启动本地 Open API 服务**：GenNX 内建 MAPI 模块 / 教育版 / 专用 MAPI server（河海是官方合作院校，向土木/力学院实验室或"未来工程师项目"申请 MAPI-Key）。
2. **设两个环境变量**（绝不写死进代码）：
   ```
   set MIDAS_API_URL=http://localhost:<port>/gen
   set MIDAS_MAPI_KEY=<你的 MAPI 鉴权>
   ```
3. **导入 adapters** → `MIDAS(NX)` 自动切为 🟢 可用，UI 直接选它。

> 端点/字段名以官方 API Manual（`MidasGen.chm` 或 MIDAS API Online Manual）为准；
> 适配器里用的是 `/db/SECT`、`/doc/ANAL`、`/doc/RESULT` 标准骨架，接入时按实际端点核对。

## 启用 Agnes 大模型决策（可选）

默认走**规则 fallback**（离线、可复现，黑客松保底）。想用真实大模型泛化解析：

```
set MACA_LLM=agnes
set AGNES_API_KEY=<你的 key>
set AGNES_BASE_URL=https://apihub.agnes-ai.com/v1
set AGNES_MODEL=agnes-2.5-flash
```

没配时自动退回规则通道，**界面会标注当前决策器**，答辩时两态都能讲。

## 答辩话术（内置在 UI 底部）

- **为什么不用 MIDAS 做 Demo？**
  > 我们在探索不依赖单一商业授权的通用范式。MIDAS 只是适配器之一，今天用开源 PyNite/理论公式跑通逻辑，填 MAPI-Key 即可无缝迁移到商业软件。
- **核心创新点？**
  > 解耦与泛化。大模型作中枢，标准化接口对接一切计算引擎，把"算得准"从单一软件抽离成 AI 可调度的服务。

## 已知边界（诚实声明，答辩加分项）

- 理论解是**简支梁**示例，PyNite 适配器同口径；扩展到多跨/框架需改 `DesignParams` 与适配器。
- MIDAS REST 字段名随版本可能变，已做宽松提取 + 失败时**如实报告原始返回、不编造数值**。
- 挠度限值默认 20mm，`DesignParams.max_serviceability_span_mm` 可改。
