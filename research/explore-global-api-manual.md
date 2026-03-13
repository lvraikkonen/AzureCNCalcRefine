# Azure Global Retail Prices 探索手册

> 包含 CLI 工具 (`explore_global_api.py`) 和 FastAPI 服务 (`app/api/explore.py`) 两种使用方式。
> 基于实际探索 Azure Functions、Event Hubs、Event Grid、API Management、Power BI Embedded、Azure Databricks、Virtual Machines 整理。

---

## 概述

`explore_global_api.py` 是一个交互式命令行工具，用于探索 **Azure Global Retail Prices API**（`https://prices.azure.com/api/retail/prices`）的数据结构。提供五个子命令，覆盖从"服务总览"到"具体 Meter 定价"的完整分析链路。

**数据来源**：全部为 Global API（美元定价，OData 查询）；CN 数据仅在 `compare` 子命令中通过本地 CSV 加载。

---

## 安装与运行

```bash
# 依赖：httpx, rich（已在 pyproject.toml 声明）
uv sync

# 运行格式
uv run python scripts/explore_global_api.py <subcommand> [args]
```

---

## 五个子命令详解

### 1. `service` — 服务维度总览

**用途**：快速了解一个服务的五个维度（productName、skuName、type、term、unitOfMeasure）的值域和频次分布。**首选入口命令**，用于确认 serviceName 是否正确，以及大致了解数据规模。

**语法**：
```bash
uv run python scripts/explore_global_api.py service "<serviceName>" [--region <region>]
```

**注意**：不过滤 `isPrimaryMeterRegion`，同一 meter 在多个 region 重复出现，**total rows 会偏大**。对于大型服务，API 分页上限（10 页 × 1000 行）会截断结果，`Virtual Machines` 等服务会显示 "Total rows: 10000" 但实际数据远超此数。

**示例**：
```bash
uv run python scripts/explore_global_api.py service "Functions"
uv run python scripts/explore_global_api.py service "API Management" --region eastus
```

**实测发现 — `serviceName` 不一定等于 UI 显示名**：

| UI 显示名 | 正确 serviceName |
|-----------|----------------|
| Azure Functions | `"Functions"` ← 去掉 "Azure" 前缀 |
| Event Hubs | `"Event Hubs"` |
| Event Grid | `"Event Grid"` |
| Azure Databricks | `"Azure Databricks"` |
| Virtual Machines | `"Virtual Machines"` |

遇到 0 行时，尝试去掉 "Azure " 前缀，或不加 `--region` 先全局查询。

---

### 2. `cascade` — 级联维度模拟（最接近 UI 的命令）

**用途**：模拟计算器 UI 的级联筛选行为，过滤掉噪音数据后，展示各维度的实际可选值。

**语法**：
```bash
uv run python scripts/explore_global_api.py cascade "<serviceName>" \
    [--region <region>] [--product <productName>] [--sku <skuName>]
```

**内置过滤逻辑**：
```python
items = [i for i in items
         if i.get("isPrimaryMeterRegion", True)   # 过滤非主 meter region 的重复行
         and i.get("type") != "DevTestConsumption"] # 过滤 Dev/Test 折扣类型
```

**输出维度顺序**：`region → productName → skuName → type → term`

**示例**：
```bash
uv run python scripts/explore_global_api.py cascade "Functions" --region eastus
uv run python scripts/explore_global_api.py cascade "Virtual Machines" --region eastus --product "Virtual Machines Dv3 Series"
```

#### `isPrimaryMeterRegion` 与 `--region Global` 的关系

这是 cascade 中最容易踩的坑：

| 查询 | 现象 | 原因 |
|------|------|------|
| `cascade "Functions" --region eastus` | 看不到消耗计划（Standard SKU）| 消耗计划主 region 是 `Global`，eastus 下 isPrimary=False |
| `cascade "Event Hubs" --region eastus` | 看不到 Basic SKU | Basic 的主 region 是 `Global` |
| `cascade "Functions" --region Global` | 只看到 Functions + Standard SKU | 这才是消耗计划的主记录 |

**规律**：全球统一定价的 SKU 的主 region 是 `"Global"`（字面量）。在具体地理区域下查询时这些 SKU 会被 cascade 过滤掉。

#### `term` 字段处理

脚本使用 `get_effective_term()` 统一处理 `term` 和 `reservationTerm`：Reservation 行的期限从 `reservationTerm` 字段读取，其他类型从 `term` 字段读取。`cascade`、`service`、`meters`、`compare` 命令均已适配。

VM Reservation 存在三种期限：`"1 Year"`、`"3 Years"`、`"5 Years"`（稀少）。

---

### 3. `subdimensions` — 维度字符串模式分析

**用途**：分析 `productName` 或 `skuName` 的字符串结构，挖掘命名规律，辅助设计分组逻辑或枚举。

**语法**：
```bash
uv run python scripts/explore_global_api.py subdimensions "<serviceName>" \
    [--field productName|skuName] [--region <region>]
```

**输出**：
- 所有不重复字段值（含词数统计）
- 对 `skuName`：拆分首词与后缀集合
- 对 `productName`：前 40 字符的频次分布

**典型用途**：在写 parser（如 `vm_parser.py`）前，用此命令摸清所有命名变体。

---

### 4. `meters` — Meter 与分层定价详情（最核心的命令）

**用途**：查看特定配置下所有 meter 的计费结构，包括分层定价（tier）、计量单位、价格。**理解计费逻辑的必用命令。**

**语法**：
```bash
uv run python scripts/explore_global_api.py meters "<serviceName>" \
    [--region <region>] [--product <productName>] [--sku <skuName>]
```

**输出**：按 `(meterName, type, term)` 分组的表格，列出层级数和各层 `tierMinimumUnits → unitPrice`。

**读懂分层格式**：
```
0.0→0.0 | 100.0→0.035
          ↑
用量达 100 单位后，单价变为 0.035
前 100 单位 price=0.0，即免费层
```

**重要**：对于大型服务（VM），务必配合 `--product` 或 `--sku` 缩小范围，否则返回数据可能不完整。

---

### 5. `compare` — Global vs CN 数据对比

**用途**：将 Global API 数据与本地 CN CSV 文件对比，逐维度检查字段对齐情况。

**前提**：需要 `sample-data/AzureRetailPrices.csv` 存在。

**语法**：
```bash
uv run python scripts/explore_global_api.py compare "<serviceName>" [--product <productName>]
```

---

## 各服务定价结构速查

### Virtual Machines — 最复杂

#### serviceName 的边界问题

`serviceName="Virtual Machines"` 是一个**宽泛分类**，不只包含 VM 计算本体，还混入了：

- `Azure Monitor`、`Standard SSD Managed Disks`、`Azure OpenAI`、`Azure Speech` 等相关计量
- 数据规模庞大（eastus 下超过 10000 行），`service` 命令会**触达 10 页分页上限而截断**

实际工作时应始终配合 `--product` 缩小范围：
```bash
uv run python scripts/explore_global_api.py meters "Virtual Machines" \
    --region eastus --product "Virtual Machines Dv3 Series"
```

#### productName 的复杂命名（vm_parser.py 负责解析）

`app/services/sub_dimensions/vm_parser.py` 将 productName 拆解为五个子维度：

| 子维度 | 含义 | 示例值 |
|--------|------|--------|
| `os` | 操作系统 | `"Linux"` / `"Windows"` |
| `deployment` | 部署类型 | `"Virtual Machines"` / `"Dedicated Host"` / `"Cloud Services"` |
| `series` | 实例系列 | `"Dv3"`, `"Eadsv5"`, `"NCads A100 v4"` |
| `category` | 实例类别 | `"General Purpose"`, `"Memory Optimized"` 等 |
| `tier` | Basic 限定符 | `"Basic"` / `None` |
| `memory_profile` | 内存配置 | `"Medium Memory"` / `None` |

**已知 productName 变体模式**（parser 均覆盖）：

| 模式 | 示例 |
|------|------|
| 标准格式 | `Virtual Machines Dv3 Series` |
| 带 OS 后缀 | `Virtual Machines Edsv5 Series Windows` |
| 缺少 "Virtual Machines" 前缀 | `DCsv3 Series Linux` |
| 小写 "series" | `Virtual Machines ECasv6 series Windows` |
| Dedicated Host 部署 | `ESv4 Series Dedicated Host` |
| Cloud Services 部署 | `Eadsv5 Series CloudServices` |
| Medium Memory 限定 | `Virtual Machines Mdsv3 Medium Memory Series Linux` |
| Basic 限定 | `Virtual Machines A Series Basic` |
| 特殊产品 | `Virtual Machines RI`, `Dedicated Host Reservation` |

#### skuName = 实例规格 + 可选模式后缀

skuName 在 API 中代表具体实例型号，但注意 **meterName 才是计费模式的最终区分**：

| meterName 格式 | 对应模式 | type 字段 |
|---------------|---------|----------|
| `D2 v3/D2s v3` | 按需（Pay-as-you-go）| `Consumption` |
| `D2 v3/D2s v3 Low Priority` | 低优先级 | `Consumption` |
| `D2 v3/D2s v3 Spot` | Spot | `Consumption` |
| `D2 v3/D2s v3`（type=Reservation）| 预留实例 | `Reservation` |
| `D2 v3/D2s v3`（type=DevTest）| Dev/Test 折扣 | `DevTestConsumption` |

Reservation 行中 skuName 不带后缀（如 `"D2 v3"`），且期限存储在 `reservationTerm` 字段（非 `term`）：

| reservationTerm | 示例价格（D2 v3 eastus）|
|-----------------|----------------------|
| `"1 Year"` | $501 /月（预付全年）|
| `"3 Years"` | $968 /月（预付三年）|
| `"5 Years"` | 极少数机型支持 |

注意：Reservation 的价格是**总包价格（月付）**，不是小时单价，单位虽然是 `1 Hour` 但 unitPrice 为全期总额。

#### meters 命令的 Reservation 显示

`meters` 命令按 `(meterName, type, effectiveTerm)` 分组，Reservation 的不同期限（1 Year / 3 Years / 5 Years）分别显示为独立行，价格标注 `(total)` 表示为全期总额。使用 `--raw N` 可查看原始 JSON 字段。

---

### Functions — 全球定价与区域定价混合

| productName | skuName | 主 region | 计费模式 |
|-------------|---------|-----------|---------|
| `Functions` | `Standard` | `Global` | 按执行时间 + 执行次数，有大额免费层 |
| `Flex Consumption` | `On Demand` | eastus 等 | 按执行时间 + 执行次数，有免费层 |
| `Flex Consumption` | `Always Ready` | eastus 等 | 三 meter 叠加，无免费层 |
| `Premium Functions` | `Premium` | eastus 等 | 按 vCPU-hour + GiB-hour，无免费层 |

**Functions（消耗计划）的分层定价**：

| Meter | 免费层 | 付费单价 | 单位 |
|-------|--------|----------|------|
| Standard Execution Time | 前 400,000 GB-秒/月免费 | $0.000016 | /GB-second |
| Standard Total Executions | 前 1,000,000 次/月免费 | $0.0000020 | /10次 |

查询时必须用 `--region Global` 才能看到此产品：
```bash
uv run python scripts/explore_global_api.py meters "Functions" --region Global --product "Functions"
```

---

### Event Grid — 纯分层定价

所有 meter 均为两层：tier=0 免费，tier≥1 付费。

| Meter | 单位 | 免费层 | 付费单价 |
|-------|------|--------|---------|
| Standard Operations | 100K | 前 100K 免费 | $0.06/100K |
| Standard Event Operations | 1M | 前 1M 免费 | $0.60/1M |
| Standard MQTT Operations | 1M | 前 1M 免费 | $1.00/1M |
| Standard Throughput Unit | 1 Hour | 无 | $0.04/小时 |

productName 和 skuName 均唯一（无选择），选定服务后直接进入 meter 用量填写。

---

### Event Hubs — Basic SKU 在 Global region

Basic SKU 的 `isPrimaryMeterRegion=True` 仅在 `"Global"` 和少数小型 region，eastus 下 isPrimary=False，`cascade --region eastus` 中不可见。

| skuName | 主 region | 代表 Meter |
|---------|-----------|-----------|
| Basic | `Global` | Basic Throughput Unit / Basic Ingress Events |
| Standard | eastus 等 | Standard Throughput Unit / Ingress Events / Kafka Endpoint / Capture |
| Premium | eastus 等 | Premium Processing Unit / Extended Retention |
| Dedicated | eastus 等 | Dedicated Capacity Unit |

---

### API Management — 三种计费模式并存

一个 serviceName 下存在三种计量单位，代表三种截然不同的计费逻辑：

| 单位 | 计费模式 | 代表 SKU | 说明 |
|------|---------|---------|------|
| `1 Hour` | 容量单元（预留容量持续计费）| Developer, Basic, Standard, Premium, Isolated | 类似 VM 按时长 |
| `10K` | API 调用量（有免费层）| Consumption, Basic v2, Standard v2 | 按使用量 |
| `1/Hour` | Workspace Pack 附加包 | Standard, Premium, Isolated（可选）| 独立可选 meter |

**Consumption SKU** 是唯一纯用量模式（无容量单元 meter）；**v2 SKU** 同时计容量单元和调用量。

| v2 SKU Calls Meter | 免费层 | 付费单价 |
|--------------------|--------|---------|
| Consumption Calls | 前 1,000,000 次（100×10K）| $0.035/10K |
| Basic v2 Calls | 前 10,000,000 次（1000×10K）| $0.030/10K |
| Standard v2 Calls | 前 50,000,000 次（5000×10K）| $0.025/10K |

---

### Power BI Embedded — 最简结构（参考基准）

完全规则，可作为其他复杂服务的对比基准：

- 1 个 productName，6 个 skuName（A1–A6）
- meterName = `{skuName} Node`，1:1 映射
- 无分层，无免费层，纯按小时，价格按 ×2 倍递增
- A1=$1.008/h → A6=$32.25/h

---

### Azure Databricks — DBU 软件费，非 VM

**核心误区**：Databricks 定价不是 VM 定价。`serviceName="Azure Databricks"` 只收 **DBU（Databricks Unit）软件层费用**，底层 VM 硬件费由 Azure Compute 单独计费，在此服务数据中不可见。

**两种 productName 的区别**：

| productName | 定价方式 | 主 region |
|-------------|---------|-----------|
| `"Azure Databricks"` | 经典集群，多数 SKU 全球统一定价 | `Global` 或少数特定 region |
| `"Azure Databricks Regional"` | 新型 Serverless 计算，区域差价 | eastus 等具体 region |

**skuName 命名规律**：`{Tier} {工作负载} [可选:引擎/特性]`

- Tier：`Standard` / `Premium` / `POC`
- 工作负载：`All-purpose Compute`, `Jobs Compute`, `Jobs Light Compute`, `SQL Analytics`, `Serverless SQL` 等
- 引擎后缀：`Photon`（向量化）
- 特性后缀：`Delta Live Tables`

每个 skuName 对应**唯一 1 个 meter**，meterName = `{skuName} DBU`，无分层定价（全部 tier=0，单一平价）。

`subdimensions "Azure Databricks" --field skuName` 是摸清全部 40+ SKU 命名结构的推荐起点。

---

## 关键概念速查

### `isPrimaryMeterRegion` 字段

| 值 | 含义 | `cascade` 中 |
|----|------|-------------|
| `True` | 该 meter 在此 region 有独立主记录 | **保留** |
| `False` | 该 meter 在别处定价，此处为引用副本 | **过滤掉** |

需要用 `--region Global` 才能看到的 SKU：

| 服务 | SKU / 特征 | 原因 |
|------|-----------|------|
| Functions | Standard（消耗计划）| 全球统一定价 |
| Event Hubs | Basic | 全球统一定价 |
| Azure Databricks | 大多数经典集群 SKU | 全球统一定价 |

### `type` 字段的三个值

| type | 说明 | `cascade` 处理 |
|------|------|--------------|
| `Consumption` | 正常按需/低优先级/Spot | **保留** |
| `DevTestConsumption` | Dev/Test 折扣价 | **过滤掉** |
| `Reservation` | 预留实例包年 | **保留** |

### `term` vs `reservationTerm`

API 中存在两个"期限"字段：

| 字段 | 存在于 | 示例值 |
|------|--------|-------|
| `term` | SavingsPlan 类 type 的行 | `"1 Year"`, `"3 Years"` |
| `reservationTerm` | `type=Reservation` 的行 | `"1 Year"`, `"3 Years"`, `"5 Years"` |

脚本通过 `get_effective_term()` 统一处理，根据行类型自动选择正确的字段。

### `unitOfMeasure` 常见值

| 值 | 计费逻辑 | 出现服务 |
|----|---------|---------|
| `1 Hour` | 按实例/节点运行小时 | VM, Power BI Embedded, Event Hubs, Databricks |
| `1/Hour` | 附加包按小时 | API Management Workspace Pack |
| `1 GB Second` | 内存×时间 | Functions |
| `1 GiB Hour` | GiB×小时 | Premium Functions Memory |
| `10K` | 每万次 API 调用 | API Management v2 / Consumption |
| `1M` | 每百万次操作 | Event Grid, Event Hubs |
| `100K` | 每十万次操作 | Event Grid Standard Operations |
| `1` | 单次或单 DBU | Databricks（Launch Charge）|
| `1/Day` | 按天 | Databricks Clean Rooms |

---

## 典型探索工作流

```
Step 1: service（无 region）
  → 确认 serviceName 拼写
  → 了解 productName / skuName 的大致分布

Step 2: cascade --region <target>
  → 模拟 UI 级联，确认可选项
  → 若某 SKU 不见了 → 改用 --region Global 重试

Step 3: subdimensions（按需）
  → 分析 skuName 命名规律（为 parser 做准备）
  → 对大型服务（VM、Databricks）特别有用

Step 4: meters --region <r> --product <p> [--sku <s>]
  → 获取分层定价结构
  → 确认每个 skuName 对应几个 meter
  → 确认是否有免费层（tier=0 且 price=0）

Step 5: compare（按需）
  → 确认 CN CSV 字段与 Global API 的对齐情况
```

---

## 常见问题

**Q: `service` 返回 0 行？**
去掉 "Azure " 前缀尝试（如 `"Azure Functions"` → `"Functions"`），或去掉 `--region`。

**Q: `cascade` 中某 SKU 消失了？**
该 SKU 的主 region 不是当前 `--region`。用 `--region Global` 重试；若仍不见，查 `service`（不过滤 isPrimary）确认 SKU 存在。

**Q: VM 查询只返回 10000 行，数据被截断？**
脚本内置最多 10 页（约 10000 行）的分页上限。`Virtual Machines` 服务数据量极大，必须配合 `--product` 缩小范围。

**Q: `meters` 中 Reservation 显示两个 `0.0→` tier，不知哪个是 1 年哪个是 3 年？**
已修复。分组 key 现包含 `reservationTerm`，不同期限独立显示。也可用 `--raw N` 查看原始 JSON。

**Q: Databricks 价格很低（$0.15/DBU-h），实际账单高很多？**
DBU 是软件层费用，底层 VM（CPU + 内存）由 Azure Compute 单独计费，不反映在 `serviceName="Azure Databricks"` 的数据里。

**Q: `term` 在 `cascade` 里始终显示 "0 options"，即使 type 有 Reservation？**
已修复。脚本现使用 `get_effective_term()` 统一读取 `term` 和 `reservationTerm` 字段。

---

## FastAPI Explore API

CLI 工具之外，项目还提供了一套 FastAPI 端点，将相同的探索能力以 REST API 形式暴露，供前端 UI 调用或直接通过 Swagger 交互。

### 启动

```bash
uv run uvicorn app.main:app --reload
# Swagger UI: http://127.0.0.1:8000/docs
```

### 端点一览

| 端点 | 方法 | 对应 CLI | 功能 |
|------|------|---------|------|
| `/api/v1/explore/service/{service_name}` | GET | `service` | 维度分布总览 |
| `/api/v1/explore/cascade` | POST | `cascade` | 级联筛选 + VM 子维度 |
| `/api/v1/explore/meters` | POST | `meters` | Meter 分层定价结构 |
| `/api/v1/explore/productparse` | POST | `productparse` | VM productName 子维度解析 |
| `/api/v1/explore/calculator` | POST | — | 价格计算（CLI 无对应命令） |

### 与 CLI 的差异

| 特性 | CLI | API |
|------|-----|-----|
| 数据渲染 | rich 表格 | JSON |
| 级联行为 | 单次查询展示 | 真正的双向级联（每次选择变更重新请求） |
| 子维度 | `productparse` 独立命令 | 集成在 `cascade` 响应中 |
| 价格计算 | 无 | `calculator` 端点 |
| 异步 | 同步 httpx | 异步 httpx.AsyncClient |

---

## Virtual Machines Walkthrough：从 API 到 UI 的完整模拟

以下以 **Virtual Machines D2 v3 (eastus)** 为例，模拟用户在 Azure Pricing Calculator UI 上的完整操作流程。每一步对应一个 API 调用。

### Step 1: 用户点击 "Add to estimate" — 查看服务总览

用户在产品目录中选择 "Virtual Machines"，系统先获取该服务的整体数据概况。

```bash
# CLI
uv run python scripts/explore_global_api.py service "Virtual Machines" --region eastus

# API
curl -s "http://127.0.0.1:8000/api/v1/explore/service/Virtual%20Machines?region=eastus"
```

**返回关键信息**：437 个 productName、1029 个 skuName、3 种 type（Consumption / DevTestConsumption / Reservation）、3 种 term（1 Year / 3 Years / 5 Years）。

> 注意 `total_rows: 10000` — 触达分页上限，后续操作必须配合更精确的筛选。

---

### Step 2: UI 展示初始下拉框 — 级联筛选（无选择）

用户看到 Region、OS、Type、Tier、Category、Instance Series、Instance 等下拉框。系统调用 cascade 获取各维度可选值。

```bash
# API — 仅选择 region
curl -s -X POST "http://127.0.0.1:8000/api/v1/explore/cascade" \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "Virtual Machines",
    "selections": {"armRegionName": "eastus"},
    "sub_selections": {}
  }'
```

**响应结构**（核心字段）：

```json
{
  "dimensions": [
    {"field": "armRegionName", "options": ["eastus", ...], "selected": "eastus"},
    {"field": "productName",  "options": ["Virtual Machines Dv3 Series", ...],
     "sub_dimensions": [
       {"field": "os",              "label": "Operating System", "options": ["Linux", "Windows"]},
       {"field": "deployment",      "label": "Deployment",       "options": ["Cloud Services", "Dedicated Host", "Virtual Machines"]},
       {"field": "tier",            "label": "Tier",             "options": ["Basic", "Standard"]},
       {"field": "category",        "label": "Category",         "options": ["Compute Optimized", "GPU", "General Purpose", ...]},
       {"field": "instance_series", "label": "Instance Series",  "options": ["A", "Av2", "Dv3", ...]}
     ]},
    {"field": "skuName", "options": [...]},
    {"field": "type",    "options": ["Consumption", "Reservation"]},
    {"field": "term",    "options": ["1 Year", "3 Years", "5 Years"], "visible": false}
  ]
}
```

**UI 维度映射**：

| UI 下拉框 | 数据来源 |
|-----------|---------|
| Region | `dimensions[0].options` |
| Operating System | `sub_dimensions[0].options` (os) |
| Type | `dimensions[3].options` (type) |
| Tier | `sub_dimensions[2].options` (tier) |
| Category | `sub_dimensions[3].options` (category) |
| Instance Series | `sub_dimensions[4].options` (instance_series) |
| Instance | `dimensions[2].options` (skuName) |

---

### Step 3: 用户逐步选择 — 级联缩窄

用户选择 OS=Linux、Tier=Standard、Category=General Purpose。前端每次选择变更都重新调用 cascade。

```bash
# API — 带子维度选择
curl -s -X POST "http://127.0.0.1:8000/api/v1/explore/cascade" \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "Virtual Machines",
    "selections": {"armRegionName": "eastus"},
    "sub_selections": {
      "os": "Linux",
      "tier": "Standard",
      "category": "General Purpose",
      "deployment": "Virtual Machines"
    }
  }'
```

**级联效果**：
- `instance_series` 缩窄到仅 Linux + Standard + General Purpose + Virtual Machines 的系列（Av2, D, Dv3, Dv4 等）
- `productName` 同步缩窄到匹配的产品
- `skuName`、`type`、`term` 也相应更新

---

### Step 4: 用户选择具体 Product — 获取 SKU 列表

用户继续选择 Instance Series = Dv3，系统选中对应的 productName。

```bash
# API — 选定 productName
curl -s -X POST "http://127.0.0.1:8000/api/v1/explore/cascade" \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "Virtual Machines",
    "selections": {
      "armRegionName": "eastus",
      "productName": "Virtual Machines Dv3 Series"
    },
    "sub_selections": {}
  }'
```

**响应**：

```json
{
  "total_rows": 35,
  "dimensions": [
    {"field": "skuName", "options": [
      "D16 v3", "D16 v3 Low Priority", "D16 v3 Spot",
      "D2 v3",  "D2 v3 Low Priority",  "D2 v3 Spot",
      "D32 v3", "D4 v3", "D48 v3", "D64 v3", "D8 v3", ...
    ]},
    {"field": "type", "options": ["Consumption", "Reservation"]},
    {"field": "term", "options": ["1 Year", "3 Years"], "visible": false}
  ]
}
```

现在 skuName 列表清晰：7 种规格 × 3 种模式（标准/Low Priority/Spot）。

---

### Step 5: 用户选择 SKU — 查看 Meter 定价

用户选择 D2 v3，查看该配置下所有 meter 的定价结构。

```bash
# CLI
uv run python scripts/explore_global_api.py meters "Virtual Machines" \
    --region eastus --product "Virtual Machines Dv3 Series" --sku "D2 v3"

# API
curl -s -X POST "http://127.0.0.1:8000/api/v1/explore/meters" \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "Virtual Machines",
    "region": "eastus",
    "product": "Virtual Machines Dv3 Series",
    "sku": "D2 v3"
  }'
```

**响应**：

```json
{
  "groups": [
    {
      "meter": "D2 v3/D2s v3", "type": "Consumption", "term": "-",
      "unit": "1 Hour", "is_reservation": false,
      "tiers": [{"tier_min_units": 0.0, "unit_price": 0.096}]
    },
    {
      "meter": "D2 v3/D2s v3", "type": "Reservation", "term": "1 Year",
      "unit": "1 Hour", "is_reservation": true,
      "tiers": [{"tier_min_units": 0.0, "unit_price": 501.0}]
    },
    {
      "meter": "D2 v3/D2s v3", "type": "Reservation", "term": "3 Years",
      "unit": "1 Hour", "is_reservation": true,
      "tiers": [{"tier_min_units": 0.0, "unit_price": 968.0}]
    }
  ]
}
```

| Type | Term | Unit Price | 含义 |
|------|------|-----------|------|
| Consumption | - | $0.096/hr | 按需付费 |
| Reservation | 1 Year | $501 | 1 年预留总价 |
| Reservation | 3 Years | $968 | 3 年预留总价 |

---

### Step 6: 用户填写用量、计算价格

用户配置完成，选择 Consumption 模式，2 台实例，730 小时/月（全月）。

```bash
# API
curl -s -X POST "http://127.0.0.1:8000/api/v1/explore/calculator" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [{
      "service_name": "Virtual Machines",
      "region": "eastus",
      "product": "Virtual Machines Dv3 Series",
      "sku": "D2 v3",
      "type": "Consumption",
      "quantity": 2,
      "hours_per_month": 730
    }]
  }'
```

**响应**：

```json
{
  "items": [{
    "meters": [{
      "meter": "D2 v3/D2s v3",
      "unit": "1 Hour",
      "tiers": [{"tier_min_units": 0.0, "unit_price": 0.096}],
      "usage": 1460.0,
      "monthly_cost": 140.16
    }],
    "monthly_cost": 140.16,
    "currency": "USD"
  }],
  "total_monthly_cost": 140.16
}
```

**计算过程**：`$0.096/hr × 730hr × 2台 = $140.16/月`

#### 多配置组合计算

calculator 支持同时提交多个配置项，模拟 UI 上的 "Estimate" 列表：

```bash
curl -s -X POST "http://127.0.0.1:8000/api/v1/explore/calculator" \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {
        "service_name": "Virtual Machines",
        "region": "eastus",
        "product": "Virtual Machines Dv3 Series",
        "sku": "D2 v3",
        "type": "Consumption",
        "quantity": 2,
        "hours_per_month": 730
      },
      {
        "service_name": "Virtual Machines",
        "region": "eastus",
        "product": "Virtual Machines Dv3 Series",
        "sku": "D2 v3",
        "type": "Reservation",
        "term": "1 Year",
        "quantity": 1
      }
    ]
  }'
```

**响应**：`total_monthly_cost = 140.16 + 501.0 = $641.16`

---

### Step 6b (可选): 用 productparse 审查子维度解析

开发阶段可用 productparse 验证 vm_parser 的解析覆盖度：

```bash
# CLI
uv run python scripts/explore_global_api.py productparse "Virtual Machines" \
    --region eastus --product "Virtual Machines Dv3 Series"

# API
curl -s -X POST "http://127.0.0.1:8000/api/v1/explore/productparse" \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "Virtual Machines",
    "region": "eastus",
    "product": "Virtual Machines Dv3 Series"
  }'
```

**响应**：

```json
{
  "unique_products": 1,
  "products": [{
    "product_name": "Virtual Machines Dv3 Series",
    "os": "Linux",
    "deployment": "Virtual Machines",
    "series": "Dv3",
    "category": "General Purpose",
    "tier": null,
    "memory_profile": null,
    "special": null
  }],
  "summary": {"os": {"Linux": 1}, "deployment": {"Virtual Machines": 1}, "category": {"General Purpose": 1}},
  "unparsed": []
}
```

---

### Walkthrough 总结：UI 操作与 API 调用对应关系

```
┌─────────────────────────────┐
│  用户点击 "Add to estimate" │
│  → GET /explore/service     │  ← 确认数据规模
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  Region = eastus            │
│  → POST /explore/cascade    │  ← 获取初始下拉框选项 + 子维度
│    selections: {region}     │
│    sub_selections: {}       │
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  OS = Linux                 │
│  Tier = Standard            │
│  Category = General Purpose │
│  → POST /explore/cascade    │  ← 子维度缩窄 productName 范围
│    sub_selections: {os,     │
│      tier, category}        │
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  Instance Series = Dv3      │
│  → POST /explore/cascade    │  ← productName 确定，skuName 列表出现
│    selections: {region,     │
│      productName}           │
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  Instance = D2 v3           │
│  → POST /explore/meters     │  ← 查看定价结构
│    {region, product, sku}   │
└──────────┬──────────────────┘
           ▼
┌─────────────────────────────┐
│  Type = Consumption         │
│  Quantity = 2, Hours = 730  │
│  → POST /explore/calculator │  ← 计算月度费用 = $140.16
└─────────────────────────────┘
```

### 计算逻辑说明

| 定价类型 | 计算公式 | 示例 |
|---------|---------|------|
| **Consumption** (`1 Hour`) | `unitPrice × hours_per_month × quantity` | $0.096 × 730 × 2 = $140.16 |
| **Reservation** | `unitPrice × quantity`（unitPrice 为承诺期总价） | $501 × 1 = $501 |
| **阶梯定价** | 按 `tierMinimumUnits` 分段累进计算 | Storage 等服务 |

Reservation 的 unitPrice 是**承诺期内总额**（非月度），API 原始数据如此定义。
