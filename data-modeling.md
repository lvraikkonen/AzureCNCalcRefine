# 级联筛选算法与数据建模

> 本文档是 Azure.cn Pricing Calculator 的核心设计文档，覆盖级联筛选算法、数据结构分析、索引策略，以及与 Azure 国际版的对比。
> 所有数据示例均来自实际 CSV 数据 (`sample-data/AzureRetailPrices.csv`, 46,877 行) 和 Azure 国际版 Retail Prices API。

---

## 一、问题定义：什么是级联筛选？

Azure Pricing Calculator 的核心交互是：用户选择一个服务（如 Virtual Machines），然后通过多个下拉框逐步配置出一个具体的产品规格，最终获得价格。

这些下拉框之间不是独立的——选了 Region 之后，Product 列表会缩小；选了 Product 之后，SKU 列表会缩小。这就是**级联筛选**。

但这里有个关键设计决策：**不是简单的自上而下单向级联，而是双向约束**。

---

## 二、数据结构：一行 CSV 代表什么？

CSV 有 46,877 行，每行代表一个**定价记录**（pricing record）。一行的核心维度：

```
serviceName → armRegionName → productName → skuName → type → term → meterName → tierMinimumUnits → unitPrice
```

**一行的语义**：在某个区域(region)，某个产品系列(product)的某个规格(sku)，按某种计费模式(type)和承诺期(term)，某个计量维度(meter)在某个用量阈值(tier)的单价。

### 全局维度基数

| 维度 | 唯一值数量 |
|------|-----------|
| serviceName | 105 |
| armRegionName | 11 (6 实际 + 5 逻辑) |
| productName | 787 |
| skuName | 2,485 |
| type | 4 |
| term | 2 |
| meterName | 3,602 |

### 用实际数据说明

**Virtual Machines D2 v3 在 chinaeast2 的全部 5 行**：

| type | term | unitPrice (CNY) | meter | 含义 |
|------|------|-----------------|-------|------|
| Consumption | (空) | 0.678302 | D2 v3/D2s v3 | 按需付费，0.68元/小时 |
| SavingsPlanConsumption | 1 Year | 0.515510 | D2 v3/D2s v3 | 1年节省计划，0.52元/小时 |
| SavingsPlanConsumption | 3 Years | 0.373066 | D2 v3/D2s v3 | 3年节省计划，0.37元/小时 |
| Reservation | 1 Year | 1624.528302 | D2 v3/D2s v3 | 1年预留，1624.53元（**总价**不是小时价） |
| Reservation | 3 Years | 2801.886792 | D2 v3/D2s v3 | 3年预留，2801.89元总价 |

同一台虚拟机，因为 type 和 term 不同，产生了 5 行不同价格。

---

## 三、级联筛选的五个维度

维度定义及顺序：

```
1. arm_region_name  — 区域（chinaeast2, chinanorth3 等）
2. product_name     — 产品系列（Virtual Machines Dv3 Series, Lasv3 Series Linux 等）
3. sku_name         — 规格/尺寸（D2 v3, D4 v3, D8 v3 等）
4. type             — 计费模式（Consumption, Reservation, SavingsPlanConsumption）
5. term             — 承诺期（1 Year, 3 Years）— 仅 Reservation/SavingsPlan 可见
```

### 为什么是这个顺序？

对应用户的思考路径：先选机房在哪 → 再选什么系列的产品 → 选具体规格大小 → 选怎么付费 → 选承诺多久。

但**这个顺序不是硬性的**——用户完全可以先选 type=Reservation，再选 region。算法必须处理任意选择顺序。

---

## 四、核心算法：双向约束筛选

### 算法伪代码

```
输入: service_name, selections = {field: value, ...}
输出: 每个维度的 {field, options[], selected, visible}

base = WHERE service_name = :sn
       AND is_primary_meter_region = TRUE
       AND type != 'DevTestConsumption'

对于每个维度 D ∈ [region, product, sku, type, term]:
    query = base
    对于每个 OTHER 已选维度 D' (D' != D 且 D' 在 selections 中):
        query = query AND D' = selections[D']
    D.options = SELECT DISTINCT D FROM query ORDER BY D
```

**关键点：计算某个维度的选项时，应用所有"其他"已选维度的过滤，但不过滤自己。**

### 为什么不过滤自己？

如果计算 region 的选项时也过滤 `region = 'chinaeast2'`，那 region 下拉框就只剩 chinaeast2 一个选项了——用户无法切换到其他区域。

不过滤自己，意味着：当前已选了 chinaeast2，但 region 下拉框仍然显示所有与"其他已选维度"兼容的区域，用户可以自由切换。

---

## 五、Azure 国际版 Pricing Calculator 的真实交互流程

> 以下基于 Azure 国际版 Pricing Calculator (https://azure.microsoft.com/en-us/pricing/calculator/)
> 的实际页面交互和 Azure Retail Prices API (https://prices.azure.com) 的真实数据。

### 5.1 国际版的维度比中国区多

Azure 国际版 Pricing Calculator 中，配置一台 VM 的下拉框顺序：

```
+-- Virtual Machines ----------------------------------------- $xxx.xx --+
|                                                                         |
|  REGION:           [v East US                      ]                    |
|  OPERATING SYSTEM: [v Linux                        ]                    |
|  TYPE:             [v OS Only                      ]                    |
|  TIER:             [v Standard                     ]                    |
|  CATEGORY:         [v General Purpose              ]                    |
|  INSTANCE SERIES:  [v Dv3                          ]                    |
|  INSTANCE:         [v D2 v3: 2 vCPU, 8GB RAM      ]                    |
|                                                                         |
|  SAVINGS OPTIONS:  [v Pay as you go                ]                    |
|                     * Pay as you go                                     |
|                     * 1 year reserved                                   |
|                     * 3 year reserved                                   |
|                     * 1 year savings plan                               |
|                     * 3 year savings plan                               |
|                                                                         |
|  Virtual machines:  [2]  x  [730] hours                                 |
|                                                                         |
|  MANAGED DISKS:    [v S4: 32 GiB, 500 IOPS        ]                    |
|  STORAGE:          [1] managed disk(s)                                  |
|                                                                         |
|  BANDWIDTH:        Inbound [5] GB  /  Outbound [5] GB                  |
|                                                                         |
|                              Estimated monthly cost: $xx.xx             |
+-------------------------------------------------------------------------+
```

**对比中国区的 5 个维度**：

| 国际版维度 | 中国区对应 | 说明 |
|-----------|-----------|------|
| REGION | arm_region_name | 直接对应 |
| OPERATING SYSTEM | 编码在 product_name 中 | 国际版: "Dv3 Series" vs "Dv3 Series Windows"；中国区: product_name 本身就区分 Linux/Windows |
| TYPE | 无（中国区数据无此维度） | "OS Only" vs "OS + Software Bundle"，中国区暂不需要 |
| TIER | 编码在 sku_name 中 | Standard/Basic/Low Priority/Spot 等，中国区体现在 skuName（如 "D2 v3" vs "D2 v3 Low Priority"） |
| CATEGORY | 不需要独立维度 | General Purpose/Compute Optimized 等，中国区产品量少，不需要这层聚合 |
| INSTANCE SERIES | product_name | 直接对应（如 "Virtual Machines Dv3 Series"） |
| INSTANCE | sku_name | 直接对应（如 "D2 v3"） |
| SAVINGS OPTIONS | type + term | 对应 Consumption/Reservation/SavingsPlan + 1 Year/3 Years |

**关键区别**：国际版有 7-8 个筛选维度，中国区合并为 5 个——因为 OS、Tier、Category 这些信息在中国区数据中已经编码在 product_name 和 sku_name 里了。

### 5.2 用国际版 API 真实数据走一遍 Virtual Machines

以下用 `https://prices.azure.com/api/retail/prices` 返回的真实数据。

#### Step 0：用户在 Calculator 中点击 "Virtual Machines"

页面在 "Your Estimate" 区域添加了一个 VM 配置卡片，所有下拉框加载默认选项。

API 角度：前端需要获取每个维度的初始可选值。等同于我们的 `POST /configurations` with `selections = {}`。

#### Step 1：用户选择 Region = East US, OS = Linux

此时 API 数据中的 productName 决定了 OS。国际版 API 的关键数据结构：

```
productName = "Virtual Machines Dv3 Series"          <-- Linux
productName = "Virtual Machines Dv3 Series Windows"   <-- Windows
```

选 Linux 后，筛选条件变为 `productName NOT LIKE '%Windows%'`（简化表达）。

在 East US + Linux + Consumption (pay-as-you-go) 下，Dv3 Series 的全部 SKU：

| Instance (skuName) | vCPU | RAM | Price/Hour (USD) |
|---------------------|------|-----|------------------|
| D2 v3 | 2 | 8 GB | $0.096 |
| D4 v3 | 4 | 16 GB | $0.192 |
| D8 v3 | 8 | 32 GB | $0.384 |
| D16 v3 | 16 | 64 GB | $0.768 |
| D32 v3 | 32 | 128 GB | $1.536 |
| D48 v3 | 48 | 192 GB | $2.304 |
| D64 v3 | 64 | 256 GB | $3.072 |

加上 Low Priority 和 Spot 变体，实际有 **21 个 SKU**：

| 类别 | 价格示例 (D2 v3) | 说明 |
|------|------------------|------|
| Standard | $0.096/hr | 正常按需 |
| Low Priority | $0.019/hr | 可被抢占的低价实例 |
| Spot | $0.018/hr | 竞价实例，价格浮动 |

#### Step 2：用户选择 Instance = D2 v3

现在配置已确定为 East US + Linux + D2 v3。用户可以选择 Savings Options。

API 返回 D2 v3 在 eastus 的**全部 5 行价格数据**（真实 API 数据）：

| productName | type | term | unitPrice (USD) |
|---|---|---|---|
| VM Dv3 Series (Linux) | Consumption | — | $0.096/hr |
| VM Dv3 Series (Linux) | Reservation | 1 Year | $501.00 (总价) |
| VM Dv3 Series (Linux) | Reservation | 3 Years | $968.00 (总价) |
| VM Dv3 Series Windows | Consumption | — | $0.188/hr |
| VM Dv3 Series Windows | DevTestConsumption | — | $0.096/hr |

**注意看**：
- Linux 版有 Consumption + 2 种 Reservation = 3 行
- Windows 版有 Consumption + DevTest = 2 行
- Windows DevTest 价格 = Linux 价格（$0.096），因为 DevTest 免 Windows 许可费
- Windows Consumption 几乎是 Linux 的 2 倍（$0.188 vs $0.096）

#### Step 3：用户选择 Savings Options = 1 Year Reserved

API 层的匹配：`type='Reservation' AND term='1 Year'` -> unitPrice = $501.00

这个 $501.00 是**1 年期的预付总价**，计算器会转换为月度展示：

```
月度估算: $501.00 / 12 = $41.75/月
vs 按需:  $0.096 x 730 = $70.08/月
节省:     40%
```

页面最终展示：

```
+-- Virtual Machines ---------------------- $41.75/month --+
|  REGION:           East US                                |
|  OPERATING SYSTEM: Linux                                  |
|  INSTANCE SERIES:  Dv3                                    |
|  INSTANCE:         D2 v3 (2 vCPU, 8 GB RAM)              |
|  SAVINGS OPTIONS:  1 year reserved                        |
|                                                           |
|  [1] VM  x  [730] hours                                   |
|                                                           |
|  Compute:    $41.75/mo (reserved)                         |
|  OS Disk:    $1.54/mo  (S4 32GB)                          |
|  Bandwidth:  $0.44/mo  (5GB out)                          |
|  ----------------------------------------                 |
|  Total:      $43.73/month                                 |
+-----------------------------------------------------------+
```

### 5.3 级联效果的真实场景演示

#### 场景 A：改变 Region，观察 Instance 选项变化

用户把 Region 从 East US 切换到 Japan West：

```
前端发送: POST /configurations
body: {selections: {arm_region_name: "japanwest", product_name: "Virtual Machines Dv3 Series"}}

级联效果:
  - Region:   可以切换到任意区域
  - Product:  japanwest 可能不支持某些系列 -> 列表可能缩小
  - SKU:      Dv3 在 japanwest 可能只有 D2~D32（没有 D48, D64）-> 列表缩小
  - Type:     japanwest 的 Dv3 可能不支持 SavingsPlan -> 选项减少
```

#### 场景 B：改变 Savings Options，观察 Instance 选项变化

用户在已选 eastus + Dv3 的情况下，把 Savings Options 改为 "3 year reserved"：

```
级联效果:
  - 反向约束: 只有支持 Reservation 的 SKU 才保留在列表中
  - 国际版 Dv3 eastus: Standard SKU 全部支持 -> 无变化
  - 但 Low Priority / Spot SKU 不支持 Reservation -> 从列表中消失
  - SKU 从 21 个 -> 7 个 (只剩 Standard)
```

### 5.4 对比：中国区与国际版的数据差异

用同一个产品 D2 v3 对比：

| 维度 | Azure Global (eastus) | Azure.cn (chinaeast2) |
|------|----------------------|----------------------|
| Linux 按需 | $0.096/hr | 0.678 CNY/hr |
| Windows 按需 | $0.188/hr | 中国区 product 直接分开 |
| Reservation 1Y | $501.00 | 1,624.53 CNY |
| Reservation 3Y | $968.00 | 2,801.89 CNY |
| SavingsPlan 1Y | 有 | 0.516 CNY/hr |
| SavingsPlan 3Y | 有 | 0.373 CNY/hr |
| DevTest | $0.096 (= Linux) | 中国区独立 type |
| Low Priority | 有 ($0.019/hr) | 中国区无 |
| Spot | 有 ($0.018/hr) | 中国区无 |
| 可选 SKU 数 | 21 个 | 7 个 |

**中国区更简单**：没有 Low Priority/Spot，SKU 变体更少，级联维度更少。

---

## 六、Storage 的特殊场景：阶梯定价

Virtual Machines 是"一个 SKU 一个价"。但 Storage 不同——同一个 meter 有多个价格档位。

### General Block Blob v2 / Hot LRS 的实际数据

**中国区 chinaeast2**：

| meter | tierMinimumUnits | unitPrice (CNY) | unitOfMeasure |
|-------|-----------------|-----------------|---------------|
| Hot LRS Data Stored | 0 | 0.140564 | 1 GB/Month |
| Hot LRS Data Stored | 51,200 | 0.134938 | 1 GB/Month |
| Hot LRS Data Stored | 512,000 | 0.129317 | 1 GB/Month |
| Hot LRS Write Operations | 0 | 0.042453 | 10K |
| Hot Read Operations | 0 | 0.014151 | 10K |
| All Other Operations | 0 | 0.0384 | 10K |
| Hot LRS Blob Inventory | 0 | 0.0187 | 1M |
| LRS List and Create Container Ops | 0 | 0.042453 | 10K |
| Index Tags | 0 | 0.288679 | 10K/Month |

**国际版 eastus**（API 真实数据）：

| meter | tierMinimumUnits | unitPrice (USD) | unitOfMeasure |
|-------|-----------------|-----------------|---------------|
| Hot LRS Data Stored | 0 | $0.0208 | 1 GB/Month |
| Hot LRS Data Stored | 51,200 | $0.019968 | 1 GB/Month |
| Hot LRS Data Stored | 512,000 | $0.019136 | 1 GB/Month |
| Hot LRS Write Operations | 0 | $0.05 | 10K |
| Hot Read Operations | 0 | $0.004 | 10K |
| All Other Operations | 0 | $0.004 | 10K |
| Hot LRS Blob Inventory | 0 | $0.0025 | 1M |
| LRS List and Create Container Ops | 0 | $0.05 | 10K |
| Index Tags | 0 | $0.03 | 10K/Month |

### 阶梯定价含义

以中国区数据为例：
- 前 51,200 GB: 0.140564 元/GB
- 51,200 ~ 512,000 GB: 0.134938 元/GB
- 512,000 GB 以上: 0.129317 元/GB

用量 100,000 GB 的计算：
```
前 51,200 GB:               51,200 x 0.140564 = 7,196.88 元
51,200 ~ 100,000 GB:        48,800 x 0.134938 = 6,584.97 元
总计:                                           13,781.85 元
```

### 阶梯定价对级联筛选的影响

级联筛选本身不受影响——筛选只关心维度值的组合是否存在，不关心价格。阶梯定价影响的是**后续的 meters API 和 pricing/calculate API**：

- `POST /products/{service_name}/meters` 需要将同一个 meter 的多行聚合为 tiers 数组
- `POST /pricing/calculate` 需要按阶梯计算费用

---

## 七、Azure Cosmos DB 的场景

Cosmos DB 展示了另一种复杂度：**同一个 serviceName 下有非常不同的子产品**。

chinaeast2 下有 13 个 product，差异巨大：

| productName | 行数 | 说明 |
|------------|------|------|
| Azure Cosmos DB | 9 | 基础吞吐量定价（RU/s） |
| Azure Cosmos DB autoscale | 8 | 自动缩放吞吐量 |
| Azure Cosmos DB serverless | 1 | 无服务器模式 |
| Azure Cosmos DB Dedicated Gateway - General Purpose | 6 | 专用网关 GP |
| Azure Cosmos DB Dedicated Gateway - Memory Optimized | 6 | 专用网关内存优化 |
| Azure Cosmos DB - PITR | 4 | 时间点恢复 |
| Graph API - General Purpose Compute | 6 | 图数据库 GP |
| Graph API - Memory Optimized Compute | 6 | 图数据库内存优化 |

这意味着用户在 Cosmos DB 场景下，**product_name 这一层的选择至关重要**——它基本决定了后续 SKU 和 meter 的完全不同的路径。

---

## 八、数据建模深度分析

### 8.1 数据的三层结构

从实际数据分析看，CSV 数据天然形成三层结构：

```
Layer 1: Configuration（配置层）
  (service_name, arm_region_name, product_name, sku_name, type, term)
  -> 定义一个"用户可以选择的产品配置"
  -> 这是级联筛选直接操作的层面

Layer 2: Meter（计量层）
  每个 Configuration 下有 1~12 个 meter
  -> 定义"这个配置需要为哪些计量维度付费"
  -> VM: 通常 1 个 meter (计算小时)
  -> Storage: 可达 12 个 meter (数据存储、读写操作、带宽、快照等)

Layer 3: Tier（阶梯层）
  每个 Meter 下有 1~6 个 tier
  -> 定义"用量越大，单价越低"
  -> 大部分 meter 只有 1 个 tier (即 tierMinimumUnits=0)
  -> Storage 的 Data Stored 类 meter 通常有 3 个 tier
```

**实际数据验证**：

| 服务 | Config 数 | 多 Meter Config 占比 | Meter/Config 分布 |
|------|----------|--------------------|--------------------|
| Virtual Machines | 20,184 | 0% | 全部 1 meter/config |
| Storage | 1,493 | 61% | 1~12 meter/config |
| SQL Database | ~500 | 较高 | 多 meter |

这意味着：
- **VM 是最简单的情况**：一个 config = 一行数据 = 一个价格
- **Storage 是最复杂的情况**：一个 config 展开后有多个 meter，每个 meter 可能有多个 tier

### 8.2 表设计：一张宽表 vs 拆分

**方案 A（当前设计）：一张宽表 retail_prices**

所有 46,877 行平铺在一张表里。级联筛选的 DISTINCT 查询直接在这张表上跑。

优点：
- 简单直接，一张表解决所有查询
- 导入逻辑简单（CSV 直接映射）
- 级联筛选查询无需 JOIN

缺点：
- Storage 类服务，同一个 config 有 9 行（9 个 meter），做 DISTINCT sku_name 时这 9 行都参与扫描但只贡献 1 个结果
- 有信息冗余（同一个 config 的 region/product/sku 在多行重复）

**方案 B：拆分为 configurations + meters + tiers**

```sql
-- 级联筛选操作此表（无冗余行）
configurations (config_id, service_name, arm_region_name, product_name, sku_name, type, term)

-- Meter 列表查询操作此表
meters (config_id, meter_name, unit_of_measure)

-- 价格计算操作此表
tiers (meter_id, tier_min_units, unit_price, retail_price)
```

优点：
- configurations 表去重后行数显著减少（VM: 20,184 不变; Storage: 5,869 -> 1,493，减少 75%）
- 级联筛选查询扫描行数更少
- 数据模型语义更清晰

缺点：
- 导入逻辑复杂（需要去重聚合）
- Meter/价格查询需要 JOIN
- 多一层抽象

**推荐：方案 A（宽表）**

原因：
1. 总数据量只有 46,877 行，PostgreSQL 在这个量级即使全表扫描也是毫秒级
2. 级联筛选的 DISTINCT 查询本身就是去重的——多几行冗余数据只是多扫描几行，对结果无影响
3. 宽表方案的代码复杂度显著低于拆分方案
4. CSV 数据定期更新，一张宽表的 TRUNCATE + INSERT 远比维护三张表的引用完整性简单

### 8.3 自然键与唯一约束

实际数据分析发现的键结构：

```
最佳自然键: (meter_id, sku_id, arm_region_name, type, tier_min_units, term)
  -> 46,817 个唯一组合（覆盖 99.87% 的行）
  -> 60 个重复（全部是完全相同的重复行，属于 CSV 数据质量问题）
  -> 其中 56 个连 isPrimaryMeterRegion 都相同（真正的重复数据）
```

**建议**：
```sql
-- 数据导入时去重：相同自然键的行只保留一条
CREATE UNIQUE INDEX idx_rp_unique_row ON retail_prices
    (meter_id, sku_id, arm_region_name, type, tier_min_units, term)
    WHERE meter_id IS NOT NULL;
```

导入时用 `ON CONFLICT ... DO NOTHING` 或在 staging 阶段先去重。

### 8.4 索引策略深度分析

级联筛选的查询模式分析（以 VM 为例，`is_primary_meter_region=TRUE` 过滤后 16,705 行）：

| 选择状态 | 最大维度查询扫描行数 | 瓶颈 |
|---------|--------------------|----|
| 无选择 | 16,705 | 全服务扫描 |
| 选了 region | 3,282 | 按 region 过滤 |
| 选了 region+product | 35~182 | 已足够小 |
| 选了 region+product+sku | 1~5 | 精确定位 |

**关键洞察：瓶颈在前两步**（无选择和只选了一个维度时）。后续步骤数据量已经足够小。

#### 索引方案

```sql
-- 索引 1: 级联筛选主索引（Partial Index + 覆盖）
CREATE INDEX idx_rp_cascade_covering ON retail_prices
    (service_name, arm_region_name, product_name, type)
    INCLUDE (sku_name, term)
    WHERE is_primary_meter_region = TRUE AND type != 'DevTestConsumption';
```

**为什么用 Partial Index（条件索引）？**

`is_primary_meter_region = TRUE` 和 `type != 'DevTestConsumption'` 是级联筛选**每次查询都带的固定条件**。用 Partial Index：
- 索引体积减小 25%（排除了 11,578 行 isPrimary=False 和 5,546 行 DevTest）
- 查询时不需要额外过滤这两个条件，直接走索引

**为什么用 INCLUDE？**

用 `INCLUDE` 子句把 sku_name 和 term 也放入索引叶节点，实现所有 5 个 DISTINCT 查询都 Index Only Scan，无需回表。

```sql
-- 索引 2: 价格查询索引（精确匹配到具体配置后查价格）
CREATE INDEX idx_rp_price_lookup ON retail_prices
    (service_name, product_name, sku_name, arm_region_name, type, term);

-- 索引 3: 产品搜索（模糊匹配）
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_rp_product_name_trgm ON retail_prices USING gin (product_name gin_trgm_ops);
CREATE INDEX idx_rp_service_name_trgm ON retail_prices USING gin (service_name gin_trgm_ops);
```

#### 各维度查询的索引命中分析

以 `selections = {region: "chinaeast2"}` 为例：

| 查询 | WHERE 条件 | 索引使用 |
|------|-----------|---------|
| DISTINCT region | sn='VM' | idx_cascade 前缀 (sn) -> Index Only Scan |
| DISTINCT product | sn='VM' AND region='ce2' | idx_cascade 前缀 (sn, region) -> Index Only Scan |
| DISTINCT sku | sn='VM' AND region='ce2' | idx_cascade INCLUDE -> Index Only Scan |
| DISTINCT type | sn='VM' AND region='ce2' | idx_cascade (sn, region, type在索引中) -> Index Only Scan |
| DISTINCT term | sn='VM' AND region='ce2' | idx_cascade INCLUDE -> Index Only Scan |

### 8.5 is_primary_meter_region 深度分析

```
Total: 46,877 行
isPrimaryMeterRegion = True:  35,299 行 (75.3%)
isPrimaryMeterRegion = False: 11,578 行 (24.7%)
```

False 行的分布：
- 分布在**所有 6 个实际区域**，不是只在逻辑区域
- 最大的贡献者：VM (4,135 行)、Storage (1,945 行)、Azure Monitor (980 行)

**这意味着 isPrimaryMeterRegion=False 的行在同一个实际区域中也存在。** 它标记的是"非主计量区域的价格副本"，可能用于跨区域定价参考。级联筛选必须过滤掉它们，否则同一个 (service, region, product, sku, type, term) 组合会出现重复的 meter 行。

### 8.6 数据稀疏性对算法的影响

VM 数据的 (region x product) 覆盖率只有 **53.9%**：
- 理论组合：6 region x 240 product = 1,440
- 实际存在：776 种

具体差异：
- chinaeast: 38 产品（最少）
- chinanorth3: 221 产品（最多）
- 差距近 6 倍

**这证明了双向约束算法的必要性**。如果用简单的"固定选项列表"，用户在 chinaeast 选了一个只有 chinanorth3 有的产品后，会得到 0 个有效 SKU——一个死胡同。双向约束算法保证每个维度列出的选项都与其他已选维度兼容，不会出现死胡同。

### 8.7 物化视图 product_catalog

```sql
CREATE MATERIALIZED VIEW product_catalog AS
SELECT DISTINCT
    service_name,
    service_family,
    MIN(effective_start_date) AS available_since,
    array_agg(DISTINCT arm_region_name) FILTER (
        WHERE arm_region_name NOT IN ('', 'China', 'CN Zone 1', 'CN Zone 2',
                                       'Zone 1 (China)', 'Azure Stack CN')
    ) AS available_regions,
    COUNT(DISTINCT product_name) AS product_variant_count
FROM retail_prices
WHERE is_primary_meter_region = TRUE
GROUP BY service_name, service_family;
```

这个视图服务于**产品目录页面**（用户添加服务到估算之前的浏览），不参与级联筛选。它在数据导入完成后 REFRESH 一次即可。

### 8.8 空值与特殊值处理

| 字段 | 空值行数 | 占比 | 处理策略 |
|------|---------|------|---------|
| armRegionName | 3,546 | 7.6% | 空区域的行在级联筛选中不显示（无法选择"无区域"） |
| term | 32,488 | 69.3% | 空 = Consumption/DevTest，正常映射为 NULL |
| armSkuName | 15,074 | 32.2% | 非筛选维度，存储即可 |

armRegionName 为空的 3,546 行属于 **Virtual Machines Licenses**（3,477 行）等不区分区域的服务。这些服务在级联筛选中 region 维度应显示为空列表或显示"Global"。

---

## 九、性能考量与优化方向

### 9.1 当前数据量下的性能预估

46,877 行，PostgreSQL 的性能表现（有索引）：
- 单条 DISTINCT 查询：< 1ms
- 5 条级联查询合计：< 5ms
- 加上网络往返和 FastAPI 开销：< 20ms 端到端

**结论：在当前数据量下，不需要任何特殊优化。**

### 9.2 可选优化（为未来扩展预留）

**优化 1: 合并 5 条查询为 1 条**

```sql
SELECT
    json_build_object(
        'arm_region_name', (SELECT json_agg(DISTINCT arm_region_name) FROM retail_prices WHERE ...),
        'product_name',    (SELECT json_agg(DISTINCT product_name) FROM retail_prices WHERE ...),
        'sku_name',        (SELECT json_agg(DISTINCT sku_name) FROM retail_prices WHERE ...),
        'type',            (SELECT json_agg(DISTINCT type) FROM retail_prices WHERE ...),
        'term',            (SELECT json_agg(DISTINCT term) FROM retail_prices WHERE ...)
    );
```

减少 5 次 DB 往返为 1 次。PostgreSQL 会并行执行子查询。

**优化 2: 前端缓存 + 防抖**

- 缓存 `selections={}` 的初始结果（最大扫描量）
- 用户快速切换下拉框时 debounce 200ms

**优化 3: 预计算（如果数据量到百万级）**

将 (service_name, 维度组合) -> 可选值预计算到一张 lookup 表。级联查询变为单行精确查找。但 46K 行不需要这个。

---

## 十、子维度拆解：productName/skuName 的隐藏结构

### 10.1 问题：当前的 productName/skuName 是"复合维度"

从 API 真实数据看，一个 skuName 或 productName 往往编码了多个独立的用户选择：

**Storage (Blob Storage)：**
```
skuName = "Hot LRS"
         ├── Access Tier = Hot     (用户选择1)
         └── Redundancy  = LRS     (用户选择2)

skuName = "Archive RA-GRS"
         ├── Access Tier = Archive (用户选择1)
         └── Redundancy  = RA-GRS  (用户选择2)
```

Azure Global Calculator 把这一个 skuName 拆成了两个独立下拉框：
```
ACCESS TIER:  [Hot ▾]  [Cool ▾]  [Cold ▾]  [Archive ▾]
REDUNDANCY:   [LRS ▾]  [ZRS ▾]  [GRS ▾]  [RA-GRS ▾]
```

**MySQL Flexible Server：**
```
productName = "Azure Database for MySQL Flexible Server General Purpose - Ddsv5 Series Compute"
             ├── Deployment = Flexible Server     (用户选择1)
             ├── Service Tier = General Purpose    (用户选择2)
             └── Series = Ddsv5                    (用户选择3)

skuName = "2 vCore"
         └── Compute Size = 2 vCore               (用户选择4)
```

**Cosmos DB：**
```
productName = "Azure Cosmos DB autoscale"
             └── Capacity Mode = autoscale         (用户选择1)

productName = "Azure Cosmos DB Dedicated Gateway - Memory Optimized"
             ├── Feature = Dedicated Gateway       (用户选择1)
             └── Tier = Memory Optimized           (用户选择2)
```

### 10.2 关键发现：子维度信息 100% 在 Retail Prices API 中

通过 DISTINCT skuName 查询就能枚举所有组合：
```
Storage Blob Storage 的 skuName：
  Hot LRS, Hot ZRS, Hot GRS, Hot RA-GRS
  Cool LRS, Cool ZRS, Cool GRS, Cool RA-GRS
  Cold LRS, Cold GRS, Cold RA-GRS
  Archive LRS, Archive GRS, Archive RA-GRS
```

从这些值中可以解析出：
- Access Tier 集合 = {Hot, Cool, Cold, Archive}
- Redundancy 集合 = {LRS, ZRS, GRS, RA-GRS}

并且**级联约束仍然有效**：Cold 没有 ZRS 选项（数据中不存在 "Cold ZRS"），选了 Cold 后 Redundancy 下拉框会自动排除 ZRS。

### 10.3 中国区真实数据验证

**Storage Block Blob — 中国区 skuName（28 个）：**
```
Hot LRS, Hot ZRS, Hot GRS, Hot RA-GRS, Hot GZRS, Hot RA-GZRS
Cool LRS, Cool ZRS, Cool GRS, Cool RA-GRS, Cool GZRS, Cool RA-GZRS
Cold LRS, Cold ZRS, Cold GRS, Cold RA-GRS, Cold GZRS, Cold RA-GZRS
Archive LRS, Archive GRS, Archive RA-GRS
Premium LRS, Premium ZRS
Standard LRS, Standard ZRS, Standard GRS, Standard RA-GRS, Standard (无后缀)
```

模式完全一致：`{AccessTier/Performance} {Redundancy}`，用空格分割即可。

**MySQL — 中国区 productName 的子维度结构：**
```
"Azure Database for MySQL Flexible Server General Purpose - Dadsv5 Series Compute"
 └── 固定前缀 ──────────────────────┘ └── Tier ───────┘   └── Series ──┘

"Azure Database for MySQL Flexible Server Burstable BS Series Compute"
 └── 固定前缀 ──────────────────────┘ └── Tier ──┘ └ Series ┘

"Azure Database for MySQL Flexible Server Storage"
 └── 固定前缀 ──────────────────────┘ └── 类别 ──┘
```

**Cosmos DB — 中国区 productName 子维度：**
```
"Azure Cosmos DB"                                    → 基础 (Provisioned)
"Azure Cosmos DB autoscale"                          → Capacity Mode = autoscale
"Azure Cosmos DB serverless"                         → Capacity Mode = serverless
"Azure Cosmos DB Dedicated Gateway - General Purpose" → Feature = Gateway, Tier = GP
"Azure Cosmos DB Dedicated Gateway - Memory Optimized"→ Feature = Gateway, Tier = MemOpt
"Azure Cosmos DB - PITR"                             → Feature = PITR
"Graph API - General Purpose Compute"                → API Type = Graph, Tier = GP
"Graph API - Memory Optimized Compute"               → API Type = Graph, Tier = MemOpt
```

### 10.4 子维度解析的具体规则

#### Storage：skuName → access_tier + redundancy

```python
# 规则：空格分割，第一个词 = access_tier，其余 = redundancy
# 特殊: "Standard" 单独出现时无 redundancy
def parse_storage_sku(sku_name: str) -> dict:
    parts = sku_name.split(" ", 1)
    if len(parts) == 2:
        return {"access_tier": parts[0], "redundancy": parts[1]}
    return {"access_tier": parts[0]}  # "Standard" alone

# 验证：28 个 skuName 全部可以正确解析
```

#### MySQL：productName → deployment + tier + series

```python
import re

def parse_mysql_product(product_name: str) -> dict:
    result = {}
    if "Flexible Server" in product_name:
        result["deployment"] = "Flexible Server"
        suffix = product_name.replace("Azure Database for MySQL Flexible Server ", "")
    elif "Single Server" in product_name:
        result["deployment"] = "Single Server"
        suffix = product_name.replace("Azure Database for MySQL Single Server ", "")
    else:
        result["deployment"] = "Legacy"
        return result

    tier_match = re.match(
        r"(General Purpose|Memory Optimized|Burstable|Business Critical)", suffix)
    if tier_match:
        result["tier"] = tier_match.group(1)
        rest = suffix[tier_match.end():].strip(" -")
        series_match = re.match(r"(\w+) Series", rest)
        if series_match:
            result["series"] = series_match.group(1)
    elif suffix.startswith("Storage") or suffix.startswith("Backup"):
        result["category"] = suffix
    return result
```

#### Cosmos DB：productName → 产品类型（查表法）

```python
COSMOS_PRODUCT_MAP = {
    "Azure Cosmos DB": {"capacity_mode": "Provisioned"},
    "Azure Cosmos DB autoscale": {"capacity_mode": "Autoscale"},
    "Azure Cosmos DB serverless": {"capacity_mode": "Serverless"},
    "Azure Cosmos DB Dedicated Gateway - General Purpose": {"feature": "Dedicated Gateway", "tier": "General Purpose"},
    "Azure Cosmos DB Dedicated Gateway - Memory Optimized": {"feature": "Dedicated Gateway", "tier": "Memory Optimized"},
    "Azure Cosmos DB - PITR": {"feature": "PITR"},
    "Azure Cosmos DB Analytics Storage": {"feature": "Analytics Storage"},
    "Graph API - General Purpose Compute": {"api_type": "Graph", "tier": "General Purpose"},
    "Graph API - Memory Optimized Compute": {"api_type": "Graph", "tier": "Memory Optimized"},
}
# Cosmos 产品数量少（中国区 8 个），直接用查表法更可靠
```

#### VM：productName → os + series_type + series

```python
def parse_vm_product(product_name: str) -> dict:
    result = {}
    if "Windows" in product_name:
        result["os"] = "Windows"
        name = product_name.replace(" Windows", "")
    else:
        result["os"] = "Linux"
        name = product_name

    if "Cloud Services" in name:
        result["series_type"] = "Cloud Services"
    elif "Dedicated Host" in name:
        result["series_type"] = "Dedicated Host"
    else:
        result["series_type"] = "Virtual Machines"

    series = name.replace("Virtual Machines ", "").replace(" Series", "").strip()
    if series:
        result["series"] = series
    return result
```

### 10.5 设计方案：后端提供子维度元数据，前端处理级联

**推荐方案**：后端在 configurations 响应中增加子维度元数据，但**查询模型完全不变**。

```
数据流:
  后端:
    1. 执行标准级联筛选 → 得到 5 维度 options
    2. 对有 sub_dimension 配置的维度: 解析 options 值 → 提取子维度 options
    3. 返回 dimensions + sub_dimensions 元数据

  前端:
    1. 渲染子维度为独立下拉框
    2. 用户选择子维度 → 前端本地过滤 → 组合回原始值
    3. 发送原始 sku_name/product_name 给后端

  关键: 后端 SQL 查询零改动！
```

API 响应结构（增强版）：

```json
{
  "service_name": "Storage",
  "dimensions": [
    {
      "field": "sku_name",
      "label": "SKU",
      "options": ["Hot LRS", "Hot ZRS", "Hot GRS", "..."],
      "selected": null,
      "sub_dimensions": [
        {
          "field": "access_tier",
          "label": "Access Tier",
          "options": ["Hot", "Cool", "Cold", "Archive", "Premium", "Standard"],
          "selected": null,
          "order": 0
        },
        {
          "field": "redundancy",
          "label": "Redundancy",
          "options": ["LRS", "ZRS", "GRS", "RA-GRS", "GZRS", "RA-GZRS"],
          "selected": null,
          "order": 1
        }
      ]
    }
  ]
}
```

### 10.6 部分选择时的级联行为

**场景**：用户选了 access_tier=Archive，但还没选 redundancy。此时其他维度的级联应该怎么办？

| 策略 | 行为 | 实现复杂度 |
|------|------|-----------|
| **延迟级联** | 子维度未全选时，不把 sku_name 发给后端。其他维度暂不受 sku 约束 | 零后端改动 |
| **前缀级联** | 子维度部分选择时，后端支持 `sku_name LIKE 'Archive%'` 过滤 | 需要改后端查询 |

**推荐：延迟级联**。理由：
1. 用户选 access_tier 后通常会立即选 redundancy，延迟很短
2. 即使暂时不约束，其他维度选项也不会"多"出太多（因为 product 已锁定）
3. 零后端改动，保持查询模型纯净

---

## 十一、Meter → 用量输入表单映射

### 11.1 从 API 数据推导输入表单

以 Storage Blob Hot LRS 为例，meters API 返回 7 个 meter。需要为每个 meter 自动生成合适的输入表单字段。

### 11.2 自动推导的三层处理

#### Layer 1: 标签清洗（去除已选维度的冗余前缀）

```python
def clean_meter_label(meter_name: str, selected_sku: str) -> str:
    """从 meterName 中去掉 skuName 的前缀，得到更简洁的标签"""
    sku_parts = selected_sku.split()
    label = meter_name
    if label.startswith(selected_sku + " "):
        label = label[len(selected_sku) + 1:]
    else:
        for part in sku_parts:
            if label.startswith(part + " "):
                label = label[len(part) + 1:]
    return label

# "Hot LRS Data Stored"       → "Data Stored"
# "Hot Read Operations"       → "Read Operations"
# "All Other Operations"      → "All Other Operations" (无变化)
# "LRS List and Create Container Ops" → "List and Create Container Ops"
```

#### Layer 2: 输入类型与默认值推导

```python
UNIT_INFERENCE = {
    "1 Hour":     {"input_unit": "Hours/Month", "default_quantity": 730,  "step": 1},
    "1 GB/Month": {"input_unit": "GB",          "default_quantity": 100,  "step": 1},
    "1 GB":       {"input_unit": "GB",          "default_quantity": 0,    "step": 1},
    "10K":        {"input_unit": "x 10K",       "default_quantity": 0,    "step": 1},
    "10K/Month":  {"input_unit": "x 10K",       "default_quantity": 0,    "step": 1},
    "1M":         {"input_unit": "x 1M",        "default_quantity": 0,    "step": 1},
    "1/Month":    {"input_unit": "Units",       "default_quantity": 1,    "step": 1},
    "1/Hour":     {"input_unit": "Units/Hour",  "default_quantity": 0,    "step": 100},
}
# 覆盖中国区 40 种 unitOfMeasure 中最常见的 ~15 种
```

#### Layer 3: meter 分类（primary / secondary / hidden）

```python
def classify_meter(meter_name: str, clean_label: str) -> str:
    HIDDEN_KEYWORDS = ["Early Delete", "Priority Data Retrieval", "Priority Read"]
    if any(kw in meter_name for kw in HIDDEN_KEYWORDS):
        return "hidden"

    PRIMARY_KEYWORDS = ["Data Stored", "vCore", "RU/s", "Compute", "Server"]
    if any(kw in clean_label for kw in PRIMARY_KEYWORDS):
        return "primary"

    return "secondary"
```

### 11.3 增强的 meters API 响应

```json
{
  "meters": [
    {
      "meter_name": "Hot LRS Data Stored",
      "display_label": "Data Stored",
      "unit_of_measure": "1 GB/Month",
      "input_unit": "GB",
      "default_quantity": 100,
      "category": "primary",
      "tiers": [
        {"min_units": 0, "unit_price": 0.140564, "description": "First 50 TB"},
        {"min_units": 51200, "unit_price": 0.134938, "description": "Next 450 TB"},
        {"min_units": 512000, "unit_price": 0.129317, "description": "Over 500 TB"}
      ]
    },
    {
      "meter_name": "Hot LRS Write Operations",
      "display_label": "Write Operations",
      "unit_of_measure": "10K",
      "input_unit": "x 10K",
      "default_quantity": 0,
      "category": "secondary",
      "tiers": [{"min_units": 0, "unit_price": 0.042453}]
    }
  ],
  "quantity_model": "per_meter",
  "hidden_meters": ["LRS Early Hot To Cool Tier Down", "..."]
}
```

### 11.4 不同服务的 quantity_model

```python
QUANTITY_MODELS = {
    "per_meter": {
        # 每个 meter 独立输入，最通用
        # 适用于: Storage, Cosmos DB, SQL Database
    },
    "instances_x_hours": {
        # 实例数 x 小时数，两个全局输入
        # 适用于: Virtual Machines, App Service, Azure Functions
        "fields": [
            {"name": "instances", "label": "Instances", "default": 1},
            {"name": "hours_per_month", "label": "Hours/Month", "default": 730},
        ],
    },
    "units_x_hours": {
        # 单位数 x 小时数
        # 适用于: Cosmos DB Dedicated Gateway
        "fields": [
            {"name": "units", "label": "Units", "default": 1},
            {"name": "hours_per_month", "label": "Hours/Month", "default": 730},
        ],
    },
}
```

### 11.5 服务配置模板系统

将子维度、meter 元数据、quantity_model 等统一为 JSON 配置文件：

```
app/config/service_configs/
  _default.json        # 通用默认配置（所有服务 fallback）
  storage.json          # Storage 专用配置
  virtual_machines.json # VM 专用配置
  cosmos_db.json        # Cosmos DB 专用配置
  mysql.json            # MySQL 专用配置
```

渐进式实施路径：
- **Phase 1 (MVP)**: 通用 5 维度 + 原始 meter → 所有 105 个服务可用
- **Phase 2**: meter 增强（自动推导 label/default/category，零配置，所有服务受益）
- **Phase 3**: 主要服务子维度拆解（需要服务配置 JSON）
- **Phase 4（可选）**: 产品规格元数据（VM vCPU/RAM 等，需额外数据源）

---

## 总结

级联筛选的本质是一个**多维度交叉约束问题**：

1. **数据模型**：retail_prices 表的每一行是一个 (region, product, sku, type, term, meter, tier) 的唯一定价记录
2. **三层结构**：Configuration -> Meter -> Tier，级联筛选只操作 Configuration 层的维度
3. **核心算法**：对每个维度，用"其他所有已选维度"做过滤，求该维度的 DISTINCT 值
4. **双向性**：不是自上而下的瀑布，而是任意维度的选择都会约束其他所有维度
5. **条件可见性**：term 维度仅在 type 为 Reservation/SavingsPlan 时可见
6. **数据稀疏**：region x product 覆盖率仅 54%，双向约束确保不出现死胡同
7. **索引策略**：Partial Index + INCLUDE 覆盖索引，实现所有查询 Index Only Scan
8. **宽表设计**：46K 行量级无需拆分，一张 retail_prices 表足够
9. **阶梯定价**：不影响级联筛选本身，在 meters 和 pricing 层处理
