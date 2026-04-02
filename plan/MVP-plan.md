# MVP Plan — Azure CN Pricing Calculator

> 基于 2026-03-31 讨论重构。融合 per-product JSON 配置设计、CN 价格数据 API、Admin WYSIWYG 预览。
> 更新 2026-04-01：新增 `quantity_formula` + View Cost Calculation 功能（基于 Pattern A 产品 API+UI 深度调研）。
> 前置研究：`research/per-pattern-json-config-design.md`、`research/product-pricing-patterns.md`

---

## 1. 项目定位

Azure.cn Pricing Calculator — 对废弃的 ACN Calculator 的**全面重做**。

核心架构决策：
- **每个产品一个 JSON 配置**（描述 UI 结构 + 价格映射），5 种渲染模板（代码）根据 `quantity_model` 选择布局
- **价格从 API 动态获取** — MVP 阶段 CN 价格数据从数据库构建 API；Global 价格从 `prices.azure.com`
- **JSON 控制内容，代码控制结构** — JSON 参数化模板内的显示名/分组/排序/条件显示/默认值；布局骨架写死在渲染模板中
- **Legacy `calculatordatamodel.js` 是一次性参考** — 提取中文名 + CN 产品范围 + UI 分组，价格数据过时不可用

---

## 2. 当前状态

### 已完成

| 模块 | 状态 | 说明 |
|------|------|------|
| Frontend estimate area (Task 1-10) | ✅ | 两阶段计算、Savings Radio、per-meter 等 |
| Config Admin (Task 12) | ✅ | CRUD + 版本历史 + draft/publish + JSON 双写 |
| 产品 catalog | ✅ | 28 个产品有中文名，10 个 family |
| 生产 service_configs | ✅ | 9 个（VM, App Service, Firewall 等），覆盖 Pattern A + B |
| ACN Datamodel 提取 (Step 1-5) | ✅ | 14 个模板已生成至 `data/generated_service_configs/` |

### 当前架构

```
Calculator Frontend (Vanilla JS)
  ↓ POST /explore/cascade, /explore/meters
Explore API (FastAPI)
  ↓ fetch_global_prices()
Azure Global Retail Prices API (prices.azure.com)

Admin UI (Alpine.js)
  ↓ /api/v1/admin/*
Admin API → PostgreSQL (service_configs + product_catalog)
```

### 已支持的定价模式

| quantity_model | 代表产品 | 状态 |
|---------------|---------|------|
| `instances_x_hours` (Pattern A) | VM, App Service, Redis | ✅ 渲染模板已有 |
| `per_meter` (Pattern B+E) | Service Bus, Firewall, VPN Gateway | ✅ 渲染模板已有 |
| `compute_plus_storage` (Pattern C) | SQL Database | ❌ 未实现 |
| `resource_dimensions` (Pattern D) | Container Instances | ❌ 未实现 |
| `cross_service_composite` (Pattern F) | HDInsight | ❌ 未实现 |

---

## 3. 数据架构

### 三种数据，三条管道

```
┌─ 配置数据 (How to present) ──────────────────────────────────────────┐
│ 内容: quantity_model, display_maps, meter_overrides, defaults...     │
│ 特征: 低频变化，人工策划                                              │
│ 来源: Admin UI → service_configs (DB + JSON 双写)                    │
│ 参考: Legacy datamodel (一次性提取中文名 + UI 分组)                    │
└──────────────────────────────────────────────────────────────────────┘

┌─ CN 价格数据 (What does it cost — China) ────────────────────────────┐
│ 内容: meter_id, retail_price, unit_price, tier_min_units, type...    │
│ 特征: CN 真实价格，定期更新                                           │
│ 来源: CN 数据库（已有权限）→ MVP 构建 CN 价格 API                      │
│ 注意: Legacy datamodel 中的价格已过时，不可用                          │
└──────────────────────────────────────────────────────────────────────┘

┌─ Global 价格数据 (What does it cost — Global) ───────────────────────┐
│ 内容: 同上                                                          │
│ 来源: Azure Global Retail Prices API (prices.azure.com)              │
│ 用途: 开发调试 + 对照参考                                             │
└──────────────────────────────────────────────────────────────────────┘
```

### 配置 ↔ 价格的关系

```
配置数据 (service_configs)          价格数据 (CN API / Global API)
┌─────────────────────┐            ┌─────────────────────┐
│ quantity_model       │            │ product_name, sku    │
│ display_maps         │  控制展示   │ retail_price         │  提供数值
│ meter_overrides      │ ─────────→ │ tier_min_units       │ ─────────→ Calculator UI
│ product_sub_dims     │  怎么展示   │ type, term           │  展示什么
│ defaults             │            │ arm_region_name      │
└─────────────────────┘            └─────────────────────┘
       ↑                                    ↑
  通过 service_name 关联              通过 service_name 查询
```

---

## 4. MVP 目标架构

```
Calculator Frontend
  │
  ├─ 5 种渲染模板 (代码)
  │   ├─ Template A: instances_x_hours (已有)
  │   ├─ Template B: per_meter (已有)
  │   ├─ Template C: compute_plus_storage (MVP Phase 2)
  │   ├─ Template D: resource_dimensions (MVP Phase 2)
  │   └─ Template F: cross_service_composite (Phase 3, OUT OF SCOPE)
  │
  ├─ JSON 配置参数化模板内容
  │   └─ display_maps, meter_overrides, product_sub_dimensions,
  │      resource_inputs, formula, sections, defaults, visible_when...
  │
  └─ 价格 API 查询
      ├─ CN 价格 API (新建, MVP 核心)
      └─ Global Retail API (开发调试)

Admin UI
  ├─ Config Editor (已有: form + JSON 双面板)
  ├─ API 预览 Tab (新增)
  └─ WYSIWYG Calculator 预览 (新增)
```

---

## 5. MVP 范围

### IN SCOPE

| # | 功能 | 优先级 | 说明 |
|---|------|--------|------|
| **1** | **CN 价格数据 API** | P0 | 从 CN 数据库构建与 Global API 相同格式的价格接口 |
| **2** | **模板导入功能** | P0 | Config Editor 中"从模板导入"→ 创建 draft |
| **3** | **API 预览 Tab** | P0 | Config Editor 中测试 cascade/meters，辅助填写配置 |
| **4** | **Admin WYSIWYG 预览** | P1 | 在 Admin 中实时预览 JSON 配置在 Calculator 中的效果 |
| **5** | **quantity_formula + View Cost Calculation** | P1 | JSON 定义计算公式，前端渲染可折叠的计算过程展示；Redis Premium 为验证场景 |
| **6** | **Pattern A/B 配置增强** | P1 | `product_sub_dimensions`（VM/App Service）、`is_base_fee`（VPN Gateway） |
| **7** | **Legacy 中文内容提取** | P1 | 从 `calculatordatamodel.js` 批量提取中文名 + CN SKU 范围 |
| **8** | **端到端 Demo** | P1 | redis-cache 走完 导入→编辑→预览→发布 全流程（含 formula 验证） |
| **9** | **Batch 1 产品接入** | P2 | 8 个简单产品（Pattern A/B），验证工作流后逐个接入 |

### OUT OF SCOPE（未来迭代）

| 功能 | 原因 | 归属 |
|------|------|------|
| Pattern C 渲染模板 (compute_plus_storage) | 需新增 mode_selector + 多 section 布局 | Phase 2 |
| Pattern D 渲染模板 (resource_dimensions) | 需 resource_inputs + 专用布局（quantity_formula 引擎已有） | Phase 2 |
| Pattern F 渲染模板 (cross_service_composite) | 跨服务查询 + 多节点角色，复杂度最高 | Phase 3 |
| SQL Database / MySQL / PostgreSQL 接入 | 依赖 Pattern C 模板 | Phase 2 |
| Container Instances 接入 | 依赖 Pattern D 模板 | Phase 2 |
| HDInsight / Databricks 接入 | 依赖 Pattern F 模板 | Phase 3 |
| region_constraints 实际生效 | 需后端筛选逻辑变更 | Phase 2+ |
| 多角色审批流程 | MVP 单人操作足够 | 按需 |
| ETL 自动化 | CN 价格 API 建成后再考虑自动更新 | 按需 |

---

## 6. 数据源策略

### MVP 双数据源

```
CN 价格 (生产):   CN 数据库 → CN 价格 API (新建, 与 Global API 相同格式)
Global 价格 (调试): prices.azure.com → 已有 explore API
```

### CN 价格 API 设计要点

- **接口格式与 Global Retail API 对齐** — 相同的 serviceName/productName/skuName/meterName 字段结构
- **数据源**: CN 数据库（你有权限访问）
- **前端切换**: explore API 增加数据源切换参数，或按 region 自动路由
- **与 Global API 的区别**: 产品范围不同（CN 不一定有 Global 的所有产品）、价格不同（CNY）、部分 SKU 可用性不同

### Legacy datamodel 价格的定位

```
Legacy 价格 (calculatordatamodel.js)  →  过时，不可用，不进入任何数据流
CN 数据库价格                          →  真实 CN 价格，MVP 数据源
Global API 价格                       →  开发参考 + 对照验证
```

---

## 7. JSON 配置 ↔ 渲染模板架构

### 核心设计原则

```
JSON 控制"内容" — 显示什么、叫什么名、什么时候显示
代码控制"结构" — 布局模板、计算引擎、API 交互

80% 的产品配置工作（调显示名、改默认值、接入 Pattern A/B 新产品）
  → 运营在 Admin UI 完成

20% 的工作（新增渲染模板、跨服务配置）
  → 需要开发
```

### 5 种 quantity_model 与渲染模板

| quantity_model | 渲染模板 | MVP 状态 | 产品 |
|---------------|---------|---------|------|
| `instances_x_hours` | Template A: [级联下拉] → [数量×小时] → [Savings] → [价格] | ✅ 已有 | VM, App Service, Redis |
| `per_meter` | Template B: [SKU选择] → [Meter列表+输入] → [总计] | ✅ 已有 | Service Bus, Firewall, VPN Gateway |
| `compute_plus_storage` | Template C: [模式切换] → [Compute] → [Storage] → [Backup] | ❌ Phase 2 | SQL Database, MySQL |
| `resource_dimensions` | Template D: [SKU选择] → [资源输入框组] → [总计] | ❌ Phase 2 | Container Instances |
| `cross_service_composite` | Template F: [集群类型] → [节点角色×N] → [存储] | ❌ Phase 3 | HDInsight |

### JSON 配置字段速查

```
所有模式共用:
  service_name, display_name_cn, quantity_model, defaults
  display_maps, hidden_dimensions, excluded_products
  quantity_formula (MVP P1) — 计算公式定义 + View Cost Calculation 展示

所有模式 — quantity_formula (MVP P1):
  quantity_formula.inputs[]         — 用户输入字段定义 (key, label, default, min)
  quantity_formula.formula          — 计算表达式 (引用 inputs 中的 key)
  quantity_formula.use_meter        — 指定用哪个 meter 取价 (如 "Cache Instance")
  quantity_formula.applies_to       — 条件触发 (如 {"tier": ["Premium"]})
  quantity_formula.display_steps[]  — View Cost Calculation 展示的中间步骤

  注: 简单产品可省略 quantity_formula，由 quantity_model 提供默认公式:
    instances_x_hours 默认: "[N] Instance × [H] Hours × $X/hr = $Y"
    per_meter 默认:         "Meter1: [Q] × $X/unit = $Y; ... Total = $Z"

Pattern A 增强 (MVP P1):
  product_sub_dimensions    — productName → 子维度解析 (VM: OS+Series, App Service: Tier+OS)

Pattern B 增强 (MVP P1):
  is_base_fee / fixed_quantity — 固定基础费识别 (VPN Gateway)

Pattern C 新增 (Phase 2):
  mode_selector, deployment_selector, sections{compute, storage, backup}

Pattern D 新增 (Phase 2):
  resource_inputs[], 专用布局 (formula 引擎复用 quantity_formula)

Pattern F 新增 (Phase 3):
  cluster_selector, node_roles[], price_composition, storage_section
```

### quantity_formula 示例

**Pattern A 默认**（VM、App Service、DMS — 无需显式配置）：
```json
// 省略 quantity_formula → 使用 instances_x_hours 默认公式
// View Cost Calculation 自动展示:
// [1] Instance × [730] Hours × $0.188/hr = $137.24
```

**Pattern A 自定义**（Redis Premium — JSON 显式配置）：
```json
{
  "quantity_formula": {
    "applies_to": { "productName": ["Azure Redis Cache Premium"] },
    "inputs": [
      { "key": "shards", "label": "Shard per Instance", "default": 1, "min": 1 },
      { "key": "additional_replicas", "label": "Additional Replicas per Shard", "default": 0, "min": 0 },
      { "key": "instances", "label": "Instance", "default": 1, "min": 1 }
    ],
    "formula": "shards * (1 + 1 + additional_replicas) * instances",
    "use_meter": "Cache Instance",
    "display_steps": [
      "{shards} Shard × ({1} Primary + {1} Built-in + {additional_replicas} Additional) = {nodes} Nodes",
      "{nodes} Nodes × {instances} Instance × {hours} Hours × ${price}/hr = ${total}"
    ]
  }
}
```

**Pattern B 默认**（Service Bus、Firewall — 无需显式配置）：
```json
// 省略 quantity_formula → 使用 per_meter 默认公式
// View Cost Calculation 自动展示:
// Deployment: [730] Hours × $1.25/hr = $912.50
// Data Processed: [100] GB × $0.016/GB = $1.60
// Total = $914.10
```

---

## 8. Legacy datamodel 利用策略

### 定位：一次性参考资源

```
calculatordatamodel.js (68K行, ~154 slug)
  │
  ├─ 能提取 ──→ 中文名、Tier分组名、Size描述、CN可用SKU范围、区域限制提示
  ├─ 不能用 ──→ 价格数据（过时）
  └─ 需注意 ──→ slug ≠ 产品（多对一: VM 有 54+ slug, Storage 有 54+ slug）
```

### 提取脚本设计

```
Phase 1: 批量提取 (脚本)
  ├─ 解析 calculatordatamodel.js (处理 CalculatorConst 引用)
  ├─ 对每个 slug 提取: 中文名, Types→Features→Sizes 结构
  └─ 输出: per-product JSON 草稿 (含中文, 缺 API 映射)

Phase 2: 归并 + 映射 (半自动)
  ├─ 多 slug → 一个 service_name (参照 slug_to_service_name)
  ├─ 判断 quantity_model
  └─ 补全 meter_overrides, formula 等

Phase 3: Admin 导入
  ├─ JSON 草稿导入 Admin CMS → draft
  ├─ Admin WYSIWYG 预览中微调
  └─ 发布
```

---

## 9. 实现计划

### P0-A: CN 价格数据 API

**目标**: 从 CN 数据库构建价格接口，前端可查询 CN 真实价格。

需要确认：
- CN 数据库的表结构 / 访问方式
- 与 Global Retail API 字段的对应关系
- 是否需要中间层做字段映射

后端实现：
- 新增 CN 数据源适配器（与 Global API 相同的查询接口）
- explore API 增加数据源路由（按 region 自动切换 or 显式参数）

### P0-B: 模板导入功能

**后端** (`app/api/admin.py`):
```
GET  /api/v1/admin/onboarding/templates        — 列出可用模板
POST /api/v1/admin/onboarding/import/{slug}     — 导入模板 → 创建 draft
```

**前端** (`admin/js/components/config-list.js`):
- Config 列表页新增"从模板导入"按钮
- 弹出模板选择列表 → 选择后创建 draft → 跳转到编辑页

### P0-C: API 预览 Tab

**在 config-editor.js 中新增第三个 Tab**（与 form、JSON 并列）:
- **测试 Cascade** — 传入 service_name + 空 selections → 展示维度和选项
- **测试 Meters** — 选定 region/product/sku → 展示 meter 列表和价格
- **辅助填写** — 根据 API 返回的 meter 名辅助填写 meter_overrides

### P1-A: Admin WYSIWYG 预览

```
┌─ Config Editor ───────────────────────────────────────────────────┐
│                                                                    │
│  ┌─ 左: 配置表单 ──────────────┐  ┌─ 右: Calculator 实时预览 ───┐ │
│  │ quantity_model: [选择▾]     │  │                              │ │
│  │ display_maps: [编辑表格]     │  │  ┌─ Redis Cache ──────────┐ │ │
│  │ meter_overrides: [编辑表格]  │  │  │ Region: [East US    ▾] │ │ │
│  │ defaults: [下拉选择]         │  │  │ SKU:    [C1         ▾] │ │ │
│  │                             │  │  │ Qty: [1] Hours: [730]  │ │ │
│  │  ← 修改左侧，右侧实时更新    │  │  │ $0.35/hr → $255.50/mo │ │ │
│  └─────────────────────────────┘  │  └────────────────────────┘ │ │
│                                   └──────────────────────────────┘ │
│  [保存草稿]  [发布]                                                 │
└────────────────────────────────────────────────────────────────────┘
```

实现方式：
- **后端**: `GET /explore/service-config/{name}?draft=true` — 加载草稿配置
- **前端 Calculator**: 检测 `?preview=<service_name>` → 自动添加该产品 + 加载草稿
- **Admin**: 编辑页"在 Calculator 中预览"按钮 → 保存草稿 → 新标签页或 iframe 打开预览

### P1-B: quantity_formula + View Cost Calculation

**目标**: 每个产品都能展示可折叠的 "View Cost Calculation" 区域，显示计算公式 + 实时数值。简单产品用默认公式，复杂产品在 JSON 中显式定义。

**设计原则**:
- 简单产品（VM、App Service、DMS）**不需要**在 JSON 中配置 formula — `quantity_model` 自带默认公式
- 复杂产品（Redis Premium）在 JSON 中配置 `quantity_formula`：自定义输入字段 + 计算表达式 + meter 选择
- 前端渲染引擎统一处理：无 formula → 用默认模板；有 formula → 渲染自定义输入 + 公式

**默认公式（无需 JSON 配置）**:
```
instances_x_hours:
  ▽ View Cost Calculation
    [1] Instance × [730] Hours × $0.188/hr = $137.24

per_meter:
  ▽ View Cost Calculation
    Deployment: [730] Hours × $1.25/hr = $912.50
    Data Processed: [100] GB × $0.016/GB = $1.60
    Total = $914.10
```

**自定义公式（Redis Premium JSON 配置）**:
```
  ▽ View Cost Calculation
    [1] Shard × ([1] Primary + [1] Built-in + [0] Additional Replicas) = [2] Nodes per Instance
    [2] Nodes × [1] Instance × [730] Hours × $0.28/hr = $404.42
```

**实现拆分**:

1. **前端 — View Cost Calculation 组件** (`frontend/js/components/cost-calculation.js`):
   - 可折叠区域，默认收起
   - 读取 `quantity_formula` 配置 → 有则渲染自定义公式，无则渲染默认公式
   - 实时更新：用户改数量/选项 → 公式中的数值同步变化

2. **前端 — 自定义输入渲染** (`frontend/js/components/estimate-card.js`):
   - 检测 `quantity_formula.applies_to` 条件（如 tier=Premium）
   - 匹配时：替换默认的 "Instance × Hours" 输入为 formula 定义的 inputs
   - 不匹配时：使用标准输入

3. **前端 — formula 计算引擎** (`frontend/js/pricing.js`):
   - 解析 formula 表达式（简单四则运算 + 变量引用）
   - 计算最终 quantity multiplier → 传入现有定价计算流程
   - 选择 `use_meter` 指定的 meter 取价

4. **验证场景 — Redis Premium**:
   - 配置 `quantity_formula` → Shard/Replicas/Instance 输入
   - 切换 tier：Basic → 标准输入; Premium → formula 输入
   - View Cost Calculation 展示完整公式
   - 最终价格与 Azure Calculator 一致：$404.42

### P1-C: Pattern A/B 配置增强

**Pattern A — `product_sub_dimensions`**:
- 解析 productName 为子维度（VM: OS + Series, App Service: Tier + OS）
- 前端从 productName 列表拆出多个下拉框
- 用户选择后拼回 productName 用于 cascade

**Pattern B — `is_base_fee`**:
- `meter_overrides` 新增 `is_base_fee: true` + `fixed_quantity` 属性
- 匹配的 meter 自动显示为固定费行（不展示输入框）
- 适用于 VPN Gateway 等 SKU 基础费

### P1-D: Legacy 中文内容提取

- 编写提取脚本解析 `calculatordatamodel.js`
- 提取：中文产品名、Tier 中文名、Size 描述、区域限制
- 输出 per-product JSON 草稿（含中文，缺 API 映射和价格）
- 注意多 slug 归并（154 slug → ~28 产品）

### P1-E: 端到端 Demo (redis-cache)

```
1. 导入模板     → POST /admin/onboarding/import/redis-cache → draft 创建
2. 编辑配置     → Config Editor form 面板调整 display_maps、defaults
3. 配置 formula → 为 Premium tier 添加 quantity_formula (Shard/Replicas/Instance)
4. API 预览     → Tab 3 测试 cascade (确认 Basic/Standard/Premium)
5. API 预览     → Tab 3 测试 meters (确认 Cache vs Cache Instance meter)
6. WYSIWYG 预览 → Calculator 预览: Basic 用默认公式, Premium 用自定义 formula
7. View Cost Calculation → 展开确认公式正确, 价格与 Azure Calculator 一致
8. 发布          → publish → Calculator 正式加载
```

### P2: Batch 1 产品接入

验证端到端流程后，逐个接入 Pattern A/B 产品（每个 15-30 min）:

| 产品 | Pattern | 预计工作 |
|------|---------|---------|
| Azure Cache for Redis | A | 模板导入 + 微调 |
| Container Registry | B | 模板导入 + meter_overrides |
| DDoS Protection | B | 简单，2 meter |
| Managed Grafana | B | 简单，3 meter |
| Notification Hubs | B | sku_groups |
| Database Migration Service | A | 简单 |
| Traffic Manager | B | 5 meter |
| Application Gateway | B | meter_overrides |

---

## 10. 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| **CN 价格 API** | | |
| `app/services/cn_price_service.py` | 新建 | CN 数据库查询适配器 |
| `app/api/explore.py` | 修改 | 数据源路由（CN / Global 切换） |
| **模板导入** | | |
| `app/api/admin.py` | 修改 | 新增 onboarding 端点 |
| `admin/js/components/config-list.js` | 修改 | "从模板导入"按钮 |
| **API 预览 Tab** | | |
| `admin/js/components/config-editor.js` | 修改 | 新增 API 预览 Tab |
| `admin/js/api.js` | 修改 | 新增 onboarding + 预览 API 函数 |
| **quantity_formula + View Cost Calculation** | | |
| `frontend/js/components/cost-calculation.js` | 新建 | 可折叠公式展示组件（默认公式 + 自定义公式渲染） |
| `frontend/js/components/estimate-card.js` | 修改 | 集成 cost-calculation 组件 + formula inputs 条件渲染 |
| `frontend/js/pricing.js` | 修改 | formula 表达式解析 + use_meter 选择 + quantity multiplier 计算 |
| **WYSIWYG 预览** | | |
| `app/api/explore.py` | 修改 | service-config 支持 `?draft=true` |
| `frontend/js/app.js` | 修改 | 检测 `?preview=` 参数 |
| `frontend/js/api.js` | 修改 | fetchServiceConfig 支持 draft |
| **Pattern A/B 增强** | | |
| `frontend/js/components/estimate-card.js` | 修改 | product_sub_dimensions 渲染 + is_base_fee 展示 |
| `frontend/js/pricing.js` | 修改 | 支持 fixed_quantity 计算 |
| **Legacy 提取** | | |
| `scripts/extract_legacy_chinese.py` | 新建 | 从 datamodel.js 提取中文内容 |

---

## 11. 验证方式

| # | 验证项 | 预期结果 |
|---|--------|---------|
| 1 | CN 价格 API 查询 redis-cache | 返回 CN 真实价格（CNY） |
| 2 | `GET /admin/onboarding/templates` | 返回可用模板列表 |
| 3 | `POST /admin/onboarding/import/redis-cache` | draft config 创建成功 |
| 4 | Config Editor API 预览 Tab | cascade 返回维度，meters 返回 CN 价格 |
| 5 | Config Editor WYSIWYG 预览 | Calculator 中 estimate card 正确渲染 |
| 6 | 修改 display_maps → 保存 → 刷新预览 | 预览中看到改动生效 |
| 7 | 发布 → Calculator 正式加载 | 正常显示，无预览模式提示 |
| 8 | View Cost Calculation（默认） | VM/App Service estimate card 展开后显示 `N × H × $/hr = $total` |
| 9 | View Cost Calculation（自定义 formula） | Redis Premium 展开后显示 Shard×Replicas 公式，价格=$404.42 |
| 10 | Redis tier 切换 | Basic → 标准输入 + 默认公式; Premium → formula 输入 + 自定义公式 |
| 11 | Legacy 提取脚本 | 输出 per-product JSON 草稿含中文名 |
| 12 | `uv run pytest` | 回归测试全部通过 |

---

## 12. 迭代路线

```
MVP (本轮)
  ├── P0: CN 价格 API + 模板导入 + API 预览 Tab
  ├── P1: WYSIWYG 预览 + quantity_formula + View Cost Calculation + Pattern A/B 增强 + Legacy 提取 + 端到端 Demo
  └── P2: Batch 1 (8 个 Pattern A/B 产品)
  │
Phase 2: 新增渲染模板
  ├── Template C: compute_plus_storage (mode_selector + 多 section)
  │     → SQL Database, MySQL, PostgreSQL, Cosmos DB
  ├── Template D: resource_dimensions (resource_inputs + formula)
  │     → Container Instances
  └── Batch 2: Pattern C/D 产品接入
  │
Phase 3: 复杂产品
  ├── Template F: cross_service_composite (跨服务 + 多节点)
  │     → HDInsight, Databricks
  ├── region_constraints 实际生效
  └── 多角色审批流程
```

---

## 13. 关键设计决策记录

| 决策 | 结论 | 理由 |
|------|------|------|
| JSON 表达力边界 | **JSON 控制内容，代码控制结构** | 更多逻辑放 JSON 会让复杂度上天；5 个渲染模板足够覆盖 6 种 Pattern |
| CN 价格数据源 | **CN 数据库 → 新建 API** | Legacy datamodel 价格过时；CN 数据库有真实数据且有权限 |
| Admin WYSIWYG | **MVP IN-SCOPE** | 运营人员需要所见即所得确认配置效果 |
| Pattern E (VPN Gateway) | **复用 per_meter + is_base_fee** | 不值得新增独立 quantity_model |
| Legacy datamodel 利用 | **提取中文 + CN 范围，不用价格** | 价格过时；slug 不等于产品（多对一） |
| MVP 数据源策略 | **CN API 为主, Global API 为辅** | CN 真实价格 > Global API 的 CN region 数据 |
| Onboarding 入口 | **扩展现有 Config Editor** | 避免功能重叠，开发成本低 |
| 渲染模板分期 | **A/B 先行, C/D Phase 2, F Phase 3** | 按覆盖产品数和复杂度递增 |
| quantity_formula 定位 | **通用能力，不是特殊 Pattern** | 每个产品都有计算公式（简单的用默认，复杂的 JSON 显式定义）；View Cost Calculation 是透明度功能 |
| Redis Premium 量化模型 | **Pattern A + quantity_formula，不新建 Pattern** | API 数据结构是 Pattern A（1 Hour, 单 meter/SKU），Shard/Replicas 是 quantity 层面的自定义，通过 JSON formula 配置 |

---

## 14. 需要确认的事项

| # | 事项 | 影响 |
|---|------|------|
| 1 | CN 数据库表结构和访问方式 | P0-A: CN 价格 API 的设计 |
| 2 | CN 数据库字段与 Global API 字段的对应关系 | 数据适配器的映射逻辑 |
| 3 | CN 数据库的更新频率和机制 | 是否需要缓存层 |
| 4 | Batch 1 产品在 CN 数据库中是否有数据 | 确定 MVP 可接入的产品范围 |
| 5 | Batch 1 产品的 family 归属确认 | catalog 分类 |
