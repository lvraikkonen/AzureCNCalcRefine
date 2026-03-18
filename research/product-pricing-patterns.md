# Azure Global Pricing Calculator：UI 配置维度与后端 API 数据关系

**目标产品：** HDInsight、Service Bus、Virtual Machines、Azure Machine Learning
**数据源：** Azure Retail Prices API (Global)
**撰写日期：** 2026-03-17

---

## 一、四个产品的 API 数据特征对比

| 特征 | HDInsight | Service Bus | Virtual Machines | Azure Machine Learning |
|------|-----------|-------------|-----------------|----------------------|
| **serviceFamily** | Analytics | Integration | Compute | AI + Machine Learning |
| **productName 数量** | 19 (按 VM 系列，eastus) | 1 ("Service Bus") | 数百个 (OS×系列×部署) | 8 (surcharge×6 + hosting + mgmt) |
| **skuName 数量 (eastus)** | ~185 (VM 实例规格) | 5 (Tier) | 数千 | ~23 (实例规格或功能标识) |
| **skuName 含义** | VM 实例规格 (≈meterName) | Tier (Basic/Standard/Premium/Hybrid/WCF) | VM 实例规格 + 后缀 | GPU 实例规格 (Managed Model Hosting) 或功能标识 |
| **type 取值** | Consumption, DevTest | Consumption only | Consumption, DevTest, Reservation | Consumption only |
| **reservationTerm** | 无 | 无 | 1 Year, 3 Years, (5 Years) | 无 |
| **SavingsPlan** | 无 | 无 | 无 (Global API 不返回，CN CSV 有) | 无 |
| **tierMinimumUnits** | 0 (无阶梯) | 有 (多层阶梯+免费层) | 0 (无阶梯) | 0 (无阶梯) |
| **unitOfMeasure** | "1 Hour" only | "1M", "1/Month", "1/Hour", "1 GB", "10K", "1" | "1 Hour" only | "1 Hour", "1K" (tokens) |
| **armSkuName** | 有 (Standard_前缀) | 空 | 有 | Managed Model Hosting 有 |
| **定价模式** | 实例×小时 (类VM) | 多meter独立计量 | 实例×小时 (最复杂) | 实例×小时 (类VM) |
| **Savings Options** | 无 | 无 | PAYG/RI 1Y/3Y/(5Y)/SavingsPlan | 无 |

---

## 二、各产品 UI 维度与 API 字段映射详细分析

### 2.1 Virtual Machines（已实现，作为参照）

**Pricing Detail Page 维度：**

| # | UI 维度 | API 字段 | 说明 |
|---|---------|---------|------|
| 1 | Region | `armRegionName` | 直接映射 |
| 2 | Operating System | `productName` 后缀 | Linux/Windows/RHEL/SUSE 编码在 productName 中 |
| 3 | Type (OS Only/SQL/BizTalk) | `productName` 前缀 | 本项目只处理 OS Only |
| 4 | Tier (Standard/Basic/Spot) | `productName` 或 `skuName` 后缀 | 编码在名称后缀中 |
| 5 | Category | 从系列名推导 | General Purpose/Compute Optimized 等 |
| 6 | Instance Series | `productName` 中段 | Dv3/Ev5 等系列名 |
| 7 | Instance | `skuName` | D2 v3/D4 v3 等具体规格 |
| 8 | Savings Options | `type` + `reservationTerm` | Consumption/Reservation 1Y/3Y |

**本项目实现：** Pattern A (`instances_x_hours` + 5个子维度解析器)

**关键特征：**
- VM 的 `productName` 编码了 OS、系列、部署方式等多个维度
- Managed Disks 和 Bandwidth 是独立服务，Calculator 仅在 UI 层捆绑显示
- SavingsPlan 在 Global API 中**不返回** VM 数据，但 CN CSV 中存在

---

### 2.2 HDInsight

**Pricing Detail Page UI 结构：**

HDInsight Calculator 的 UI 按**集群类型 (Component)** 组织，每个集群类型下有多个**节点角色**，每个角色独立选择 VM 规格和数量：

```
HDInsight
├─ Cluster Type: [Hadoop | Spark | Kafka | HBase | Storm | Interactive Query | ML Services]
├─ Region: [East US | ...]
│
├─ Head Node:      [D12 v2 ▼] × 2 nodes  × 730 hours
├─ Worker Node:    [D4 v2  ▼] × 4 nodes  × 730 hours
└─ ZooKeeper Node: [A2 v2  ▼] × 3 nodes  × 730 hours
```

**UI 维度 → API 映射：**

| # | UI 维度 | API 字段 | 说明 |
|---|---------|---------|------|
| 1 | Region | `armRegionName` | 直接映射 |
| 2 | Cluster Type | 无直接字段 | Hadoop/Spark/Kafka 等，API 不区分集群类型 |
| 3 | Node Role | 无直接字段 | Head/Worker/Zookeeper 是 UI 层概念，API 只返回 VM 单价 |
| 4 | VM Size (per role) | `skuName` ≈ `meterName` | 1:1 对应，如 "D12 v2" |
| 5 | Node Count (per role) | 用户输入 | 乘数，不在 API 中 |
| 6 | Savings Options | 无 | 只有 Consumption 和 DevTestConsumption |

**API 数据结构（eastus）：**

```
productName = "HDInsight {Series} Series"   (19 个，如 "HDInsight Ev3 Series")
            | "HDInsight A Series Windows"  (唯一带 OS 后缀的)
            | "HDInsight Storage"           (磁盘定价)
            | "HDInsight ID Broker"         (基础设施组件)

skuName ≈ meterName = "{instance_size}"     (如 "E16 v3", "D16a v4/D16as v4")
type = "Consumption" | "DevTestConsumption"
unitOfMeasure = "1 Hour"
tierMinimumUnits = 0.0                       (无阶梯定价)
```

**productName 完整列表 (eastus)：**

| productName | 示例 skuName | 说明 |
|-------------|-------------|------|
| HDInsight A Series | A1-A7 | 老一代通用 |
| HDInsight A Series Windows | A1 | 唯一带 OS 后缀 |
| HDInsight Av2 Series | A1v2-A8mv2 | 通用第2代 |
| HDInsight D Series | D2a-D96a v4, Dv2 1-14 | 通用 |
| HDInsight Dadsv5 Series | D2ads-D96ads v5 | 通用最新代 |
| HDInsight Eadsv5 Series | E2ads-E96ads v5 | 内存优化 |
| HDInsight Edv5/Edsv5 Series | E2d-E104id v5 | 内存优化 |
| HDInsight ESv3/Ev3 Series | E2-E64i v3 | 内存优化 |
| HDInsight Eav4/Easv4 Series | E2a-E96a v4 | 内存优化 |
| HDInsight F/FS/FSv2 Series | F1-F72sv2 | 计算优化 |
| HDInsight G Series | G1-G5 | 大内存(旧) |
| HDInsight Lasv3 Series | L8as-L96as v3 | 存储优化 |
| HDInsight NC Series | NC6-NC24r | GPU |
| HDInsight Storage | S30/P30 Disk | 磁盘 |
| HDInsight ID Broker | A2 v2 | 基础设施 |

**定价模型：**

HDInsight 定价由**两部分**组成：
1. **HDInsight 服务费** — `serviceName = "HDInsight"` 的数据，按节点小时收费
2. **底层 VM 费用** — `serviceName = "Virtual Machines"` 的数据（独立计费）

每个节点角色的完整价格 = HDInsight 服务费/小时 + VM 费用/小时

**关键特征：无 Savings Options**
- 只有 Consumption 和 DevTestConsumption
- DevTest 折扣约 10%，部分新系列 DevTest 价格为 $0.00
- 部分新系列（Dadsv5, Edv5, FSv2, NC 等）无 DevTest 条目

---

### 2.3 Service Bus（已实现）

**Pricing Detail Page 维度：**

| # | UI 维度 | API 字段 | 说明 |
|---|---------|---------|------|
| 1 | Region | `armRegionName` | 直接映射 |
| 2 | Tier | `skuName` | Basic/Standard/Premium（Standard 还包含 Hybrid Connections 和 WCF Relay） |

**API 数据结构：**

```
productName = "Service Bus"                 (唯一值)
skuName = "Basic" | "Standard" | "Premium" | "Hybrid Connections" | "WCF Relay"
type = "Consumption"                        (唯一值)
unitOfMeasure = 多种 ("1M", "1/Month", "1/Hour", "1 GB", "10K", "1")
tierMinimumUnits = 有阶梯定价 + 免费层
```

**定价模型（按 Tier）：**

| Tier | Meter 构成 | 阶梯定价 |
|------|-----------|---------|
| Basic | Messaging Operations (per 1M) | 无 |
| Standard | Base Unit (hourly) + Messaging Operations (per 1M, 阶梯含免费层) + Brokered Connections (阶梯含免费层) | 有 |
| Premium | Messaging Unit (hourly) | 无 |
| Hybrid Connections | Data Transfer (GB, 阶梯含免费层) + Listener Units | 有 |
| WCF Relay | Relay Hours (per 100h) + Messages (per 10K) | 无 |

**本项目实现：** Pattern B (`per_meter` + `sku_groups` + `hidden_dimensions`)

**关键设计决策：**
- `sku_groups` 将 Standard/Hybrid Connections/WCF Relay 合并为一个 "Standard" 虚拟 Tier
- `productName` 隐藏（只有一个值 "Service Bus"）
- `skuName` 标签重命名为 "Tier"
- 每个 meter 独立输入用量，前端根据 `unitOfMeasure` 渲染合适的输入控件

---

### 2.4 Azure Machine Learning

**Pricing Detail Page UI 结构：**

Azure ML Calculator 的 UI 与 VM 非常相似 — 选择实例规格，按小时定价：

```
Azure Machine Learning
├─ Region: [East US | ...]
├─ Pricing Options: [Pay as you go | Savings Plan 1yr/3yr | Reserved 1yr/3yr]
├─ Instance Category: [General Purpose | Compute Optimized | Memory Optimized | GPU | HPC | Managed Spark]
├─ Instance: [D2 v3 | ... | NC6s v3 | ... | ND96asr A100 v4 | ...]
└─ Quantity: [1] instances × [730] hours
```

> **注意：** Pricing Detail 页面显示的 Savings Plan/RI 选项来自**底层 VM 服务**，而非 `serviceName = "Azure Machine Learning"` 本身的 API 数据。

**UI 维度 → API 映射：**

| # | UI 维度 | API 字段 | 说明 |
|---|---------|---------|------|
| 1 | Region | `armRegionName` | 直接映射 |
| 2 | Pricing Options | `type` | 仅 Consumption（Savings Plan/RI 来自底层 VM 服务） |
| 3 | Instance Category | 从 `skuName` 前缀推导 | NC=GPU, ND=Dense GPU, NV=Visualization, D=通用 |
| 4 | Instance | `skuName` = `armSkuName` | 具体实例规格，如 NCadisH100v5 |
| 5 | Savings Options | 无 (ML API 层面) | 无 Reservation/SavingsPlan |

**API 数据结构（eastus，28 items）：**

API 返回的数据分为三个明显不同的产品类别：

**类别 1: Managed Model Hosting Service（核心定价，15 items）**

```
productName = "Managed Model Hosting Service"       (单一 productName)
skuName = armSkuName = GPU 实例规格                   (如 "NCadisH100v5", "NV36adsA10v5")
meterName = "{skuName} Capacity Unit"
type = "Consumption"
unitOfMeasure = "1 Hour"
unitPrice = $0.454 ~ $12.29/hr
```

| skuName (eastus) | unitPrice/hr | GPU 类型 |
|------------------|-------------|---------|
| NV6adsv5 | $0.454 | A10 (入门) |
| NC4asT4 v3 | $0.526 | T4 |
| NV12adsA10v5 | $0.908 | A10 |
| NCadsA10v4 | $1.10 | A10 |
| NV18adsA10v5 | $1.60 | A10 |
| NV36adsA10v5 | $3.20 | A10 |
| NDasrA100v4 | $3.40 | A100 |
| NCadsA100v4 | $3.67 | A100 |
| NDamsrA100v4 | $4.10 | A100 |
| NV36admsA10v5 | $4.52 | A10 (大内存) |
| NV72adsA10v5 | $6.52 | A10 |
| NCadisH100v5 | $6.98 | H100 |
| NCadsH100 v5 | $6.98 | H100 |
| NDisrMI300Xv5 | $11.06 | MI300X |
| NDisrH100v5 | $12.29 | H100 |

**类别 2: Machine Learning service（附加费，大部分 $0，8 items）**

```
productName = "Machine Learning service"
skuName = "Standard" | "PB" | "Evaluation Input Tokens" | "Evaluation Output Tokens"
meterName = "Standard vCPU Surcharge" ($0) | "PB vCPU Surcharge" ($0.055) | ...
```
- 大部分是 $0 的 tracking meters（历史遗留）
- 少数有价格：GPU Surcharge ($0.11/hr), PB Surcharge ($0.055/hr)
- Evaluation Tokens: Input ($0.02/1K), Output ($0.06/1K)

**类别 3: Enterprise Inferencing（废弃，6 items，全部 $0）**

```
productName = "Azure Machine Learning Enterprise GPU {Series} Series Inferencing"
           | "Azure Machine Learning Enterprise General Compute Inferencing"
skuName = "vCPU"
unitPrice = $0.00
```

**类别 4: Token 计费（特定区域，不在 eastus）**

```
productName = "Managed Model Hosting Service"
skuName = "Llama-4-Scout-17B-16E-In" 等
unitOfMeasure = "1K"                                  (per 1K tokens)
unitPrice = $0.00016 ~ $0.00116/1K tokens
```
- 仅在 eastus2/swedencentral 等特定区域
- LLM 模型推理的 token 计费

**定价模式结论：**

Azure ML **本质上是 VM-like 的 `instances_x_hours` 模式**：
- "Managed Model Hosting Service" 是核心产品，skuName = GPU 实例规格
- 用户选择实例 → 获得小时单价 → 乘以数量和小时数
- 与 VM 的区别：所有实例在同一个 productName 下（不像 VM 按系列拆分 productName）
- 无 Reservation/SavingsPlan savings options

---

## 三、定价模式归纳与 quantity_model 对应

| 模式 | 代表产品 | 特征 | quantity_model | Savings Options |
|------|---------|------|---------------|-----------------|
| **A: 实例×小时** | VM, App Service, Power BI, Azure ML, HDInsight | 选实例规格 → 小时单价 × 数量 × 小时 | `instances_x_hours` | VM 有 RI/SavingsPlan；ML/HDInsight 无 |
| **B: 多 meter 独立计量** | Service Bus, Firewall, Event Grid | 多 meter 各自独立输入用量 | `per_meter` | 无 |

**Azure ML 与 VM、HDInsight 的对比：**

| 对比维度 | Virtual Machines | Azure ML | HDInsight |
|---------|-----------------|----------|-----------|
| productName 结构 | `VM {Series} Series {OS}` | `Managed Model Hosting Service` (单一) | `HDInsight {Series} Series` |
| skuName = 实例规格 | ✅ (D2 v3, E16 v5 等) | ✅ (NCadisH100v5, NV36adsA10v5 等) | ✅ (E16 v3, D16a v4 等) |
| 需要子维度解析器 | ✅ (OS/tier/category/series) | ❌ (productName 单一) | ❌ (Series 直接在主维度) |
| Reservation/SavingsPlan | ✅ | ❌ | ❌ |
| 阶梯定价 | ❌ | ❌ | ❌ |
| 多 Component | ❌ | ❌ | ✅ (多节点角色，完整版需要) |

---

## 四、各产品接入建议与配置方案

### 4.1 Virtual Machines — 已实现 ✅

Pattern A (`instances_x_hours` + 5 个子维度 + Reservation/SavingsPlan)。最复杂的产品。

### 4.2 Service Bus — 已实现 ✅

Pattern B (`per_meter` + `sku_groups` + `hidden_dimensions`)。

### 4.3 Azure Machine Learning — `instances_x_hours`（类 VM，无子维度）

**理由：**
- "Managed Model Hosting Service" 是选 GPU 实例 → 小时定价，与 VM 结构一致
- productName 只有一个值，无需子维度解析
- 无 Reservation/SavingsPlan
- 无阶梯定价

**配置方案：**

```json
{
  "service_name": "Azure Machine Learning",
  "api_service_name": "Azure Machine Learning",
  "quantity_model": "instances_x_hours",
  "quantity_label": "Instances",
  "static_subs": [],
  "hidden_subs": [],
  "defaults": {
    "hours_per_month": 730,
    "selections": { "armRegionName": "eastus" }
  }
}
```

**后续可选优化：**
- 通过 `excluded_products` 排除 `productName = "Machine Learning service"` 的 $0 meters
- 按 skuName 前缀（NC/ND/NV）添加 Instance Category 子维度

### 4.4 HDInsight — `instances_x_hours`（类 VM，无子维度，MVP 版本）

**理由：**
- productName = "HDInsight {Series} Series"，skuName = 实例规格，与 VM 结构一致
- 无 Reservation/SavingsPlan
- 无阶梯定价
- 多 Component（节点角色）可通过多张 estimate card 模拟，完整版后续迭代

**配置方案：**

```json
{
  "service_name": "HDInsight",
  "quantity_model": "instances_x_hours",
  "quantity_label": "Nodes",
  "static_subs": [],
  "hidden_subs": [],
  "defaults": {
    "hours_per_month": 730,
    "selections": { "armRegionName": "eastus" }
  }
}
```

**后续可选优化：**
- 完整多节点角色模型需要新的 `multi_component` quantity_model
- 同时查询 `serviceName = "HDInsight"` 和 `serviceName = "Virtual Machines"` 以合并完整价格

---

## 五、未解决问题与后续迭代方向

1. **HDInsight 多 Component 模型**：完整的 HDInsight Calculator 需要支持多节点角色（Head/Worker/Zookeeper），每个角色独立配置 VM 规格和数量。同时需要跨服务查询（HDInsight 服务费 + VM 底层费用）。这需要新的 `quantity_model`（如 `multi_component`）和新的 UI 组件。**MVP 先用 instances_x_hours 单实例模式**。

2. **Azure ML Token 计费**：Managed Model Hosting Service 中有 token 计费的 LLM 模型（unitOfMeasure="1K"），这些会出现在 meter 列表中但不适合 `instances_x_hours` 的计算逻辑。MVP 中这些 meter 会显示但计算可能不准确，后续可考虑混合模式或排除处理。

3. **Azure ML 的 $0 surcharge meters**：`productName = "Machine Learning service"` 下的大量 $0 附加费 meters 会出现在 cascade 中，可能需要通过 `excluded_products` 配置排除。

4. **跨服务价格合并**：HDInsight 和 Azure ML 的 Pricing Detail 页面都显示了"底层 VM + 服务费"的合并价格。如需实现，需要支持单个 estimate card 同时查询多个 serviceName 的能力。

5. **SavingsPlan 数据源差异**：Global API 不返回 VM SavingsPlan 数据，但 CN CSV 有。

---

## 六、验证命令参考

```bash
# 查看各产品的 API 维度分布
uv run python scripts/explore_global_api.py service "HDInsight"
uv run python scripts/explore_global_api.py service "Service Bus"
uv run python scripts/explore_global_api.py service "Virtual Machines" --region eastus
uv run python scripts/explore_global_api.py service "Azure Machine Learning"

# 查看级联筛选结果
uv run python scripts/explore_global_api.py cascade "HDInsight" --region eastus
uv run python scripts/explore_global_api.py cascade "Azure Machine Learning" --region eastus

# 查看具体 meter 定价
uv run python scripts/explore_global_api.py meters "Service Bus" --region eastus --sku Standard
```
