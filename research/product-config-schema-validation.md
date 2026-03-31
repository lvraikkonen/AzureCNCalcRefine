# 产品配置 JSON Schema — "现代化 CN Legacy" 方案设计与验证

> **方案定位**：每个产品一个 JSON 配置（描述 UI 结构 + 价格映射），价格从 Retail API 动态获取。
> **核心决策**：采用"思路3"（混合方案）— 配置定义结构/映射，API 提供可用选项，前端取交集渲染。
> **数据源**：Azure Global Retail Prices API
> **日期**：2026-03-30（初版）→ 2026-03-31（融合思路3 + CMS 设计 + 区域验证）

---

## 一、方案背景与演进

### 三种架构对比

| | CN Legacy (已废弃) | Azure Global Calculator | 我们的方案 |
|---|---|---|---|
| 数据来源 | 手动维护价格，内嵌在 68K 行 JS 中 | 手动维护，per-product Calculator API | **Retail API 自动获取** |
| 产品配置 | 固定 4 层级: Types > Features > Sizes | per-product React 组件 (~2.9MB modules.js) | **per-product JSON 配置** |
| UI 渲染 | 前端根据固定层级渲染 | 179 个前端硬编码组件 | **通用渲染引擎 + JSON 驱动** |
| 区域处理 | 写死在 slug 名字里 | dimensions 动态筛选 | **cascade API 动态筛选** |
| 新增产品 | 编辑 JS 文件 | 写 React 组件 (~25KB/产品) | **写 JSON 配置 (~50-100 行)** |
| Savings Plan | 无 | 内含 | **cascade + type/term 自动提取** |

### 演进路径

```
CN Legacy (2018?)            →   Azure Global (2025)
一个大文件, 价格内嵌               per-product API + React 组件
Types > Features > Sizes         schema + offers + skus + resources
手动维护价格                       手动维护价格（结构更精细）
                    ↘                         ↙
               我们的方案 (取两者之长)
               per-product JSON (UI 结构)
               + Retail API (价格自动获取)
               + 通用渲染引擎 (不写前端代码)
```

### 与现有系统的关系

现有系统已实现：
- `instances_x_hours` 模式（VM、Redis、App Service）— 标准级联 + 数量 × 小时
- `per_meter` 模式（Service Bus、Firewall、SignalR）— 级联 + 多 meter 独立输入
- Config Admin CMS 的 draft/publish/archive 工作流

本方案在此基础上**增量扩展**：
- 新增 `resource_dimensions` 模式（Container Instances 等）
- 新增 `display_maps` 机制（所有模式通用的区域自适应下拉框增强）
- 扩展 CMS 表单以支持新字段

---

## 二、核心机制："思路3" — display_maps

### 问题

dropdown 选项需要同时满足两个需求：
1. **区域自适应** — 不同区域的 SKU 可用性不同（如 Standard Spot 在 eastasia 不可用）
2. **显示定制** — 需要控制选项的显示名、中文名、排序、分组

如果选项写死在配置中 → 无法适应区域差异。如果完全由 API 返回 → 无法控制显示效果。

### 解决方案：配置定义映射，API 提供可用列表，前端取交集

```
┌─────────────────────────┐     ┌─────────────────────────────┐
│  配置中的 display_maps   │     │  API 返回的实际可用选项       │
│                         │     │  (随 region 变化)             │
│  "Standard" → "Linux"   │     │  eastus:   [Standard,        │
│  "Std Spot" → "Spot"    │     │             Standard Spot,   │
│  "K80"      → "GPU-K80" │     │             K80, V100]       │
│  "V100"     → "GPU-V100"│     │  eastasia: [Standard,        │
└────────────┬────────────┘     │             K80, V100]       │
             │                  └──────────────┬──────────────┘
             │         前端取交集               │
             └──────────────┬──────────────────┘
                            ▼
               eastus 渲染:    ┌─标准──────────┐
                               │ Linux         │
                               │ Linux (Spot)  │  ← Spot 在
                               ├─GPU───────────┤
                               │ GPU - K80     │
                               │ GPU - V100    │
                               └───────────────┘

               eastasia 渲染:  ┌─标准──────────┐
                               │ Linux         │  ← Spot 不在，自动消失
                               ├─GPU───────────┤
                               │ GPU - K80     │
                               │ GPU - V100    │
                               └───────────────┘
```

### display_maps 数据结构

```jsonc
"display_maps": {
  "skuName": {                           // 目标维度（与 cascade 维度名对应）
    "entries": [
      {
        "api_value": "Standard",         // Retail API 中的原始值
        "display": "Linux",              // 英文显示名
        "display_cn": "Linux",           // 中文显示名
        "group": "Standard",             // 下拉框分组标题（渲染为 <optgroup>）
        "order": 1                       // 排序权重
      },
      // ...
    ],
    "hide_unmapped": false               // false = API 新增的未映射值自动显示（运营友好）
                                         // true  = 只显示映射表中有的值（严格控制）
  }
}
```

### 区域差异实测数据

| 产品 | 差异类型 | 示例 |
|------|---------|------|
| Container Instances | SKU 可用性不同 | eastus 有 Standard Spot, eastasia 没有 |
| Redis Cache | 产品家族不同 | Managed Redis 系列可能不在所有区域 |
| Blob Storage | SKU 基本一致 | 12 个 SKU 在所有 Global 区域都有 |
| 所有产品 | 价格不同 | Blob Hot LRS: eastus $0.0208, brazilsouth $0.0326 |

**结论**：价格差异由 Retail API 自动处理。SKU 可用性差异由 display_maps 交集机制自动处理。JSON 配置本身不需要包含任何区域相关信息。

---

## 三、产品验证 1: Redis Cache (Pattern A — 最简单)

### Retail API 数据结构

```
serviceName: "Redis Cache"
productName: 10 个，编码了 tier/family
  - "Azure Redis Cache Basic"      → tier=Basic, sizes: C0-C6
  - "Azure Redis Cache Standard"   → tier=Standard, sizes: C0-C6
  - "Azure Redis Cache Premium"    → tier=Premium, sizes: P1-P5
  - "Azure Redis Cache Enterprise" → tier=Enterprise, sizes: E1-E400
  - "Azure Redis Cache Enterprise Flash" → tier=Enterprise Flash
  - "Azure Redis Cache Isolated"   → tier=Isolated
  - "Azure Managed Redis - Balanced/Compute/Flash/Memory" → 新一代 (4 个)
type: Consumption + Reservation (1Y/3Y)
unitOfMeasure: 全部 "1 Hour"
每个 SKU 只有 1 个 meter
```

### 产品配置 JSON

```jsonc
{
  "service_name": "Redis Cache",
  "display_name_cn": "Azure Redis 缓存",
  "quantity_model": "instances_x_hours",
  "quantity_label": "Instances",

  "display_maps": {
    "skuName": {
      "entries": [
        // Basic tier
        { "api_value": "C0", "display": "Basic C0 (250 MB)", "display_cn": "基本 C0 (250 MB)", "group": "Basic", "order": 1 },
        { "api_value": "C1", "display": "Basic C1 (1 GB)",   "display_cn": "基本 C1 (1 GB)",   "group": "Basic", "order": 2 },
        // ... C2-C6
        // Standard tier
        { "api_value": "C0", "display": "Standard C0 (250 MB)", "display_cn": "标准 C0 (250 MB)", "group": "Standard", "order": 10 },
        { "api_value": "C1", "display": "Standard C1 (1 GB)",   "display_cn": "标准 C1 (1 GB)",   "group": "Standard", "order": 11 },
        // ... C2-C6
        // Premium tier
        { "api_value": "P1", "display": "Premium P1 (6 GB)",  "display_cn": "高级 P1 (6 GB)",  "group": "Premium", "order": 20 },
        { "api_value": "P2", "display": "Premium P2 (13 GB)", "display_cn": "高级 P2 (13 GB)", "group": "Premium", "order": 21 },
        // ... P3-P5
        // Enterprise tier
        { "api_value": "E1",  "display": "Enterprise E1",  "display_cn": "企业版 E1",  "group": "Enterprise", "order": 30 },
        { "api_value": "E5",  "display": "Enterprise E5",  "display_cn": "企业版 E5",  "group": "Enterprise", "order": 31 },
        // ... E10-E400
        // Enterprise Flash
        { "api_value": "F300",  "display": "Enterprise Flash F300",  "display_cn": "企业闪存 F300",  "group": "Enterprise Flash", "order": 40 },
        { "api_value": "F700",  "display": "Enterprise Flash F700",  "display_cn": "企业闪存 F700",  "group": "Enterprise Flash", "order": 41 },
        { "api_value": "F1500", "display": "Enterprise Flash F1500", "display_cn": "企业闪存 F1500", "group": "Enterprise Flash", "order": 42 }
      ],
      "hide_unmapped": false
    }
  },

  "defaults": {
    "hours_per_month": 730,
    "selections": {
      "armRegionName": "eastus",
      "skuName": "C1"
    }
  }
}
```

### 数据流

```
1. 用户打开 Redis Cache 卡片
   → GET /explore/service-config/Redis%20Cache       (获取配置)
   → POST /explore/cascade {selections: {}}          (获取所有维度选项)

2. Cascade 返回 skuName.options = ["C0", "C1", ..., "P1", ..., "E1", ...]
   → 前端用 display_maps.skuName.entries 取交集
   → 渲染分组下拉框: [Basic: C0/C1/... | Standard: C0/C1/... | Premium: P1/P2/... | ...]

3. 用户选择 "Premium P1"
   → selections.skuName = "P1" (存储 api_value)
   → POST /explore/meters {service_name, region: "eastus", sku: "P1"}
   → 返回: [{meter: "P1 Cache Instance", type: "Consumption", unit_price: $0.554/hr},
            {meter: "P1 Cache Instance", type: "Reservation", term: "1 Year", ...},
            {meter: "P1 Cache Instance", type: "Reservation", term: "3 Years", ...}]

4. 本地计算: $0.554 × 1 instance × 730 hours = $404.42/mo
   1Y RI: $258.83/mo (节省 36%)
   3Y RI: $182.00/mo (节省 55%)

5. 用户切换 region → 重新 cascade → display_maps 交集自动过滤不可用 SKU
```

**结论：Pattern A 产品极其简单。现有级联系统完全复用，display_maps 仅作为可选增强（分组 + 中文名）。这类产品甚至可以用默认配置，不需要独立 JSON 文件。**

---

## 四、产品验证 2: Container Instances (Pattern D — 中等复杂)

### Retail API 数据结构

```
serviceName: "Container Instances"
productName: 2 个
  - "Container Instances"           → Standard / Confidential / Standard Spot
  - "Container Instances with GPU"  → K80 / P100 / V100

Standard SKU 的 3 个 meter:
  - "Standard vCPU Duration"            → $0.0405/hr
  - "Standard Memory Duration"          → $0.00445/GB·hr
  - "Standard Windows Software Duration"→ $0.000012/s (仅 Windows)

unitOfMeasure 混合: "1 Hour", "1 GB Hour", "1 Second", "100 Seconds", "100 GB Seconds"
type: 仅 Consumption（Savings Plan 只在 Calculator API 中有，Retail API 无）

区域差异: eastus 有 6 个 SKU (含 Standard Spot), eastasia 只有 5 个 (无 Spot)
```

### 产品配置 JSON

```jsonc
{
  "service_name": "Container Instances",
  "display_name_cn": "容器实例",
  "quantity_model": "resource_dimensions",
  "quantity_label": "Container Groups",

  // 思路3 核心：display_maps 处理区域差异
  "display_maps": {
    "skuName": {
      "entries": [
        { "api_value": "Standard",                    "display": "Linux",            "display_cn": "Linux",         "group": "Standard",     "order": 1 },
        { "api_value": "Standard Spot",               "display": "Linux (Spot)",     "display_cn": "Linux (Spot)",  "group": "Standard",     "order": 2 },
        { "api_value": "Confidential containers ACI", "display": "Confidential",     "display_cn": "机密容器",       "group": "Standard",     "order": 3 },
        { "api_value": "K80",                         "display": "GPU - K80",        "display_cn": "GPU - K80",     "group": "GPU",          "order": 10 },
        { "api_value": "P100",                        "display": "GPU - P100",       "display_cn": "GPU - P100",    "group": "GPU",          "order": 11 },
        { "api_value": "V100",                        "display": "GPU - V100",       "display_cn": "GPU - V100",    "group": "GPU",          "order": 12 }
      ],
      "hide_unmapped": false
    }
  },

  // 新概念：资源输入项（替代简单的 quantity 输入）
  "resource_inputs": [
    {
      "key": "vcpus",
      "label": "Number of vCPUs",
      "label_cn": "vCPU 数量",
      "default": 2, "min": 1, "max": 16, "step": 1,
      "meter_mapping": "vCPU Duration"
    },
    {
      "key": "memory_gb",
      "label": "Memory (GB)",
      "label_cn": "内存 (GB)",
      "default": 4, "min": 0.5, "max": 64, "step": 0.5,
      "unit_suffix": "GB",
      "meter_mapping": "Memory Duration"
    },
    {
      "key": "gpu_count",
      "label": "Number of GPUs",
      "label_cn": "GPU 数量",
      "default": 0, "min": 0, "max": 4, "step": 1,
      "meter_mapping": "GPU Duration",
      "visible_when": { "field": "skuName", "pattern": "K80|P100|V100" }
    }
  ],

  // 计算公式
  "formula": {
    "type": "resource_sum",
    "duration_default": 730,
    "terms": [
      { "meter_match": "vCPU Duration",             "input_key": "vcpus" },
      { "meter_match": "Memory Duration",           "input_key": "memory_gb" },
      { "meter_match": "GPU Duration",              "input_key": "gpu_count" },
      { "meter_match": "Windows Software Duration", "input_key": "vcpus", "unit_conversion": 3600 }
    ]
  },

  "hidden_dimensions": ["productName"],
  "hidden_meters": ["Windows Software Duration"],

  "defaults": {
    "hours_per_month": 730,
    "selections": {
      "armRegionName": "eastus",
      "skuName": "Standard"
    },
    "resource_defaults": {
      "vcpus": 2,
      "memory_gb": 4,
      "gpu_count": 0
    }
  }
}
```

### 数据流

```
1. 用户打开 Container Instances 卡片
   → 获取配置: quantity_model = "resource_dimensions" → 激活资源输入渲染路径

2. POST /cascade {selections: {armRegionName: "eastus"}}
   → skuName.options = ["Standard", "Standard Spot", "Confidential...", "K80", "P100", "V100"]
   → display_maps 交集 → 渲染分组下拉:
     ┌─Standard─────────────┐
     │ Linux                │
     │ Linux (Spot)         │
     │ Confidential         │
     ├─GPU──────────────────┤
     │ GPU - K80            │
     │ GPU - P100           │
     │ GPU - V100           │
     └──────────────────────┘

3. 用户选择 "Standard" (Linux)
   → POST /meters {sku: "Standard", region: "eastus"}
   → 返回 3 个 meter: vCPU ($0.0405/hr), Memory ($0.00445/GB·hr), Windows ($0.000012/s)
   → 渲染 resource_inputs: [vCPU: 2] [Memory: 4 GB] [GPU: 隐藏]
   → 渲染 duration: 730 hours

4. 前端本地计算 (formula: resource_sum):
   vCPU:   $0.0405 × 2 × 730 = $59.13
   Memory: $0.00445 × 4 × 730 = $12.99
   Total: $72.12/mo

5. 用户改 vCPU 为 4 → 纯本地重算，不调 API:
   vCPU:   $0.0405 × 4 × 730 = $118.26
   Memory: $0.00445 × 4 × 730 = $12.99
   Total: $131.25/mo

6. 用户切换到 "GPU - V100"
   → visible_when 匹配 → GPU 输入框出现
   → POST /meters {sku: "V100"} → 新 meter 单价
   → formula 重算，含 GPU 项

7. 用户切换 region 到 eastasia
   → POST /cascade → Standard Spot 不在返回列表中
   → display_maps 交集 → Spot 自动从下拉框消失
```

### 发现的 schema 扩展点

| 扩展点 | 说明 | 必要性 |
|--------|------|-------|
| `resource_inputs` | 新 quantity_model 的核心 — 定义 vCPU/Memory/GPU 等输入项 | 必须 |
| `formula` | 定义如何从 meter 单价 × 资源数量 × 时长计算总价 | 必须 |
| `visible_when` | 条件显示/隐藏（GPU 输入仅 GPU SKU 显示） | 必须 |
| `hidden_meters` | 隐藏 Windows Software 等不直接展示的 meter | 已有 |
| `unit_conversion` | 处理 Retail API 的 "1 Second" vs "1 Hour" 差异 | 必须 |

---

## 五、产品验证 3: Blob Storage (Pattern B + 阶梯 — 最复杂)

### Retail API 数据结构

```
serviceName: "Storage"
productName: "Blob Storage"
skuName: 12 个，编码了 access_tier × redundancy
  Hot LRS / Hot GRS / Hot RA-GRS
  Cool LRS / Cool GRS / Cool RA-GRS
  Cold LRS / Cold GRS / Cold RA-GRS
  Archive LRS / Archive GRS / Archive RA-GRS

每个 SKU 7-9 个 meter:
  - Data Stored (GB/Month) — 有阶梯! 0/50TB/500TB 三档
  - Write Operations (10K)
  - Read Operations (10K)
  - All Other Operations (10K)
  - List and Create Container Operations (10K)
  - Data Retrieval (GB) — Cool/Cold/Archive only
  - Data Write (GB) — Archive only
  - Early Delete (GB) — Cool/Cold/Archive only
  - Priority Data Retrieval (GB) — Archive only
  - Priority Read Operations (10K) — Archive only
  - Index Tags (10K/Month)
```

### 产品配置 JSON

```jsonc
{
  "service_name": "Storage",
  "api_service_name": "Storage",
  "display_name_cn": "Blob 存储",
  "quantity_model": "per_meter",

  // skuName 由两个下拉框拼接构建
  "sku_template": "{accessTier} {redundancy}",

  // 自定义维度（不走标准级联）
  "custom_dimensions": [
    {
      "field": "redundancy",
      "label": "Redundancy",
      "label_cn": "冗余类型",
      "options": [
        { "value": "LRS",    "label": "LRS (Locally Redundant)",       "label_cn": "LRS (本地冗余)" },
        { "value": "GRS",    "label": "GRS (Geo-Redundant)",           "label_cn": "GRS (异地冗余)" },
        { "value": "RA-GRS", "label": "RA-GRS (Read-Access Geo)",      "label_cn": "RA-GRS (读取访问异地冗余)" }
      ],
      "default": "LRS"
    },
    {
      "field": "accessTier",
      "label": "Access Tier",
      "label_cn": "访问层",
      "options": [
        { "value": "Hot",     "label": "Hot",     "label_cn": "热" },
        { "value": "Cool",    "label": "Cool",    "label_cn": "冷" },
        { "value": "Cold",    "label": "Cold",    "label_cn": "冷（低频）" },
        { "value": "Archive", "label": "Archive", "label_cn": "存档" }
      ],
      "default": "Hot"
    }
  ],

  // Meter 动态发现 + 覆盖配置
  "meter_overrides": {
    "*Data Stored": {
      "label": "Data Storage", "label_cn": "数据存储",
      "default_quantity": 1000, "unit_display": "GB/Month",
      "note": "阶梯定价: 0-50TB, 50-500TB, 500TB+",
      "order": 1
    },
    "*Write Operations": {
      "label": "Write Operations", "label_cn": "写入操作",
      "default_quantity": 100, "unit_display": "x 10K",
      "order": 2
    },
    "*Read Operations": {
      "label": "Read Operations", "label_cn": "读取操作",
      "default_quantity": 100, "unit_display": "x 10K",
      "order": 3
    },
    "All Other Operations": {
      "label": "Other Operations", "label_cn": "其他操作",
      "default_quantity": 100, "unit_display": "x 10K",
      "order": 4
    },
    "*List and Create*": {
      "label": "List/Create Operations", "label_cn": "列表/创建操作",
      "default_quantity": 100, "unit_display": "x 10K",
      "order": 5
    },
    "*Data Retrieval": {
      "label": "Data Retrieval", "label_cn": "数据检索",
      "visible_when": { "accessTier": ["Cool", "Cold", "Archive"] },
      "order": 6
    },
    "*Early Delete": {
      "label": "Early Deletion", "label_cn": "提前删除",
      "visible_when": { "accessTier": ["Cool", "Cold", "Archive"] },
      "order": 7
    },
    "*Priority*": {
      "visible_when": { "accessTier": ["Archive"] },
      "order": 8
    },
    "*Index Tags*": {
      "label": "Blob Index Tags", "label_cn": "Blob 索引标签",
      "order": 9
    }
  },

  "hidden_dimensions": ["productName", "skuName"],

  "formula": "sum_meters_tiered",

  "defaults": {
    "selections": {
      "armRegionName": "eastus"
    }
  }
}
```

### 数据流

```
1. 用户打开 Blob Storage 卡片
   → 获取配置: 发现 sku_template + custom_dimensions

2. 渲染自定义下拉框: [Redundancy: LRS/GRS/RA-GRS] [Access Tier: Hot/Cool/Cold/Archive]

3. 用户选择 redundancy=LRS, accessTier=Hot
   → sku_template 拼接: "Hot LRS"
   → POST /meters {service_name: "Storage", product: "Blob Storage", sku: "Hot LRS", region: "eastus"}
   → 返回 8 个 meter:
     - Hot LRS Data Stored: $0.0208/GB (tier0), $0.019968 (tier 50TB+), $0.019136 (tier 500TB+)
     - Hot LRS Write Operations: $0.05/10K
     - Hot Read Operations: $0.004/10K
     - All Other Operations: $0.004/10K
     - ... (Data Retrieval 等 Cool/Archive only 的 meter 不在 Hot SKU 中)

4. 前端用 meter_overrides 匹配 meter 名 → 应用标签、排序、默认数量
   → 渲染 meter 输入表:
     Data Storage:    [1000] GB/Month    $20.80   (阶梯: 0-50TB $0.0208, 50-500TB $0.019968...)
     Write Ops:       [100]  x 10K       $5.00
     Read Ops:        [100]  x 10K       $0.40
     Other Ops:       [100]  x 10K       $0.40
     List/Create:     [100]  x 10K       $5.00
     Blob Index Tags: [0]    x 10K/Month $0.00
     Total: $31.60/mo

5. 用户切换 accessTier 到 Archive
   → sku_template 拼接: "Archive LRS"
   → POST /meters → 返回不同 meter 集合（含 Data Retrieval, Early Delete, Priority）
   → visible_when 匹配 → Data Retrieval, Early Delete 出现; Priority 出现
```

### 发现的 schema 扩展点

| 扩展点 | 说明 | 必要性 |
|--------|------|-------|
| `sku_template` | 多下拉框拼接 skuName（不走标准级联） | Blob Storage 等复合 SKU 产品必须 |
| `custom_dimensions` | 配置中定义的下拉框（选项静态，不依赖 API） | Blob Storage 的 redundancy/accessTier |
| `meter_overrides` | 通配符匹配 meter 名 → 覆盖标签、排序、条件显示 | 动态 meter 列表的显示定制 |
| 阶梯 + 非阶梯混合 | 同一 SKU 下部分 meter 有阶梯（Data Stored），部分没有 | 前端已有 calculateTieredCost() 处理 |

---

## 六、Schema 表达力总结

### 配置结构（核心 + 扩展）

```
固定部分（所有产品必填）:
  service_name          — 服务名称
  display_name_cn       — 中文显示名
  quantity_model        — "instances_x_hours" | "per_meter" | "resource_dimensions"
  defaults              — 默认值

通用扩展（所有模式可选）:
  display_maps          — 思路3 核心：API 值 → 显示名映射（区域自适应）
  hidden_dimensions     — 隐藏的级联维度
  dimension_labels      — 维度标签覆盖

per_meter 扩展:
  sku_groups            — 虚拟 Tier → API SKU 映射
  meter_labels          — meter 显示名
  meter_order           — meter 排序
  hidden_meters         — 隐藏的 meter
  meter_free_quota      — 跨 meter 免费额度
  sku_template          — 多下拉框拼接 skuName
  custom_dimensions     — 配置定义的下拉框
  meter_overrides       — meter 显示覆盖 + 条件可见

resource_dimensions 扩展:
  resource_inputs       — 资源输入项定义（vCPU, Memory, GPU 等）
  formula               — 计算公式（resource_sum + terms）
```

### Section Types 与 quantity_model 的关系

| quantity_model | 级联维度渲染 | 数量输入渲染 | 价格计算 |
|---------------|-------------|-------------|---------|
| `instances_x_hours` | 标准 cascade（可选 display_maps 增强） | 数量 × 小时 | unitPrice × quantity × hours |
| `per_meter` | cascade 或 custom_dimensions（可选 sku_template） | 每 meter 独立输入 | Σ tiered_price(meter, quantity) |
| `resource_dimensions` | cascade(仅 region) + display_maps | resource_inputs 定义的输入框 | formula.terms: Σ(meter × resource × duration) |

### 跨模式通用机制

| 机制 | 适用场景 | 示例 |
|------|---------|------|
| `display_maps` | 所有模式 — 下拉框显示增强 + 区域自适应 | Redis SKU 分组, ACI variant 映射 |
| `visible_when` | 条件显示/隐藏 UI 元素 | ACI GPU 输入, Blob Archive-only meters |
| `meter_overrides` | per_meter — 覆盖动态 meter 的默认显示 | Blob: Data Stored 的标签和默认数量 |
| `hidden_dimensions` / `hidden_meters` | 隐藏不需要用户看到的维度/meter | productName 维度通常隐藏 |

---

## 七、CMS 表单设计

### 设计原则

1. **运营人员只看到表单，不接触 JSON** — 所有字段通过表单控件编辑
2. **条件显示** — 选择不同 quantity_model 后，只显示相关的配置区域
3. **拖拽排序** — display_maps entries 和 resource_inputs 支持拖拽重排
4. **批量导入** — display_maps 支持从 CSV/粘贴板批量导入
5. **交叉校验** — formula.terms 的 input_key 必须引用已定义的 resource_inputs

### 表单区域布局

| 区域 | CMS 中文标题 | 包含字段 | 条件显示 |
|------|-------------|---------|---------|
| 1 | 基础设置 | service_name, display_name_cn, quantity_model, quantity_label | 始终 |
| 2 | 级联维度 | dimension_labels, hidden_dimensions, excluded_products | 始终 |
| 3 | 显示名称映射 | display_maps 可排序表格 | 始终 |
| 4 | SKU 分组 | sku_groups 映射 | per_meter |
| 5 | 计量器定制 | meter_labels, meter_order, hidden_meters, meter_free_quota, meter_overrides | per_meter |
| 6 | SKU 模板 | sku_template, custom_dimensions | per_meter（复合 SKU 时） |
| 7 | 资源输入项 | resource_inputs 可排序卡片 | resource_dimensions |
| 8 | 计算公式 | formula.type, terms[], duration_default | resource_dimensions |
| 9 | 默认值 | region, SKU, hours, resource_defaults | 始终 |

### Display Maps 编辑器（核心交互）

```
┌─ 显示名称映射: skuName ──────────────────────────────────────┐
│ ☐ 隐藏未映射项                                                │
│                                                              │
│ ┌──┬───────────────┬──────────────┬──────────┬──────┬──────┐ │
│ │⠿│ API 值         │ 显示名称      │ 中文名称  │ 分组  │ 排序 │ │
│ ├──┼───────────────┼──────────────┼──────────┼──────┼──────┤ │
│ │⠿│ Standard      │ Linux        │ Linux    │ 标准  │  1   │ │
│ │⠿│ Standard Spot │ Linux (Spot) │ Linux... │ 标准  │  2   │ │
│ │⠿│ K80           │ GPU - K80    │ GPU-K80  │ GPU  │ 10   │ │
│ │⠿│ V100          │ GPU - V100   │ GPU-V100 │ GPU  │ 12   │ │
│ └──┴───────────────┴──────────────┴──────────┴──────┴──────┘ │
│                                          [+ 添加行] [批量导入] │
└──────────────────────────────────────────────────────────────┘
 ⠿ = 拖拽排序手柄
```

### Resource Inputs 编辑器

```
┌─ 资源输入项 ─────────────────────────────────────────────────┐
│                                                              │
│ ┌─ #1 vCPU 数量 ─────────────────────────── [↑] [↓] [✕] ─┐ │
│ │ 键名: vcpus          英文标签: vCPUs                      │ │
│ │ 中文标签: vCPU 数量    默认值: 2                           │ │
│ │ 最小值: 1  最大值: 16  步长: 1  单位后缀: (空)             │ │
│ │ 对应 Meter: vCPU Duration                                │ │
│ │ ☐ 条件可见  字段: [skuName ▾]  匹配: [K80|P100|V100]     │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│ ┌─ #2 内存 (GB) ─────────────────────────── [↑] [↓] [✕] ─┐ │
│ │ 键名: memory_gb      英文标签: Memory (GB)                │ │
│ │ 中文标签: 内存 (GB)    默认值: 4                           │ │
│ │ 最小值: 0.5  最大值: 64  步长: 0.5  单位后缀: GB           │ │
│ │ 对应 Meter: Memory Duration                              │ │
│ │ ☐ 条件可见                                                │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│ ┌─ #3 GPU 数量 ──────────────────────────── [↑] [↓] [✕] ─┐ │
│ │ 键名: gpu_count      英文标签: GPUs                       │ │
│ │ 中文标签: GPU 数量     默认值: 0                           │ │
│ │ 最小值: 0  最大值: 4  步长: 1  单位后缀: (空)              │ │
│ │ 对应 Meter: GPU Duration                                 │ │
│ │ ☑ 条件可见  字段: [skuName ▾]  匹配: [K80|P100|V100]     │ │
│ └──────────────────────────────────────────────────────────┘ │
│                                                              │
│                                              [+ 添加输入项]   │
└──────────────────────────────────────────────────────────────┘
```

### Formula 编辑器

```
┌─ 计算公式 ───────────────────────────────────────────────────┐
│ 公式类型: [resource_sum ▾]                                    │
│ 默认时长: [730] 小时/月                                       │
│                                                              │
│ ┌─ Meter 匹配     │ 输入项       │ 单位转换 ─────────────────┐│
│ │ vCPU Duration   │ vcpus ▾     │ 1                         ││
│ │ Memory Duration │ memory_gb ▾ │ 1                         ││
│ │ GPU Duration    │ gpu_count ▾ │ 1                         ││
│ │ Windows Software│ vcpus ▾     │ 3600  ← 秒转小时          ││
│ └────────────────────────────────────────── [+ 添加公式项] ──┘│
│                                                              │
│ 说明: total = Σ(meter_price × 输入值 × 时长 × 单位转换)       │
└──────────────────────────────────────────────────────────────┘
```

### 校验规则

| 规则 | 触发条件 | 错误提示 |
|------|---------|---------|
| quantity_model = resource_dimensions → resource_inputs 必填 | 保存时 | "资源维度模式需要至少定义一个资源输入项" |
| quantity_model = resource_dimensions → formula 必填 | 保存时 | "资源维度模式需要定义计算公式" |
| formula.terms[].input_key 必须在 resource_inputs 中 | 保存时 | "公式项 'xxx' 引用了未定义的输入项 'yyy'" |
| display_maps.entries[].api_value 不能重复 | 实时 | "API 值 'xxx' 重复" |
| sku_template 中的 `{field}` 必须在 custom_dimensions 中 | 保存时 | "SKU 模板引用了未定义的维度 'xxx'" |

---

## 八、可变性与扩展性

### Schema 可变性总结

```
固定骨架（所有产品相同）:
  service_name, display_name_cn, quantity_model, defaults

可变内容（随产品复杂度伸缩）:
  简单产品 (Pattern A):  可能只需要 display_maps         → ~30 行配置
  中等产品 (Pattern B):  + sku_groups + meter_labels      → ~50 行配置
  复杂产品 (Pattern D):  + resource_inputs + formula      → ~80 行配置
  最复杂 (Pattern B+阶梯): + sku_template + meter_overrides → ~100 行配置
```

### 向后兼容

- 现有 `instances_x_hours` 配置（VM、Redis、App Service）无需任何修改
- 现有 `per_meter` 配置（Service Bus、Firewall）无需任何修改
- 新字段（display_maps、resource_inputs、formula）全部可选
- 前端渲染引擎对新字段做防御性检查：`config.display_maps || {}`

### 未来扩展

| Pattern | 方向 | 扩展方式 |
|---------|------|---------|
| C (compute + storage) | SQL Database, Managed Disks | 新增 quantity_model: "compute_plus_storage"，配置包含 compute_section + storage_section |
| F (跨服务组合) | Azure ML, HDInsight | 新增 `related_services` 字段，引用其他服务配置 |
| 新的 section type | 未知需求 | 新增 section type 定义，前端忽略不认识的类型 |
