# Azure Global Pricing Calculator：定价模式分类与 API 数据分析

**数据源：** Azure Retail Prices API (Global)
**初版日期：** 2026-03-17（VM、Service Bus、HDInsight、Azure ML 四产品分析）
**更新日期：** 2026-03-26（扩展至 6 种定价模式，覆盖 20+ 产品 API 调研）

---

## 一、定价模式全景

通过对 Azure Global Retail Prices API 中 20+ 产品的实际数据调研，归纳出 **6 种定价模式**：

| 模式 | 名称 | 用户输入 | 数据源特征 | 系统支持 |
|------|------|---------|-----------|---------|
| **A** | `instances_x_hours` | 选实例 × 数量 × 小时 | 单服务, `unitOfMeasure = "1 Hour"` | ✅ 已实现 |
| **B** | `per_meter` | 每 meter 独立输入用量 | 单服务, 多种 unitOfMeasure | ✅ 已实现 |
| **C** | `compute_plus_storage` | 选计算规格 + 输入存储/IOPS | 单服务内多 productName | ❌ 未实现 |
| **D** | `resource_dimensions` | 指定多资源数量 × 时长 | 单服务, 多 unitOfMeasure | ❌ 未实现 |
| **E** | `sku_base_plus_meter` | 选 SKU 基础费 + 附加 meter | 单服务, 混合 unit | ⚠️ per_meter 近似 |
| **F** | `cross_service_composite` | 服务费 + 底层基础设施费 | **跨两个 serviceName** | ❌ 未实现 |

复杂度递增：

```
A (instances_x_hours)        ← 最简单
B (per_meter)                ← 多 meter
E (sku_base_plus_meter)      ← B 的变体
C (compute_plus_storage)     ← A + B 的混合，影响面最广（PaaS 数据库）
D (resource_dimensions)      ← 组合资源维度
F (cross_service_composite)  ← 最复杂，跨服务 + 外部映射表
```

---

## 二、Pattern A: `instances_x_hours` — 选实例 × 小时

**核心逻辑**：用户从级联筛选中选定一个实例/规格 → 获得小时单价 → `unitPrice × quantity × hours`

**API 共性**：
- `unitOfMeasure = "1 Hour"`（统一）
- 每个 skuName 通常对应一个 meter（一对一）
- 可能有 Reservation / SavingsPlan

### 产品示例

#### Virtual Machines（已实现 ✅，最复杂的 Pattern A）

```
serviceName = "Virtual Machines" (eastus, 数千行)
productName = "Virtual Machines {Series} Series {OS}" (数百个)
skuName = 实例规格 (D2 v3, E16 v5 等)
type = Consumption | DevTestConsumption | Reservation
unitOfMeasure = "1 Hour"
```

| # | UI 维度 | API 字段 | 说明 |
|---|---------|---------|------|
| 1 | Region | `armRegionName` | 直接映射 |
| 2 | Operating System | `productName` 后缀 | Linux/Windows/RHEL/SUSE |
| 3 | Tier | `productName` 或 `skuName` 后缀 | Standard/Basic/Spot |
| 4 | Category | 从系列名推导 | General Purpose/Compute Optimized |
| 5 | Instance Series | `productName` 中段 | Dv3/Ev5 |
| 6 | Instance | `skuName` | D2 v3/D4 v3 |
| 7 | Savings Options | `type` + `reservationTerm` | Consumption/RI 1Y/3Y/5Y |

**复杂之处**：`productName` 编码了 OS、系列、部署方式等多个维度，需要 5 个子维度解析器。SavingsPlan 在 Global API 中不返回 VM 数据，但 CN CSV 中存在。Managed Disks 和 Bandwidth 是独立服务，Calculator 仅在 UI 层捆绑显示。

#### App Service

```
serviceName = "Azure App Service" (eastus, 269 行, 21 productName, 60 skuName)
productName = "Azure App Service {Tier} Plan {-Linux}" (按 Tier×OS 拆分)
skuName = 实例规格 (P1 v3, P2mv3, I1 v2 等)
type = Consumption | Reservation
unitOfMeasure = "1 Hour"
```

结构与 VM 类似但更简单：`productName` 包含 Tier（Basic/Standard/Premium/Isolated）和 OS（后缀 `-Linux`）两个子维度。有 RI 选项。

#### Azure Cache for Redis

```
serviceName = "Azure Cache for Redis" (eastus)
productName = "Azure Cache for Redis"
skuName = Tier + 实例 (如 "Basic C0", "Standard C1", "Premium P1")
type = Consumption | Reservation
unitOfMeasure = "1 Hour"
```

简单的 Pattern A：单一 productName，skuName 编码了 Tier + 实例大小。有 RI 选项。

#### Power BI Embedded

```
serviceName = "Power BI Embedded" (eastus)
productName = "Power BI Embedded"
skuName = 节点规格 (A1, A2, A4, A5, A6)
type = Consumption only
unitOfMeasure = "1 Hour"
```

最简单的 Pattern A：单一 productName，无 RI，无子维度。

#### Azure Machine Learning（部分 — Managed Model Hosting）

```
serviceName = "Azure Machine Learning" (eastus, 28 行)
productName = "Managed Model Hosting Service" (核心定价, 15 items)
skuName = GPU 实例规格 (NCadisH100v5, NV36adsA10v5)
type = Consumption only
unitOfMeasure = "1 Hour"
unitPrice = $0.454 ~ $12.29/hr
```

| skuName (eastus) | $/hr | GPU |
|------------------|------|-----|
| NV6adsv5 | $0.454 | A10 |
| NC4asT4 v3 | $0.526 | T4 |
| NDasrA100v4 | $3.40 | A100 |
| NCadisH100v5 | $6.98 | H100 |
| NDisrH100v5 | $12.29 | H100 |

> **注意**：Azure ML 的完整定价模型属于 Pattern F（服务费 + VM 费），但 Managed Model Hosting Service 部分可以用 Pattern A 近似。另有 $0 surcharge meters 和 token 计费（特定区域），见 Pattern F 章节。

### Pattern A 内部变体总结

| 变体 | 产品 | 说明 |
|------|------|------|
| 有子维度解析器 | VM (5 个), App Service (OS+Tier) | productName 编码了多个维度 |
| 无子维度 | Redis, Power BI, Azure ML | productName 单一或少量 |
| 有 Savings Options | VM (RI+SP), App Service (RI), Redis (RI) | type + reservationTerm |
| 无 Savings Options | Power BI, Azure ML, HDInsight | type 仅 Consumption |

---

## 三、Pattern B: `per_meter` — 多 meter 独立计量

**核心逻辑**：用户通过级联选择 SKU/Tier 后，看到多个 meter，每个 meter 独立输入用量。

**API 共性**：
- `unitOfMeasure` 多样化（`"1M"`, `"1/Month"`, `"1/Hour"`, `"1 GB"`, `"10K"`, `"1"` 等）
- 一个 skuName 下有多个 meterName
- 常有阶梯定价（`tierMinimumUnits > 0`）和免费层
- 通常无 Reservation / SavingsPlan

### 产品示例

#### Service Bus（已实现 ✅）

```
serviceName = "Service Bus" (eastus)
productName = "Service Bus" (唯一值)
skuName = "Basic" | "Standard" | "Premium" | "Hybrid Connections" | "WCF Relay"
type = Consumption only
unitOfMeasure = "1M", "1/Month", "1/Hour", "1 GB", "10K", "1"
tierMinimumUnits = 有阶梯 + 免费层
```

| Tier | Meter 构成 | 阶梯 |
|------|-----------|------|
| Basic | Messaging Operations (per 1M) | 无 |
| Standard | Base Unit (hourly) + Messaging Operations (阶梯+免费) + Brokered Connections (阶梯+免费) | 有 |
| Premium | Messaging Unit (hourly) | 无 |
| Hybrid Connections | Data Transfer (GB, 阶梯+免费) + Listener Units | 有 |
| WCF Relay | Relay Hours (per 100h) + Messages (per 10K) | 无 |

配置使用 `sku_groups` 将 Standard/Hybrid/WCF 合并为一个 "Standard" 虚拟 Tier。

#### Azure Firewall（已实现 ✅）

```
serviceName = "Azure Firewall" (eastus)
skuName = VNet/Hub × Basic/Standard/Premium (6 种配置)
meter = Deployment (hourly) + Data Processed (per GB)
```

每个 SKU 两个 meter：部署费（固定小时费）+ 数据处理费（按 GB）。

#### Event Grid（已实现 ✅）

```
serviceName = "Event Grid" (eastus)
skuName = "Basic" | "Standard"
meter = Operations + Throughput Unit + MQTT Operations
```

#### SignalR Service（已实现 ✅）

```
serviceName = "SignalR" (eastus)
skuName = "Free" | "Standard" | "Premium"
meter = Unit (hourly) + Message
meter_free_quota: Standard/Premium Message 有免费额度（按 Unit 数量计算）
```

#### Load Balancer（已实现 ✅）

```
serviceName = "Load Balancer" (eastus)
skuName = "Basic" | "Standard" | "Gateway"
meter = Data Processed + Included LB Rules + Overage LB Rules + Chain
```

#### DDoS Protection

```
serviceName = "Azure DDoS Protection" (eastus)
productName = 单一
meter = 月费 (固定) + 超额 (按 GB)
hidden_dimensions: ["productName"]
```

只有 2 个 meter，结构极简。

#### Managed Grafana

```
serviceName = "Managed Grafana" (eastus)
productName = 单一
meter = 操作输入 + 活跃用户 + 区域冗余 (3 个 meter)
hidden_dimensions: ["productName"]
```

#### Azure Fluid Relay

```
serviceName = "Azure Fluid Relay" (eastus)
productName = 单一
meter = Input Ops + Output Ops + Client Connection Minutes + Storage (4 个 meter)
```

#### Site Recovery

```
serviceName = "Site Recovery" (eastus)
meter = Azure 到客户站点 + Azure 到 Azure (2 个 meter)
```

#### Traffic Manager

```
serviceName = "Traffic Manager" (eastus)
meter = DNS queries + Azure endpoint checks + External endpoint checks + Fast interval checks × 2 (5 个 meter)
```

#### Notification Hubs

```
serviceName = "Notification Hubs" (eastus)
skuName = "Free" | "Basic" | "Standard"
```

有 Tier 选择（`sku_groups`），按 Tier 展示不同 meter。

#### Container Registry

```
serviceName = "Container Registry" (eastus)
skuName = "Basic" | "Standard" | "Premium"
```

Tier 选择 + 对应月费 meter。

### Pattern B 配置要素总结

| 配置项 | 说明 | 使用产品 |
|--------|------|---------|
| `sku_groups` | 合并多个 API skuName 为逻辑 Tier | Service Bus, Firewall, Notification Hubs |
| `meter_labels` | 自定义 meter 显示名 | Service Bus, Firewall, Load Balancer |
| `meter_order` | 控制 meter 排序 | 所有 per_meter 产品 |
| `meter_free_quota` | 跨 meter 免费额度 | SignalR (Message 免费额度按 Unit 计) |
| `hidden_meters` | 隐藏不需展示的 meter | Firewall (Capacity Unit) |
| `hidden_dimensions` | 隐藏单值维度 | DDoS, Grafana, Fluid Relay 等 (单一 productName) |

---

## 四、Pattern C: `compute_plus_storage` — 计算 + 存储组合 ❌ 未实现

**核心逻辑**：用户先选**计算规格**（类似 Pattern A），再指定**存储容量、IOPS、备份**等附加资源（类似 Pattern B）。总费用 = 计算费 + 存储费 + 附加费。

**API 共性**：
- 同一 serviceName 下有多个 productName，按功能分组（Compute / Storage / Backup）
- Compute：`unitOfMeasure = "1 Hour"` 或 `"1/Day"`（DTU），skuName = 实例规格或 vCore 数
- Storage：`unitOfMeasure = "1 GB/Month"` 或 `"1 GiB/Month"`
- 附加：IOPS（`"1 IOPS/Month"`）、Backup（`"1 GB/Month"`）、Operations（`"1M"`）

**这是影响面最广的新模式**——所有 PaaS 数据库服务都属于此模式。

### 产品示例

#### SQL Database（最复杂，DTU + vCore 双模型共存）

```
serviceName = "SQL Database" (eastus, 348 行, 39 productName, 121 skuName)

Compute — DTU 模型:
  productName = "SQL Database Single Standard"
  skuName = S0, S1, S2, S3, S4, S6, S7, S9, S12
  unitOfMeasure = "1/Day"     ← 日费率，不是小时！
  tierMinimumUnits > 0        ← S7 有 6 级阶梯定价
  type = Consumption only

Compute — vCore 模型:
  productName = "SQL Database Single/Elastic Pool General Purpose - Compute Gen5"
  skuName = "1 vCore", "2 vCore", "4 vCore", ... "80 vCore"
  unitOfMeasure = "1 Hour"
  type = Consumption + Reservation (1Y/3Y)

Storage:
  productName = "SQL Database Single/Elastic Pool General Purpose - Storage"
  unitOfMeasure = "1 GB/Month"

Backup:
  productName = "SQL Database Single/Elastic Pool PITR Backup Storage"
  skuName = "Backup LRS" | "Backup RA-GRS" | "Backup ZRS"
  unitOfMeasure = "1 GB/Month"
```

Azure Calculator UI：选择购买模型 (DTU/vCore) → 选择 Tier → 选择规格 → 指定存储 GB → 指定备份冗余。DTU 模型用 `1/Day` 计费是个独特特征。

#### Azure Database for MySQL（Flexible Server）

```
serviceName = "Azure Database for MySQL" (eastus, 112 行, 33 productName)

Compute:
  productName = "...Flexible Server Burstable BS Series Compute"
             | "...Memory Optimized Edsv5 Series Compute"
             | "...General Purpose Ddsv5 Series Compute"    (十几个系列)
  skuName = "B1MS", "B2MS", "Standard_B12MS", ...
  unitOfMeasure = "1 Hour"

Storage:
  productName = "...Flexible Server Storage"
  skuName = "Standard" | "PMD LRS" | "SSD v2" | ...
  unitOfMeasure = "1 GB/Month" | "1 GiB/Month" | "1 IOPS/Month" | "1M"

Backup:
  productName = "...Flexible Server Backup Storage"
  unitOfMeasure = "1 GB/Month"
```

Azure Calculator UI：选择 Tier (Burstable/GP/MO) → 选 Compute → 指定 Storage GB + Storage Type + IOPS + Backup。

#### Azure Database for PostgreSQL

结构与 MySQL Flexible Server 基本一致，Compute/Storage/Backup 三层。

#### Azure Cosmos DB

```
serviceName = "Azure Cosmos DB" (eastus, 109 行, 15 productName)

RU/s 吞吐量 (核心):
  productName = "Azure DocumentDB"
  skuName = "RUs" | "mRUs" | "RUm"
  unitOfMeasure = "1/Hour"          ← 按 RU/小时计费
  type = Consumption + Reservation (1Y/3Y)

专用计算节点:
  productName = "Azure Cosmos DB Dedicated Gateway - General Purpose"
  skuName = "D2s", "D4s", ... "D64s", "E2s", ... "E64s"
  unitOfMeasure = "1 Hour"

Serverless:
  productName = "Azure Cosmos DB serverless"
  unitOfMeasure = "1M" (per 1M RU)

Storage:
  productName = "Azure Cosmos DB Analytics Storage" | "...PITR" | "...Snapshot"
  unitOfMeasure = "1 GB/Month"
```

Cosmos DB 最独特之处：RU/s 按 `"1/Hour"` 计费的容量单元模型，加上 Reservation 选项。

### 为什么当前系统不能处理 Pattern C

- `instances_x_hours` 只处理计算部分，无法加上存储费用
- `per_meter` 不支持"先选计算实例再看附加 meter"的交互
- 需要的是：cascade 选实例（计算）→ 展示实例价格 → 额外输入框填写存储 GB / IOPS → 总费用合并

**MVP 近似**：用 `instances_x_hours` 只展示计算费用，标注"存储费用另计"。或等 Task 8（Related Services）完成后将存储作为附加组件。

---

## 五、Pattern D: `resource_dimensions` — 多资源维度组合 ❌ 未实现

**核心逻辑**：没有预定义的"实例列表"，用户自行指定多个资源维度的数量（vCPU 数 + 内存 GB），每个维度有独立费率，总费用 = Σ(维度费率 × 维度数量) × 时长。

**与 Pattern A 的本质区别**：Pattern A 从预定义列表中选实例（D2 v3），一个 skuName = 一个价格；Pattern D 由用户自行组合资源规格，多个 meter 按维度独立计费再求和。

### 产品示例

#### Container Instances

```
serviceName = "Container Instances" (eastus, 16 行)
productName = "Container Instances" | "Container Instances with GPU"
skuName = "Standard" | "Standard Spot" | "Confidential containers ACI" | GPU 型号

Standard SKU 的 3 个 meter:
  ┌──────────────────────────┬────────────┬──────────────┐
  │ meterName                │ unit       │ unitPrice    │
  ├──────────────────────────┼────────────┼──────────────┤
  │ Standard vCPU Duration   │ 1 Hour     │ $0.0365/hr   │
  │ Standard Memory Duration │ 1 GB Hour  │ $0.004/GB·hr │
  │ Standard Windows Software│ 1 Second   │ $0.000012/s  │
  └──────────────────────────┴────────────┴──────────────┘

GPU SKU (V100) 的 meter:
  ┌──────────────────────────┬────────────────┬────────────┐
  │ meterName                │ unit           │ unitPrice  │
  ├──────────────────────────┼────────────────┼────────────┤
  │ V100 GPU Duration        │ 1 Hour         │ $3.06/hr   │
  │ V100 vCPU Duration       │ 100 Seconds    │ ...        │
  │ V100 Memory Duration     │ 100 GB Seconds │ ...        │
  └──────────────────────────┴────────────────┴────────────┘
```

Azure Calculator UI:

```
Container Instances
├─ Region: [East US]
├─ OS: [Linux | Windows]
├─ vCPUs: [2]
├─ Memory (GB): [4]
├─ Duration: [730] hours
└─ 月费 = (0.0365 × 2 + 0.004 × 4) × 730 = $64.97
```

**MVP 近似**：用 `per_meter` 将 vCPU Duration、Memory Duration 作为独立 meter，用户分别输入。计算可接受但 UI 不够直观。该模式产品极少（目前仅 Container Instances），优先级低。

---

## 六、Pattern E: `sku_base_plus_meter` — SKU 基础费 + 附加计量 ⚠️ per_meter 近似

**核心逻辑**：选择 SKU 后获得一个固定基础费率（不论用量），再加上按用量计费的附加 meter。

**与 Pattern B 的区别**：Pattern B 中所有 meter 地位平等，用户为每个 meter 输入用量；Pattern E 中有一个"固定基础费"不需要输入用量（选了 SKU 就收费），其余才是按量。

### 产品示例

#### VPN Gateway

```
serviceName = "VPN Gateway" (eastus, 30 行, 12 skuName)
productName = "VPN Gateway" (唯一)
unitOfMeasure = "1 Hour" (全部)

VpnGw1 SKU 的 3 个 meter:
  ┌──────────────────────┬────────┬─────────┐
  │ meterName            │ unit   │ $/hr    │
  ├──────────────────────┼────────┼─────────┤
  │ VpnGw1 (基础费)      │ 1 Hour │ $0.19   │ ← 固定基础费（选了就收）
  │ S2S Connection       │ 1 Hour │ $0.015  │ ← 按 S2S 连接数
  │ P2S Connection       │ 1 Hour │ $0.01   │ ← 按 P2S 连接数
  └──────────────────────┴────────┴─────────┘

月费 = (0.19 + 0.015 × S2S连接数 + 0.01 × P2S连接数) × 730
```

12 个 SKU（Basic, VpnGw1-5, VpnGw1AZ-5AZ），每个有类似结构。Advanced Connectivity Add-On 是独立附加项。

#### Bandwidth（纯按量 + 重度阶梯）

```
serviceName = "Bandwidth" (eastus, 23 行)
productName = "Rtn Preference: MGN" | "Bandwidth - Routing Preference: Internet"
skuName = "Standard" | "China"
unitOfMeasure = "1 GB" (17 行) | "1 Hour" (6 行)

Standard Data Transfer Out — 11 级阶梯:
  0-5 GB:     $0.00 (免费)
  5-100 GB:   $0.00 (免费)
  100 GB-10TB: $0.087/GB
  10-50 TB:   $0.083/GB
  50-150 TB:  $0.07/GB
  150-500 TB: $0.05/GB
  500+ TB:    $0.05/GB

Data Transfer In:   $0/GB (免费)
From China:         $0.09/GB
```

11 级阶梯定价对前端 `calculateTieredCost()` 是个考验，但逻辑已支持。

#### Key Vault（纯按操作次数）

```
serviceName = "Key Vault" (eastus, 17 行)
productName = "Key Vault" | "Key Vault HSM Pool" | "Azure Dedicated HSM"

Standard SKU 的 meter:
  ┌─────────────────────────┬────────────┬──────────┐
  │ meterName               │ unit       │ price    │
  ├─────────────────────────┼────────────┼──────────┤
  │ Operations              │ 10K        │ $0.03    │
  │ Advanced Key Operations │ 10K        │ $0.03    │
  │ Certificate Renewal     │ 1          │ $3.00    │
  │ Secret Renewal          │ 1          │ $1.00    │
  │ Automated Key Rotation  │ 1 Rotation │ $1.00    │
  └─────────────────────────┴────────────┴──────────┘

Premium SKU 额外: HSM Protected Keys ($0.03/10K) + HSM Instance ($4.xx/hr)
```

Key Vault 没有"固定基础费"，所有 meter 都是按操作/事件计费，本质更接近 Pattern B。

### 为什么 per_meter 可以近似

- VPN Gateway：基础费作为一个 meter（quantity = 1），附加费作为其他 meter — 可行
- Key Vault：天然适合 per_meter
- Bandwidth：阶梯定价由 `calculateTieredCost()` 处理 — 可行

**近似的局限**：VPN Gateway 的基础费理想 UI 是"选 SKU → 自动显示月基础费 $138.7"，不应让用户输入"1"。但 MVP 可接受。

---

## 七、Pattern F: `cross_service_composite` — 跨服务复合定价 ❌ 未实现

**核心逻辑**：产品的总费用由**两个不同 serviceName** 的数据相加：`服务溢价 + 底层 VM 基础设施费`。

**API 共性**：
- 需要查询两个 serviceName
- 服务 A 提供"服务费/溢价"
- 服务 B（通常是 `"Virtual Machines"`）提供"基础设施费"
- 可能需要外部映射表

### 产品示例

#### Azure Databricks（最复杂 — DBU + VM + 外部映射表）

```
serviceName = "Azure Databricks" (eastus, 41 行)
productName = "Azure Databricks" (24 行) | "Azure Databricks Regional" (17 行)

费用公式:
  总费用/hr = DBU 费率 × 该 VM 的 DBU 数 + VM 小时价
              ↑                    ↑            ↑
        serviceName=          外部映射表     serviceName=
        "Azure Databricks"    (不在API中)   "Virtual Machines"

DBU 费率表 (productName = "Azure Databricks"):
  ┌─────────────────────────────────┬───────────┐
  │ skuName                         │ $/DBU-hr  │
  ├─────────────────────────────────┼───────────┤
  │ Standard All-purpose Compute    │ $0.40     │
  │ Standard Jobs Compute           │ $0.15     │
  │ Standard Jobs Light Compute     │ $0.07     │
  │ Standard All-Purpose Photon     │ $0.40     │
  │ Standard SQL Analytics          │ $0.22     │
  │ Premium All-purpose Compute     │ $0.55     │
  │ Premium Jobs Compute            │ $0.30     │
  │ Premium Jobs Light Compute      │ $0.22     │
  │ Premium All-Purpose Photon      │ $0.55     │
  │ Premium SQL Analytics           │ $0.22     │
  │ Premium Advanced Compute DLT    │ $0.54     │
  │ Premium Enhanced Security       │ $0.10     │
  │ Free Trial (×4)                 │ $0.00     │
  └─────────────────────────────────┴───────────┘

Serverless DBU (productName = "Azure Databricks Regional"):
  ┌─────────────────────────────────────┬───────────┐
  │ skuName                             │ $/DBU-hr  │
  ├─────────────────────────────────────┼───────────┤
  │ Premium Serverless SQL              │ $0.70     │
  │ Premium Interactive Serverless      │ $0.95     │
  │ Premium Automated Serverless        │ $0.45     │
  │ Premium Database Serverless         │ $0.26     │
  │ Premium Model Training              │ $0.65     │
  │ Premium SQL Compute Pro             │ $0.55     │
  │ Premium Serverless Realtime Infer.  │ $0.07     │
  │ Premium Databricks Storage Unit DSU │ $0.023    │
  └─────────────────────────────────────┴───────────┘

计算示例: Premium All-Purpose + Standard_DS3_v2 (0.75 DBU)
  DBU 费 = $0.55 × 0.75 = $0.4125/hr
  VM 费  = $0.166/hr
  总费用 = $0.5785/hr × 730 = $422.31/月
```

**特殊复杂度**：
1. VM → DBU 数量的映射表不在 API 中，是 Databricks 文档中的硬编码数据
2. Serverless 模式不需要选 VM（只按 DBU 计费）
3. Clean Rooms 按 `1/Day` 计费（$50/天），唯一的日费率
4. 有 Driver + Worker 多节点角色

#### HDInsight（跨服务 + 多节点角色）

```
serviceName = "HDInsight" (eastus, ~185 行, 19 productName)

费用公式:
  每节点/hr = HDInsight 服务费 + VM 费
              ↑                   ↑
        serviceName=          serviceName=
        "HDInsight"           "Virtual Machines"
        (相同 skuName)        (相同 skuName)

productName = "HDInsight {Series} Series" (如 "HDInsight Ev3 Series")
skuName ≈ meterName = 实例规格 (如 "E16 v3")
type = "Consumption" | "DevTestConsumption"
unitOfMeasure = "1 Hour"
```

Azure Calculator UI 按节点角色组织：

```
HDInsight
├─ Cluster Type: [Hadoop | Spark | Kafka | HBase | ...]
├─ Region: [East US]
├─ Head Node:      [D12 v2 ▼] × 2 nodes  × 730 hours
├─ Worker Node:    [D4 v2  ▼] × 4 nodes  × 730 hours
└─ ZooKeeper Node: [A2 v2  ▼] × 3 nodes  × 730 hours
```

与 Databricks 相比简单之处：服务费和 VM 费使用**相同 skuName**（如 "D12 v2"），可直接按名匹配相加，不需要外部映射表。

#### Azure Machine Learning（Surcharge 大部分 $0）

```
serviceName = "Azure Machine Learning"

费用公式:
  总费用/hr = ML Surcharge + VM 费
  ML Surcharge 大部分 $0，实际费用几乎全来自 VM。

productName = "Machine Learning service":
  "Standard vCPU Surcharge":    $0.00/hr (tracking)
  "GPU Surcharge":              $0.11/hr
  "PB vCPU Surcharge":          $0.055/hr
  "Evaluation Input Tokens":    $0.02/1K
  "Evaluation Output Tokens":   $0.06/1K

productName = "Managed Model Hosting Service":
  GPU 实例小时费 ($0.45~$12.29/hr)

废弃 — "Enterprise Inferencing" (6 items): 全部 $0
```

Azure Calculator UI 中的 Savings Plan/RI 选项实际来自底层 VM 服务，不在 `serviceName = "Azure Machine Learning"` 的 API 数据中。

### Pattern F 产品对比

| | Databricks | HDInsight | Azure ML |
|---|-----------|-----------|----------|
| 服务费查询 | `"Azure Databricks"` | `"HDInsight"` | `"Azure Machine Learning"` |
| VM 费查询 | `"Virtual Machines"` | `"Virtual Machines"` | `"Virtual Machines"` |
| 关联方式 | 外部 DBU 映射表 | 相同 skuName 直接相加 | surcharge 大部分 $0 |
| 多节点角色 | ✅ (Driver + Worker) | ✅ (Head + Worker + ZK) | ❌ |
| Serverless 模式 | ✅ (只按 DBU) | ❌ | ❌ |
| Savings Options | 底层 VM 有 RI | 无 | 底层 VM 有 RI/SP |
| MVP 近似 | ❌ 暂不接入 | Pattern A 近似（仅服务费） | Pattern A 近似 ✅ |

---

## 八、模式与产品映射总表

| Family | 产品 | 模式 | 系统支持 | MVP 接入策略 |
|--------|------|------|---------|-------------|
| **Compute** | Virtual Machines | A | ✅ | 已实现 |
| | App Service | A | ✅ | 已实现 |
| | Container Instances | D | ❌ | per_meter 近似 |
| | Azure Functions | — | — | Global API 返回 0 |
| | AKS | — | — | Global API 返回 0 |
| **Networking** | Azure Firewall | B | ✅ | 已实现 |
| | Load Balancer | B | ✅ | 已实现 |
| | VPN Gateway | E | ⚠️ | per_meter 近似 |
| | Application Gateway | B | ⚠️ | Batch 2 待接入 |
| | DDoS Protection | B | ⚠️ | Batch 1 待接入 |
| | Traffic Manager | B | ⚠️ | Batch 2 待接入 |
| | Network Watcher | B | ⚠️ | Batch 2 待接入 |
| | Public IP Addresses | B | ⚠️ | Batch 2 待接入 |
| | Bandwidth | E | ⚠️ | per_meter 近似 (11 级阶梯) |
| **Storage** | Storage Accounts | C | ❌ | Pattern A 近似（复杂，暂缓） |
| | Managed Disks | — | — | Global API serviceName 不匹配 |
| **Databases** | SQL Database | C | ❌ | Pattern A 近似 (DTU `1/Day` 特殊) |
| | Azure Cache for Redis | A | ⚠️ | Batch 1 待接入 |
| | Azure Cosmos DB | C | ❌ | Pattern A 近似 (RU/s 模型特殊) |
| | Azure Database for MySQL | C | ❌ | Pattern A 近似 |
| | Azure Database for PostgreSQL | C | ❌ | Pattern A 近似 |
| | Container Registry | B | ⚠️ | Batch 1 待接入 |
| | Database Migration Service | A | ⚠️ | Batch 1 待接入 |
| **AI + ML** | Azure Machine Learning | F→A | ⚠️ | Pattern A 近似 (忽略 surcharge) |
| | Cognitive Services | — | — | Global API 返回 0 |
| **Analytics** | HDInsight | F | ❌ | Pattern A 近似 (仅服务费) |
| | Power BI Embedded | A | ✅ | 已实现 |
| | Azure Databricks | F | ❌ | 暂不接入 (最复杂) |
| **Web** | Azure SignalR Service | B | ✅ | 已实现 |
| | Azure CDN | — | — | Global API 返回 0 |
| **Integration** | API Management | B | — | catalog 中有 |
| | Event Grid | B | ✅ | 已实现 |
| | Service Bus | B | ✅ | 已实现 |
| | Notification Hubs | B | ⚠️ | Batch 1 待接入 |
| **Security** | Key Vault | E→B | — | per_meter 可处理 |
| **DevOps** | Azure DevOps | — | — | Global API 返回 0 |
| | Managed Grafana | B | ⚠️ | Batch 1 待接入 |

> 标注 `—` 的产品在 Global API 中使用了不同的 serviceName，需进一步调查。

---

## 九、未来迭代方向

### 按优先级排序

1. **Pattern C 支持**（影响 SQL Database, MySQL, PostgreSQL, Cosmos DB）
   - 新增 `compute_plus_storage` quantity_model
   - 或扩展 Task 8（Related Services）将存储/备份作为附加组件
   - SQL Database 的 DTU `1/Day` 计费需要特殊处理

2. **Pattern F: HDInsight 跨服务查询**
   - 单个 estimate card 查询多个 serviceName
   - 多节点角色需新 UI 组件

3. **Pattern D: Container Instances 资源维度**
   - per_meter 近似足够实用，优先级低

4. **Pattern F: Azure Databricks 完整支持**
   - 需要 DBU 映射表 + 跨服务查询 + Serverless 模式
   - 复杂度最高，最后实现

### 需进一步调查的产品

| 产品 | 尝试的 serviceName | 可能的实际名称 |
|------|-------------------|--------------|
| Azure Functions | "Azure Functions" | 可能归入 "Azure App Service" |
| AKS | "Azure Kubernetes Service (AKS)" | 控制面免费，节点用 VM 计费 |
| Managed Disks | "Managed Disks" | 可能归入 "Storage" (serviceName = "Storage") |
| Azure CDN | "Azure CDN" | 可能是 "Content Delivery Network" |
| Cognitive Services | "Cognitive Services" | 可能按具体子服务拆分 |
| Azure DevOps | "Azure DevOps" | 可能不在 Retail Prices API 中 |

### 其他未解决问题

1. **SavingsPlan 数据源差异**：Global API 不返回 VM SavingsPlan 数据，但 CN CSV 有
2. **Azure ML Token 计费**：特定区域的 LLM 模型 token 计费（`unitOfMeasure = "1K"`）不适合 `instances_x_hours`
3. **Azure ML $0 surcharge**：cascade 中会出现大量 $0 meter，需通过 `excluded_products` 排除

---

## 十、验证命令参考

```bash
# Pattern A 产品
uv run python scripts/explore_global_api.py service "Virtual Machines" --region eastus
uv run python scripts/explore_global_api.py service "Azure App Service" --region eastus
uv run python scripts/explore_global_api.py service "Azure Machine Learning" --region eastus

# Pattern B 产品
uv run python scripts/explore_global_api.py service "Service Bus" --region eastus
uv run python scripts/explore_global_api.py meters "Service Bus" --region eastus --sku Standard
uv run python scripts/explore_global_api.py service "Key Vault" --region eastus
uv run python scripts/explore_global_api.py meters "Key Vault" --region eastus --sku Standard

# Pattern C 产品
uv run python scripts/explore_global_api.py service "SQL Database" --region eastus
uv run python scripts/explore_global_api.py meters "SQL Database" --region eastus --product "SQL Database Single Standard"
uv run python scripts/explore_global_api.py service "Azure Database for MySQL" --region eastus
uv run python scripts/explore_global_api.py meters "Azure Database for MySQL" --region eastus --product "Azure Database for MySQL Flexible Server Storage"
uv run python scripts/explore_global_api.py service "Azure Cosmos DB" --region eastus

# Pattern D 产品
uv run python scripts/explore_global_api.py service "Container Instances" --region eastus
uv run python scripts/explore_global_api.py meters "Container Instances" --region eastus --product "Container Instances" --sku Standard

# Pattern E 产品
uv run python scripts/explore_global_api.py service "VPN Gateway" --region eastus
uv run python scripts/explore_global_api.py meters "VPN Gateway" --region eastus --sku VpnGw1
uv run python scripts/explore_global_api.py service "Bandwidth" --region eastus
uv run python scripts/explore_global_api.py meters "Bandwidth" --region eastus --sku Standard

# Pattern F 产品
uv run python scripts/explore_global_api.py service "Azure Databricks" --region eastus
uv run python scripts/explore_global_api.py meters "Azure Databricks" --region eastus --product "Azure Databricks"
uv run python scripts/explore_global_api.py meters "Azure Databricks" --region eastus --product "Azure Databricks Regional"
uv run python scripts/explore_global_api.py service "HDInsight" --region eastus
uv run python scripts/explore_global_api.py cascade "HDInsight" --region eastus
```
