# VM Calculator UI ↔ Retail Prices API 数据映射

> 调研日期：2026-03-09
> 数据来源：Azure Global Retail Prices API (`https://prices.azure.com/api/retail/prices`)、Azure.cn CSV (`sample-data/AzureRetailPrices.csv`, 46,877 行)
> 参照页面：Azure Global Pricing Calculator (https://azure.microsoft.com/en-us/pricing/calculator/)

---

## 一、Calculator VM 配置面板 UI 结构

Azure Global Pricing Calculator 中 Virtual Machines 的配置面板包含以下控件（从上到下）：

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

### 1.1 维度清单

| # | UI 维度 | 控件类型 | 选项示例 | 默认值 |
|---|---------|---------|---------|--------|
| 1 | REGION | 下拉框 | East US, West Europe, Japan West, ... | East US |
| 2 | OPERATING SYSTEM | 下拉框 | Linux, Windows, Red Hat Enterprise Linux, SUSE Linux, ... | Linux |
| 3 | TYPE | 下拉框 | OS Only, SQL Server Enterprise, BizTalk Enterprise, ... | OS Only |
| 4 | TIER | 下拉框 | Standard, Basic, Low Priority, Spot | Standard |
| 5 | CATEGORY | 下拉框 | General Purpose, Compute Optimized, Memory Optimized, Storage Optimized, GPU, HPC | General Purpose |
| 6 | INSTANCE SERIES | 下拉框 | Dv3, Dv5, Ev5, FSv2, NCasT4 v3, ... | (依赖 Category) |
| 7 | INSTANCE | 下拉框 | D2 v3: 2 vCPU, 8 GB RAM, ... | (依赖 Series) |
| 8 | SAVINGS OPTIONS | 下拉框/单选 | Pay as you go, 1 year reserved, 3 year reserved, 1 year savings plan, 3 year savings plan | Pay as you go |
| 9 | 数量输入 | 数字 × 数字 | [N] virtual machines × [730] hours | 1 × 730 |
| 10 | MANAGED DISKS | 下拉框 | S4: 32 GiB, S6: 64 GiB, ... | S4 |
| 11 | STORAGE | 数字 | [N] managed disk(s) | 1 |
| 12 | BANDWIDTH | 数字 × 2 | Inbound [N] GB / Outbound [N] GB | 5 / 5 |

### 1.2 维度联动行为

- **REGION** → 影响所有后续维度（不同区域支持的系列/实例不同）
- **OPERATING SYSTEM** → 决定 productName 后缀（Linux 无后缀 vs Windows）→ 影响 INSTANCE SERIES 和价格
- **TYPE** → 区分 "OS Only" vs 软件捆绑（SQL Server 等）→ 改变 productName 前缀
- **TIER** → Standard / Basic / Low Priority / Spot → 对应 skuName 后缀
- **CATEGORY** → 前端分组维度（General Purpose / GPU 等）→ 过滤 INSTANCE SERIES
- **INSTANCE SERIES** → 对应 productName 中的系列名 → 决定 INSTANCE 列表
- **INSTANCE** → 精确到 skuName → 决定 meter 和价格
- **SAVINGS OPTIONS** → 对应 type + reservationTerm 组合

### 1.3 附加项说明

MANAGED DISKS 和 BANDWIDTH 是 **独立服务**，不属于 Virtual Machines 的 Retail Prices API 数据。它们有各自的 serviceName：
- Managed Disks → `serviceName = "Storage"`, `productName LIKE '%Managed Disks%'`
- Bandwidth → `serviceName = "Bandwidth"` 或 `serviceName = "Virtual Network"`

Calculator 将它们捆绑在 VM 配置卡片中是 **UI 层的便利设计**，底层是独立的定价查询。

---

## 二、维度映射表（核心）

### 2.1 REGION ↔ armRegionName

| 属性 | 值 |
|------|-----|
| **UI 维度** | REGION |
| **API 字段** | `armRegionName` |
| **映射方式** | **直接取值** |
| **示例** | UI "East US" → API `armRegionName = "eastus"` |
| **反向映射** | API 值 → 需要 display name 映射表（"eastus" → "East US"） |
| **Global 数量** | 约 60+ 区域 |
| **CN 数量** | 6 实际区域 + 5 逻辑区域 |

**注意**：UI 显示的是人类可读名称（"East US"），API 使用的是 ARM 标识符（"eastus"）。Calculator 前端维护了一套区域名称映射表。Azure.cn 数据中 `location` 字段存储了中文显示名。

### 2.2 OPERATING SYSTEM ↔ productName 后缀

| 属性 | 值 |
|------|-----|
| **UI 维度** | OPERATING SYSTEM |
| **API 字段** | `productName`（后缀编码） |
| **映射方式** | **解析规则** |

**解析规则**：

```
productName 结尾            → OPERATING SYSTEM
─────────────────────────────────────────────
无 "Windows"/"Linux" 后缀   → Linux（默认）
"... Windows"               → Windows
"... Linux"                 → Linux（显式标注）
```

**真实数据示例**：
```
"Virtual Machines Dv3 Series"          → Linux
"Virtual Machines Dv3 Series Windows"  → Windows
"Virtual Machines Dnv6 Series Linux"   → Linux (显式)
"Virtual Machines Ebdsv6-Series Linux" → Linux (显式)
```

**边界情况**：
- 一些较新的系列显式标注 "Linux" 后缀（如 Dnv6、Ebdsv6），而非依赖"无后缀=Linux"约定
- Red Hat Enterprise Linux、SUSE 等非 Windows 操作系统在 Calculator UI 中可选，但在 Retail Prices API 中体现为 **不同的 productName** 或 **不同的 serviceName**（如 `serviceName = "Virtual Machines Licenses"`）
- TYPE 维度中的 "SQL Server Enterprise" 等软件捆绑也改变 productName（如 `"SQL Server Enterprise Red Hat Enterprise Linux"` 是独立 productName）

**CN 区一致性**：CN CSV 使用相同规则——无后缀=Linux，"Windows" 后缀=Windows。

### 2.3 TYPE ↔ productName 前缀（软件捆绑）

| 属性 | 值 |
|------|-----|
| **UI 维度** | TYPE |
| **API 字段** | `productName`（前缀编码） |
| **映射方式** | **推导规则** |

**映射逻辑**：

| UI TYPE 值 | productName 模式 |
|-------------|-----------------|
| OS Only | `"Virtual Machines {Series} Series [Windows\|Linux]"` |
| SQL Server Enterprise | `"SQL Server Enterprise ..."` |
| SQL Server Standard | `"SQL Server Standard ..."` |
| SQL Server Web | `"SQL Server Web ..."` |
| BizTalk Enterprise | `"BizTalk Enterprise ..."` |
| Red Hat Enterprise Linux | `"Red Hat Enterprise Linux ..."` |

**关键发现**：TYPE = "OS Only" 是默认值，对应 productName 以 "Virtual Machines" 开头。其他 TYPE 值对应不同的 productName 前缀，这些产品在 serviceName = "Virtual Machines" 下仍然可查到。

**CN 区现状**：CN CSV 中无软件捆绑产品（无 SQL Server、BizTalk 等），TYPE 维度对 CN 区不适用。

### 2.4 TIER ↔ skuName 后缀

| 属性 | 值 |
|------|-----|
| **UI 维度** | TIER |
| **API 字段** | `skuName`（后缀编码） |
| **映射方式** | **解析规则** |

**解析规则**：

```
skuName 后缀          → TIER
──────────────────────────────
无后缀                → Standard
" Low Priority"       → Low Priority
" Spot"               → Spot
"Basic" (productName) → Basic
```

**真实数据示例**（eastus, Dv5 Series）：
```
"Standard_D2_v5"               → Standard
"Standard_D2_v5 Low Priority"  → Low Priority
"Standard_D2_v5 Spot"          → Spot
```

**真实数据示例**（eastus, Dv3 Series）：
```
"D2 v3"               → Standard
"D2 v3 Low Priority"  → Low Priority
"D2 v3 Spot"          → Spot
```

**Basic 的特殊处理**：Basic 不通过 skuName 后缀区分，而是通过 productName：
```
"Virtual Machines A Series"        → Standard tier
"Virtual Machines A Series Basic"  → Basic tier（独立 productName）
```

**CN 区差异**：CN 区无 Low Priority / Spot 变体。只有 Standard（和极少量 Basic）。

### 2.5 CATEGORY ↔ 从 productName 中的 Series 名推导

| 属性 | 值 |
|------|-----|
| **UI 维度** | CATEGORY |
| **API 字段** | 无直接字段 — **从 series 名推导** |
| **映射方式** | **推导规则（首字母/前缀）** |

**推导规则**：

| Series 首字母/前缀 | CATEGORY |
|---------------------|----------|
| A, B, D | General Purpose |
| E, M | Memory Optimized |
| F | Compute Optimized |
| H (HB, HC, HX) | High Performance Compute (HPC) |
| L | Storage Optimized |
| N (NC, ND, NV, NP) | GPU |
| DC, EC | Confidential Computing（部分 Calculator 归入 General Purpose） |

**真实数据验证**（eastus, 437 个 productName）：

| Category | 代表性 productName | Series 名 |
|----------|-------------------|-----------|
| General Purpose | Virtual Machines Dv5 Series | Dv5 |
| General Purpose | Virtual Machines Bsv2 Series | Bsv2 |
| Memory Optimized | Virtual Machines Edsv5 Series | Edsv5 |
| Memory Optimized | Virtual Machines MS Series | MS |
| Compute Optimized | Virtual Machines FSv2 Series | FSv2 |
| Storage Optimized | Virtual Machines Lsv3 Series | Lsv3 |
| GPU | Virtual Machines NCasT4 v3 Series | NCasT4 v3 |
| GPU | Virtual Machines NVadsA10v5 Series | NVadsA10v5 |
| HPC | Virtual Machines HBSv2 Series | HBSv2 |

**已实现**：`app/services/sub_dimensions/vm_category_map.py` 中有完整的 category 推导逻辑，使用多字符前缀优先匹配（DC, EC, NC, NV, ND, HB, HC 等）再回退到首字母匹配。

### 2.6 INSTANCE SERIES ↔ productName 中间部分

| 属性 | 值 |
|------|-----|
| **UI 维度** | INSTANCE SERIES |
| **API 字段** | `productName`（中间部分） |
| **映射方式** | **解析规则** |

**解析规则**：
```python
productName = "Virtual Machines {Series} Series [Windows|Linux]"
                                ^^^^^^^^
                           INSTANCE SERIES
```

**提取步骤**（已在 `vm_parser.py` 中实现）：
1. 去掉 OS 后缀（" Windows" / " Linux"）
2. 检测 deployment 类型（Dedicated Host / Cloud Services / Virtual Machines）
3. 去掉 "Virtual Machines " 前缀
4. 去掉 "Series" / "series" 关键词
5. 提取 qualifier（Basic, Medium Memory, High Memory）
6. 剩余文本 = series 名

**真实数据示例**：

| productName | 提取的 Series |
|-------------|--------------|
| Virtual Machines Dv5 Series | Dv5 |
| Virtual Machines Dv3 Series Windows | Dv3 |
| Virtual Machines NCasT4 v3 Series | NCasT4 v3 |
| Virtual Machines Mdsv3 Medium Memory Series Linux | Mdsv3 |
| Virtual Machines A Series Basic | A |
| Dadsv5 Series Dedicated Host | Dadsv5 |

**注意**：Calculator UI 中 INSTANCE SERIES 显示的是简化名（如 "Dv3"），不包含 "Virtual Machines" 前缀和 "Series" 后缀。

### 2.7 INSTANCE ↔ skuName / armSkuName / meterName

| 属性 | 值 |
|------|-----|
| **UI 维度** | INSTANCE |
| **API 字段** | `skuName`（主键）+ `armSkuName`（ARM 标识）+ `meterName`（显示名） |
| **映射方式** | **直接取值，但格式需注意** |

**三个相关字段的关系**：

| 字段 | 用途 | 格式 | 示例（Dv3）| 示例（Dv5）|
|------|------|------|-----------|-----------|
| `skuName` | API 筛选键 | 不一致 | `D2 v3` | `Standard_D2_v5` |
| `armSkuName` | ARM 资源标识 | 统一 `Standard_` 前缀 | `Standard_D2_v3` | `Standard_D2_v5` |
| `meterName` | 计量名称/显示名 | 人类可读 | `D2 v3/D2s v3` | `D2 v5` |

**关键发现：skuName 格式不一致**

这是一个重要的发现——不同代次的 VM 系列使用不同的 skuName 格式：

| 代次 | skuName 格式 | 示例 |
|------|-------------|------|
| 旧（v3 及以前）| 简短格式 | `D2 v3`, `E4 v3`, `A1` |
| 新（v5+）| ARM 格式（带 Standard_ 前缀和下划线）| `Standard_D2_v5`, `Standard_E8_v5` |
| GPU | 简短格式 | `NC4as T4 v3`, `NC64asT4 v3` |
| Dedicated Host | Type 编号 | `Dadsv5 Type1`, `Easv4 Type2` |

**armSkuName 始终使用 ARM 格式**（`Standard_D2_v3`），无论 skuName 用什么格式。

**Calculator UI 显示**：UI 中 INSTANCE 显示的是人类可读格式 + 规格信息：`D2 v3: 2 vCPU, 8 GB RAM`。规格信息（vCPU、RAM）**不在 Retail Prices API 中**，来自 Azure 的 VM SKU 元数据 API。

**TIER 后缀在 skuName 中**：
```
"D2 v3"               → Standard tier 的 D2 v3 实例
"D2 v3 Low Priority"  → Low Priority tier 的 D2 v3 实例
"D2 v3 Spot"          → Spot tier 的 D2 v3 实例
```

去掉 TIER 后缀后的 base skuName 才是真正的 INSTANCE。

### 2.8 SAVINGS OPTIONS ↔ type + reservationTerm

| 属性 | 值 |
|------|-----|
| **UI 维度** | SAVINGS OPTIONS |
| **API 字段（Global）** | `type` + `reservationTerm` |
| **API 字段（CN CSV）** | `type` + `term` |
| **映射方式** | **组合映射** |

**映射表**：

| UI SAVINGS OPTIONS | Global API `type` | Global API `reservationTerm` | CN CSV `type` | CN CSV `term` |
|--------------------|-------------------|-----------------------------|---------------|---------------|
| Pay as you go | `Consumption` | (null) | `Consumption` | (空) |
| 1 year reserved | `Reservation` | `1 Year` | `Reservation` | `1 Year` |
| 3 year reserved | `Reservation` | `3 Years` | `Reservation` | `3 Years` |
| 1 year savings plan | — (不在 VM API 中) | — | `SavingsPlanConsumption` | `1 Year` |
| 3 year savings plan | — (不在 VM API 中) | — | `SavingsPlanConsumption` | `3 Years` |

**关键发现：Global API vs CN CSV 的字段名差异**

| 差异点 | Global API | CN CSV |
|--------|-----------|--------|
| 承诺期字段名 | `reservationTerm` | `term` |
| 5 年预留 | 存在（少量产品） | 不存在 |
| SavingsPlanConsumption | **不在 VM API 中返回** | **存在** |
| DevTestConsumption | 存在 | 存在 |

**SavingsPlan 的差异说明**：Global Retail Prices API 的 VM 查询中没有 `type = "SavingsPlanConsumption"` 的行。这可能是因为 Savings Plan 定价在 Global 中通过独立的 API 或服务提供。而 CN CSV 将 SavingsPlan 定价直接包含在同一数据集中。

**DevTestConsumption**：在级联筛选中默认排除。DevTest 的 Windows VM 价格 = Linux 价格（免 Windows 许可费）。

### 2.9 数量模型 ↔ unitOfMeasure

| 属性 | 值 |
|------|-----|
| **UI 维度** | 数量输入（[N] VMs × [730] hours） |
| **API 字段** | `unitOfMeasure` |
| **映射方式** | **推导规则** |

VM 的 `unitOfMeasure` 几乎全部是 `"1 Hour"`。Calculator UI 的数量模型：

```
monthly_cost = unitPrice × quantity × hours_per_month
             = unitPrice × N_vms × 730

例外：Reservation 的 unitPrice 是预付总价
monthly_cost = reservationPrice / (term_months)
             = $501.00 / 12 = $41.75/月  (1 Year Reserved)
```

**Reservation 价格的特殊处理**：
- Reservation 行的 `unitOfMeasure` 也是 `"1 Hour"`，但 `unitPrice` 是整个承诺期的总价（不是小时价）
- Calculator 需要除以承诺期月数来转换为月费
- 1 Year → ÷ 12，3 Years → ÷ 36，5 Years → ÷ 60

---

## 三、端到端 Walkthrough

### 3.1 标准 VM：eastus / Linux / General Purpose / Dv5 / D2 v5 / PayAsYouGo

**Calculator UI 选择**：
```
REGION:           East US
OPERATING SYSTEM: Linux
TYPE:             OS Only
TIER:             Standard
CATEGORY:         General Purpose
INSTANCE SERIES:  Dv5
INSTANCE:         D2 v5 (2 vCPU, 8 GB RAM)
SAVINGS OPTIONS:  Pay as you go
```

**API 查询参数**：
```
serviceName = "Virtual Machines"
armRegionName = "eastus"
productName = "Virtual Machines Dv5 Series"     ← Linux（无后缀）
skuName = "Standard_D2_v5"                      ← 新格式（带 Standard_ 前缀）
```

**API 返回数据**（3 行）：

| skuName | armSkuName | meterName | type | reservationTerm | unitPrice (USD) | unitOfMeasure |
|---------|------------|-----------|------|-----------------|-----------------|---------------|
| Standard_D2_v5 | Standard_D2_v5 | D2 v5 | Consumption | (null) | $0.096 | 1 Hour |
| Standard_D2_v5 | Standard_D2_v5 | D2 v5 | Reservation | 1 Year | $496.00 | 1 Hour |
| Standard_D2_v5 | Standard_D2_v5 | D2 v5 | Reservation | 3 Years | $933.00 | 1 Hour |

**价格计算**（Pay as you go, 1 VM, 730 小时/月）：
```
Compute = $0.096/hr × 1 × 730 = $70.08/月
```

**级联筛选可用选项**（Dv5 Series 在 eastus 的全部 SKU）：

| skuName（Standard） | skuName（Low Priority） | skuName（Spot） |
|---------------------|------------------------|----------------|
| Standard_D2_v5 | Standard_D2_v5 Low Priority | Standard_D2_v5 Spot |
| Standard_D4_v5 | Standard_D4_v5 Low Priority | Standard_D4_v5 Spot |
| Standard_D8_v5 | Standard_D8_v5 Low Priority | Standard_D8_v5 Spot |
| Standard_D16_v5 | Standard_D16_v5 Low Priority | Standard_D16_v5 Spot |
| Standard_D32_v5 | Standard_D32_v5 Low Priority | Standard_D32_v5 Spot |
| Standard_D48_v5 | Standard_D48_v5 Low Priority | Standard_D48_v5 Spot |
| Standard_D64_v5 | Standard_D64_v5 Low Priority | Standard_D64_v5 Spot |
| Standard_D96_v5 | Standard_D96_v5 Low Priority | Standard_D96_v5 Spot |

共 24 个 SKU = 8 实例 × 3 tier。选 TIER=Standard 后，INSTANCE 下拉框显示 8 个选项。

### 3.2 GPU VM：eastus / Windows / GPU / NCasT4 v3 / NC4as T4 v3 / Reserved 1Y

**Calculator UI 选择**：
```
REGION:           East US
OPERATING SYSTEM: Windows
TYPE:             OS Only
TIER:             Standard
CATEGORY:         GPU
INSTANCE SERIES:  NCasT4 v3
INSTANCE:         NC4as T4 v3
SAVINGS OPTIONS:  1 year reserved
```

**API 查询参数**：
```
serviceName = "Virtual Machines"
armRegionName = "eastus"
productName = "Virtual Machines NCasT4 v3 Series Windows"  ← Windows 后缀
skuName = "NC4as T4 v3"                                     ← 旧格式（无 Standard_ 前缀）
```

**API 返回数据 — Windows 版**（2 行）：

| meterName | type | reservationTerm | unitPrice (USD) | unitOfMeasure |
|-----------|------|-----------------|-----------------|---------------|
| NC4as T4 v3 | Consumption | (null) | $0.710 | 1 Hour |
| NC4as T4 v3 | DevTestConsumption | (null) | $0.526 | 1 Hour |

**问题**：Windows 版 NCasT4 v3 只有 Consumption 和 DevTest，**没有 Reservation**。

**API 返回数据 — Linux 版**（`productName = "Virtual Machines NCasT4 v3 Series"`）：

| meterName | type | reservationTerm | unitPrice (USD) | unitOfMeasure |
|-----------|------|-----------------|-----------------|---------------|
| NC4as T4 v3 | Consumption | (null) | $0.526 | 1 Hour |
| NC4as T4 v3 | Reservation | 1 Year | $2,709.00 | 1 Hour |
| NC4as T4 v3 | Reservation | 3 Years | $5,198.00 | 1 Hour |

**价格计算**（Linux, Reserved 1 Year）：
```
Compute = $2,709.00 / 12 = $225.75/月
vs Pay-as-you-go: $0.526 × 730 = $383.98/月
节省: 41%
```

**关键观察**：
- Windows DevTest 价格 ($0.526) = Linux 按需价格（免 Windows 许可费）
- Windows 比 Linux 贵 $0.184/hr（$0.710 - $0.526），这是 Windows 许可费
- 不是所有 OS + SKU 组合都支持 Reservation（Windows NCasT4 v3 不支持）
- **级联约束**：选了 Windows + Reserved 时，NCasT4 v3 应从 INSTANCE SERIES 中消失

### 3.3 边界情况：A Series Basic

**Calculator UI 选择**：
```
REGION:           East US
OPERATING SYSTEM: Linux
TYPE:             OS Only
TIER:             Basic
CATEGORY:         General Purpose
INSTANCE SERIES:  A
INSTANCE:         A0
SAVINGS OPTIONS:  Pay as you go
```

**API 查询参数**：
```
serviceName = "Virtual Machines"
armRegionName = "eastus"
productName = "Virtual Machines A Series Basic"  ← Basic 编码在 productName 中
```

**API 返回数据**（15 行，全部 Consumption）：

| meterName | type | unitPrice (USD) | 说明 |
|-----------|------|-----------------|------|
| A0 | Consumption | $0.018 | Standard |
| A0 Low Priority | Consumption | $0.004 | Low Priority |
| A0 Spot | Consumption | $0.016 | Spot |
| A1 | Consumption | $0.023 | Standard |
| A1 Low Priority | Consumption | $0.005 | Low Priority |
| A1 Spot | Consumption | $0.021 | Spot |
| A2 | Consumption | $0.079 | Standard |
| A3 | Consumption | $0.176 | Standard |
| A4 | Consumption | $0.352 | Standard |
| ... | ... | ... | ... |

**关键观察**：
- Basic 系列 **没有 Reservation** — SAVINGS OPTIONS 只有 Pay as you go
- Basic 是 "Virtual Machines A Series Basic"（productName），不是通过 skuName 区分
- TIER 后缀（Low Priority / Spot）仍然通过 skuName 区分
- meterName 和 skuName 一致（如 skuName = "A0", meterName = "A0"）

### 3.4 Dedicated Host

**API 查询参数**：
```
serviceName = "Virtual Machines"
armRegionName = "eastus"
productName = "Dadsv5 Series Dedicated Host"  ← 无 "Virtual Machines" 前缀！
skuName = "Dadsv5 Type1"                      ← Type 编号
```

**API 返回数据**（3 行）：

| meterName | type | reservationTerm | unitPrice (USD) |
|-----------|------|-----------------|-----------------|
| Dadsv5 Type1 | Consumption | (null) | $6.345/hr |
| Dadsv5 Type1 | Reservation | 1 Year | $32,792.00 |
| Dadsv5 Type1 | Reservation | 3 Years | $63,362.00 |

**关键观察**：
- productName **不以 "Virtual Machines" 开头** — 直接是 `"{Series} Series Dedicated Host"`
- 命名不一致：部分用 "Dedicated Host"（有空格），部分用 "DedicatedHost"（无空格）
- skuName 是 `{Series}Type{N}` 格式（如 "Dadsv5 Type1", "Easv4 Type2"）
- 价格远高于普通 VM（$6.345/hr vs D2 v5 的 $0.096/hr）— 因为是整台物理主机

---

## 四、Global API vs CN CSV 字段差异汇总

| 差异点 | Global API | CN CSV | 影响 |
|--------|-----------|--------|------|
| 承诺期字段 | `reservationTerm` | `term` | 代码中需要适配两种字段名 |
| 5 年预留 | 存在 | 不存在 | CN 区不需要处理 |
| SavingsPlan | 不在 VM API 中 | `type = "SavingsPlanConsumption"` | CN 区需要处理 SavingsPlan |
| Low Priority / Spot | 存在 | 不存在 | CN 区 TIER 维度更简单 |
| skuName 格式 | 混合（旧式 `D2 v3` + 新式 `Standard_D2_v5`） | 同样混合 | 解析逻辑需要兼容两种格式 |
| productName 前缀 | 部分无 "Virtual Machines"（Dedicated Host、Lasv3 Series Linux） | 同样不一致 | 解析时不能假设统一前缀 |
| type 值 | Consumption, Reservation, DevTestConsumption | 加上 SavingsPlanConsumption | CN 多一种 type |
| productName 后缀 | 混合（"Series" / "series"，"Windows" / "Linux"） | 同样 | 解析需 case-insensitive |
| 价格单位 | USD | CNY | 仅币种不同，结构一致 |

### CN CSV 中的 VM productName 统计

| 分类 | 数量 | 示例 |
|------|------|------|
| "Virtual Machines" 前缀 | 193 | Virtual Machines Dv3 Series |
| Dedicated Host | 28 | Dadsv5 Series Dedicated Host |
| Cloud Services | 4 | Basv2 Series Cloud Services |
| 其他（无标准前缀） | 15 | Lasv3 Series Linux, NCads A100 v4 Series Linux |
| **合计** | 240 | |

---

## 五、未解问题 & 后续调研方向

### 5.1 armSkuName vs skuName 的关系（已部分解决）

**已明确**：
- `armSkuName` 是 ARM 资源标识符，始终使用 `Standard_{Size}_{Version}` 格式
- `skuName` 是 API 的主键/筛选键，格式不一致（旧系列用简短格式，新系列用 ARM 格式）
- 两者的值在新系列（v5+）中相同，在旧系列中不同

**待确认**：
- 是否所有新系列（v5+, v6+）都统一使用 ARM 格式的 skuName？
- 中国区的 skuName 格式分布是否与 Global 一致？（初步检查：3,018 行使用 Standard_ 前缀）

### 5.2 VM 规格元数据（vCPU、RAM）的来源

Calculator UI 中 INSTANCE 下拉框显示 "D2 v3: **2 vCPU, 8 GB RAM**"。这些规格信息 **不在 Retail Prices API 中**。

可能的来源：
1. Azure Resource SKUs API (`GET /subscriptions/{subId}/providers/Microsoft.Compute/skus`)
2. Calculator 前端内嵌的静态映射表
3. 从 armSkuName 推导（如 `Standard_D2_v5` 中的 "2" 表示 2 vCPU — 但这只是部分信息）

**对本项目的影响**：如果要在前端显示 vCPU/RAM 信息，需要额外的数据源或维护一份静态映射。MVP 可以先只显示 skuName。

### 5.3 SavingsPlan 定价在 Global API 中的位置

Global API 的 VM 查询中没有 `type = "SavingsPlanConsumption"` 的行，但 Calculator UI 提供了 "1 year savings plan" 和 "3 year savings plan" 选项。

可能的解释：
1. SavingsPlan 定价通过独立的 API 端点提供
2. SavingsPlan 是 Compute 层级的承诺（跨 VM 大小），不绑定到具体 SKU
3. Calculator 可能使用与 Retail Prices API 不同的内部定价源

**对 CN 区的影响**：CN CSV 已包含 SavingsPlan 行，可直接使用，无需追踪 Global 的 SavingsPlan 数据源。

### 5.4 unitOfMeasure 与计费模型

**已明确**：
- VM 的 `unitOfMeasure = "1 Hour"` 对应 `instances × hours` 模型
- Reservation 的 unitPrice 是总价（非小时价），但 unitOfMeasure 仍标注为 "1 Hour"

**待确认**：
- Reservation 总价是否应该用 reservationTerm 对应的总小时数来换算？（1Y = 8760 hr, 3Y = 26280 hr）
- 还是直接除以月数？（Azure Calculator 用的是除以月数）

### 5.5 Managed Disks 和 Bandwidth 的精确 API 映射

Calculator 将 Managed Disks 和 Bandwidth 捆绑在 VM 卡片中显示。后续调研需要覆盖：
- Managed Disks 的 serviceName、productName、skuName 结构
- Bandwidth（出站流量）的定价 — 通常按阶梯（前 5 GB 免费）

### 5.6 meterName 中的共享 meter 模式

**已发现**：Dv3 系列的 meterName 是 `"D2 v3/D2s v3"`（共享 meter），而 Dv5 系列是 `"D2 v5"`（独立 meter）。

**含义**：
- Dv3 的 D2 v3 和 D2s v3 共享相同的 compute meter（价格相同）
- "s" 后缀表示支持 Premium Storage
- 共享 meter 意味着 meterName 不能直接用于反向查找 skuName

### 5.7 productName 命名规范化方向

现有的不一致：
- 大小写：`"Series"` vs `"series"`（如 "DCadsv6 series" vs "Dv5 Series"）
- 空格："DedicatedHost" vs "Dedicated Host"，"CloudServices" vs "Cloud Services"
- 前缀：有/无 "Virtual Machines "
- 连字符："Ebdsv6-Series" vs "Ebdsv6 Series"

这些不一致在 `vm_parser.py` 中已处理，但后续新系列可能引入新的变体。

---

## 六、方法论总结（可复用到其他服务）

本次 VM 调研建立的分析框架可复用到 Storage、Database 等服务：

### 分析步骤

1. **抓取 Calculator UI 结构** — 记录所有下拉框维度、选项、默认值
2. **API 维度分布** — `explore_global_api.py service` 获取全貌
3. **productName 子维度分析** — `subdimensions --field productName` 找出编码模式
4. **skuName 子维度分析** — `subdimensions --field skuName` 找出编码模式
5. **逐维度映射** — UI 维度 → API 字段 → 解析规则 → 示例
6. **端到端 walkthrough** — 选 2-3 个代表性配置验证完整链路
7. **CN 对比** — Global vs CN CSV 的字段差异、数据覆盖差异

### 关键问题模板

- UI 显示的维度在 API 的哪个字段？是直接取值还是需要解析？
- 维度间的联动关系在 API 层如何体现？
- API 中有但 UI 不直接显示的字段有哪些？有什么用？
- Global 和 CN 的字段名、值域、数据覆盖有什么差异？
- 哪些信息需要 Retail Prices API 之外的数据源？
