# Azure Global Pricing Calculator：定价模式分类与 API 数据分析

**数据源：** Azure Retail Prices API (Global) + Azure Calculator UI 截图验证
**初版日期：** 2026-03-17（VM、Service Bus、HDInsight、Azure ML 四产品分析）
**更新日期：** 2026-03-26（扩展至 6 种定价模式，覆盖 20+ 产品 API 调研）
**更新日期：** 2026-04-01（Pattern A 四产品 API+UI 深度调研：VM、App Service、Redis、DMS）

---

## 一、定价模式全景

通过对 Azure Global Retail Prices API 中 20+ 产品的实际数据调研，归纳出 **6 种定价模式**：

| 模式 | 名称 | 用户输入 | 数据源特征 | 系统支持 |
|------|------|---------|-----------|---------|
| **A** | `instances_x_hours` | 选实例 × 数量 × 小时 | 单服务, `unitOfMeasure = "1 Hour"` | ⚠️  待验证 |
| **B** | `per_meter` | 每 meter 独立输入用量 | 单服务, 多种 unitOfMeasure | ⚠️  待验证 |
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

#### Virtual Machines（最复杂的 Pattern A）

```
serviceName = "Virtual Machines" (eastus, 10000+ 行, 440 productName, 993 skuName)
productName = "Virtual Machines {Series} Series {OS}" (数百个)
skuName = 实例规格 (D2 v3, E16 v5 等)
type = Consumption | DevTestConsumption | Reservation
unitOfMeasure = "1 Hour"
```

**Azure Calculator UI 布局**（已验证截图）：

```
行1: Region [East US ▼]  Operating system [Windows ▼]  Type [(OS Only) ▼]  Tier [Standard ▼]
行2: Category [All ▼]    Instance Series [All ▼]       INSTANCE [🔍 D2 v3: 2 vCPUs, 8 GB RAM, 50 GB, $0.188/hour ▼]
行3: [1] Virtual machines × [730] [Hours ▼]

Savings Options (双列布局):
  左列 — Compute (D2 v3):              右列 — OS (Windows):
    ● Pay as you go                       ● License included
    Savings plan ⓘ                        ○ Azure Hybrid Benefit ⓘ
      ○ 1 year savings plan (~31%)
      ○ 3 year savings plan (~53%)
    Reservations ⓘ
      ○ 1 year reserved (~40%)
      ○ 3 year reserved (~62%)

价格: $70.08 (Compute) + $67.16 (OS) = $137.24 Average per month

▽ Managed Disks        $0.00    ← 折叠的 Related Services（独立 serviceName）
▽ Storage transactions $0.00
▽ Bandwidth            $0.00
```

| # | UI 维度 | API 字段 | 说明 |
|---|---------|---------|------|
| 1 | Region | `armRegionName` | 直接映射 |
| 2 | Operating System | `productName` 后缀 | Linux/Windows/RHEL/SUSE |
| 3 | Type | `productName` 中 | (OS Only) / Windows Container 等 |
| 4 | Tier | `productName` 或 `skuName` 后缀 | Standard/Basic/Spot |
| 5 | Category | 从系列名推导 | General Purpose/Compute Optimized |
| 6 | Instance Series | `productName` 中段 | Dv3/Ev5 |
| 7 | Instance | `skuName` | D2 v3/D4 v3（搜索框含 vCPU/RAM/存储/价格） |
| 8 | Savings Options | `type` + `reservationTerm` | PAYG / SP 1Y/3Y / RI 1Y/3Y |

**复杂之处**：
- `productName` 编码了 OS、系列、部署方式等多个维度，需要 5 个子维度解析器
- SavingsPlan 在 Global API 中不返回 VM 数据，但 CN CSV 中存在
- **Compute + OS 双价格列**：UI 将计算费和 OS 许可费分开显示，各自独立计价
- **Azure Hybrid Benefit**：Windows OS 可选 BYOL，减免 OS 费用
- **Related Services**：Managed Disks / Storage transactions / Bandwidth 是独立 serviceName，Calculator 仅在 UI 层折叠捆绑显示

#### App Service

```
serviceName = "Azure App Service" (eastus, 269 行, 21 productName, 60 skuName)
productName = "Azure App Service {Tier} Plan {- Linux}" (按 Tier×OS 拆分)
skuName = 实例规格 (P1 v3, P2mv3, I1 v2 等)
type = Consumption | DevTestConsumption | Reservation
unitOfMeasure = "1 Hour" (266行) | "1/Month" (2行 SSL) | "1/Year" (1行 Domain)
```

**productName 层级与 RI 可用性**：

| productName | skuName | type | RI |
|-------------|---------|------|----|
| Azure App Service Free Plan {- Linux} | F1 | Consumption | ❌ |
| Azure App Service Shared Plan | Shared | Consumption + DevTest | ❌ |
| Azure App Service Basic Plan {- Linux} | B1, B2, B3 | Consumption + DevTest | ❌ |
| Azure App Service Standard Plan {- Linux} | S1, S2, S3 | Consumption + DevTest | ❌ |
| Azure App Service Premium Plan | P1-P4 | Consumption | ❌ |
| Azure App Service Premium v2 Plan {- Linux} | P1v2, P2v2, P3v2 | Consumption + DevTest | ❌ |
| Azure App Service Premium v3 Plan {- Linux} | P0v3, P1v3, P1mv3, ... P5mv3 (9) | Consumption + DevTest + **RI 1Y/3Y** | ✅ |
| Azure App Service Premium v4 Plan {- Linux} | P0v4, P1v4, P1mv4, ... P5mv4 (9) | Consumption + DevTest + **RI 1Y/3Y** | ✅ |
| Azure App Service Premium Windows Container Plan | PC2, PC3, PC4 | Consumption | ❌ |
| Azure App Service Isolated Plan {- Linux} | I1-I3 + Stamp + Front End | Consumption + **RI 3Y** | ✅ |
| Azure App Service Isolated v2 Plan {- Linux} | I1v2-I6v2 + I1mv2-I5mv2 + ASIP (13) | Consumption + **RI 1Y/3Y** | ✅ |
| Azure App Service SSL Connections | IP SSL, SNI SSL | Consumption | ❌ |
| Azure App Service Domain | Redemption Fee | Consumption ($80/yr) | ❌ |

**子维度解析**：
- **OS**: productName 后缀 `- Linux` → Linux；无后缀 → Windows
- **Tier**: productName 中段 Free/Shared/Basic/Standard/Premium/Pv2/Pv3/Pv4/Isolated/Iv2
- **特殊产品**: SSL Connections (`1/Month`), Domain (`1/Year`) 不是计算实例，需 `excluded_products` 排除
- **Isolated Stamp fee**: Isolated v1 有 "Stamp" SKU（环境固定费），v2 有 "ASIP"（类似），不是计算实例

**Azure Calculator UI 布局**（已验证截图 — Premium V3 + Linux）：

```
行1: Region [West US ▼]  Operating system [Linux ▼]  Tier [Premium V3 ▼] ⓘ

Premium V3 (tier 标题)
  INSTANCE: [P0V3: 1 vCPU(s), 4 GB RAM, 250 GB Storage, $0.088 ▼]
  [1] Instances × [730] [Hours ▼]

Savings Options:
  ● Pay as you go
  Savings plan ⓘ
    ○ 1 year savings plan (~25% discount)
    ○ 3 year savings plan (~45% discount)
  Reservations ⓘ
    ○ 1 year reserved (~35% discount)
    ○ 3 year reserved (~55% discount)

价格: $63.87 Average per month ($0.00 charged upfront)

▽ SSL Connections                 $0.00  ← 折叠的 Related Services
▽ Custom Domain and Certificates  $0.00
```

**与 VM 的对比**：
- **有 Savings Plan**（UI 显示 SP 1Y/3Y，但 Global API 不返回 SP 数据——与 VM 相同）
- 无 Compute+OS 分价（单价格列），无 Category/Instance Series 层级
- `productName` 只编码 Tier + OS 两个子维度（VM 编码了 5 个）
- 3 个级联下拉 + 1 个 Instance 选择（VM 有 7 个）
- Instance 下拉含规格信息：`P0V3: 1 vCPU(s), 4 GB RAM, 250 GB Storage, $0.088`
- **Related Services**：SSL Connections + Custom Domain（独立 productName，非计算实例）

#### Azure Cache for Redis

```
serviceName = "Redis Cache" (注意：不是 "Azure Cache for Redis"!)
eastus: 193 行, 10 productName, 70 skuName
type = Consumption | Reservation (无 DevTest)
unitOfMeasure = "1 Hour" (全部统一)
```

**4 条产品线 × 10 个 productName**：

| 产品线 | productName | skuName | RI |
|--------|------------|---------|-----|
| **Classic Basic** | Azure Redis Cache Basic | C0-C6 (7) | ❌ |
| **Classic Standard** | Azure Redis Cache Standard | C0-C6 (7) | ❌ |
| **Classic Premium** | Azure Redis Cache Premium | P1-P5 (5) | ✅ 1Y/3Y |
| **Enterprise** | Azure Redis Cache Enterprise | E1, E5, E10, E20, E50, E100, E200, E400 + E1 Internal | ✅ 1Y/3Y |
| **Enterprise Flash** | Azure Redis Cache Enterprise Flash | F300, F700, F1500 | ✅ 1Y/3Y |
| **Managed Balanced** | Azure Managed Redis - Balanced | B0-B1000 (14) | ✅ 1Y/3Y |
| **Managed Compute** | Azure Managed Redis - Compute Optimized | X1-X700 (12) | ✅ 1Y/3Y |
| **Managed Memory** | Azure Managed Redis - Memory Optimized | M10-M2000 (12) | ✅ 1Y/3Y |
| **Managed Flash** | Azure Managed Redis - Flash Optimized | A250-A4500 (7) | ✅ 1Y/3Y |
| **Isolated** | Azure Redis Cache Isolated | I100 (1) | ❌ |

**关键发现 — "Cache" vs "Cache Instance" 双 meter**：

Premium 和 Standard 每个 SKU 有两个 Consumption meter：

```
Premium P1:
  "P1 Cache"          $0.555/hr  ← per-shard 价格 (= primary + built-in replica = 2 nodes)
  "P1 Cache Instance" $0.277/hr  ← per-node 价格 (单个节点)
  
  关系: $0.555 ≈ $0.277 × 2
  RI 仅在 "Cache Instance" meter 上提供
```

**Azure Calculator UI 布局**（已验证截图）：

```
行1: Region [West US ▼]  Tier [Premium ▼]  INSTANCE [P1: 6,144 MB cache, $0.554/hour ▼]

Premium (tier 特有输入区):
  [1] Shard per Instance × [0] Additional Replicas per Shard × [1] Instance × [730] [Hours ▼]

View Cost Calculation ⓘ (展开):
  1 Shard × ( 1 Primary Node + 1 Built-in Replica + 0 Additional Replicas ) = 2 Nodes per Instance
  2 Nodes × 1 Instance × 730 Hours × $0.28 Per Node per Hour = $404.42

Savings Options:
  ● Pay as you go
  Reservations ⓘ
    ○ 1 year reserved (~36% savings)
    ○ 3 year reserved (~55% savings)

价格: $404.42 Average per month ($0.00 charged upfront)
```

**关键设计要点**：
- **Tier 决定量化模型**：Basic/Standard = `[N] Instance × [H] Hours`（简单）; Premium = `Shard × Replicas × Instance × Hours`（复杂）
- **Premium 计费公式**：`shards × (1 primary + 1 built-in + additional_replicas) × instances × hours × per_node_price`
- **API 用 "Cache Instance" meter**（per-node），UI 展示的 $0.28 即此价格
- **Instance 下拉含规格信息**：`P1: 6,144 MB cache, $0.554/hour`（$0.554 是 per-shard 价格，即 2 nodes）
- **无 Savings Plan**，仅有 RI 1Y/3Y
- **Managed Redis 系列是新产品线**，只有 "Cache Instance" meter（无 "Cache"），结构更简洁

#### Power BI Embedded

```
serviceName = "Power BI Embedded" (eastus)
productName = "Power BI Embedded"
skuName = 节点规格 (A1, A2, A4, A5, A6)
type = Consumption only
unitOfMeasure = "1 Hour"
```

最简单的 Pattern A：单一 productName，无 RI，无子维度。

#### Azure Database Migration Service（最简 Pattern A）

```
serviceName = "Azure Database Migration Service" (eastus, 11 行, 4 productName, 6 skuName)
type = Consumption only (无 RI, 无 DevTest, 无 SP)
unitOfMeasure = "1 Hour" (9行) | "1 GB/Month" (2行, 全 $0)
```

**API 数据结构**：

| productName | skuName | meterName | unit | price |
|-------------|---------|-----------|------|-------|
| ...Basic Compute | 1 vCore | 1 vCore | 1 Hour | $0.018 |
| ...Basic Compute | 1 vCore | 1 vCore vCore - Free | 1 Hour | $0.000 |
| ...Basic Compute | 2 vCore | 2 vCore | 1 Hour | $0.037 |
| ...General Purpose Compute | 4 vCore | 4 vCore | 1 Hour | $0.154 |
| ...General Purpose Compute | 8 vCore | 8 vCore | 1 Hour | $0.309 |
| ...General Purpose Compute | 16 vCore | 16 vCore | 1 Hour | $0.618 |
| ...General Purpose Storage | General Purpose | Data Stored - Free | 1 GB/Month | $0.000 |
| ...General Purpose Storage | General Purpose | Data Stored - Free | 1 GB/Month | $0.000 |
| ...Premium Compute | 4 vCore | 4 vCore | 1 Hour | $0.308 |
| ...Premium Compute | 8 vCore | 8 vCore | 1 Hour | $0.616 |
| ...Premium Compute | 16 vCore | 16 vCore | 1 Hour | $1.232 |

**Azure Calculator UI 布局**（已验证截图）：

```
标题: Azure Database Migration Service (classic)

行1: Region [East US ▼]  Pricing Tier [Premium ▼]  Instance [4 vCore ▼]
行2: [1] Instances × [1] [Hours ▼]                                = $0.31

Upfront cost   $0.00
Monthly cost   $0.31
```

**关键特征**：
- **最简 Pattern A**：3 个下拉 + Instance × Hours，无任何 Savings Options
- **UI 标注 "(classic)"**，说明这是即将退役的旧版服务
- **productName 编码 Tier**：Basic/General Purpose/Premium 三个 Compute 级别
- **Storage 全免费**：General Purpose Storage 的 meter 全部 $0，UI 中不显示
- **skuName = vCore 数量**：1/2/4/8/16 vCore
- **Basic 有免费 meter**：`1 vCore vCore - Free` ($0)，可能是免费试用配额
- **Pricing Tier 维度**：UI 显示为 "Pricing Tier"（不同于 VM 的 "Tier"），映射到 productName 中的 Basic/GP/Premium



### Pattern A 内部变体总结

| 维度 | VM | App Service | Redis | DMS | Power BI | Azure ML |
|------|----|----|-------|-----|---------|---------|
| **级联层级** | 7（Region→OS→Type→Tier→Category→Series→Instance） | 4（Region→OS→Tier→Instance） | 3（Region→Tier→Instance） | 3（Region→PricingTier→Instance） | 2（Region→Instance） | 2（Region→Instance） |
| **productName 子维度** | 5（OS/Series/Type/Tier/部署） | 2（Tier/OS） | 1（Tier=productName） | 1（Tier=productName） | 无 | 无 |
| **Savings Plan** | ✅ SP 1Y/3Y (UI有，API无) | ✅ SP 1Y/3Y (UI有，API无) | ❌ | ❌ | ❌ | ❌ |
| **Reservation** | ✅ RI 1Y/3Y | ✅ RI 1Y/3Y (Pv3/Pv4/Iv2) | ✅ RI 1Y/3Y (Premium+) | ❌ | ❌ | ❌ |
| **DevTest** | ✅ | ✅ (Basic/Std/Pv2-v4) | ❌ | ❌ | ❌ | ❌ |
| **特殊量化** | Compute+OS 双价格列 | 无 | Premium: Shard×Replicas | 无 | 无 | 无 |
| **Related Services** | Disks+Storage+Bandwidth | SSL+Domain | 无 | 无 | 无 | 无 |
| **Instance 描述** | vCPU/RAM/Storage/$/hr | vCPU/RAM/Storage/$/hr | MB cache/$/hr | vCore | 规格代号 | GPU型号 |
| **serviceName** | Virtual Machines | Azure App Service | Redis Cache ⚠️ | Azure Database Migration Service | Power BI Embedded | Azure Machine Learning |

> ⚠️ Redis serviceName = `"Redis Cache"`（不是 `"Azure Cache for Redis"`）

---

## 三、Pattern B: `per_meter` — 多 meter 独立计量

> 更新 2026-04-01：基于 API 数据 + UI 截图深度调研 Service Bus / Azure Firewall / Event Grid / Traffic Manager / Notification Hubs

**核心逻辑**：用户通过级联选择 SKU/Tier 后，看到多个 meter，每个 meter 独立输入用量。

**API 共性**：
- `unitOfMeasure` 多样化（`"1M"`, `"1/Month"`, `"1/Hour"`, `"1 GB"`, `"10K"`, `"100 Hours"`, `"1"` 等）
- 一个 skuName 下有多个 meterName
- 常有阶梯定价（`tierMinimumUnits > 0`）和免费层（tier=0 + price=$0）
- 通常无 Reservation / SavingsPlan（5 个调研产品全部 `type = Consumption only`）
- `productName` 通常只有 1 个（与 Pattern A 的多 productName 子维度不同）

**⚠️ 重要发现：UI = API 数据的配置化子集/重组**

通过 API 数据与 Calculator UI 对照，发现 Pattern B 产品的 UI 普遍不是 API 数据的直接映射：
- **过滤**：Firewall UI 只展示 VNet SKU，过滤掉了 Secured Virtual Hub 变体
- **虚拟分层**：Event Grid API 全部 `skuName="Standard"`，但 UI 创建了 Basic/Standard 虚拟 Tier
- **隐藏 SKU**：Notification Hubs UI 只展示 Free/Basic/Standard，隐藏了 1P Direct Send / AZ / Private Link 等附加 SKU
- **Region 映射**：Traffic Manager API 用 Global/Delos/US Gov 分区，但 UI 提供标准 Region 选择器并映射到定价区域

这验证了我们 per-product JSON 配置的设计方向——配置文件决定 API 数据的哪些子集以什么方式呈现给用户。

**与 Pattern A 的核心区别**：
| 维度 | Pattern A | Pattern B |
|------|-----------|-----------|
| unit 类型 | 统一 `"1 Hour"` | 多种混合（1M, 1/Month, 1 GB, 1 Hour...） |
| 用户输入 | 选实例 → 输入数量+时长 | 选 Tier → 每个 meter 独立输入用量 |
| 费用展示 | 单一计算行 | 多行 meter × 用量 |
| RI/SP | 常见 | 通常无 |

### 3.1 Service Bus ✅

```
serviceName = "Service Bus"
serviceFamily = "Integration"
productName = "Service Bus"（唯一）
armRegionName = 需要 region 筛选
总行数（eastus）= 18
type = Consumption only
```

**完整 API 数据表（eastus, 18 rows）：**

| skuName | meterName | unitOfMeasure | retailPrice | tierMinimumUnits |
|---------|-----------|---------------|-------------|------------------|
| Basic | Basic Messaging Operations | 1M | $0.05 | 0 |
| Standard | Standard Base Unit | 1/Hour | $0.013441 | 0 |
| Standard | Standard Base Unit | 1/Month | $10.0 | 0 |
| Standard | Standard Messaging Operations | 1M | $0.0 | 0 |
| Standard | Standard Messaging Operations | 1M | $0.8 | 13 |
| Standard | Standard Messaging Operations | 1M | $0.5 | 100 |
| Standard | Standard Messaging Operations | 1M | $0.2 | 2500 |
| Standard | Standard Brokered Connection | 1 | $0.0 | 0 |
| Standard | Standard Brokered Connection | 1 | $0.03 | 1,000 |
| Standard | Standard Brokered Connection | 1 | $0.025 | 100,000 |
| Standard | Standard Brokered Connection | 1 | $0.015 | 500,000 |
| Premium | Premium Messaging Unit | 1/Hour | $0.9275 | 0 |
| Hybrid Connections | Hybrid Connections Data Transfer | 1 GB | $0.0 | 0 |
| Hybrid Connections | Hybrid Connections Data Transfer | 1 GB | $1.0 | 5 |
| Hybrid Connections | Hybrid Connections Listener Unit | 1 Hour | $0.0134 | 0 |
| WCF Relay | WCF Relay | 100 Hours | $0.1 | 0 |
| WCF Relay | WCF Relay Message | 10K | $0.01 | 0 |
| Geo Replication Zone 1 | Geo Replication Zone 1 Data Transfer | 1 GB | $0.09 | 0 |

**关键发现：**

1. **Standard Base Unit 双 unit 行**：同一 meterName "Standard Base Unit" 有两行：`1/Hour = $0.013441` 和 `1/Month = $10.0`。这两个不是不同 meter——$0.013441 × 730h ≈ $9.81 ≠ $10，说明月费是固定费而非小时费的累计。UI 显示的是月费 $10。
2. **6 个 skuName 但逻辑上 3 个 Tier**：Basic / Standard (含 Hybrid Connections + WCF Relay + Geo Replication) / Premium
3. **阶梯定价 + 免费层**：Standard Messaging Operations 和 Brokered Connection 都有 tier=0 且 price=$0 的免费层
4. **unitOfMeasure 极度多样化**：8 种不同 unit（`1M`, `1/Month`, `1/Hour`, `1 Hour`, `1 GB`, `100 Hours`, `10K`, `1`）

**Tier → Meter 结构映射：**

```
Basic
 └─ Messaging Operations ($0.05/1M)

Standard
 ├─ Base Unit ($10/month 固定)
 ├─ Messaging Operations (4级阶梯: 0-13M 免费 → 13-100M $0.80/1M → 100-2500M $0.50/1M → 2500M+ $0.20/1M)
 ├─ Brokered Connections (4级阶梯: 0-1K 免费 → 1K-100K $0.03 → 100K-500K $0.025 → 500K+ $0.015)
 ├─ [Hybrid] Data Transfer (2级: 0-5GB 免费 → 5GB+ $1/GB)
 ├─ [Hybrid] Listener Unit ($0.0134/hr)
 ├─ [WCF] Relay Hours ($0.1/100hr)
 ├─ [WCF] Relay Messages ($0.01/10K)
 └─ [Geo] Replication Data Transfer ($0.09/GB)

Premium
 └─ Messaging Unit ($0.9275/hr)
```

**UI 布局（截图确认，Standard tier）：**

```
Region: [East US v]    Tier: [Standard v]
─────────────────────────────────────────────────────
Messaging operations
  Base charge:          [730] [Hours v] × $0.013/hr              = $9.81
  Operations per month: [0] x 1 million operations               = $0.00

Brokered Connections
  Connections per month: [0] Brokered Connections                = $0.00

Hybrid Connections
  Connection Charge:    [0] Listeners × $9.78 Per listener       = $0.00
  Data Transfer Overage:
    ⓘ Each listener connection includes 5 GB of data transfer.
                        [0] Overage GB × $1.00 Per overage GB    = $0.00

WCF Relays
  Relay hours:          [0] x 100 relay hours × $0.10 Per 100h   = $0.00
  Messages:             [0] x 10,000 messages × $0.01 Per 10K   = $0.00
```

**UI vs API 关键差异：**
1. **Base charge 用小时费率**：UI 用 $0.013/hr × 730h = $9.81，而非 API 的 $10/month 固定行。`$0.013` 是 `$0.013441` 的展示舍入，计算用完整精度
2. **Hybrid listener 也转为月价**：$0.0134/hr × 730h = $9.78/listener/month
3. **免费额度用文字提示**：Data Transfer 的 5GB 免费额度不通过阶梯价展示，而是用 info 文字说明
4. **Standard 包含 Hybrid/WCF**：虽然 API 是不同 skuName，UI 将它们作为 Standard tier 的 sub-sections 展示

**配置要点：**
- `sku_groups`: 将 Standard + Hybrid Connections + WCF Relay + Geo Replication 合并为 "Standard" 逻辑 Tier
- `meter_labels`: API meterName → UI 显示名映射（如 "Standard Base Unit" → "Base charge"）
- 小时费率 → 月价转换：部分 meter 用 `unitOfMeasure = "1/Hour"` 但 UI 展示月费
- 免费层用 info 提示文字而非阶梯价格展示

### 3.2 Azure Firewall ✅

```
serviceName = "Azure Firewall"
serviceFamily = "Networking"
productName = "Azure Firewall"（唯一）
armRegionName = 需要 region 筛选
总行数（eastus）= 16
type = Consumption only
```

**完整 API 数据表（eastus, 16 rows）：**

| skuName | meterName | unitOfMeasure | retailPrice |
|---------|-----------|---------------|-------------|
| Basic | Basic Deployment | 1 Hour | $0.395 |
| Basic | Basic Data Processed | 1 GB | $0.065 |
| Basic Secured Virtual Hub | Basic Secured Virtual Hub Deployment | 1 Hour | $0.395 |
| Basic Secured Virtual Hub | Basic Secured Virtual Hub Data Processed | 1 GB | $0.065 |
| Standard | Standard Deployment | 1 Hour | $1.25 |
| Standard | Standard Data Processed | 1 GB | $0.016 |
| Standard | Standard Capacity Unit | 1 Hour | $0.07 |
| Standard Secure Virtual Hub | Standard Secure Virtual Hub Deployment | 1 Hour | $1.25 |
| Standard Secure Virtual Hub | Standard Secure Virtual Hub Data Processed | 1 GB | $0.016 |
| Standard Secure Virtual Hub | Standard Secure Virtual Hub Capacity Unit | 1 Hour | $0.07 |
| Premium | Premium Deployment | 1 Hour | $1.75 |
| Premium | Premium Data Processed | 1 GB | $0.016 |
| Premium | Premium Capacity Unit | 1 Hour | $0.11 |
| Premium Secured Virtual Hub | Premium Secured Virtual Hub Deployment | 1 Hour | $1.75 |
| Premium Secured Virtual Hub | Premium Secured Virtual Hub Data Processed | 1 GB | $0.016 |
| Premium Secured Virtual Hub | Premium Secured Virtual Hub Capacity Unit | 1 Hour | $0.11 |

**关键发现：**

1. **API 6 个 skuName = 3 Tier × 2 Deployment，但 UI 只展示 3 个 Tier**：
   - API: Basic / Basic Secured Virtual Hub / Standard / Standard Secure Virtual Hub / Premium / Premium Secured Virtual Hub
   - **UI: 只有 Basic / Standard / Premium 三个 Tier 选项**（无 Deployment 维度）
   - Hub 变体在 UI 中被完全过滤掉——JSON 配置中应有 `sku_filter` 排除含 "Virtual Hub" / "Secure" 的 skuName
2. **Tier 决定 meter 数量**：
   - Basic: 2 个 meter（Deployment + Data Processed）
   - Standard: 3 个 meter（+ Capacity Unit）
   - Premium: 3 个 meter（+ Capacity Unit）
3. **VNet vs Hub 价格完全相同**：证实了 UI 过滤 Hub 的合理性——两者价格一模一样，展示 Hub 只会增加复杂度
4. **无阶梯定价**：全部 `tierMinimumUnits = 0`，每个 meter 只有 1 个价格行
5. **混合 unit**：`1 Hour`（Deployment + Capacity Unit）+ `1 GB`（Data Processed）
6. **isPrimaryMeterRegion 特殊**：eastus 全部 `isPrimaryMeterRegion=false`，primary 分散在其他区域。查询时需忽略此字段。

**UI 布局（截图确认，Standard tier）：**

```
Region: [West US v]    Tier: [Standard v]
─────────────────────────────────────────────────────
Firewall Deployment
  [1] Logical firewall units × [730] [Hours v] × $1.25     = $912.50
      Per hour per logical firewall unit

Data processed
  [100] [GB v]                                               = $1.60
```

**UI vs API 关键差异：**
1. **只展示 2 个 meter**：Standard 在 API 有 3 个 meter（Deployment + Data + Capacity Unit），但 UI 隐藏了 Capacity Unit。Capacity Unit 在所有 Tier 中都不展示
2. **Deployment 使用 Pattern A 风格**：`units × hours × $/hr` 布局（与 Pattern A 的 instances × hours 相同）
3. **Hub 变体完全不展示**：UI 只有 Basic/Standard/Premium 三个选项

**实际展示的 meter 矩阵（截图确认）：**

| Tier | Deployment (units×hours×$/hr) | Data Processed (GB) | Capacity Unit |
|------|-------------------------------|---------------------|---------------|
| Basic | ✅ $0.395/hr | ✅ $0.065/GB | ❌ 无此 meter |
| Standard | ✅ $1.25/hr | ✅ $0.016/GB | ❌ API 有但 UI 隐藏 |
| Premium | ✅ $1.75/hr | ✅ $0.016/GB | ❌ API 有但 UI 隐藏 |

**配置要点：**
- `sku_filter`: 排除含 "Secured Virtual Hub" / "Secure Virtual Hub" 的 skuName
- `hidden_meters`: 隐藏 "Capacity Unit" meter（Standard/Premium 的 Capacity Unit 存在于 API 但 UI 不展示）
- Deployment meter 使用 Pattern A 风格布局（units × hours × price），而非普通 per_meter 的单输入框

### 3.3 Event Grid ✅

```
serviceName = "Event Grid"
serviceFamily = "Internet of Things"  ← 注意不是 Integration
productName = "Event Grid"（唯一）
armRegionName = 需要 region 筛选
总行数（eastus）= 7
type = Consumption only
```

**完整 API 数据表（eastus, 7 rows）：**

| skuName | meterName | unitOfMeasure | retailPrice | tierMinimumUnits |
|---------|-----------|---------------|-------------|------------------|
| Standard | Standard Event Operations | 1M | $0.0 | 0 |
| Standard | Standard Event Operations | 1M | $0.6 | 1 |
| Standard | Standard MQTT Operations | 1M | $0.0 | 0 |
| Standard | Standard MQTT Operations | 1M | $1.0 | 1 |
| Standard | Standard Operations | 100K | $0.0 | 0 |
| Standard | Standard Operations | 100K | $0.06 | 1 |
| Standard | Standard Throughput Unit | 1 Hour | $0.04 | 0 |

**关键发现：**

1. **API 只有单一 skuName="Standard"，但 UI 有 Basic/Standard 虚拟 Tier**：
   - 全部 412 行（所有 region）的 `skuName` 都是 `"Standard"`——API 不存在 "Basic"
   - **UI 的 Basic/Standard Tier 是配置创造的虚拟分层**，通过配置决定每个 Tier 展示哪些 meter
2. **"Standard Operations" 属于 Basic Tier**：
   - 用户从 UI 确认：`"Standard Operations"` (100K, $0.06) 在 UI 中显示为 Basic Tier 的 meter
   - `"Standard Event Operations"` (1M, $0.60) 也应属于 Basic Tier 范围
   - MQTT Operations 和 Throughput Unit 可能是 Standard Tier 专有 meter
3. **3 个 meter 有免费层**：Event Operations / MQTT Operations / Operations 都是 tier=0 免费 + tier=1 开始收费
4. **3 种 unitOfMeasure**：`1M` / `100K` / `1 Hour`

**UI 布局（截图确认，Standard tier）：**

```
Region: [East US v]    Tier: [Standard v]
─────────────────────────────────────────────────────
Standard - Event Grid Namespace

Throughput
  [1] Throughput Units × [0] [Hours v] × $0.040           = $0.00
      Per Throughput Unit Hour

Event Operations
  ⓘ The first 1 million event operations per month are included.
  [0] X1 million Event Operations                          = $0.00

MQTT Operations
  ⓘ The first 1 million MQTT operations per month are included.
  [0] X1 million MQTT Operations                           = $0.00
```

**UI vs API 关键差异：**
1. **Standard 展示 3 个 meter**（不是 4 个）：Throughput + Event Operations + MQTT Operations
2. **"Standard Operations" ($0.06/100K) 不在 Standard tier 中**——确认属于 Basic tier
3. **标题 "Standard - Event Grid Namespace"**：暗示 Standard 是 Namespace 功能（MQTT + Throughput），Basic 是传统事件路由
4. **Throughput 使用 Pattern A 风格**：`units × hours × $/hr`（与 Firewall Deployment 相同）
5. **免费层用 info 文字提示**：与 Service Bus 一致，不直接展示阶梯价格

**UI Tier → API Meter 映射（截图确认 Standard，Basic 推断）：**

| UI Tier | 展示的 Meter | API meterName |
|---------|-------------|---------------|
| Basic | Event Operations | Standard Event Operations |
| Basic | Operations | Standard Operations |
| Standard | Throughput | Standard Throughput Unit |
| Standard | Event Operations | Standard Event Operations |
| Standard | MQTT Operations | Standard MQTT Operations |

**⚠️ Pattern B 最重要的发现之一**：API 的 skuName 不一定对应 UI Tier。Event Grid API 全部是 `skuName="Standard"`，但 UI 创建了 Basic/Standard 虚拟 Tier，由配置决定每个 Tier 展示哪些 meter：

```json
{
  "virtual_tiers": {
    "Basic": { "meters": ["Standard Event Operations", "Standard Operations"] },
    "Standard": { "meters": ["Standard Throughput Unit", "Standard Event Operations", "Standard MQTT Operations"] }
  }
}
```

**配置要点：**
- `virtual_tiers`: API 无 Tier 区分，由配置定义虚拟 Tier 及其 meter 集合
- `hidden_dimensions`: 隐藏 productName 和 skuName（都是唯一值）
- 免费层用 info 提示文字展示
- Throughput meter 使用 instances×hours 布局（跨 Pattern 复用）

### 3.4 Traffic Manager ✅

```
serviceName = "Traffic Manager"
serviceFamily = "Networking"
productName = "Traffic Manager"（唯一）
armRegionName = 全局服务，不按 region 筛选！
总行数（全部）= 67, isPrimaryMeterRegion=true: 35
type = Consumption only
```

**⚠️ 特殊：全局服务 + 分区定价 + Region 选择器**

Traffic Manager 使用 **分区定价**（Zone-based pricing），与其他按标准 ARM region 定价的产品不同：
- API `armRegionName` = `"Global"` / `"Delos"` / `"US Gov"`（定价区域，非标准 ARM region）
- 同一 meterName 在不同定价区域有不同价格
- API 查询 `armRegionName eq 'eastus'` 返回 0 行——因为不使用标准 region
- **但 UI 有 Region 选择器**（用户确认），Calculator 将标准 Azure region 映射到定价区域后取对应价格

**5 个 skuName 的逻辑分类：**

| skuName | 逻辑类别 | 含义 |
|---------|---------|------|
| Azure Endpoint | Endpoint Health Check | Azure 内部端点的健康检查费 |
| Non-Azure Endpoint | Endpoint Health Check | 外部端点的健康检查费（更贵） |
| Azure Region | DNS + RUM | Azure 区域的 DNS 查询 + Real User Measurements |
| Non-Azure Region | DNS + RUM | 外部区域的 RUM |
| Traffic View | 增值功能 | Traffic View 数据分析 |

**Meter 结构（isPrimaryMeterRegion=true, 按 skuName 分组）：**

| skuName | meterName | unit | 价格范围（多定价区域） |
|---------|-----------|------|---------------------|
| Azure Endpoint | Health Checks | 1 | $0.01 ~ $0.45 |
| Azure Endpoint | Fast Interval HC Add-ons | 1 | $0.01 ~ $1.25 |
| Azure Region | DNS Queries | 1M | $0.01 ~ $0.675（+ tier=1000 阶梯） |
| Azure Region | Real User Measurements | 1M | $0.0 ~ $0.01 |
| Non-Azure Endpoint | Health Checks | 1 | $0.01 ~ $0.675 |
| Non-Azure Endpoint | Fast Interval HC Add-ons | 1 | $0.01 ~ $2.5 |
| Non-Azure Region | Real User Measurements | 1M | $0.0 ~ $0.01 |
| Traffic View | Data Points Processed | 1M | $0.01 ~ $2.2 |

**关键发现：**

1. **分区定价 = 按地理区域收费不同**：DNS Queries 有 Zone 1/2/3 等不同费率。armRegionName 中 "Global" = Zone 1，"Delos" = Zone 2 等。
2. **DNS Queries 有阶梯定价**：tier=0 和 tier=1000（前 10 亿次查询 vs 超过 10 亿次）
3. **端点按个数收费，不按用量**：unitOfMeasure = "1"（每个端点/月），不是按操作次数
4. **Azure vs Non-Azure 端点价格差异大**：Non-Azure 端点健康检查费约为 Azure 端点的 1.5-2 倍
5. **Real User Measurements 大部分免费**：多数定价区域 $0.0

**UI 布局（截图确认）：**

```
Region: [East US v]    （无 Tier 选择器）
─────────────────────────────────────────────────────
DNS Queries
  [0] Million/month                                        = $0.00

Health Checks
  Azure
    [0] Endpoints × $0.36 Per month                        = $0.00
  Fast Interval Health Checks Add-on (Azure)
    [0] Endpoints × $1.00 Per month                        = $0.00
    ⓘ Fast endpoint health checks need to be purchased as an add-on...
  External
    [0] Endpoints × $0.54 Per month                        = $0.00
  Fast Interval Health Checks Add-on (External)
    [0] Endpoints × $2.00 Per month                        = $0.00
    ⓘ Fast endpoint health checks need to be purchased as an add-on...

Real User Measurements ⓘ
  [0] Million measurements × $0.00 Per month               = $0.00

Traffic View
  [0] Million data points processed × $2.00 Per month      = $0.00
```

**UI vs API 关键差异：**
1. **有 Region 选择器**：East US 选中，价格与 API `armRegionName="Global"` 数据完全匹配（$0.36, $0.54, $1.00, $2.00）。说明 East US 映射到 Global 定价区域
2. **UI 标签与 API meterName 差异大**：
   - API `"Non-Azure Endpoint Health Checks"` → UI **"External"**（不叫 "Non-Azure"）
   - API `"Azure Endpoint Fast Interval Health Check Add-ons"` → UI **"Fast Interval Health Checks Add-on (Azure)"**
3. **DNS Queries 不显示单价**：因为有阶梯定价（$0.54/1M 前 1B，$0.375/1M 超过 1B），UI 只显示输入框，价格在计算后展示
4. **健康检查按组织结构分组**：Azure 和 External 各自包含 基础 + Fast Interval Add-on，层级清晰
5. **7 个独立输入框**：DNS Queries / Azure HC / Azure Fast HC / External HC / External Fast HC / RUM / Traffic View

**配置要点：**
- **Region → Zone 映射**：East US → Global zone 价格。需要 `region_to_zone` 映射表
- `meter_labels`: 大量重命名（API "Non-Azure" → UI "External"）
- `meter_order`: UI 按逻辑分组（DNS → Health Checks Azure/External → RUM → Traffic View）
- `hidden_dimensions`: 隐藏 productName（唯一值）
- `meter_groups`: Health Checks 下有 Azure/External 分组，可能需要 meter 分组配置

### 3.5 Notification Hubs ✅

```
serviceName = "Notification Hubs"
serviceFamily = "Mobile"
productName = "Notification Hubs"（唯一）
armRegionName = 需要 region 筛选
总行数（eastus）= 11
type = Consumption only
```

**完整 API 数据表（eastus, 11 rows）：**

| skuName | meterName | unitOfMeasure | retailPrice | tierMinimumUnits |
|---------|-----------|---------------|-------------|------------------|
| Free | Free Unit | 1/Month | $0.0 | 0 |
| Basic | Basic Unit | 1/Month | $10.0 | 0 |
| Basic | Basic Pushes | 1M | $0.0 | 0 |
| Basic | Basic Pushes | 1M | $1.0 | 10 |
| Standard | Standard Unit | 1/Month | $200.0 | 0 |
| Standard | Standard Pushes | 1M | $0.0 | 0 |
| Standard | Standard Pushes | 1M | $10.0 | 10 |
| Standard | Standard Pushes | 1M | $2.5 | 100 |
| 1P Direct Send | 1P Direct Send Pushes | 1M | $0.36 | 0 |
| Availability Zones SKU | Availability Zones Unit | 1/Month | $350.0 | 0 |
| Private Link | Private Link Unit | 1/Month | $35.0 | 0 |

**关键发现：**

1. **API 有 6 个 skuName，但 UI 只展示 3 个 Tier (Free/Basic/Standard)**：
   - UI 展示：Free / Basic ($10/月) / Standard ($200/月)——只有 Pushes 阶梯定价
   - **UI 不展示的附加 SKU**：1P Direct Send / Availability Zones SKU / Private Link
   - 这些附加 SKU 存在于 API 但被 Calculator UI 过滤掉了
2. **每个 Tier = 固定月费 (Unit) + 按量推送费 (Pushes)**：
   - Free: $0/月（含 1M pushes / 500 devices）
   - Basic: $10/月 + Pushes（前 10M 免费 → $1/1M）
   - Standard: $200/月 + Pushes（前 10M 免费 → 10-100M $10/1M → 100M+ $2.5/1M）
3. **免费层 + 阶梯定价**：Basic 有 2 级阶梯，Standard 有 3 级阶梯

**UI 布局（截图确认，Standard tier）：**

```
Region: [East US v]    Tier: [Standard v]
─────────────────────────────────────────────────────
ⓘ The first 10 million pushes are included for 10,000,000
  active devices and unlimited broadcast (tag size).

Additional pushes
  [1] Millions + $200.00 Per month                         = $200.00
```

**UI vs API 关键差异：**
1. **极简单行布局**：Pushes 和月费合并为一行 `[pushes] Millions + $200/month = total`
2. **月费不是独立行**：$200.00 不是单独的 "Namespace charge" 行，而是作为 Pushes 行的常数加项展示
3. **免费额度用 info 文字**："The first 10 million pushes are included for 10,000,000 active devices..."
4. **附加 SKU 完全不出现**：UI 只有 Free/Basic/Standard 三个 Tier

**各 Tier 的 UI 展示：**

| Tier | 月费（加项） | Pushes 输入 | 免费额度 |
|------|-------------|------------|---------|
| Free | $0 | 无输入框 | 1M pushes / 500 devices |
| Basic | + $10.00/month | [N] Millions | 前 10M 免费, $1/1M |
| Standard | + $200.00/month | [N] Millions | 前 10M 免费, 阶梯: 10-100M $10/1M, 100M+ $2.5/1M |

**API 中存在但 UI 不展示的 SKU（3 个）：**

| skuName | 说明 | 月费 |
|---------|------|------|
| 1P Direct Send | 独立推送渠道 | $0.36/1M pushes |
| Availability Zones SKU | 区域冗余 | $350/month |
| Private Link | 私有链接 | $35/month |

**配置要点：**
- `sku_filter`: 过滤只展示 Free/Basic/Standard，排除附加 SKU
- **Pushes + 月费合并展示**：`[pushes] + $X/month = total`——这是一种特殊的 meter 渲染模式，固定月费作为常数加项，而非独立 meter 行
- 免费层用 info 提示文字展示（"The first 10 million pushes are included..."）
- 阶梯定价由 `calculateTieredCost()` 处理

### Pattern B 五产品对比表

| 对比维度 | Service Bus | Azure Firewall | Event Grid | Traffic Manager | Notification Hubs |
|---------|-------------|----------------|------------|-----------------|-------------------|
| **serviceName** | `Service Bus` | `Azure Firewall` | `Event Grid` | `Traffic Manager` | `Notification Hubs` |
| **serviceFamily** | Integration | Networking | IoT | Networking | Mobile |
| **productName 数** | 1 | 1 | 1 | 1 | 1 |
| **skuName 数** | 6 | 6 | 1 | 5 | 6 |
| **逻辑 Tier 数** | 3 (Basic/Std/Prem) | 3 (Basic/Std/Prem) | 无 | 无 | 3 (Free/Basic/Std) |
| **总行数 (eastus)** | 18 | 16 | 7 | 67 (全局) | 11 |
| **unitOfMeasure 种类** | 8 种 | 2 种 | 3 种 | 2 种 | 2 种 |
| **阶梯定价** | ✅ 多级 | ❌ | ✅ 免费+收费 | ✅ DNS 二级 | ✅ 免费+多级 |
| **免费层** | ✅ Std meters | ❌ | ✅ 3/4 meters | ❌ | ✅ Free Tier + 推送免费额度 |
| **RI/SP** | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Region 筛选** | ✅ | ✅ | ✅ | ❌ 全局 | ✅ |
| **子维度** | SKU→逻辑Tier | sku_filter 过滤Hub | virtual_tiers | Region→Zone映射 | sku_filter 过滤附加SKU |
| **固定月费** | Std Base Unit $10 | ❌（按小时） | ❌ | ❌ | ✅ Unit meter |
| **UI vs API 差异** | sku_groups 合并 | 过滤 Hub 变体 | 虚拟 Tier (API无Basic) | Region映射Zone | 隐藏 3 个附加 SKU |
| **配置复杂度** | 高（sku_groups+阶梯） | 中（sku_filter+meter数变化） | 中（virtual_tiers） | 中（zone映射+分区定价） | 中（sku_filter+阶梯） |

### Pattern B 配置要素总结

| 配置项 | 说明 | 使用产品 |
|--------|------|---------|
| `sku_groups` | 合并多个 API skuName 为逻辑 Tier | Service Bus |
| `sku_filter` | 过滤掉不展示的 skuName（UI ⊂ API） | Firewall (过滤Hub), Notification Hubs (过滤附加SKU) |
| `virtual_tiers` | 在 API 无 Tier 区分时，由配置定义虚拟 Tier 及其 meter 集合 | Event Grid (API全为Standard，UI分Basic/Standard) |
| `meter_labels` | 自定义 meter 显示名 | Service Bus, Firewall, Traffic Manager |
| `meter_order` | 控制 meter 排序 | 所有 per_meter 产品 |
| `hidden_meters` | 隐藏不需展示的 meter | Firewall (Capacity Unit) |
| `hidden_dimensions` | 隐藏单值维度 | Event Grid (productName+skuName), Traffic Manager (productName) |
| `meter_free_quota` | 跨 meter 免费额度 | SignalR (Message 免费额度按 Unit 计) |
| `region_to_zone` | 将标准 Azure region 映射为定价区域 | Traffic Manager (eastus→Global/Zone1) |
| `tier_meter_count` | 不同 Tier 下 meter 数量不同 | Firewall (Basic=2, Std/Prem=3), Event Grid (Basic=2, Std=4) |

### Pattern B 关键设计要点

1. **UI = API 数据的配置化子集**（本次最重要发现）：
   - Firewall: 过滤 Hub 变体 + 隐藏 Capacity Unit meter → `sku_filter` + `hidden_meters`
   - Event Grid: 创建虚拟 Tier → `virtual_tiers`
   - Notification Hubs: 隐藏附加 SKU → `sku_filter`
   - Traffic Manager: Region → Zone 映射 → `region_to_zone`
   - **设计影响**：JSON 配置不仅控制"怎么展示"，还控制"展示 API 数据的哪个子集"

2. **Meter 渲染模式多样化**（截图确认的 3 种模式）：
   - **`quantity × price`**：最常见，输入用量 × 单价 = 费用（Service Bus Operations, Traffic Manager Health Checks）
   - **`units × hours × price`**：Pattern A 风格，实例 × 时长 × 单价（Firewall Deployment, Event Grid Throughput）
   - **`quantity + monthly_fee`**：用量费 + 固定月费合并一行（Notification Hubs: `[pushes] + $200/month`）

3. **固定月费展示方式**：不是独立行，而是合并到 Pushes 行的常数加项（Notification Hubs），或通过 hourly×730 展示（Service Bus Base charge $0.013×730=$9.81）

4. **免费层统一用 info 提示文字**：所有产品的免费额度都用 ⓘ 文字说明（"The first X included..."），而非直接展示阶梯价格表

5. **Tier 改变 meter 集合**：Firewall Basic 2 meter / Standard 2 meter (隐藏 CU)；Event Grid Basic 2 meter / Standard 3 meter

6. **分区定价（Zone-based pricing）**：Traffic Manager UI 有 Region 选择器（East US），价格与 API Global zone 完全匹配。说明 East US 映射到 Global 定价区域

7. **附加 SKU = 不展示**：Notification Hubs 的附加 SKU 在 Calculator UI 中完全不出现，直接被过滤

8. **API meterName → UI 标签差异显著**：Traffic Manager "Non-Azure" → UI "External"；Service Bus "Standard Base Unit" → UI "Base charge"。`meter_labels` 配置必不可少

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
