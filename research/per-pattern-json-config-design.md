# Per-Product JSON 配置设计 — 按定价 Pattern 逐一验证

> **核心思路**：每个产品一个 JSON 配置（描述 UI 结构 + 价格映射），价格从 Retail API 动态获取。
> **数据源**：Azure Retail Prices API（Global: `prices.azure.com`，CN: `prices.azure.cn`，结构相同）
> **日期**：2026-03-31
> **前置文档**：`product-pricing-patterns.md`（6 种模式分类）、`product-config-schema-validation.md`（display_maps 机制）

---

## 总览

| Pattern | 名称 | 代表产品 | quantity_model | 核心挑战 |
|---------|------|---------|----------------|---------|
| A | instances × hours | **Virtual Machines**, **App Service** | `instances_x_hours` | productName 编码多子维度（OS/Series/Tier） |
| B | 多 meter 独立计量 | **Service Bus**, **Azure Firewall** | `per_meter` | 混合 unitOfMeasure + 阶梯 + 免费层 |
| C | 计算 + 存储组合 | **Azure SQL Database** | `compute_plus_storage` | DTU/vCore 双模型 + 多 section + 日费率 |
| D | 多资源维度组合 | **Azure Container Instances** | `resource_dimensions` | 用户自组合 vCPU/Memory/GPU + 混合单位 |
| E | SKU 基础费 + 附加 meter | **VPN Gateway** | `sku_base_plus_meter` | 固定基础费 + 按连接数附加 |
| F | 跨服务复合 | **HDInsight** | `cross_service_composite` | 服务费 + VM 费来自不同 serviceName + 多节点角色 |

---

## Pattern A: `instances_x_hours` — Virtual Machines / App Service

### A.1 实际 API 数据

#### Virtual Machines (eastus)

```
总行数: 10,000+ (max_pages 截断)
productName: 431 distinct — 编码了 OS + Series
  "Virtual Machines Dv3 Series"           → Linux + Dv3
  "Virtual Machines Dv3 Series Windows"   → Windows + Dv3
  "Virtual Machines ESv3 Series"          → Linux + ESv3
skuName: 943 distinct — 实例规格 (D2 v3, E16 v5, ...)
type: Consumption | Reservation | DevTestConsumption
unitOfMeasure: "1 Hour" (统一)
term: 1 Year | 3 Years (RI)
```

#### App Service (eastus)

```
总行数: 269
productName: 21 distinct — 编码了 Tier + OS
  "Azure App Service Premium v3 Plan"          → Windows + Premium v3
  "Azure App Service Premium v3 Plan - Linux"  → Linux + Premium v3
  "Azure App Service Isolated v2 Plan"         → Windows + Isolated v2
skuName: 60 distinct — 实例规格 (P1 v3, P2mv3, I1 v2, ...)
type: Consumption | Reservation | DevTestConsumption
unitOfMeasure: "1 Hour" (统一)
term: 1 Year | 3 Years (RI)
```

App Service P1 v3 meter 示例：

```
Consumption:      $0.30/hr
DevTestConsumption: $0.10/hr
Reservation 1Y:   $2,075 (total)
Reservation 3Y:   $5,075 (total)
```

### A.2 核心挑战：productName 子维度解析

VM 有 431 个 productName，App Service 有 21 个。直接展示为一个下拉框不可用。需要从 productName 中解析出用户可理解的子维度。

**productName 编码规律**：

| 产品 | 模式 | 示例 |
|------|------|------|
| VM | `"Virtual Machines {Series} Series {OS?}"` | `"Virtual Machines Dv3 Series Windows"` |
| App Service | `"Azure App Service {Tier} Plan {- Linux?}"` | `"Azure App Service Premium v3 Plan - Linux"` |

**解析规则**：尾部匹配已知后缀 → 提取子维度，剩余部分作为另一个子维度。

### A.3 JSON 配置设计

#### Virtual Machines

```jsonc
{
  "service_name": "Virtual Machines",
  "display_name_cn": "虚拟机",
  "quantity_model": "instances_x_hours",

  // productName → 用户可见的子维度
  "product_sub_dimensions": {
    "prefix": "Virtual Machines ",        // 去掉的公共前缀
    "suffix_dimension": {
      "field": "os",
      "label": "Operating System",
      "label_cn": "操作系统",
      "suffixes": {
        "Windows": "Windows",
        "RHEL": "Red Hat Enterprise Linux",
        "SUSE": "SUSE Linux Enterprise",
        "Ubuntu Pro": "Ubuntu Pro"
      },
      "default_label": "Linux"            // 无后缀时的显示名
    },
    "remaining_dimension": {
      "field": "series",
      "label": "Instance Series",
      "label_cn": "实例系列"
      // 值即去掉前缀和后缀后的剩余，如 "Dv3 Series", "ESv3 Series"
      // 不需要 display_map — 系列名已可读
    }
  },

  // skuName 维度：Standard/Spot/Low Priority 从 skuName 后缀区分
  "display_maps": {
    "skuName": {
      "hide_unmapped": false,
      "suffix_groups": {
        "Spot": { "group": "Spot", "group_cn": "竞价" },
        "Low Priority": { "group": "Low Priority", "group_cn": "低优先级" }
      },
      "default_group": "Standard",
      "default_group_cn": "标准"
    }
  },

  "defaults": {
    "hours_per_month": 730,
    "selections": {
      "armRegionName": "eastus",
      "os": "Linux",
      "skuName": "D2 v3"
    }
  }
}
```

#### App Service

```jsonc
{
  "service_name": "Azure App Service",
  "display_name_cn": "应用服务",
  "quantity_model": "instances_x_hours",

  "product_sub_dimensions": {
    "prefix": "Azure App Service ",
    "suffix_dimension": {
      "field": "os",
      "label": "Operating System",
      "label_cn": "操作系统",
      "suffixes": {
        "- Linux": "Linux"
      },
      "default_label": "Windows"
    },
    "remaining_dimension": {
      "field": "tier",
      "label": "Tier",
      "label_cn": "层级"
      // 值如 "Premium v3 Plan", "Isolated v2 Plan"
      // 可选 display_map 去掉 "Plan" 后缀
    }
  },

  // 过滤掉不属于实例定价的 productName
  "excluded_products": [
    "Azure App Service SSL Connections",
    "Azure App Service Domain"
  ],

  "defaults": {
    "hours_per_month": 730,
    "selections": {
      "armRegionName": "eastus",
      "os": "Linux",
      "tier": "Premium v3 Plan",
      "skuName": "P1 v3"
    }
  }
}
```

### A.4 数据流

```
1. 用户打开 VM 卡片
   → GET /config/Virtual%20Machines → 获取配置（含 product_sub_dimensions）
   → POST /cascade {service_name: "Virtual Machines", selections: {armRegionName: "eastus"}}
   → 返回 productName options (431 个)

2. 前端用 product_sub_dimensions 解析 productName 列表:
   "Virtual Machines Dv3 Series"         → os=Linux,  series="Dv3 Series"
   "Virtual Machines Dv3 Series Windows" → os=Windows, series="Dv3 Series"
   → 渲染两个独立下拉框: [OS: Linux ▾] [Series: Dv3 Series ▾]

3. 用户选择 os=Linux, series="Dv3 Series"
   → 拼回 productName = "Virtual Machines Dv3 Series"
   → POST /cascade {selections: {armRegionName: "eastus", productName: "Virtual Machines Dv3 Series"}}
   → 返回 skuName options: ["D2 v3", "D4 v3", "D8 v3", "D16 v3", ...]

4. 用户选择 skuName = "D2 v3"
   → POST /meters → 返回 Consumption/RI 价格
   → 本地计算: $0.096 × 1 × 730 = $70.08/mo

5. 用户切换 region → 重新 cascade → 新 productName 列表 → sub_dimensions 重新解析
   → 某些 series 可能在新 region 不可用 → 自动消失
```

### A.5 渲染引擎需支持

| 能力 | 说明 | 复杂度 |
|------|------|-------|
| `product_sub_dimensions` 解析 | 将 productName 列表拆分为多个子维度下拉框 | 中 — 解析逻辑通用（前缀+后缀匹配） |
| 子维度 → productName 反向拼接 | 用户选择子维度后拼回 productName 用于 cascade | 低 |
| `excluded_products` 过滤 | cascade 返回中排除不相关的 productName | 低 |
| RI/SP 展示 | type + term 组合展示为 Savings Options | 已有 |

---

## Pattern B: `per_meter` — Service Bus / Azure Firewall

### B.1 实际 API 数据

#### Service Bus (eastus)

```
总行数: 18
productName: 1 (唯一值 "Service Bus")
skuName: 6 — Basic | Standard | Premium | Hybrid Connections | WCF Relay | Geo Replication Zone 1
type: Consumption only
unitOfMeasure: 8 种 — "1M", "1", "1 GB", "1/Hour", "100 Hours", "10K", "1 Hour", "1/Month"

Standard SKU (3 个 meter):
  ┌─────────────────────────────────┬────────┬────────────────────────────────┐
  │ meterName                       │ unit   │ 阶梯                           │
  ├─────────────────────────────────┼────────┼────────────────────────────────┤
  │ Standard Base Unit              │ 1/Hour │ 2 档: 0→$0.0, 0→$10.0         │
  │ Standard Brokered Connections   │ 1      │ 4 档: 0 (免费), 1K→, 100K→, 500K→ │
  │ Standard Messaging Operations   │ 1M     │ 4 档: 0 (免费), 13→$0.8, 100→, 2500→ │
  └─────────────────────────────────┴────────┴────────────────────────────────┘
```

#### Azure Firewall (eastus)

```
总行数: 16
productName: 1 (唯一值 "Azure Firewall")
skuName: 6 — Basic | Standard | Premium × VNet | Secured Virtual Hub
type: Consumption only
unitOfMeasure: 2 种 — "1 Hour", "1 GB"

Standard SKU (3 个 meter):
  ┌──────────────────────────┬────────┬──────────┐
  │ meterName                │ unit   │ price    │
  ├──────────────────────────┼────────┼──────────┤
  │ Standard Deployment      │ 1 Hour │ $1.25/hr │ ← 固定部署费
  │ Standard Data Processed  │ 1 GB   │ $0.016/GB│ ← 按流量
  │ Standard Capacity Unit   │ 1 Hour │ $0.07/hr │ ← 可隐藏（自动扩展）
  └──────────────────────────┴────────┴──────────┘
```

### B.2 核心挑战

1. **混合 unitOfMeasure** — 同一 SKU 下 meter 单位不同（1M, 1, 1/Hour, 1 GB）
2. **阶梯 + 免费层** — Service Bus Standard 的 Messaging Operations 有 4 档阶梯，第一档免费
3. **sku_groups** — Standard + Hybrid Connections + WCF Relay 逻辑上都属于 Standard tier，需合并
4. **隐藏 meter** — Firewall Capacity Unit 不需要用户输入

### B.3 JSON 配置设计

#### Service Bus

```jsonc
{
  "service_name": "Service Bus",
  "display_name_cn": "服务总线",
  "quantity_model": "per_meter",

  // 将多个 API skuName 合并为逻辑 Tier
  "sku_groups": {
    "Basic":    ["Basic"],
    "Standard": ["Standard", "Hybrid Connections", "WCF Relay"],
    "Premium":  ["Premium"]
  },

  "hidden_dimensions": ["productName"],

  "meter_overrides": {
    "Standard Base Unit": {
      "label": "Base Charge",
      "label_cn": "基础费用",
      "default_quantity": 1,
      "unit_display": "per hour",
      "order": 1
    },
    "*Messaging Operations": {
      "label": "Messaging Operations",
      "label_cn": "消息操作",
      "default_quantity": 1,
      "unit_display": "millions",
      "note_cn": "前 1300 万次免费",
      "order": 2
    },
    "*Brokered Connections": {
      "label": "Brokered Connections",
      "label_cn": "中转连接",
      "default_quantity": 0,
      "unit_display": "connections",
      "note_cn": "前 1000 个免费",
      "order": 3
    },
    "*Data Transfer*": {
      "label": "Hybrid Data Transfer",
      "label_cn": "混合数据传输",
      "unit_display": "GB",
      "visible_when": { "sku_group": ["Standard"] },
      "order": 4
    },
    "*Relay Hours*": {
      "label": "Relay Hours",
      "label_cn": "中继小时数",
      "unit_display": "per 100 hours",
      "visible_when": { "sku_group": ["Standard"] },
      "order": 5
    },
    "*Listener*": {
      "label": "Listener Connections",
      "label_cn": "侦听器连接",
      "visible_when": { "sku_group": ["Standard"] },
      "order": 6
    },
    "*Messages*": {
      "label": "WCF Relay Messages",
      "label_cn": "WCF 中继消息",
      "unit_display": "per 10K",
      "visible_when": { "sku_group": ["Standard"] },
      "order": 7
    },
    "Messaging Unit": {
      "label": "Messaging Units",
      "label_cn": "消息传送单元",
      "default_quantity": 1,
      "unit_display": "per hour",
      "visible_when": { "sku_group": ["Premium"] },
      "order": 1
    }
  },

  "defaults": {
    "selections": {
      "armRegionName": "eastus",
      "sku_group": "Standard"
    }
  }
}
```

#### Azure Firewall

```jsonc
{
  "service_name": "Azure Firewall",
  "display_name_cn": "Azure 防火墙",
  "quantity_model": "per_meter",

  "hidden_dimensions": ["productName"],
  "hidden_meters": ["*Capacity Unit*"],

  "display_maps": {
    "skuName": {
      "entries": [
        { "api_value": "Basic",                       "display": "Basic - VNet",       "group": "Basic",    "order": 1 },
        { "api_value": "Basic Secured Virtual Hub",   "display": "Basic - Hub",        "group": "Basic",    "order": 2 },
        { "api_value": "Standard",                    "display": "Standard - VNet",    "group": "Standard", "order": 3 },
        { "api_value": "Standard Secure Virtual Hub", "display": "Standard - Hub",     "group": "Standard", "order": 4 },
        { "api_value": "Premium",                     "display": "Premium - VNet",     "group": "Premium",  "order": 5 },
        { "api_value": "Premium Secured Virtual Hub", "display": "Premium - Hub",      "group": "Premium",  "order": 6 }
      ],
      "hide_unmapped": false
    }
  },

  "meter_overrides": {
    "*Deployment*": {
      "label": "Deployment (Fixed)",
      "label_cn": "部署费（固定）",
      "default_quantity": 730,
      "unit_display": "hours/month",
      "order": 1
    },
    "*Data Processed*": {
      "label": "Data Processed",
      "label_cn": "数据处理",
      "default_quantity": 1000,
      "unit_display": "GB",
      "order": 2
    }
  },

  "defaults": {
    "selections": {
      "armRegionName": "eastus",
      "skuName": "Standard"
    }
  }
}
```

### B.4 数据流

```
Service Bus 数据流:

1. 用户打开 Service Bus 卡片
   → 获取配置 → 发现 sku_groups → 渲染虚拟 Tier 下拉框: [Basic | Standard | Premium]

2. 用户选择 "Standard"
   → sku_groups["Standard"] = ["Standard", "Hybrid Connections", "WCF Relay"]
   → POST /meters {service_name: "Service Bus", region: "eastus", skuName: ["Standard", "Hybrid Connections", "WCF Relay"]}
   → 返回 3 组 meter (共 ~10 个 meter)

3. 前端用 meter_overrides 匹配 → 排序 → 条件显示:
   Standard 选中时:
     Base Charge:         [1] per hour        → $10.00/mo (730h)
     Messaging Operations: [1] millions       → $0.80 (阶梯第二档)
     Brokered Connections: [0] connections    → $0.00 (免费额度内)
     Hybrid Data Transfer: [0] GB             → $0.00
     Relay Hours:          [0] per 100 hours  → $0.00
     ...
   总计: $10.80/mo

4. 用户修改用量 → 纯本地重算（含阶梯逻辑）

Azure Firewall 数据流:

1. 选择 SKU → display_maps 渲染分组下拉框
2. POST /meters → 返回 3 个 meter → hidden_meters 过滤 Capacity Unit
3. 渲染 2 个输入:
   Deployment:     [730] hours    → $1.25 × 730 = $912.50
   Data Processed: [1000] GB     → $0.016 × 1000 = $16.00
   总计: $928.50/mo
```

### B.5 渲染引擎需支持

| 能力 | 说明 | 复杂度 |
|------|------|-------|
| `sku_groups` | 多个 API skuName 合并为逻辑 Tier | 已有 |
| `meter_overrides` 通配符匹配 | `*xxx*` 模式匹配 meterName | 已有 |
| `visible_when` (sku_group) | 按当前 sku_group 条件显示/隐藏 meter | 已有 |
| `hidden_meters` | 完全隐藏不展示的 meter | 已有 |
| 阶梯 + 免费层计算 | `calculateTieredCost()` 处理多档阶梯 | 已有 |

**结论：Pattern B 现有系统完全覆盖，仅需配置。**

---

## Pattern C: `compute_plus_storage` — Azure SQL Database

### C.1 实际 API 数据

```
serviceName: "SQL Database" (eastus)
总行数: 348, productName: 39 distinct, skuName: 121 distinct
type: Consumption (328) | Reservation (20)
unitOfMeasure: "1 Hour" (228) | "1/Day" (91) | "1 GB/Month" (25) | "1M" (4)
```

**数据按功能分层**：

```
SQL Database
├─ 购买模型选择
│  ├─ DTU 模型 (legacy)
│  │  ├─ Basic:    "SQL Database Single Basic"           → skuName: "1 DTU"    → 1/Day
│  │  ├─ Standard: "SQL Database Single Standard"        → skuName: S0-S12     → 1/Day
│  │  │            (S7 有 6 级阶梯定价!)
│  │  └─ Premium:  "SQL Database Single Premium"         → skuName: P1-P15     → 1/Day
│  │
│  └─ vCore 模型 (modern)
│     ├─ General Purpose:
│     │  ├─ Compute: "...General Purpose - Compute Gen5" → skuName: 1-80 vCore → 1 Hour
│     │  │           (有 RI 1Y/3Y)
│     │  │           (Zone Redundancy 变体: skuName 带 "Zone Redundancy" 后缀)
│     │  ├─ Storage:  "...General Purpose - Storage"     → skuName: GP/GP ZR   → 1 GB/Month
│     │  │            (含免费额度 meter)
│     │  └─ IO:       同 Storage product 下              → "IO Rate Operations" → 1M
│     │
│     ├─ Business Critical:
│     │  ├─ Compute: "...Business Critical - Compute Gen5" → 同结构
│     │  └─ Storage:  "...Business Critical - Storage"
│     │
│     └─ Hyperscale:
│        ├─ Compute: "...Hyperscale - Compute Gen5"
│        └─ Storage:  "...Hyperscale - Storage"
│
├─ Serverless 变体 (vCore, GP/Hyperscale only)
│  └─ "SQL Database General Purpose - Serverless - Compute Gen5"
│
├─ Elastic Pool 变体 (与 Single 共享 productName 前缀 "Single/Elastic Pool")
│
└─ Backup (所有模型共用)
   └─ "...PITR Backup Storage" → skuName: Backup LRS/GRS/RA-GRS/RA-GZRS/ZRS → 1 GB/Month
```

**关键数据点**：

DTU Standard S0:
```
meterName: "S0 DTUs"     unit: 1/Day    price: $0.49/day  → $14.72/mo (×30)
                         还有 "S0 Secondary Active DTUs" (Geo-Replication)
                         还有 "S0 Secondary DTUs" (Geo-Replication standby)
```

DTU Standard S7 (最复杂 — 6 级阶梯):
```
meterName: "10 DTUs"     unit: 1/Day    6 档阶梯 (按 DTU 数量阶梯)
```

vCore GP 2 vCore:
```
meterName: "Zone Redundancy vCore"  unit: 1 Hour  price: varies by vCore count
type: Consumption | Reservation 1Y ($520 total) | Reservation 3Y ($1080 total)
31 档阶梯 (按 vCore 数量，每个 vCore 数一个档位)
```

Storage:
```
meterName: "General Purpose Data Stored"        unit: 1 GB/Month  $0.115/GB
meterName: "General Purpose Data Stored - Free" unit: 1 GB/Month  $0.00 (32GB 免费)
meterName: "General Purpose IO Rate Operations" unit: 1M          $0.20/1M ops
```

Backup:
```
meterName: "Data Stored - Free"  $0.00 (=已分配存储大小的免费备份)
meterName: "LRS Data Stored"     $0.10/GB/Month
meterName: "RA-GRS Data Stored"  $0.20/GB/Month
meterName: "ZRS Data Stored"     $0.125/GB/Month
meterName: "RA-GZRS Data Stored" $0.25/GB/Month
```

### C.2 核心挑战

1. **DTU vs vCore 双模型** — 完全不同的 UI 流、productName、计费单位
2. **日费率 (1/Day)** — DTU 模型独有，计算需 ×30 (月) 而非 ×730 (小时)
3. **多 Section** — Compute + Storage + Backup 独立计费，各有各的 productName 和 cascade
4. **Zone Redundancy** — vCore 模型有普通和 ZR 两种变体，skuName 不同
5. **阶梯 DTU** — S7 有 6 级阶梯按 DTU 数计费，罕见
6. **Elastic Pool** — 与 Single 共享 productName 前缀，需用户先选部署类型
7. **Serverless** — vCore 变体，Compute 用量可自动伸缩，有最小/最大 vCore 设定

### C.3 JSON 配置设计

```jsonc
{
  "service_name": "SQL Database",
  "display_name_cn": "SQL 数据库",
  "quantity_model": "compute_plus_storage",

  // 顶层模式选择器 — 决定后续 UI 结构
  "mode_selector": {
    "field": "purchase_model",
    "label": "Purchase Model",
    "label_cn": "购买模型",
    "options": [
      { "value": "dtu", "label": "DTU-based", "label_cn": "基于 DTU" },
      { "value": "vcore", "label": "vCore-based", "label_cn": "基于 vCore" }
    ],
    "default": "vcore"
  },

  // 部署类型选择器
  "deployment_selector": {
    "field": "deployment",
    "label": "Deployment Type",
    "label_cn": "部署类型",
    "options": [
      { "value": "single", "label": "Single Database", "label_cn": "单一数据库" },
      { "value": "elastic", "label": "Elastic Pool", "label_cn": "弹性池" }
    ],
    "default": "single"
  },

  // ========== Compute Section ==========
  "sections": {
    "compute": {
      "label": "Compute",
      "label_cn": "计算",

      "modes": {
        "dtu": {
          "product_filter": {
            "single": ["SQL Database Single Basic", "SQL Database Single Standard", "SQL Database Single Premium"],
            "elastic": ["SQL Database Elastic Pool - Basic", "SQL Database Elastic Pool - Standard", "SQL Database Elastic Pool - Premium"]
          },
          "billing_unit": "1/Day",
          "monthly_multiplier": 30,          // ← 日费率 ×30 = 月费
          "display_maps": {
            "productName": {
              "entries": [
                { "api_value": "SQL Database Single Basic",    "display": "Basic",    "order": 1 },
                { "api_value": "SQL Database Single Standard", "display": "Standard", "order": 2 },
                { "api_value": "SQL Database Single Premium",  "display": "Premium",  "order": 3 }
              ]
            },
            "skuName": {
              // S0-S12, P1-P15 已可读
              "hide_unmapped": false
            }
          },
          // DTU 模型 — Standard 已包含 250GB 存储, Premium 已包含 500GB
          "included_storage_note_cn": "Standard 含 250GB, Premium 含 500GB 存储"
        },

        "vcore": {
          "product_filter": {
            "single": [
              "SQL Database Single/Elastic Pool General Purpose - Compute Gen5",
              "SQL Database Single/Elastic Pool Business Critical - Compute Gen5",
              "SQL Database SingleDB/Elastic Pool Hyperscale - Compute Gen5"
            ],
            "elastic": [
              // 同一组 productName（包含 "Single/Elastic Pool"）
            ]
          },
          "billing_unit": "1 Hour",
          "monthly_multiplier": 730,
          "has_reservation": true,

          // productName → Tier 子维度
          "product_sub_dimensions": {
            "tier": {
              "label": "Service Tier",
              "label_cn": "服务层级",
              "mapping": {
                "*General Purpose*": "General Purpose",
                "*Business Critical*": "Business Critical",
                "*Hyperscale*": "Hyperscale"
              }
            },
            "compute_gen": {
              "label": "Compute Generation",
              "label_cn": "计算代系",
              "mapping": {
                "*Gen5*": "Gen5",
                "*Gen4*": "Gen4",
                "*DC-Series*": "DC-Series",
                "*FSv2*": "FSv2 Series",
                "*M Series*": "M Series"
              }
            }
          },

          // Zone Redundancy 作为独立开关
          "zone_redundancy": {
            "field": "zone_redundant",
            "label": "Zone Redundancy",
            "label_cn": "区域冗余",
            "sku_suffix": "Zone Redundancy"      // skuName 含此后缀时为 ZR 版本
          }
        }
      }
    },

    // ========== Storage Section ==========
    "storage": {
      "label": "Data Storage",
      "label_cn": "数据存储",
      "visible_when": { "purchase_model": "vcore" },      // DTU 已含存储

      "product_filter": {
        "General Purpose": "SQL Database Single/Elastic Pool General Purpose - Storage",
        "Business Critical": "SQL Database Single/Elastic Pool Business Critical - Storage",
        "Hyperscale": "SQL Database SingleDB Hyperscale - Storage"
      },
      "billing_unit": "1 GB/Month",
      "input": {
        "label": "Storage (GB)",
        "label_cn": "存储 (GB)",
        "default": 32,
        "min": 1,
        "max": 4096,
        "free_tier_gb": 32                        // 前 32GB 免费
      }
    },

    // ========== Backup Section ==========
    "backup": {
      "label": "Backup Storage",
      "label_cn": "备份存储",

      "product_filter": "SQL Database Single/Elastic Pool PITR Backup Storage",
      "billing_unit": "1 GB/Month",

      "cascade_dimensions": ["skuName"],          // 选择备份冗余类型
      "display_maps": {
        "skuName": {
          "entries": [
            { "api_value": "Backup LRS",     "display": "LRS (Locally Redundant)",    "order": 1 },
            { "api_value": "Backup ZRS",     "display": "ZRS (Zone Redundant)",       "order": 2 },
            { "api_value": "Backup RA-GRS",  "display": "RA-GRS (Read-Access Geo)",   "order": 3 },
            { "api_value": "Backup RA-GZRS", "display": "RA-GZRS (Read-Access Geo-Zone)", "order": 4 }
          ]
        }
      },
      "input": {
        "label": "Backup Storage (GB)",
        "label_cn": "备份存储 (GB)",
        "default": 0,
        "note_cn": "等于已分配存储大小的备份为免费"
      }
    }
  },

  "defaults": {
    "selections": {
      "armRegionName": "eastus",
      "purchase_model": "vcore",
      "deployment": "single"
    }
  }
}
```

### C.4 数据流

```
vCore 模型数据流:

1. 用户打开 SQL Database 卡片
   → 配置加载 → quantity_model = "compute_plus_storage"
   → 渲染: [Purchase Model: vCore ▾] [Deployment: Single Database ▾]

2. Compute Section:
   → product_filter 得到目标 productName 列表
   → POST /cascade {service_name: "SQL Database", region: "eastus",
                     productName: [...GP Compute Gen5, ...BC Compute Gen5, ...]}
   → 返回 skuName options: ["1 vCore", "2 vCore", ..., "80 vCore",
                              "1 vCore Zone Redundancy", ...]
   → product_sub_dimensions 解析 → 渲染:
     [Tier: General Purpose ▾] [Gen: Gen5 ▾] [vCores: 4 ▾] ☐ Zone Redundancy

3. 用户选择 GP / Gen5 / 4 vCore
   → POST /meters → 返回 Consumption: $0.xxx/hr + RI 1Y/3Y
   → 计算: $0.xxx × 730 = $xxx/mo

4. Storage Section:
   → product_filter["General Purpose"] 得到 Storage productName
   → POST /meters → 返回 $0.115/GB/Month
   → 渲染: Storage (GB): [32] → (32GB 免费) → $0.00

5. Backup Section:
   → cascade 得到 backup skuName 选项 → display_maps 渲染
   → 渲染: [Backup LRS ▾] Storage: [0] GB → $0.00

6. 总费用 = Compute + Storage + Backup

DTU 模型数据流:

1. 用户切换 Purchase Model 到 "DTU"
   → UI 切换为 DTU 布局，Storage Section 隐藏（DTU 含存储）
   → product_filter["single"] → ["Single Basic", "Single Standard", "Single Premium"]

2. 用户选择 Standard / S2
   → POST /meters → 返回 $2.42/day
   → 计算: $2.42 × 30 = $72.60/mo

3. Backup Section 仍然可见 → 独立计费
```

### C.5 渲染引擎需支持（新增）

| 能力 | 说明 | 复杂度 |
|------|------|-------|
| `mode_selector` | 顶层模式切换（DTU/vCore），切换后整个 UI 重组 | **高** |
| `sections` 多区域布局 | Compute + Storage + Backup 独立渲染、独立查 API | **高** |
| `monthly_multiplier` | 日费率 ×30 vs 小时费率 ×730 | 低 |
| `product_filter` 动态 | 按 mode + deployment + tier 组合确定查询目标 productName | 中 |
| Section 间联动 | Storage section 的 product_filter 依赖 Compute 的 tier 选择 | 中 |
| `zone_redundancy` 开关 | 切换 skuName 后缀变体 | 低 |
| `free_tier_gb` | Storage 免费额度显示 | 低 |

**结论：Pattern C 是最复杂的模式。需要新增 `compute_plus_storage` 渲染模板。核心新增：mode_selector、多 section 布局、section 间联动。**

---

## Pattern D: `resource_dimensions` — Azure Container Instances

### D.1 实际 API 数据

```
serviceName: "Container Instances" (eastus)
总行数: 16
productName: 2 — "Container Instances" | "Container Instances with GPU"
skuName: 6 — Standard | Standard Spot | Confidential containers ACI | K80 | P100 | V100
type: Consumption only
unitOfMeasure: 5 种 — "1 Hour", "1 GB Hour", "1 Second", "100 Seconds", "100 GB Seconds"

Standard SKU (3 meter):
  ┌─────────────────────────────┬──────────┬──────────────┐
  │ meterName                   │ unit     │ price        │
  ├─────────────────────────────┼──────────┼──────────────┤
  │ Standard vCPU Duration      │ 1 Hour   │ $0.0405/hr   │
  │ Standard Memory Duration    │ 1 GB Hour│ $0.00445/GB·hr│
  │ Standard Windows Software   │ 1 Second │ $0.000012/s  │
  └─────────────────────────────┴──────────┴──────────────┘

V100 GPU SKU (3 meter):
  ┌─────────────────────────────┬──────────────┬──────────────┐
  │ meterName                   │ unit         │ price        │
  ├─────────────────────────────┼──────────────┼──────────────┤
  │ vCPU Duration               │ 100 Seconds  │ $0.00xxx     │
  │ Memory Duration             │ 100 GB Seconds│ $0.0000x    │
  │ V100 vGPU Duration          │ 100 Seconds  │ $0.085       │
  └─────────────────────────────┴──────────────┴──────────────┘

区域差异: eastus 有 6 SKU (含 Standard Spot), eastasia 5 SKU (无 Spot)
```

### D.2 核心挑战

1. **用户自定义资源组合** — 没有预定义"实例列表"，用户输入 vCPU/Memory/GPU 数量
2. **混合计量单位** — Standard: "1 Hour" + "1 GB Hour" + "1 Second"；GPU: 全部 "100 Seconds"
3. **单位转换** — "1 Second" 需 ×3600 转小时, "100 Seconds" 需 ×36 转小时
4. **条件显示** — GPU 输入仅 GPU SKU 显示；Windows Software 仅 Standard 显示

### D.3 JSON 配置设计

```jsonc
{
  "service_name": "Container Instances",
  "display_name_cn": "容器实例",
  "quantity_model": "resource_dimensions",
  "quantity_label": "Container Groups",

  "display_maps": {
    "skuName": {
      "entries": [
        { "api_value": "Standard",                    "display": "Linux",        "group": "Standard", "order": 1 },
        { "api_value": "Standard Spot",               "display": "Linux (Spot)", "group": "Standard", "order": 2 },
        { "api_value": "Confidential containers ACI", "display": "Confidential", "group": "Standard", "order": 3 },
        { "api_value": "K80",  "display": "GPU - K80",  "group": "GPU", "order": 10 },
        { "api_value": "P100", "display": "GPU - P100", "group": "GPU", "order": 11 },
        { "api_value": "V100", "display": "GPU - V100", "group": "GPU", "order": 12 }
      ],
      "hide_unmapped": false
    }
  },

  "hidden_dimensions": ["productName"],

  "resource_inputs": [
    {
      "key": "vcpus",
      "label": "Number of vCPUs",
      "label_cn": "vCPU 数量",
      "default": 2, "min": 1, "max": 16, "step": 1,
      "meter_match": "*vCPU Duration"
    },
    {
      "key": "memory_gb",
      "label": "Memory (GB)",
      "label_cn": "内存 (GB)",
      "default": 4, "min": 0.5, "max": 64, "step": 0.5,
      "meter_match": "*Memory Duration"
    },
    {
      "key": "gpu_count",
      "label": "Number of GPUs",
      "label_cn": "GPU 数量",
      "default": 1, "min": 1, "max": 4, "step": 1,
      "meter_match": "*GPU Duration|*vGPU Duration",
      "visible_when": { "skuName": ["K80", "P100", "V100"] }
    }
  ],

  "formula": {
    "type": "resource_sum",
    "duration_hours": 730,
    "unit_conversions": {
      "1 Second":      3600,     // ×3600 → 每小时费率
      "100 Seconds":   36,       // ×36   → 每小时费率
      "100 GB Seconds": 36,      // ×36   → 每 GB·小时费率
      "1 GB Hour":     1,        // 已经是 GB·小时
      "1 Hour":        1         // 已经是小时
    }
  },

  "defaults": {
    "hours_per_month": 730,
    "selections": {
      "armRegionName": "eastus",
      "skuName": "Standard"
    }
  }
}
```

### D.4 数据流

```
1. 用户打开 Container Instances 卡片
   → quantity_model = "resource_dimensions" → 渲染资源输入布局

2. POST /cascade → skuName options → display_maps 交集 → 渲染分组下拉:
     ┌─Standard──────────┐
     │ Linux              │
     │ Linux (Spot)       │
     │ Confidential       │
     ├─GPU────────────────┤
     │ GPU - K80          │
     │ GPU - P100         │
     │ GPU - V100         │
     └────────────────────┘

3. 用户选 "Linux" (api_value = "Standard")
   → POST /meters → 3 个 meter
   → resource_inputs 渲染: [vCPU: 2] [Memory: 4 GB] [GPU: 隐藏]
   → Duration: [730] hours

4. 前端计算 (formula.type = "resource_sum"):
   vCPU:   找 meter "*vCPU Duration" → unit "1 Hour" → conv=1 → $0.0405 × 2 × 730 = $59.13
   Memory: 找 meter "*Memory Duration" → unit "1 GB Hour" → conv=1 → $0.00445 × 4 × 730 = $12.99
   GPU:    gpu_count=0, 跳过
   Total: $72.12/mo

5. 用户切 "GPU - V100"
   → GPU 输入框出现 (visible_when 匹配)
   → POST /meters → 3 个新 meter (全部 "100 Seconds")
   → 计算: 单位转换 ×36 → 得到每小时费率 → × resource × 730
```

### D.5 渲染引擎需支持（新增）

| 能力 | 说明 | 复杂度 |
|------|------|-------|
| `resource_inputs` 渲染 | 动态数量输入框（非固定的 quantity × hours） | **中** |
| `meter_match` | 从 meter 列表中按通配符匹配到正确的 meter | 低 |
| `visible_when` (resource) | 按 cascade 选择条件显示/隐藏输入框 | 已有 |
| `unit_conversions` | 按 unitOfMeasure 自动转换到统一的小时/GB·小时费率 | **中** |
| `formula.resource_sum` | Σ(meter_price × resource_quantity × duration × unit_conv) | **中** |

---

## Pattern E: `sku_base_plus_meter` — VPN Gateway

### E.1 实际 API 数据

```
serviceName: "VPN Gateway" (eastus)
总行数: 30
productName: 1 (唯一值 "VPN Gateway")
skuName: 12 — Basic | VpnGw1-5 | VpnGw1AZ-5AZ | Advanced Connectivity Add-On
type: Consumption only
unitOfMeasure: "1 Hour" (统一)

VpnGw1 (3 meter):
  ┌──────────────────┬────────┬──────────┐
  │ meterName        │ unit   │ price    │
  ├──────────────────┼────────┼──────────┤
  │ VpnGw1           │ 1 Hour │ $0.19/hr │ ← 固定基础费（选了就收）
  │ S2S Connection   │ 1 Hour │ $0.015/hr│ ← × S2S 连接数
  │ P2S Connection   │ 1 Hour │ $0.01/hr │ ← × P2S 连接数
  └──────────────────┴────────┴──────────┘

Basic (3 meter):
  ┌──────────────────┬────────┬───────────┐
  │ meterName        │ unit   │ price     │
  ├──────────────────┼────────┼───────────┤
  │ Basic Gateway    │ 1 Hour │ $0.036/hr │ ← 固定基础费
  │ S2S Connection   │ 1 Hour │ $0.015/hr │
  │ P2S Connection   │ 1 Hour │ $0.01/hr  │
  └──────────────────┴────────┴───────────┘

Advanced Connectivity Add-On (1 meter):
  ┌────────────────────────────┬────────┬──────────┐
  │ meterName                  │ unit   │ price    │
  ├────────────────────────────┼────────┼──────────┤
  │ Advanced Connectivity Unit │ 1 Hour │ $0.035/hr│
  └────────────────────────────┴────────┴──────────┘

规律: 每个 SKU 都有一个同名 meter（基础费）+ S2S + P2S
```

### E.2 核心挑战

1. **基础费不需要用户输入** — 选了 SKU 就收（quantity 固定 = 1）
2. **附加 meter 按连接数** — S2S/P2S Connection 需要用户输入数量
3. **同名 meter** — 基础费 meterName = skuName（如 "VpnGw1"），需自动识别
4. **Add-On** — "Advanced Connectivity Add-On" 是独立附加项

### E.3 JSON 配置设计

```jsonc
{
  "service_name": "VPN Gateway",
  "display_name_cn": "VPN 网关",
  "quantity_model": "sku_base_plus_meter",

  "hidden_dimensions": ["productName"],

  // 基础费自动识别规则: meterName 等于或包含 skuName 时为基础费
  "base_fee_rule": "meter_name_contains_sku",

  "display_maps": {
    "skuName": {
      "entries": [
        { "api_value": "Basic",    "display": "Basic",     "group": "Basic",    "order": 1 },
        { "api_value": "VpnGw1",   "display": "VpnGw1",   "group": "Standard", "order": 2 },
        { "api_value": "VpnGw2",   "display": "VpnGw2",   "group": "Standard", "order": 3 },
        { "api_value": "VpnGw3",   "display": "VpnGw3",   "group": "Standard", "order": 4 },
        { "api_value": "VpnGw4",   "display": "VpnGw4",   "group": "Standard", "order": 5 },
        { "api_value": "VpnGw5",   "display": "VpnGw5",   "group": "Standard", "order": 6 },
        { "api_value": "VpnGw1AZ", "display": "VpnGw1AZ", "group": "AZ-enabled", "order": 7 },
        { "api_value": "VpnGw2AZ", "display": "VpnGw2AZ", "group": "AZ-enabled", "order": 8 },
        { "api_value": "VpnGw3AZ", "display": "VpnGw3AZ", "group": "AZ-enabled", "order": 9 },
        { "api_value": "VpnGw4AZ", "display": "VpnGw4AZ", "group": "AZ-enabled", "order": 10 },
        { "api_value": "VpnGw5AZ", "display": "VpnGw5AZ", "group": "AZ-enabled", "order": 11 }
      ],
      "hide_unmapped": false
    }
  },

  "meter_overrides": {
    "S2S Connection": {
      "label": "Site-to-Site Tunnels",
      "label_cn": "站点到站点隧道",
      "default_quantity": 1,
      "order": 2
    },
    "P2S Connection": {
      "label": "Point-to-Site Connections",
      "label_cn": "点到站点连接",
      "default_quantity": 0,
      "order": 3
    },
    "Advanced Connectivity Unit": {
      "label": "Advanced Connectivity Add-On",
      "label_cn": "高级连接附加组件",
      "default_quantity": 0,
      "note_cn": "需要单独启用",
      "order": 4
    }
  },

  "defaults": {
    "hours_per_month": 730,
    "selections": {
      "armRegionName": "eastus",
      "skuName": "VpnGw1"
    }
  }
}
```

### E.4 数据流

```
1. 用户选择 VpnGw1
   → POST /meters → 3 个 meter

2. 渲染:
   ┌──────────────────────────────────────────────────────┐
   │ VPN Gateway SKU: [VpnGw1 ▾]                          │
   │                                                      │
   │ Gateway Fee (fixed):    $0.19/hr   → $138.70/mo      │  ← 自动识别，不需输入
   │ S2S Tunnels:       [1]  $0.015/hr  → $10.95/mo       │
   │ P2S Connections:   [0]  $0.01/hr   → $0.00/mo        │
   │ ─────────────────────────────────────────────────     │
   │ Total:                              $149.65/mo       │
   └──────────────────────────────────────────────────────┘

3. base_fee_rule = "meter_name_contains_sku":
   meterName="VpnGw1" 包含 skuName="VpnGw1" → 识别为基础费 → quantity 固定=1
   meterName="S2S Connection" 不包含 → 用户输入
   meterName="P2S Connection" 不包含 → 用户输入
```

### E.5 渲染引擎需支持

| 能力 | 说明 | 复杂度 |
|------|------|-------|
| `base_fee_rule` | 自动识别固定基础费 meter（不展示输入框，quantity=1） | **低** |
| 基础费单独展示 | "Gateway Fee: $138.70/mo" 作为固定行，不可编辑 | 低 |
| 附加 meter 输入 | 与 per_meter 相同 | 已有 |

**结论：Pattern E 本质是 per_meter 的变体。核心新增仅 `base_fee_rule` — 一条识别规则。可以作为 `per_meter` 的扩展选项实现，不需要独立的 quantity_model。**

### E.6 替代方案：复用 per_meter

```jsonc
{
  "quantity_model": "per_meter",
  // ...
  "meter_overrides": {
    "VpnGw1|VpnGw2|VpnGw3|VpnGw4|VpnGw5|VpnGw1AZ|...|Basic Gateway": {
      "is_base_fee": true,           // ← per_meter 的新可选属性
      "label": "Gateway Fee (fixed)",
      "fixed_quantity": 730,          // 730 hours/month
      "order": 1
    },
    // ...
  }
}
```

这样不需要新 quantity_model，只需 per_meter 支持 `is_base_fee` / `fixed_quantity` 属性。

---

## Pattern F: `cross_service_composite` — HDInsight

### F.1 实际 API 数据

```
serviceName: "HDInsight" (eastus)
总行数: 191
productName: 19 distinct — 按 VM 系列组织
  "HDInsight D Series"        → D 系列实例
  "HDInsight Ev3 Series"      → Ev3 系列实例
  "HDInsight Eadsv5 Series"   → Eadsv5 系列实例
  "HDInsight Storage"         → 存储 (P30/S30 磁盘)
  "HDInsight ID Broker"       → 身份代理 (固定 A2 v2)
  ...
skuName: 120 distinct — 实例规格 (E2 v3, E16 v3, D2 v2, ...)
type: Consumption (134) | DevTestConsumption (57)
unitOfMeasure: "1 Hour" (186) | "1/Month" (3) | "10K" (2)

HDInsight Ev3 Series — E16 v3 meter:
  ┌────────────────────┬────────┬───────────┐
  │ meterName          │ unit   │ price     │
  ├────────────────────┼────────┼───────────┤
  │ E16 v3/E16s v3     │ 1 Hour │ $1.344/hr │ ← HDInsight 服务费 (仅此)
  └────────────────────┴────────┴───────────┘

  同时需要查: serviceName="Virtual Machines", productName="Virtual Machines ESv3 Series", skuName="E16s v3"
  → VM 费: ~$1.008/hr
  → 总费用/hr = $1.344 + $1.008 = $2.352/hr

HDInsight Storage:
  ┌──────────────────┬──────────┬──────────────┐
  │ meterName        │ unit     │ price        │
  ├──────────────────┼──────────┼──────────────┤
  │ S30 Disk         │ 1/Month  │ $40.96/mo    │
  │ P30 Disk         │ 1/Month  │ $135.17/mo   │
  │ P30 - ZRS Disk   │ 1/Month  │ $202.75/mo   │
  │ Operations       │ 10K      │ $0.002/10K (阶梯) │
  └──────────────────┴──────────┴──────────────┘
```

**Azure Calculator UI — HDInsight 交互**：

```
HDInsight
├─ Cluster Type: [Hadoop | Spark | Kafka | HBase | Interactive Query | ML Services]
├─ Region: [East US ▾]
├─ Nodes:
│  ├─ Head Node:      [E8 v3  ▾] × [2] nodes × [730] hours
│  ├─ Worker Node:    [D4 v2  ▾] × [4] nodes × [730] hours
│  └─ ZooKeeper Node: [A2 v2  ▾] × [3] nodes × [730] hours
├─ Storage:
│  └─ Disk Type: [S30 ▾] × [nodes] disks
└─ 总月费 = Σ(HDInsight_price + VM_price) × nodes × hours + storage
```

### F.2 核心挑战

1. **跨 serviceName 查询** — 一个 estimate card 需要查 "HDInsight" + "Virtual Machines" 两个 service
2. **SKU 对应关系** — HDInsight skuName ≈ VM skuName（如 "E16 v3" → "E16s v3"），但不完全一致
3. **多节点角色** — Head/Worker/ZooKeeper 各有独立的实例选择和数量
4. **Cluster Type** — Hadoop/Spark/Kafka 等决定了可选实例范围和节点角色（不在 API 中）
5. **Storage** — HDInsight Storage 是独立 productName（P30/S30 磁盘 + 操作数）
6. **外部映射** — Cluster Type → 推荐实例规格/默认节点数，这些信息不在 Retail API 中

### F.3 JSON 配置设计

```jsonc
{
  "service_name": "HDInsight",
  "display_name_cn": "HDInsight",
  "quantity_model": "cross_service_composite",

  // 集群类型选择器（不影响 API 查询，仅决定默认值和推荐）
  "cluster_selector": {
    "field": "cluster_type",
    "label": "Cluster Type",
    "label_cn": "集群类型",
    "options": [
      { "value": "hadoop",    "label": "Hadoop",          "label_cn": "Hadoop" },
      { "value": "spark",     "label": "Spark",           "label_cn": "Spark" },
      { "value": "kafka",     "label": "Kafka",           "label_cn": "Kafka" },
      { "value": "hbase",     "label": "HBase",           "label_cn": "HBase" },
      { "value": "query",     "label": "Interactive Query","label_cn": "交互式查询" },
      { "value": "ml",        "label": "ML Services",     "label_cn": "ML 服务" }
    ],
    "default": "spark"
  },

  // 多节点角色定义
  "node_roles": [
    {
      "role": "head",
      "label": "Head Node",
      "label_cn": "头节点",
      "default_count": 2,
      "min_count": 2, "max_count": 2,   // 固定 2 个
      "default_sku": "E8 v3"
    },
    {
      "role": "worker",
      "label": "Worker Node",
      "label_cn": "工作节点",
      "default_count": 4,
      "min_count": 1, "max_count": 100,
      "default_sku": "D4 v2"
    },
    {
      "role": "zookeeper",
      "label": "ZooKeeper Node",
      "label_cn": "ZooKeeper 节点",
      "default_count": 3,
      "min_count": 3, "max_count": 3,   // 固定 3 个
      "default_sku": "A2 v2"
    }
  ],

  // 跨服务价格组合
  "price_composition": {
    "service_fee": {
      "service_name": "HDInsight",
      "label": "HDInsight Service Fee",
      "label_cn": "HDInsight 服务费"
      // 直接按 skuName 查 HDInsight 服务下的价格
    },
    "infra_fee": {
      "service_name": "Virtual Machines",
      "label": "VM Infrastructure Fee",
      "label_cn": "VM 基础设施费",
      // skuName 映射规则: HDInsight "E16 v3" → VM "E16s v3" (加 "s")
      "sku_mapping_rule": "try_add_s_suffix"
      // 特殊情况: HDInsight "D2 v2" → VM "D2 v2" (不需要加 s)
    }
  },

  // 存储 Section
  "storage_section": {
    "product_filter": "HDInsight Storage",
    "display_maps": {
      "skuName": {
        "entries": [
          { "api_value": "S30",      "display": "S30 (Standard HDD, 1TB)",  "order": 1 },
          { "api_value": "P30",      "display": "P30 (Premium SSD, 1TB)",   "order": 2 },
          { "api_value": "P30 - ZRS","display": "P30 ZRS (Premium SSD, 1TB, Zone Redundant)", "order": 3 }
        ]
      }
    },
    "per_node_disks": 1                 // 每节点 1 个磁盘
  },

  "formula": {
    "per_node": "(hdi_price + vm_price) × node_count × hours",
    "storage":  "disk_price × total_disk_count",
    "total":    "Σ per_node + storage"
  },

  "defaults": {
    "hours_per_month": 730,
    "selections": {
      "armRegionName": "eastus",
      "cluster_type": "spark"
    }
  }
}
```

### F.4 数据流

```
1. 用户打开 HDInsight 卡片
   → quantity_model = "cross_service_composite"
   → 渲染 Cluster Type 选择器 + 多节点角色布局

2. 每个节点角色独立 cascade:
   Head Node:
     → POST /cascade {service_name: "HDInsight", region: "eastus"}
     → 返回 productName (HDInsight 系列列表) + skuName (实例列表)
     → 用户选 E8 v3, 数量 = 2

3. 价格查询 (跨服务):
   → POST /meters {service_name: "HDInsight", sku: "E8 v3"} → $0.672/hr (HDI 服务费)
   → POST /meters {service_name: "Virtual Machines", sku: "E8s v3", product: "...ESv3 Series"} → $0.504/hr (VM 费)
   → 节点单价 = $0.672 + $0.504 = $1.176/hr

4. 计算:
   Head:      $1.176 × 2 × 730 = $1,716.96
   Worker:    (hdi_D4v2 + vm_D4v2) × 4 × 730 = $xxx
   ZooKeeper: (hdi_A2v2 + vm_A2v2) × 3 × 730 = $xxx
   Storage:   S30 $40.96 × 9 disks = $368.64
   Total: Σ

5. 用户改节点数/实例规格 → 重新查价格 → 重算
```

### F.5 渲染引擎需支持（新增）

| 能力 | 说明 | 复杂度 |
|------|------|-------|
| `node_roles` 多角色布局 | 渲染 N 组 [实例选择 × 数量 × 小时] | **高** |
| 跨 serviceName 查价格 | 一个节点查两个 API（HDInsight + VM） | **高** |
| `sku_mapping_rule` | HDInsight SKU → VM SKU 名称映射 | 中 — 规则可能不完全覆盖 |
| `cluster_selector` | 决定默认值/推荐实例（非 API 驱动） | 低 |
| Storage section | 独立的存储选择 + 按节点数计算磁盘数 | 中 |

**结论：Pattern F 复杂度最高（跨服务 + 多角色 + SKU 映射）。MVP 阶段建议仅展示 HDInsight 服务费（Pattern A 近似），VM 基础设施费标注"另行计算"。**

---

## 统一 Schema 总结

### quantity_model 决策树

```
用户选择产品后，根据 quantity_model 决定渲染模板:

instances_x_hours (Pattern A)
  → 标准 cascade + display_maps/product_sub_dimensions
  → 数量 × 小时 输入
  → unit_price × quantity × hours
  → 产品: VM, App Service, Redis, Power BI Embedded

per_meter (Pattern B + E)
  → cascade + sku_groups
  → 每 meter 独立输入（支持 is_base_fee 固定费）
  → Σ tiered_price(meter, quantity)
  → 产品: Service Bus, Firewall, Event Grid, SignalR, VPN Gateway, Key Vault

compute_plus_storage (Pattern C)                    ← 新增
  → mode_selector + 多 section 布局
  → Compute cascade + Storage input + Backup cascade
  → Σ section_cost
  → 产品: SQL Database, MySQL, PostgreSQL, Cosmos DB

resource_dimensions (Pattern D)                     ← 新增
  → cascade(region + SKU) + resource_inputs
  → formula: Σ(meter_price × resource × duration × unit_conv)
  → 产品: Container Instances

cross_service_composite (Pattern F)                 ← 新增，MVP 暂缓
  → node_roles × (service_fee + infra_fee)
  → 跨 serviceName 查价格
  → 产品: HDInsight, Databricks, Azure ML
```

### 配置 JSON 结构（所有模式的超集）

```jsonc
{
  // ===== 所有模式必填 =====
  "service_name": "string",
  "display_name_cn": "string",
  "quantity_model": "instances_x_hours | per_meter | compute_plus_storage | resource_dimensions | cross_service_composite",

  // ===== 通用可选 =====
  "display_maps": {},              // 所有模式 — 下拉框显示增强
  "hidden_dimensions": [],         // 所有模式 — 隐藏级联维度
  "excluded_products": [],         // 所有模式 — 排除的 productName
  "defaults": {},                  // 所有模式 — 默认值

  // ===== instances_x_hours 专属 =====
  "product_sub_dimensions": {},    // productName → 子维度解析规则

  // ===== per_meter 专属 =====
  "sku_groups": {},                // 多 skuName 合并为逻辑 Tier
  "meter_overrides": {},           // meter 显示覆盖 + 排序 + is_base_fee
  "hidden_meters": [],             // 隐藏 meter

  // ===== compute_plus_storage 专属 =====
  "mode_selector": {},             // 顶层模式切换 (DTU/vCore)
  "deployment_selector": {},       // 部署类型 (Single/Elastic)
  "sections": {                    // 多 section 布局
    "compute": {},
    "storage": {},
    "backup": {}
  },

  // ===== resource_dimensions 专属 =====
  "resource_inputs": [],           // 资源输入项定义
  "formula": {},                   // 计算公式 + unit_conversions

  // ===== cross_service_composite 专属 =====
  "cluster_selector": {},          // 集群类型选择
  "node_roles": [],                // 多节点角色定义
  "price_composition": {},         // 跨服务价格组合规则
  "storage_section": {}            // 存储 section
}
```

### 实现优先级

```
Phase 1 (已有):
  ✅ instances_x_hours (A) — VM, App Service, Redis
  ✅ per_meter (B+E) — Service Bus, Firewall, VPN Gateway

Phase 2 (扩展已有):
  🔲 product_sub_dimensions — VM/App Service 的 productName 子维度解析
  🔲 is_base_fee — VPN Gateway 等的固定基础费识别
  🔲 display_maps 通用化

Phase 3 (新增模式):
  🔲 resource_dimensions (D) — Container Instances
     工作量: resource_inputs 渲染 + formula 计算引擎 + unit_conversions

Phase 4 (最复杂):
  🔲 compute_plus_storage (C) — SQL Database
     工作量: mode_selector + 多 section 布局 + section 间联动
     影响面最广 — 所有 PaaS 数据库都用此模式

Phase 5 (MVP 后):
  🔲 cross_service_composite (F) — HDInsight
     工作量: 跨 serviceName 查询 + node_roles + SKU 映射
```

---

## 对 data-modeling 和 implement-plan 的影响

### 架构变更

旧架构：
```
Azure.cn CSV → downloader → parser → importer → PostgreSQL → Production API → 前端
                                                                   ↑
                                                          固定级联逻辑
```

新架构：
```
Azure Retail API (Global/CN) → 动态查询 → 前端
         ↑                        ↑
    prices.azure.com         通用 cascade/meters API
    prices.azure.cn          (后端代理 + 缓存)
         ↓                        ↑
  per-product JSON 配置 → 定义 UI 结构 + 价格映射规则
  (存储在 DB/文件系统)
```

### 需要重构的模块

| 模块 | 当前 | 目标 |
|------|------|------|
| 数据源 | CSV 下载 + PostgreSQL 导入 | Retail API 代理 + 缓存层 |
| 级联 API | 固定 5 维度级联 | 通用级联 + product_sub_dimensions + mode_selector |
| Meters API | 简单 meter 列表 | 支持 sku_groups + meter_overrides + cross_service |
| 前端渲染 | 硬编码 3 种布局 | JSON 驱动的通用渲染引擎 (5 种 quantity_model) |
| 配置管理 | service_configs 表 | 扩展字段 + CMS 表单适配 |
| 价格计算 | pricing.js 2 种模式 | 5 种 formula 引擎 (instances, sum_meters, resource_sum, sections_sum, cross_service) |

### data-modeling.md 重写方向

1. 删除 CSV 数据模型（retail_prices 表、product_catalog 视图）
2. 新增 Retail API 代理层设计（缓存策略、Global/CN 切换）
3. 新增 per-product JSON 配置的存储模型（service_configs 表扩展）
4. 保留 display_maps、sku_groups 等配置机制定义

### implement-plan.md 重写方向

1. Phase 1: Retail API 代理 + 缓存层（替代 CSV 导入）
2. Phase 2: product_sub_dimensions + display_maps 通用化
3. Phase 3: resource_dimensions (Pattern D) 前端渲染引擎
4. Phase 4: compute_plus_storage (Pattern C) 多 section 布局
5. Phase 5: cross_service_composite (Pattern F) 跨服务查询

---

## 验证命令参考

```bash
# Pattern A
uv run python scripts/explore_global_api.py service "Virtual Machines" --region eastus
uv run python scripts/explore_global_api.py productparse "Azure App Service" --region eastus
uv run python scripts/explore_global_api.py meters "Azure App Service" --region eastus --product "Azure App Service Premium v3 Plan" --sku "P1 v3"

# Pattern B
uv run python scripts/explore_global_api.py meters "Service Bus" --region eastus --sku Standard
uv run python scripts/explore_global_api.py meters "Azure Firewall" --region eastus --sku Standard

# Pattern C
uv run python scripts/explore_global_api.py service "SQL Database" --region eastus
uv run python scripts/explore_global_api.py meters "SQL Database" --region eastus --product "SQL Database Single Standard"
uv run python scripts/explore_global_api.py meters "SQL Database" --region eastus --product "SQL Database Single/Elastic Pool General Purpose - Compute Gen5"
uv run python scripts/explore_global_api.py meters "SQL Database" --region eastus --product "SQL Database Single/Elastic Pool General Purpose - Storage"
uv run python scripts/explore_global_api.py meters "SQL Database" --region eastus --product "SQL Database Single/Elastic Pool PITR Backup Storage"

# Pattern D
uv run python scripts/explore_global_api.py meters "Container Instances" --region eastus --product "Container Instances" --sku Standard
uv run python scripts/explore_global_api.py meters "Container Instances" --region eastus --product "Container Instances with GPU" --sku V100

# Pattern E
uv run python scripts/explore_global_api.py meters "VPN Gateway" --region eastus --sku VpnGw1
uv run python scripts/explore_global_api.py meters "VPN Gateway" --region eastus --sku Basic

# Pattern F
uv run python scripts/explore_global_api.py service "HDInsight" --region eastus
uv run python scripts/explore_global_api.py meters "HDInsight" --region eastus --product "HDInsight Ev3 Series"
uv run python scripts/explore_global_api.py meters "HDInsight" --region eastus --product "HDInsight Storage"
```
