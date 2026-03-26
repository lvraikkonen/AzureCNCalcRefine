# MVP Plan — 产品接入工作流 + Admin 增强

> 基于 2025-03-25 讨论，综合 `acn-datamodel-onboarding-plan.md`、`onboarding-mvp-realign-plan.md` 的结论。

---

## 1. 项目定位

本项目是对废弃的 ACN Calculator 的**全面重做**：
- 新系统以 Azure Global Retail Prices API 为数据源，配置驱动，支持长期运营维护
- ACN Legacy `calculatordatamodel.js` 是**一次性参考数据来源**（中文名、区域约束、维度结构），已完成提取（Step 1-5），不再依赖
- Legacy datamodel 不进入生产数据流，提取脚本可重复执行但非设计目标

---

## 2. 当前状态

### 已完成

| 模块 | 状态 | 说明 |
|------|------|------|
| ACN Datamodel 提取 (Step 1-5) | ✅ | 14 个模板已生成至 `data/generated_service_configs/` |
| Frontend estimate area (Task 1-10) | ✅ | 两阶段计算、Savings Radio、per-meter 等 |
| Config Admin (Task 12) | ✅ | CRUD + 版本历史 + draft/publish + JSON 双写 |
| 产品 catalog | ✅ | 28 个产品有中文名，10 个 family |
| 生产 service_configs | ✅ | 9 个（VM, App Service, Firewall, Event Grid, SignalR, Load Balancer, Service Bus, Power BI Embedded, Azure SignalR Service） |

### 当前架构

```
Calculator Frontend (Vanilla JS)
  ↓ POST /explore/cascade, /explore/meters
Explore API (FastAPI)
  ↓ fetch_global_prices()
Azure Global Retail Prices API (prices.azure.com)
  ↗ 查询 CN 区域（chinaeast2 等）返回 CNY 价格

Admin UI (Alpine.js)
  ↓ /api/v1/admin/*
Admin API → PostgreSQL (service_configs + product_catalog)
                      ↕ JSON 文件 (app/config/service_configs/*.json 降级)
```

### 现有 Admin 基础设施

Admin 后端已有完整的 CRUD + 版本控制 + 发布工作流：

| 端点 | 用途 |
|------|------|
| `GET/POST/PUT/DELETE /admin/configs/*` | Config CRUD + 草稿/发布/归档 |
| `POST /admin/configs/{name}/publish` | 发布配置 |
| `POST /admin/configs/{name}/validate` | 校验配置 |
| `GET /admin/configs/{name}/history` | 版本历史 |
| `POST /admin/configs/{name}/revert/{ver}` | 回退版本 |
| `GET/POST/PUT/DELETE /admin/catalog/*` | Catalog family + service CRUD |
| `POST /admin/import/json-files` | 批量导入 JSON 文件 |

Admin 前端已有 4 个组件：config-list、config-editor（form+JSON 双面板）、catalog-manager、version-history。

---

## 3. 数据架构：价格数据 vs 配置数据

项目中存在两种**本质不同**的数据，生命周期和管道完全独立：

### 价格数据（What does it cost）

```
内容:     meter_id, retail_price, unit_price, tier_min_units, type, term...
特征:     高频变化（微软调价），量大（~47k rows）
MVP 来源: Azure Global Retail Prices API (prices.azure.com) — 实时查询
未来来源: CN CSV (azure.cn) → ETL → PostgreSQL retail_prices 表
```

### 配置数据（How to present it）

```
内容:     中文名、区域约束、维度结构、quantity_model、meter_labels、defaults...
特征:     低频变化（产品重新设计时才变），人工策划
来源:     Admin UI → service_configs (DB + JSON 双写)
参考:     ACN Legacy datamodel（一次性提取，模板 + 中文名）
```

### 两者的关系

```
配置数据 (service_configs)          价格数据 (Global API / 未来 PostgreSQL)
┌─────────────────────┐            ┌─────────────────────┐
│ quantity_model       │            │ product_name, sku    │
│ dimension_labels     │  控制展示   │ retail_price         │  提供数值
│ hidden_dimensions    │ ─────────→ │ tier_min_units       │ ─────────→ Calculator UI
│ meter_labels/order   │  怎么展示   │ type, term           │  展示什么
│ defaults             │            │ arm_region_name      │
└─────────────────────┘            └─────────────────────┘
       ↑                                    ↑
  通过 service_name 关联              通过 service_name 查询
```

### ACN Legacy Datamodel 的定位

| 提取物 | 性质 | 当前用途 | 生产环境角色 |
|--------|------|---------|------------|
| `acn_product_names.json` | 配置 | 中文名 + 区域约束 → catalog | 已消费完毕，不再需要 |
| `data/acn_dimension_templates/` | 配置 | 维度结构 → service_config 模板参考 | Onboarding 时人工参考 |
| `data/generated_service_configs/` | 配置 | 14 个待导入模板（~40% 完成度） | 导入后即完成使命 |
| `acn_price_validation.json` | 价格快照 | 无 | 未来数据源切换时 sanity check |

**Legacy datamodel 的提取是一次性任务，提取脚本幂等可重复执行但不进入生产数据流。一旦 Phase 4 (CN CSV → PostgreSQL) 完成，legacy 数据的历史使命彻底结束。**

---

## 4. MVP 范围

### IN SCOPE（本轮实现）

| # | 功能 | 优先级 | 说明 |
|---|------|--------|------|
| 1 | **模板导入功能** — 在现有 Config Editor 中增加"从模板导入"能力 | P0 | 后端 2 个端点 + 前端导入按钮 |
| 2 | **API 预览 Tab** — Config Editor 中新增 Tab，测试 cascade/meters | P0 | 辅助填写 meter_labels、meter_order |
| 3 | **Admin Config Preview** — 在 Admin 中预览 config 在 Calculator 中的效果 | P1 | 新标签页打开 Calculator + `?draft=true` |
| 4 | **redis-cache 端到端 demo** — 用第一个产品验证完整工作流 | P1 | 模板导入 → 编辑 → 预览 → 发布 |
| 5 | **slug_to_service_name 映射表升级** — 补充字段，支持 Onboarding 自动化 | P1 | 新增 family_keys、api_service_name、role 等 |

### OUT OF SCOPE（未来迭代）

| 功能 | 原因 | 归属 |
|------|------|------|
| 独立 `#/onboarding` 页面 | 在现有 `#/configs` 编辑器上扩展更经济 | 按需评估 |
| 数据源切换到 CN CSV + PostgreSQL | 独立的数据管道架构，Phase 4 | 独立规划 |
| region_constraints 在 cascade 中实际生效 | 需后端筛选逻辑变更 | Phase 4+ |
| 多角色审批流程 | MVP 单人操作足够 | 按需评估 |
| Batch 2-3 产品接入 | 依赖工作流验证后自行完成 | 工作流就绪后 |
| 复杂鉴权（preview token 等） | MVP 内部工具不需要复杂化 | 上线前 |
| ETL 自动化（Airflow DAG） | Phase 4 数据源切换的一部分 | 独立规划 |

---

## 5. 数据源策略

**MVP 阶段以 Azure Global Retail Prices API 为准**，目标是对齐 Global Calculator 的 UI 和配置模式。

```
MVP:     Explore API → Global Retail Prices API (实时, CNY for CN regions)
Phase 4: Explore API → 本地 PostgreSQL (CN CSV 导入, ~10ms 查询)
```

- 接入的产品**必须在 Global API 中有 CN 区域数据**，否则 cascade/meters 无法工作
- ACN Legacy 价格数据仅作参考，不参与 MVP 定价
- 数据源切换接口已预留：`explore.py` 中的 `fetch_global_prices()` 是唯一数据获取入口，未来替换为本地 DB 查询，路由层和前端无需改动

---

## 6. 关键数据结构：slug_to_service_name 升级

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

Legacy 的一个 slug 对应我们系统中的一个**维度切片**，不是独立产品。

### 对 Onboarding 的影响

| 情况 | 例子 | 策略 |
|------|------|------|
| 1 slug = 1 product（简单） | redis-cache, managed-grafana | `template` — 可直接导入模板 |
| 2-3 slugs = 1 product（小聚合） | ddos-protection + ddos-ipprotection | 选主 slug 导入，其余标记"已覆盖" |
| 多 slugs = 1 product（大聚合） | VM (54+), Storage (54+) | `manual` — 模板仅供参考，config 需手工策划 |

**Batch 1-2 的 14 个模板全部是简单产品（1:1 映射），多对一问题不影响近期工作。**

### 升级后的结构

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

关键字段说明：

| 字段 | 说明 |
|------|------|
| `role` | `primary`（主 slug）或 `variant`（同产品的其他 slug） |
| `api_service_name` | Azure API 中的 serviceName（如果和 service_name 不同） |
| `family_keys` | 支持一个产品归属多个 family（如 App Gateway → networking + security） |
| `primary_family` | 主 family，用于需要唯一归属的场景 |
| `onboarding_strategy` | `template`（可直接导入）或 `manual`（需手工策划） |

---

## 7. 实现计划

### P0-A: 模板导入功能

**后端新增** (`app/api/admin.py`)：

```
GET  /api/v1/admin/onboarding/templates        — 列出可用模板
POST /api/v1/admin/onboarding/import/{slug}     — 导入模板 → 创建 draft
```

`GET /templates` 返回：
```json
[
  {
    "slug": "redis-cache",
    "display_name_cn": "Azure Redis 缓存",
    "service_name": "Azure Cache for Redis",
    "quantity_model": "instances_x_hours",
    "status": "available",
    "onboarding_strategy": "template"
  }
]
```

`POST /import/{slug}` 自动处理：
1. 读取 `data/generated_service_configs/{slug}.json`
2. 移除 `_acn_slug`、`_acn_display_name` 等生成元数据
3. 从 `slug_to_service_name.json` 查找英文 `service_name`、`display_name_cn`、`family_keys`
4. 调用已有 `config_repo.create_config()` 创建 draft
5. 如果产品不在 catalog → 按 `_product_index` 中的 `primary_family` 自动添加到对应 family

**前端改动** (`admin/js/components/config-list.js`)：
- Config 列表页顶部新增"从模板导入"按钮
- 点击弹出模板选择列表（来自 `GET /templates`）
- 选择后调用 `POST /import/{slug}` → 创建 draft → 自动跳转到编辑页

### P0-B: Config Editor 增加 API 预览 Tab

**在现有 config-editor.js 中新增第三个 Tab**（与 form 面板、JSON 面板并列）：

API 预览 Tab 功能：
- **测试 Cascade** — 传入当前 config 的 `service_name` + 空 selections → 调用 `POST /explore/cascade` → 展示返回的维度和选项
- **测试 Meters** — 选定 region/product/sku 后调用 `POST /explore/meters` → 展示 meter 列表
- **辅助填写** — 根据 API 返回的 meter 名，辅助填写 `meter_labels`、`meter_order`、`hidden_meters`

这是最高价值的功能——让开发者看到 API 实际返回什么数据，就知道 config 该怎么填。

### P1-A: Admin Config Preview（在 Calculator 中预览）

**后端改动** (`app/api/explore.py`)：
```
GET /api/v1/explore/service-config/{service_name}?draft=true
```
- `draft=true` 时从 DB 查 draft/published config（不走发布缓存）
- MVP 阶段不加复杂鉴权，仅在 Admin UI 中使用

**前端改动**：
- Calculator (`frontend/js/app.js`)：检测 `?preview=<service_name>` URL 参数 → 自动添加该 service 到 estimate → 加载 config 时带 `?draft=true`
- Calculator (`frontend/index.html`)：预览模式顶部显示提示条"预览模式 — 当前使用草稿配置"
- Admin (`admin/js/components/config-editor.js`)：编辑页面新增"在 Calculator 中预览"按钮 → 先保存草稿 → 新标签页打开 `frontend/?preview=<service_name>`

预览功能仅在 Admin UI 中触发。MVP 不需要复杂鉴权，将来上线时再加 origin check 或 session token。

### P1-B: redis-cache 端到端 Demo

用 redis-cache 作为第一个产品走完整个工作流：

```
1. 导入模板 → POST /admin/onboarding/import/redis-cache → draft config 创建
2. 编辑配置 → Config Editor form 面板调整 meter_labels、defaults
3. API 预览 → Tab 2 测试 cascade（确认 Basic/Standard/Premium tier 可选）
4. API 预览 → Tab 2 测试 meters（确认 meter 列表和价格）
5. Calculator 预览 → 新标签页看到 estimate card 正确渲染
6. 发布 → publish → Calculator 正式加载
```

通过此 demo 验证：
- config schema 的哪些字段实际控制了 Calculator UI 的哪些部分
- 模板 ~40% 完成度的具体 gap 是什么
- 工作流是否顺畅，是否需要调整

### P1-C: slug_to_service_name 映射表升级

为 Batch 1-2 的 14 个 slug 补充字段：
- 新增 `api_service_name`（查 Global API 确认）
- 新增 `role` 字段
- 新增 `_product_index` 段（含 `family_keys`、`primary_family`、`onboarding_strategy`）
- 需要**同事确认** family 归属（见第 9 节）

---

## 8. 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `app/api/admin.py` | 修改 | 新增 2 个 onboarding 端点（list templates, import） |
| `app/api/explore.py` | 修改 | service-config 端点新增 `?draft=true` 参数 |
| `admin/js/components/config-list.js` | 修改 | 新增"从模板导入"按钮 |
| `admin/js/components/config-editor.js` | 修改 | 新增 API 预览 Tab + "在 Calculator 中预览"按钮 |
| `admin/js/api.js` | 修改 | 新增 onboarding API 函数 |
| `admin/index.html` | 修改 | config-editor 区域新增 API 预览 Tab 模板 |
| `frontend/js/app.js` | 修改 | 检测 `?preview=` 参数，自动添加 service |
| `frontend/js/api.js` | 修改 | `fetchServiceConfig()` 支持 `draft` 参数 |
| `frontend/index.html` | 修改 | 预览模式提示条 |
| `data/slug_to_service_name.json` | 修改 | 补充 `_product_index`、`role`、`api_service_name`、`family_keys` |

**不新建独立 onboarding 页面/组件** — 所有功能集成到现有 config-list 和 config-editor 中。

---

## 9. 需要同事确认的事项

### 9.1 Batch 1-2 产品的 family 归属

| slug | 建议 service_name | 建议 family | 是否需新建 family |
|------|-------------------|-------------|------------------|
| redis-cache | Azure Cache for Redis | databases | 否（已在 catalog） |
| container-registry | Container Registry | databases | 否 |
| managed-grafana | Managed Grafana | devops | 否（已在 catalog） |
| site-recovery | Site Recovery | management | **是** |
| azure-ddos-protection | Azure DDoS Protection | networking | 否 |
| azure-ddos-ipprotection | Azure DDoS IP Protection | networking | 否 |
| azure-fluid-relay | Azure Fluid Relay | web | 否 |
| notification-hub | Notification Hubs | integration | 否 |
| database-migration | Database Migration Service | databases | 否 |
| traffic-manager | Traffic Manager | networking | 否 |
| network-watcher | Network Watcher | networking | 否 |
| ip-address | Public IP Addresses | networking | 否 |
| application-gateway-standard-v2 | Application Gateway | networking | 否（已在 catalog） |
| schedule | Scheduler | integration | 否 |

**确认项**：
1. 上述 family 归属是否正确？
2. 是否有产品需要归属**多个 family**（如 Application Gateway → networking + security）？
3. 是否需要新建 `management` family（给 Site Recovery）？还是归入已有的 `security`？

### 9.2 api_service_name 确认

每个产品在 Azure Global Retail Prices API 中的 `serviceName` 需要查 API 实际返回值确认。这决定了 cascade/meters 查询能否返回数据。

### 9.3 Batch 1 产品在 Global API 中是否有 CN 区域数据

需要验证：对 14 个产品分别查询 `prices.azure.com`，确认 `chinaeast2` 等 CN 区域是否有返回数据。没有数据的产品 MVP 阶段暂缓接入。

---

## 10. 验证方式

| # | 验证项 | 预期结果 |
|---|--------|---------|
| 1 | `GET /admin/onboarding/templates` | 返回 14 个模板，每个标注 status 和 strategy |
| 2 | `POST /admin/onboarding/import/redis-cache` | draft config 创建成功，catalog 中出现产品 |
| 3 | Admin Config List 点"从模板导入" | 弹出模板列表，选择后跳转到编辑页 |
| 4 | Config Editor API 预览 Tab | 测试 cascade 返回维度选项，测试 meters 返回 meter 列表 |
| 5 | Config Editor 点"在 Calculator 中预览" | 新标签页打开，estimate card 正确渲染，显示"预览模式" |
| 6 | 编辑 meter_labels → 保存草稿 → 刷新预览 | 预览中看到改动生效 |
| 7 | 发布 → Calculator 正式加载 | 正常显示，无"预览模式"提示 |
| 8 | `uv run pytest` | 回归测试全部通过 |

---

## 11. 后续迭代路线（OUT OF SCOPE 参考）

```
本轮 MVP
  │
  ├── 工作流验证后 → Batch 1 剩余 8 个产品接入（每个 15-30 min）
  ├── Batch 1 完成后 → Batch 2 五个 per_meter 产品（每个 30-60 min）
  │
  ├── Phase 4: 数据源切换
  │     ├── CN CSV 定期下载 + import_data.py → retail_prices 表
  │     ├── explore.py: fetch_global_prices() → SQLAlchemy 本地查询
  │     ├── price_drift_report.py 验证价格一致性
  │     └── ETL 自动化（定时任务 / Airflow DAG）
  │
  ├── region_constraints 实际生效（cascade 按 region 过滤不可用产品）
  ├── 多角色审批（draft → pending_review → publish）
  └── Batch 3 需架构扩展的产品（front-door, hdinsight, iot-hub 等）
```

---

## 12. 关键设计决策记录

| 决策 | 结论 | 理由 |
|------|------|------|
| Onboarding 独立页面 vs 扩展现有 Config Editor | **扩展现有编辑器** | 避免功能重叠，开发成本低，核心价值（模板导入 + API 预览）可集成到现有组件 |
| ACN Legacy 数据的角色 | **一次性参考，不进入生产数据流** | Legacy 是静态快照不再更新，价格数据来自 Global API / 未来 CN CSV |
| MVP 数据源 | **Global Retail Prices API** | 对齐 Global Calculator UI 和配置模式，CN 区域查询可返回 CNY 价格 |
| Preview 鉴权 | **MVP 不加复杂鉴权** | 内部工具，将来上线前再加 |
| slug_to_service_name 存储 | **继续用 JSON 文件** | ~30 条目 + 低变更频率，JSON 文件足够 |
| 多 family 归属 | **family_keys 数组** | 符合 Azure 官方分类，实现简单 |
| 多 slug → 一个产品 | **_product_index 反向索引 + role 标记** | 区分 template/manual 策略，简单产品直接导入，大聚合产品仅参考 |
