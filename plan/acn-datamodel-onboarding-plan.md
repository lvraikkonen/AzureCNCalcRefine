# 利用 ACN Legacy Datamodel 提升项目体验

> 更新于 2025-03-25，基于 MVP 范围讨论结论修订。Step 6 及 QA 部分有重大调整。

## Context

本项目是对废弃的 ACN Calculator 的**全面重做**，以 Azure Global Retail Prices API 为数据源，配置驱动，支持长期运营维护。

面向 azure.cn 中国市场时存在明显体验缺口：

- **28 个产品全部没有中文名**（`display_name_cn: null`）
- **部分产品描述是占位符**（如 "ftcsdgvyldsabfhugjnkml"）
- **无区域可用性约束**（`region_constraints: null`）
- **仅 9 个产品有 service_config**，其余无法提供预填默认值

废弃的 ACN Calculator 的 `calculatordatamodel.js`（69K 行、260 个服务条目）包含完整的中文产品名、中文描述、区域限制、维度结构和 CNY 价格数据。

**目标**：通过提取和整合 legacy 数据，快速弥补以上缺口，使项目在产品发现、中文本地化、区域准确性方面对齐甚至超越 Global Calculator。

### 价格数据 vs 配置数据

Legacy datamodel 中包含两类本质不同的数据，需要区分对待：

| | 配置数据（How to present） | 价格数据（What does it cost） |
|---|---|---|
| **内容** | 中文名、区域约束、维度结构、quantity_model、meter_labels | meter_id、retail_price、unit_price、tier_min_units |
| **变化频率** | 低（产品重新设计时才变） | 高（微软调价，日/周级） |
| **管理方式** | Admin UI 人工策划 | 自动化管道（ETL） |
| **存储** | service_configs (DB + JSON 双写) | MVP: Global API 实时查询 / 未来: PostgreSQL |

**Legacy datamodel 主要贡献的是配置数据**（中文名、维度结构）。价格数据来自 Global API（MVP）/ CN CSV（Phase 4），两者通过 `service_name` 关联但独立管理。

### 数据源策略

**MVP 阶段以 Azure Global Retail Prices API 为准**，目的是对齐 Global Calculator 的 UI 和配置模式：

```
MVP:     Explore API → Global Retail Prices API (实时, CN 区域返回 CNY 价格)
Phase 4: Explore API → 本地 PostgreSQL (CN CSV 导入)
```

- 产品接入**必须在 Global API 中有 CN 区域数据**，否则 cascade/meters 无法工作
- Legacy 价格数据仅作参考，不参与 MVP 定价
- 数据源切换接口已预留：`fetch_global_prices()` 是唯一数据获取入口

### Legacy slug 与产品的粒度差异

Legacy datamodel 有 **260 个 slug**，但我们的 catalog 只有 **28 个产品**。关系是**多对一**：

```
virtual-machines-windows        ─┐
virtual-machines-linux           ├──→ Virtual Machines (1 个 service_config)
virtual-machines-sql-server-*   ─┘     cascade 中通过 productName 维度区分

storage-general-purpose-v2-*    ─┐
storage-queues-gpv2-*            ├──→ Storage Accounts (1 个 service_config)
storage-files-*                 ─┘     (~54 个 slug → 1 个产品)
```

Legacy 的一个 slug 对应的是我们系统中的一个**维度切片**，而不是独立产品。在新系统中，这些切片通过 cascade 级联筛选（`productName → skuName → type → term`）动态呈现。

这对 Onboarding 的影响：

| 情况 | 例子 | 策略 |
|------|------|------|
| 1 slug = 1 product（简单） | redis-cache, managed-grafana | `template` — 可直接导入模板 |
| 2-3 slugs = 1 product（小聚合） | ddos-protection + ddos-ipprotection | 选主 slug 导入，其余标记"已覆盖" |
| 多 slugs = 1 product（大聚合） | VM (54+), Storage (54+) | `manual` — 模板仅供参考，config 需手工策划 |

---

## 实现方案

### Step 1: JS → JSON 转换 ✅ 已完成（一次性任务）

> **定位**：一次性提取脚本，不进入生产数据流。脚本幂等可重复执行但非设计目标。

**创建**: `scripts/convert_acn_datamodel.js`

使用 Node.js 原生执行（系统已有 v22.18.0），因为：
- 文件中有 2,250 次 `CalculatorConst.xxx` 引用，必须通过 JS 执行来解析
- 包含 JS 枚举（`PriceTierEnum.Fixed`）、注释、非标准 JSON 语法
- Python regex 方案脆弱不可靠

```
输入: prod-config/calculatorconst.js + calculatordatamodel.js
输出:
  - prod-config/calculatordatamodel.json (完整 260 条目)
  - prod-config/calculatorconst.json (380 个常量)
  - prod-config/duplicate_slugs.json (3 组重复 slug 报告)
```

实现要点：
- `eval()` 加载两个 JS 文件，解析所有常量引用
- 正则预扫描原始文件检测重复 slug（`app-service`, `api-management`, `storage-queues-gpv2-east3`）
- `JSON.stringify` 输出标准 JSON

### Step 2: Python 提取脚本 ✅ 已完成（一次性任务）

> **定位**：一次性提取脚本，输出的 JSON 文件作为静态参考数据存在于 `data/` 目录。

**创建**: `scripts/extract_acn_metadata.py`

消费 Step 1 的 JSON 输出，生成 3 个结构化文件：

**输出 1**: `data/acn_product_names.json` — slug → 中文名 + 区域约束

```json
{
  "redis-cache": {
    "display_name_raw": "Redis 缓存 - 用于 Redis 的 Azure 缓存",
    "display_name_clean": "Redis 缓存",
    "region_constraints": null
  },
  "azure-fluid-relay": {
    "display_name_raw": "Azure Fluid Relay - 仅适用于中国北部3",
    "display_name_clean": "Azure Fluid Relay",
    "region_constraints": ["chinanorth3"]
  }
}
```

区域解析规则（regex 匹配 "仅适用于"/"仅支持" + 区域名）：
- 中国东部/中国东部1 → `chinaeast`
- 中国东部2 → `chinaeast2`  | 中国东部3 → `chinaeast3`
- 中国北部/中国北部1 → `chinanorth`
- 中国北部2 → `chinanorth2` | 中国北部3 → `chinanorth3`

**输出 2**: `data/acn_dimension_templates/` — 每产品一个 JSON，描述维度结构

包含 types_semantic 分类（tier/default/category/deployment/sku/service）、features_semantic 分类、suggested_config（推荐的 quantity_model、dimension_labels、hidden_dimensions）。

**输出 3**: `data/acn_price_validation.json` — 已知 CNY 价格快照

> 仅用于未来 Phase 4 数据源切换到 CN CSV + PostgreSQL 时的 sanity check，MVP 阶段不使用。

### Step 3: 应用中文名和描述到 Product Catalog ✅ 已完成（一次性任务）

**创建**: `scripts/apply_cn_names.py`

需要一个手工维护的 **slug → service_name 映射表** (`data/slug_to_service_name.json`)，因为：
- Legacy 用 slug（`redis-cache`），我们用 service_name（`Azure Cache for Redis`）
- 有合并关系（`virtual-machines-windows` + `virtual-machines-linux` → `Virtual Machines`）
- Storage 有 54 个 legacy 条目映射到 2 个现有服务

当前 28 个 catalog 产品的映射需手工确认。脚本执行：
1. 读取映射表 + `acn_product_names.json`
2. 更新 `product_catalog.json` 中的 `display_name_cn` 和 `region_constraints`
3. 替换占位符描述（如 "ftcsdgvyldsabfhugjnkml"）为 legacy 中文描述

**前端改动**: `nav-area.js` 中 service-picker 优先显示 `display_name_cn`（如果有），fallback 到 `service_name`。

### Step 4: 批量生成 Service Config 模板 ✅ 已完成（一次性任务）

**创建**: `scripts/generate_service_configs.py`

读取 `data/acn_dimension_templates/`，按映射规则自动生成 draft config：

| Legacy 结构 | 推导规则 |
|------------|---------|
| Types = Tier 名（基本/标准/高级）| `dimension_labels: {"skuName": "Tier"}` |
| 单一 productName | `hidden_dimensions: ["productName"]` |
| Features 全 "default" + Hourly | `quantity_model: "instances_x_hours"` |
| 多命名 Features 或 Monthly | `quantity_model: "per_meter"` |

**输出到** `data/generated_service_configs/`（非 `app/config/service_configs/`），需人工审核后采用。

### Step 5: 价格验证框架 ✅ 已完成（一次性任务）

> **定位**：仅用于未来 Phase 4 数据源切换（CN CSV → PostgreSQL）时的价格一致性验证，MVP 阶段不使用。

**创建**: `scripts/price_drift_report.py`

---

## Step 6: 产品接入工作流（当前阶段）

> **2025-03-25 修订**：基于 MVP 讨论，将原"独立 `#/onboarding` 页面"方案改为"在现有 Config Editor 上扩展"。

Step 1-5 已完成提取和模板生成。接下来是逐个产品审核、修正、发布。

### 6.1 生成模板与生产 Config 的 GAP

生成的模板约 **40% 完成度**，需人工修正以下内容：

| 问题 | 说明 | 填写方式 | 每产品耗时 |
|------|------|---------|-----------|
| 移除 `_acn_*` 字段 | `_acn_slug`、`_acn_display_name` 是生成元数据 | 导入端点自动清理 | 自动化 |
| 修正 `service_name` | 生成的部分使用中文名，需改为英文 catalog 名 | 导入端点自动修正（映射表） | 自动化 |
| 确认 `api_service_name` | Azure API 的 serviceName 可能与 catalog 名不同 | 查 Global API 确认 | 2 min |
| 补充 `meter_labels` | per_meter 产品需要人工可读的 meter 显示名 | **API 预览 Tab** — 看到 API 返回的 meter 名后填写 | 5-10 min |
| 补充 `meter_order` | 生成的是中文 feature 名，需改为 API 中的英文 meter 名 | **API 预览 Tab** — 从 meters 结果中获取 | 5-10 min |
| 补充 `hidden_dimensions` | 单一 productName 的产品需隐藏 | **API 预览 Tab** — 从 cascade 结果中判断 | 2 min |
| 完善 `defaults` | 添加默认 skuName/tier 选择 | Config Editor form 面板 | 2 min |

**核心工具**：Config Editor 中新增的 API 预览 Tab 是填写 `meter_labels`、`meter_order`、`hidden_dimensions` 等字段的主要依据。开发者在 Tab 中看到 API 实际返回什么数据，就知道 config 该怎么填。

### 6.2 在现有 Admin Config Editor 中扩展接入能力

> **修订说明**：原方案为新增独立 `#/onboarding` 路由和 `onboarding.js` 组件。基于讨论，改为在现有 `#/configs` 页面和 `config-editor` 组件上扩展，避免功能重叠，降低开发成本。

#### 后端新增

**新增端点** `app/api/admin.py`：

```
GET  /api/v1/admin/onboarding/templates     — 列出可用模板（含状态和策略）
POST /api/v1/admin/onboarding/import/{slug}  — 导入模板 → 自动清理 → 创建 draft
```

`GET /templates` 返回：
```json
[
  {
    "slug": "redis-cache",
    "display_name_cn": "Azure Redis 缓存",
    "service_name": "Azure Cache for Redis",
    "quantity_model": "instances_x_hours",
    "onboarding_strategy": "template",
    "status": "available"
  }
]
```

`POST /import/{slug}` 导入时自动处理：
1. 读取 `data/generated_service_configs/{slug}.json`
2. 移除 `_acn_slug`、`_acn_display_name` 等生成元数据
3. 从 `data/slug_to_service_name.json` 查找英文 `service_name`、`display_name_cn`、`family_keys`
4. 创建 draft config（调用已有 `config_repo.create_config`）
5. 如果产品不在 catalog 中，按 `_product_index` 中的 `primary_family` 自动添加到对应 family（含 `display_name_cn`）

**复用已有端点**（无需修改）：
- `POST /explore/cascade` — 预览级联筛选
- `POST /explore/meters` — 预览 meter 数据
- `PUT /admin/configs/{name}` — 保存编辑
- `POST /admin/configs/{name}/validate` — 校验
- `POST /admin/configs/{name}/publish` — 发布

**新增参数** `app/api/explore.py`：
```
GET /api/v1/explore/service-config/{service_name}?draft=true
```
- `draft=true` 时从 DB 查 draft/published config（不走发布缓存）
- 用于 Admin 中的 Calculator 预览功能
- MVP 阶段不加复杂鉴权，仅在 Admin UI 中触发

#### 前端改动（扩展现有组件，不新建页面）

**config-list.js 改动**：
- Config 列表页顶部新增"从模板导入"按钮
- 点击弹出模板选择列表（调用 `GET /admin/onboarding/templates`）
- 每个模板显示：slug、中文名、quantity_model、状态（可导入 / 已导入为 draft / 已发布）、策略（template / manual）
- 选择后调用 `POST /admin/onboarding/import/{slug}` → 创建 draft → 自动跳转到编辑页

**config-editor.js 改动**：
- 新增 **API 预览 Tab**（与现有 form 面板、JSON 面板并列）：
  - 「测试 Cascade」按钮 → 调用 `POST /explore/cascade`（空 selections）→ 展示可用维度和选项
  - 「测试 Meters」按钮 → 选定 region/product/sku 后调用 `POST /explore/meters` → 展示 meter 列表
  - 展示结果辅助填写 meter_labels、meter_order、hidden_meters、hidden_dimensions
- 新增 **"在 Calculator 中预览"按钮**：
  - 点击后先保存当前草稿 → 新标签页打开 `frontend/?preview=<service_name>`
  - Calculator 检测 `?preview=` 参数，自动添加 service 到 estimate + 加载 config 时带 `?draft=true`
  - 页面显示"预览模式"提示条

**不新增的内容**：
- ~~`#/onboarding` 路由~~ — 不需要
- ~~`onboarding.js` 组件~~ — 不需要
- ~~独立的"发布检查 Tab"~~ — config-editor 已有 validate + publish 按钮

#### 工作流程

```
开发者打开 Admin UI → #/configs
  │
  ├── 1. 点击"从模板导入" → 选择 slug → 后端自动清理 + 创建 draft
  │     └─ 如产品不在 catalog → 自动按 primary_family 添加
  │
  ├── 2. 进入 Config Editor → form/JSON 双面板编辑
  │     └─ 调整 service_name、defaults、hidden_dimensions 等
  │
  ├── 3. 切到 API 预览 Tab
  │     └─ 测试 cascade → 看到可用维度/选项
  │     └─ 测试 meters → 看到 meter 列表 → 据此填写 meter_labels、meter_order
  │
  ├── 4. 点击"在 Calculator 中预览"
  │     └─ 新标签页打开 Calculator → 看到 estimate card 实际渲染效果
  │     └─ 根据渲染结果回来调整 config
  │
  └── 5. 校验 + 发布
        └─ validate → publish → 自动导出 JSON + 更新缓存
```

### 6.3 slug_to_service_name 映射表升级

映射表需要扩展以支持 Onboarding 自动化和多对一映射：

```json
{
  "_comment": "slug → product mapping + product index",

  "redis-cache": {
    "service_name": "Azure Cache for Redis",
    "api_service_name": "Azure Cache for Redis",
    "display_name_cn": "Azure Redis 缓存",
    "description_cn": "为应用提供高吞吐量、低延迟的数据缓存",
    "role": "primary"
  },
  "virtual-machines-linux": {
    "service_name": "Virtual Machines",
    "display_name_cn": "虚拟机",
    "role": "variant"
  },
  "virtual-machines-windows": {
    "service_name": "Virtual Machines",
    "display_name_cn": "虚拟机",
    "role": "variant"
  },

  "_product_index": {
    "Azure Cache for Redis": {
      "primary_slug": "redis-cache",
      "all_slugs": ["redis-cache"],
      "family_keys": ["databases"],
      "primary_family": "databases",
      "onboarding_strategy": "template"
    },
    "Virtual Machines": {
      "primary_slug": "virtual-machines-linux",
      "all_slugs": ["virtual-machines-linux", "virtual-machines-windows", "..."],
      "family_keys": ["compute"],
      "primary_family": "compute",
      "onboarding_strategy": "manual",
      "note": "大聚合产品，config 需手工策划"
    },
    "Application Gateway": {
      "primary_slug": "application-gateway-standard-v2",
      "all_slugs": ["application-gateway-standard-v2"],
      "family_keys": ["networking", "security"],
      "primary_family": "networking",
      "onboarding_strategy": "template"
    }
  }
}
```

新增字段说明：

| 字段 | 位置 | 说明 |
|------|------|------|
| `role` | slug 条目 | `primary`（主 slug）或 `variant`（同产品的其他 slug） |
| `api_service_name` | slug 条目 | Azure API 中的 serviceName（如果和 service_name 不同） |
| `family_keys` | _product_index | 数组，支持一个产品归属多个 family |
| `primary_family` | _product_index | 主 family，用于 Onboarding 导入时的 catalog 归类 |
| `onboarding_strategy` | _product_index | `template`（可直接导入）或 `manual`（需手工策划） |

### 6.4 产品接入优先级

**前提条件**：每个产品接入前，需先确认该产品在 Azure Global Retail Prices API 中查询 CN 区域时有数据。没有数据的产品 MVP 阶段暂缓，等 Phase 4 数据源切换后再处理。

**Batch 1 — 简单产品（1:1 slug 映射，预计每个 15-30 min）**

| slug | service_name | api_service_name | quantity_model | Global API CN 数据 | 备注 |
|------|-------------|-----------------|---------------|-------------------|------|
| redis-cache | Azure Cache for Redis | 待确认 | instances_x_hours | 待验证 | Tier 选择，已在 catalog |
| container-registry | Container Registry | 待确认 | per_meter | 待验证 | Tier + 月费 |
| managed-grafana | Managed Grafana | 待确认 | per_meter | 待验证 | 3 个 meter，已在 catalog |
| site-recovery | Site Recovery | 待确认 | per_meter | 待验证 | 2 个 meter |
| azure-ddos-protection | Azure DDoS Protection | 待确认 | per_meter | 待验证 | 月费 + 超额 |
| azure-ddos-ipprotection | Azure DDoS IP Protection | 待确认 | per_meter | 待验证 | 每 IP 月费 |
| azure-fluid-relay | Azure Fluid Relay | 待确认 | per_meter | 待验证 | 4 个 meter |
| notification-hub | Notification Hubs | 待确认 | per_meter | 待验证 | Tier + 阶梯 |
| database-migration | Database Migration Service | 待确认 | instances_x_hours | 待验证 | 简单实例选择 |

**Batch 2 — per_meter 细化（预计每个 30-60 min）**

| slug | service_name | api_service_name | Global API CN 数据 | 备注 |
|------|-------------|-----------------|-------------------|------|
| traffic-manager | Traffic Manager | 待确认 | 待验证 | 5 meter，DNS 有阶梯 |
| network-watcher | Network Watcher | 待确认 | 待验证 | 4 meter，各有不同阶梯 |
| ip-address | Public IP Addresses | 待确认 | 待验证 | 3 种部署模型 |
| application-gateway-standard-v2 | Application Gateway | 待确认 | 待验证 | 2 个费用组件，已在 catalog |
| schedule | Scheduler | 待确认 | 待验证 | Tier + 用量阶梯 |

**Batch 3 — 需架构扩展（暂缓，OUT OF SCOPE）**
- azure-front-door, hdinsight, iot-hub+dps, active-directory-b2c

**Batch 1-2 的 14 个模板全部是简单产品（1:1 slug 映射），多对一映射问题不影响近期工作。**

### 6.5 Catalog 中尚需添加的产品

当前 catalog 有 28 个产品、10 个 family。Batch 1-2 中部分产品不在 catalog 中，导入时由后端按 `_product_index.primary_family` 自动添加。

| 产品 | family_keys | primary_family | 需新建 family |
|------|-------------|---------------|--------------|
| Container Registry | ["databases"] | databases | 否 |
| Site Recovery | ["management"] | management | **待确认** — 是否新建，或归入 security |
| Azure DDoS Protection | ["networking", "security"] | networking | 否 |
| Azure DDoS IP Protection | ["networking", "security"] | networking | 否 |
| Azure Fluid Relay | ["web"] | web | 否 |
| Notification Hubs | ["integration"] | integration | 否 |
| Database Migration Service | ["databases"] | databases | 否 |
| Traffic Manager | ["networking"] | networking | 否 |
| Network Watcher | ["networking"] | networking | 否 |
| Public IP Addresses | ["networking"] | networking | 否 |
| Scheduler | ["integration"] | integration | 否 |

> **需同事确认**：(1) 上述 family 归属是否正确 (2) 哪些产品需归属多个 family (3) 是否新建 management family

---

## 依赖关系

```
Step 1-5 (✅ 已完成，一次性任务)
  │
  ├──→ Step 6.2 (扩展 Config Editor: 模板导入 + API 预览 + Calculator 预览)
  ├──→ Step 6.3 (映射表升级: family_keys + _product_index)
  └──→ Step 6.4 (逐产品接入，按 Batch 1 → 2 → 3 顺序)
        └── 前提: 确认 Global API 有 CN 区域数据
```

---

## 涉及的关键文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/convert_acn_datamodel.js` | ✅ 已完成 | Node.js JS→JSON 转换器（一次性） |
| `scripts/extract_acn_metadata.py` | ✅ 已完成 | Python 元数据提取（一次性） |
| `scripts/apply_cn_names.py` | ✅ 已完成 | 应用中文名到 catalog（一次性） |
| `scripts/generate_service_configs.py` | ✅ 已完成 | 批量生成 config 模板（一次性） |
| `scripts/price_drift_report.py` | ✅ 已完成 | 价格对比报告（Phase 4 使用） |
| `app/api/admin.py` | **修改** | 新增 2 个 onboarding 端点（list templates, import） |
| `app/api/explore.py` | **修改** | service-config 端点新增 `?draft=true` 参数 |
| `admin/js/components/config-list.js` | **修改** | 新增"从模板导入"按钮 |
| `admin/js/components/config-editor.js` | **修改** | 新增 API 预览 Tab + "在 Calculator 中预览"按钮 |
| `admin/js/api.js` | **修改** | 新增 onboarding + preview API 函数 |
| `admin/index.html` | **修改** | config-editor 区域新增 API 预览 Tab 模板 |
| `frontend/js/app.js` | **修改** | 检测 `?preview=` 参数，自动添加 service |
| `frontend/js/api.js` | **修改** | `fetchServiceConfig()` 支持 `draft` 参数 |
| `frontend/index.html` | **修改** | 预览模式提示条 |
| `data/slug_to_service_name.json` | **修改** | 补充 `_product_index`、`role`、`api_service_name`、`family_keys` |

> **不新建**独立 `#/onboarding` 路由或 `onboarding.js` 组件 — 所有功能集成到现有 config-list 和 config-editor 中。

---

## 验证方式

1. **Step 1-3**: ✅ 已验证（257 条目提取，28 产品中文名已填充，306 测试通过）
2. **模板导入后端**:
   - `GET /admin/onboarding/templates` 返回 14 个模板列表（含 status 和 strategy）
   - `POST /admin/onboarding/import/redis-cache` → 成功创建 draft config + catalog entry
3. **Config Editor 扩展**:
   - Config 列表页点击"从模板导入" → 弹出模板列表 → 选择 → 跳转编辑页
   - Config Editor API 预览 Tab → 测试 cascade 返回维度选项，测试 meters 返回 meter 列表
   - "在 Calculator 中预览" → 新标签页打开，estimate card 正确渲染，显示"预览模式"提示条
4. **端到端验证**（redis-cache demo）:
   - 导入 → 编辑 → API 预览辅助填 meter_labels → Calculator 预览 → 发布
   - Calculator 正式加载该产品
5. **回归测试**: `uv run pytest` 确保后端测试仍全部通过

---

## 讨论问题（QA）

### Q1: 生成的模板和 Azure Global API 数据不匹配怎么办？

Legacy datamodel 中的产品结构（Types/Features/Sizes）是 ACN 特有的硬编码数据，和 Azure Global Retail Prices API 的维度结构可能不同。例如：
- Legacy 中 Redis Cache 有 3 个 Tier（基本/标准/高级），Global API 可能有 5 个（含 Enterprise/Enterprise Flash）
- Legacy 中的 meter 名称是中文，Global API 返回英文

**结论**：生成的模板只作为**起点参考**（quantity_model、dimension_labels 等结构性建议），具体的 meter_labels、meter_order、sku_groups 等值在 Config Editor 的 **API 预览 Tab** 中查看实际 API 返回后填写。这是 API 预览 Tab 存在的核心价值。

### Q2: 产品在 Global API 中没有 CN 区域数据怎么办？

某些 ACN 特有产品可能在 Global Retail Prices API 中没有 CN 区域的返回数据。这些产品在 MVP 阶段无法通过 Explore API 获取定价。

**结论**：
- 模板列表中显示「API 无数据」标记
- 这些产品 MVP 暂不接入，等 Phase 4 数据源切换到 CN CSV + PostgreSQL 后再处理
- Batch 1-2 产品接入前需先验证 Global API 数据可用性（见 6.4 表格中"Global API CN 数据"列）

### Q3: 是否需要审核/审批流程？

**结论**：MVP 阶段保持单人操作（draft → publish），未来可扩展：
- 增加 `status: "pending_review"` 状态
- 发布前需要另一人确认
- 与企业 SSO/RBAC 集成

### Q4: slug_to_service_name 映射表的维护和多对一映射

260 个 legacy slug 对应 28 个产品，关系是多对一。映射表通过 `role`（primary/variant）和 `_product_index`（反向索引）来管理这种关系。

**结论**：
- 映射表继续用 JSON 文件维护（~30 条目 + 低变更频率）
- `_product_index` 段提供以产品为中心的反向索引，含 `family_keys`（数组，支持多 family 归属）、`onboarding_strategy`（template/manual）
- 大聚合产品（VM 54+ slugs、Storage 54+ slugs）标记为 `manual` 策略，模板仅供参考
- Batch 1-2 全部是 1:1 简单映射，不受多对一问题影响

### Q5: 区域约束（region_constraints）的使用

`region_constraints` 已写入 `product_catalog.json`，但前端筛选和后端 cascade 并未实际使用。

**结论**：**OUT OF SCOPE for MVP**。
- 本轮已完成数据标记
- 后续迭代中：前端 service-picker 显示区域标签，后端 cascade 按 region 过滤
- 需要确认约束粒度：service 级别还是 meter/SKU 级别

### Q6: data/generated_service_configs/ 这些文件是否需要版本控制？

**结论**：保留在 git 中作为参考。这些是一次性脚本产物，量不大（14 个文件），作为 Onboarding 导入的数据源需要可访问。最终生产 config 在 `app/config/service_configs/` 中。
