# MIDAS Gen NX Open API 接入手册（MACA 配套）

> 基于本机 `C:\Program Files\MIDAS\MIDAS GEN NX\` 二进制（`wg_api_framework.dll` / `GC_api.dll`，
> v26.09）字符串反推的真实端点表，**不是猜测路径**。

## 它到底怎么接

MIDAS Gen NX 的 Open API **不是独立服务**，而是**内置在 GenNX 进程里**的一个 Rust HTTP 服务框架
（`wg_api_framework.dll` 154 MB）。要连它，三样缺一不可：

| 需要什么 | 从哪拿 | 说明 |
|---|---|---|
| `MIDAS_API_URL`（监听地址） | 你启动 GenNX 后，看它控制台/日志打印的本地端口 | 例：`http://localhost:3030/gen` |
| `MIDAS_MAPI_KEY`（鉴权） | 迈达斯官方 / 学校加密锁 / 教育版发放 | 请求头 `MAPI-Key` |
| 端点路径 | 本文件（已对齐二进制） | `/DB/SECT`、`/DOC/ANAL`、`/DOC/EXPORT` |

**没有这两样（端口 + Key）之前，MIDAS 引擎必然处于"灰色待接入"状态。**
代码已写好——你拿到 Key，设两个环境变量，UI 里选 `MIDAS(NX)` 立刻变绿，**架构一行不用改**。

## 真实端点（二进制反推）

| 用途 | 方法 + 路径 | 请求体（JSON） | 对应 MACA 调用 |
|---|---|---|---|
| 改截面 | `PUT /DB/SECT` | `{"id":"SEC1","b":250,"h":500,"material":"C30"}` | 迭代前写入新截面 |
| 触发分析 | `POST /DOC/ANAL` | `{"type":"linear"}` | 跑一次 FEA |
| 取结果 | `GET /DOC/EXPORT` | — | 读最大应力 / 中点挠度 |

鉴权：每个请求带 `MAPI-Key: <你的 Key>` 头。
（完整端点表有 1800+ 条，`/DB/*` 管数据、`/DOC/*` 管文档、`/DESIGN/*` 管规范验算、`/OPE/*` 管操作，
详见 `artifact://...wg_api_framework` 端点清单或官方 `MidasGen.chm` / API Online Manual。）

## 一步到位：拿到 Key 后怎么跑

```powershell
# 1. 启动 GenNX（教育版/试用版带 MAPI 模块），记下它打印的本地端口，例如 3030

# 2. 设环境变量（PowerShell）
$env:MIDAS_API_URL = "http://localhost:3030/gen"
$env:MIDAS_MAPI_KEY = "你的MAPI-Key"
$env:MIDAS_SECT_ID = "SEC1"

# 3. 跑 MACA 闭环，选 MIDAS 引擎
cd D:\AIToolboxConsole\新建文件夹\maca
python demo.py --engine "MIDAS(NX)"
```

成功时你会看到类似：
```
[step 1] 200x300  应力比=0.889  δ=27.3mm  ok=False
         建议: 挠度27.3mm超限(20.0mm)，加高截面→340.0mm
[step 2] 200x340  应力比=0.793  δ=19.0mm  ok=True   ← 这次是真 MIDAS 算的
收敛=True
```

## 字段名对不上怎么办（已内置兜底）

`/DOC/EXPORT` 返回的字段名会随版本变。`midas_mock_adapter.py` 做了**宽松提取**：
- 应力优先找 `stress_max` / `max_stress` / `sigma_max`；
- 挠度优先找 `deflection_max` / `disp_max` / `delta` / `mid_deflection`；
- **都对不上 → 如实把原始返回打进日志，绝不编造数值**（这是答辩时能讲的工程诚实度）。

## 常见卡点

1. **连接被拒（10061）**：GenNX 没起 / 端口不对 → 确认 GenNX 控制台里那行 `listening on :PORT`。
2. **401/403**：`MIDAS_MAPI_KEY` 没生效 → 确认请求头名就是 `MAPI-Key`（二进制里写死的），值要完整。
3. **能连通但"结果字段未对齐"**：版本端点/字段变了 → 按上面兜底日志看原始 JSON，把字段名补进 `_first_present` 列表。
4. **加密狗没插**：商业版 MAPI 通常绑加密锁，没锁 = 拿不到 Key = 接不了。这正是要走**河海合作院校渠道**申请教育版的原因。

## 和 MACA 其它引擎的关系

| 引擎 | 状态 | 什么时候用 |
|---|---|---|
| `FormulaEngine` | 🟢 永远可用 | 对照基准 / 离线保底 |
| `PyNite` | 🟢 装 `PyniteFEA` 即可 | 现场真跑 FEA（开源） |
| `MIDAS(NX)` | ⚪ 需 Key+端口 | 拿到授权后，演示"可插拔"核心卖点 |

**答辩话术不变**：MIDAS 只是适配器之一；没授权用 PyNite/理论公式跑通逻辑，填 MAPI-Key 即无缝迁移。
