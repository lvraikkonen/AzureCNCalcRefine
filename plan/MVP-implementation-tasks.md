# MVP 实现任务计划 — Azure CN Pricing Calculator

> 基于 `plan/MVP-plan.md` 和 `research/product-pricing-patterns.md` 的 Pattern A/B 深度调研整理。
> 创建日期: 2026-04-02
> 前置文档: `plan/MVP-plan.md`、`research/product-pricing-patterns.md`
> 
> **⚠️ 实施原则**: MVP 阶段基于当前已有的知识和数据（一次性 CSV、已确认的字段映射和 serviceName 差异等）开始实现，后期随时可能根据新信息修改调整。

---

## 项目当前状态

### 当前状态

- Frontend 两阶段计算（cascade → meters → local calc），概念已验证。
- Pattern A (`instances_x_hours`) + Pattern B (`per_meter`) 渲染模板，待细化打磨
- Admin CRUD（draft/publish/版本历史/JSON 双面板），开发完成
- service_config: 需按照Pattern A/B 中列出研究的产品进行添加验证
- Product catalog: 28 产品, 10 family。已添加，导航已验证
- 本地 PostgreSQL 数据库已创建，数据库`azurecn_calc`

### 未实现（MVP 范围）

- CN csv价格数据导入
- CN 价格数据 API
- Admin 模板导入工作流
- Config Editor API 预览 Tab
- Admin WYSIWYG 预览
- quantity_formula + View Cost Calculation
- Pattern A/B 配置增强（Redis sub_dimensions、VPN Gateway is_base_fee）
- Legacy 中文内容提取
- Batch 产品接入

---

## 数据源策略：CN + Global 并行

**MVP 阶段 CN 数据源和 Global Pricing API 数据源并行使用。**

```
┌─ CN 数据源 (生产) ──────────────────────────────────────────────┐
│ 来源: 本地 PostgreSQL retail_prices 表 (CSV 导入, ~47k 行, CNY) │
│ 用途: CN region 的真实定价                                      │
│ 状态: 数据已有，需构建查询 API                                   │
│ 待确认: 表结构字段映射、更新频率、产品覆盖范围                     │
│         → 需与 ACN 价格数据同事沟通                              │
└─────────────────────────────────────────────────────────────────┘

┌─ Global 数据源 (开发/调试) ─────────────────────────────────────┐
│ 来源: Azure Global Retail Prices API (prices.azure.com)        │
│ 用途: 开发调试 + 对照参考 + Global region 定价                   │
│ 状态: 已接入，explore API 当前使用                               │
└─────────────────────────────────────────────────────────────────┘
```

**路由规则**:
- `armRegionName = china*` → CN 数据源
- 其他 region → Global API
- 可通过 `data_source` 参数显式切换

**设计要求**: CN 查询接口返回与 Global API 相同字段结构（serviceName, productName, skuName, meterName, unitPrice, tierMinimumUnits 等），前端和 explore API 逻辑无需感知数据源差异。

---

## 任务总览与依赖关系

```
P0-A: CN 价格导入数据库 / 价格 API ─────────┐
P0-B: 模板导入 ──────────┐                 │
P0-C: API 预览 Tab ──────┤                │
P1-B: quantity_formula ──┤  (可并行)      │
P1-C: Pattern A/B 增强 ──┤               │
P1-D: Legacy 提取脚本 ───┘                │
                         ↓              ↓
P1-A: WYSIWYG 预览 ─────────────────────┤
                                        ↓
P1-E: 端到端 Demo (redis-cache) ────────┘
                         ↓
P2: Batch 1 产品接入 (8 个)
```

**关键路径**: P0-A → P1-A → P1-E → P2

**可并行**: P0-B / P0-C / P1-B / P1-C / P1-D 互相独立

---

## Phase 1: P0 — 基础设施

### Task 1: CN 价格数据 API [P0-A, 工作量: L]

**目标**: 将ACN 价格数据 csv 导入本地PostgreSQL数据库，从本地 PostgreSQL `retail_prices` 表构建价格查询接口，格式与 Global API 对齐。Explore API 按 region 自动路由或显式切换 CN / Global 数据源。

**前置条件**: 需与 ACN 价格数据同事确认:

- `retail_prices` 表字段与 Global API 字段的对应关系
- CN 数据的更新频率和机制
- Batch 1 产品在 CN 数据库中的覆盖情况

**技术方案**:

1. **新建 CN 价格查询服务** `app/services/cn_pricing.py`
   - `async fetch_cn_prices(filters: dict) -> list[dict]`
   - 从 `retail_prices` 表查询，返回与 Global API 相同字段结构的 dict 列表
   - 字段映射: `retail_prices` 表字段 → Global API 字段名
     - `product_name → productName`
     - `sku_name → skuName`
     - `arm_region_name → armRegionName`
     - `tier_min_units → tierMinimumUnits`
     - `unit_price → unitPrice`
     - `retail_price → retailPrice`
     - `unit_of_measure → unitOfMeasure`
     - `meter_name → meterName` (待确认)
     - `service_name → serviceName`
     - `service_family → serviceFamily`
     - `type → type`
     - `term → reservationTerm / term` (待确认)
   - 复用 `global_pricing.py` 中的 `filter_non_devtest()` 等过滤逻辑

2. **修改 Explore API** `app/api/explore.py`
   - 新增 `data_source` 可选参数（`"cn"` / `"global"`）
   - 自动路由: `armRegionName` 以 `china` 开头 → CN 数据源
   - 统一入口 `_fetch_prices()` 内部按 data_source 分发

3. **前端** `frontend/js/api.js`
   - cascade/meters 请求可选传 `data_source` 参数（后端自动判断时可不传）

**涉及文件**:
| 文件 | 操作 |
|------|------|
| `app/services/cn_pricing.py` | 新建 |
| `app/api/explore.py` | 修改（数据源路由） |
| `app/schemas/explore.py` | 修改（+data_source 可选字段） |
| `frontend/js/api.js` | 可选修改 |

**验证**: CN region 查询 redis-cache 返回 CNY 价格；Global region 查询走原有 API

---

### Task 2: 模板导入功能 [P0-B, 工作量: S]

**目标**: Admin Config List 页面新增"从模板导入"，将 `data/generated_service_configs/` 中的模板创建为 draft config。

**技术方案**:

1. **后端** `app/api/admin.py` 新增两个端点:
   - `GET /api/v1/admin/onboarding/templates` — 扫描 `data/generated_service_configs/*.json`，返回列表（标注已导入的）
   - `POST /api/v1/admin/onboarding/import/{slug}` — 读取模板 → `create_config()` 创建 draft

2. **前端** `admin/js/components/config-list.js`:
   - 列表页新增 "从模板导入" 按钮
   - 弹出模板选择列表 modal → 选择 → 调用 import API → 刷新列表

3. **前端** `admin/js/api.js`:
   - `listTemplates()` / `importTemplate(slug)`

**涉及文件**:
| 文件 | 操作 |
|------|------|
| `app/api/admin.py` | 修改（+2 endpoints） |
| `admin/js/components/config-list.js` | 修改（+按钮 +modal） |
| `admin/js/api.js` | 修改（+2 API functions） |

**验证**: 导入 redis-cache 模板 → draft config 创建 → Config Editor 可编辑

---

### Task 3: API 预览 Tab [P0-C, 工作量: M]

**目标**: Config Editor 新增第三个 Tab（与 Form、JSON 并列），可测试 cascade/meters API，辅助配置填写。

**技术方案**:

`admin/js/components/config-editor.js` 新增 `"api-preview"` 面板:
- **Cascade 测试区**: 输入 service_name + region → `/explore/cascade` → 展示维度和选项
- **Meters 测试区**: 选择 region/product/sku → `/explore/meters` → 展示 meter 列表 + 价格
- **辅助提示**: 根据返回的 meterName 建议 `meter_labels` / `meter_order` 填写
- 支持切换 CN / Global 数据源

**涉及文件**:
| 文件 | 操作 |
|------|------|
| `admin/js/components/config-editor.js` | 修改（+API Preview tab） |
| `admin/js/api.js` | 修改（+explore API wrappers） |

**验证**: 在 Config Editor 中测试 Service Bus cascade → 看到 Basic/Standard/Premium

---

## Phase 2: P1 — 核心功能

### Task 4: quantity_formula + View Cost Calculation [P1-B, 工作量: L]

**目标**: 每个 estimate card 可展示可折叠 "View Cost Calculation"；简单产品用默认公式，复杂产品（Redis Premium）用 JSON 定义自定义公式。

**设计原则**:
- 简单产品（VM、App Service、DMS）**不需要** JSON 配置 — `quantity_model` 自带默认公式
- 复杂产品（Redis Premium）在 JSON 中配置 `quantity_formula`：自定义输入字段 + 计算表达式 + meter 选择
- 前端渲染引擎统一处理：无 formula → 默认模板；有 formula → 自定义输入 + 公式

**技术方案**:

1. **公式计算引擎** `frontend/js/pricing.js`:
   - `evaluateFormula(formula, variables)` — 简单四则运算 + 变量引用
   - `resolveFormulaQuantity(formulaConfig, inputs, metersCache)` → `{quantity, useMeter, steps[]}`

2. **View Cost Calculation 组件** `frontend/js/components/cost-calculation.js` (新建):
   - 可折叠区域，默认收起
   - 无 formula → 默认公式:
     - `instances_x_hours`: `[N] Instance x [H] Hours x $X/hr = $Y`
     - `per_meter`: 每个 meter 一行
   - 有 formula → 渲染 `display_steps` 模板，实时填入数值

3. **formula inputs 条件渲染** `frontend/js/components/estimate-card.js`:
   - 检测 `quantity_formula.applies_to` 条件
   - 匹配: 替换默认输入为 formula 定义的 inputs（Shard/Replicas/Instance）
   - 不匹配: 标准输入

4. **JSON 配置格式示例**:
   ```json
   {
     "quantity_formula": {
       "applies_to": {"productName": ["Azure Redis Cache Premium"]},
       "inputs": [
         {"key": "shards", "label": "Shard per Instance", "default": 1, "min": 1},
         {"key": "additional_replicas", "label": "Additional Replicas per Shard", "default": 0, "min": 0},
         {"key": "instances", "label": "Instance", "default": 1, "min": 1}
       ],
       "formula": "shards * (1 + 1 + additional_replicas) * instances",
       "use_meter": "Cache Instance",
       "display_steps": [
         "{shards} Shard x ({1} Primary + {1} Built-in + {additional_replicas} Additional) = {nodes} Nodes",
         "{nodes} Nodes x {instances} Instance x {hours} Hours x ${price}/hr = ${total}"
       ]
     }
   }
   ```

**涉及文件**:
| 文件 | 操作 |
|------|------|
| `frontend/js/pricing.js` | 修改（+formula 引擎） |
| `frontend/js/components/cost-calculation.js` | 新建 |
| `frontend/js/components/estimate-card.js` | 修改（集成 formula inputs + cost-calculation） |

**验证**:
- Redis Premium: 展开 View Cost Calculation → Shard x Replicas 公式 → $404.42
- Redis Basic: 展开 → 默认 `N x H x $/hr = $Y`
- VM: 展开 → 默认公式

---

### Task 5: Pattern A/B 配置增强 [P1-C, 工作量: M]

**5a: Redis Cache sub_dimensions (Pattern A)**

Redis `productName` 编码 Tier（`Azure Redis Cache Basic/Standard/Premium/Enterprise...`），需 sub_dimensions 解析。

- 新建 `app/services/sub_dimensions/redis_parser.py` — 从 productName 提取 Tier
- 更新 redis-cache service_config 添加 `sub_dimensions` 配置
- `quantity_model` 保持 `instances_x_hours`

**5b: VPN Gateway is_base_fee (Pattern B/E)**

- `meter_overrides` 新增 `is_base_fee: true` + `fixed_quantity: 1` 属性
- 前端 `estimate-card.js`: 识别 `is_base_fee` → 不显示输入框，固定用量 = 1
- 前端 `pricing.js`: 识别 `fixed_quantity` → 跳过用户输入

**涉及文件**:
| 文件 | 操作 |
|------|------|
| `app/services/sub_dimensions/redis_parser.py` | 新建 |
| `frontend/js/components/estimate-card.js` | 修改（is_base_fee 渲染） |
| `frontend/js/pricing.js` | 修改（fixed_quantity 计算） |

**验证**: Redis Tier 级联筛选正确；VPN Gateway 基础费自动计算无输入框

---

### Task 6: Admin WYSIWYG 预览 [P1-A, 工作量: M]

**目标**: Admin 编辑配置时可实时预览 Calculator 中的效果。

**依赖**: Task 1 (CN 价格 API)

**技术方案**:

1. **后端** `app/api/explore.py`:
   - `GET /explore/service-config/{name}?draft=true` — 从 DB 加载 draft（而非 published）
   - cascade/meters 使用 draft config 渲染

2. **前端 Calculator** `frontend/js/app.js`:
   - 检测 `?preview=<service_name>` → 自动添加产品 + 加载 draft 配置
   - 预览模式显示提示条 "Preview Mode — Draft Config"

3. **Admin** `admin/js/components/config-editor.js`:
   - "在 Calculator 中预览" 按钮 → 保存 draft → 新标签页打开预览

**涉及文件**:
| 文件 | 操作 |
|------|------|
| `app/api/explore.py` | 修改（draft 参数） |
| `app/services/config_repo.py` | 修改（get_draft_config） |
| `frontend/js/app.js` | 修改（preview 模式） |
| `frontend/js/api.js` | 修改（fetchServiceConfig +draft） |
| `admin/js/components/config-editor.js` | 修改（+预览按钮） |

**验证**: 修改 redis-cache config → 保存 → 预览 → Calculator 中看到改动

---

### Task 7: Legacy 中文内容提取 [P1-D, 工作量: S]

**目标**: 从 `calculatordatamodel.js` 批量提取中文名 + CN SKU 范围。

- 新建 `scripts/extract_legacy_chinese.py`
- 输出: 更新 `slug_to_service_name.json` 中的 `display_name_cn` + 生成 per-product 中文名映射

**涉及文件**:
| 文件 | 操作 |
|------|------|
| `scripts/extract_legacy_chinese.py` | 新建 |
| `data/slug_to_service_name.json` | 更新 |

**验证**: 输出含中文 Tier 名、Size 描述

---

### Task 8: 端到端 Demo — redis-cache [P1-E, 工作量: M]

**依赖**: Task 1 + 2 + 3 + 4 + 5a + 6

**Demo 流程**:
1. 模板导入 → `POST /admin/onboarding/import/redis-cache` → draft 创建
2. 编辑配置 → 调整 display_maps、defaults、quantity_formula
3. API 预览 → 测试 cascade（确认 Basic/Standard/Premium Tier）
4. API 预览 → 测试 meters（确认 Cache vs Cache Instance、CN 价格 CNY）
5. WYSIWYG 预览 → Basic=默认公式, Premium=自定义 formula
6. View Cost Calculation → 展开确认公式正确
7. 发布 → publish → Calculator 正式加载

**验证**: 全流程走通 + CN 价格 + formula 计算正确

---

## Phase 3: P2 — 批量接入

### Task 9: Batch 1 产品接入 [P2, 工作量: M]

验证端到端流程后，逐个接入 8 个 Pattern A/B 产品（每个 15-30 min）:

| 产品 | Pattern | 工作内容 |
|------|---------|---------|
| Azure Cache for Redis | A | 模板导入 + quantity_formula(Premium) + sub_dimensions |
| Container Registry | B | 模板导入 + meter_overrides |
| DDoS Protection | B | 简单，2 meter |
| Managed Grafana | B | 简单，3 meter |
| Notification Hubs | B | sku_filter + 阶梯定价 |
| Database Migration Service | A | 最简 Pattern A |
| Traffic Manager | B | region_to_zone 映射（可能需新增配置支持） |
| Application Gateway | B | meter_overrides |

---

## 建议实施顺序

```
Week 1:  Task 1 (CN 价格 API) ← 关键路径，最先开始
         Task 2 (模板导入)    ← 并行，S 量级
         Task 7 (Legacy 提取)  ← 并行，S 量级

Week 2:  Task 3 (API 预览 Tab)       ← 依赖 explore API 稳定
         Task 4 (quantity_formula)    ← 独立前端功能，并行
         Task 5 (Pattern A/B 增强)    ← 并行

Week 3:  Task 6 (WYSIWYG 预览)       ← 依赖 Task 1
         Task 8 (端到端 Demo)          ← 集成验证

Week 4:  Task 9 (Batch 1 接入)        ← 逐个产品上线
```

---

## 验证清单

| # | 验证项 | 预期结果 |
|---|--------|---------|
| 1 | CN 价格 API 查询 redis-cache (chinaeast2) | 返回 CNY 价格 |
| 2 | Global API 查询 redis-cache (eastus) | 返回 USD 价格（现有功能不受影响） |
| 3 | `GET /admin/onboarding/templates` | 返回可用模板列表 |
| 4 | `POST /admin/onboarding/import/redis-cache` | draft config 创建成功 |
| 5 | Config Editor API Preview Tab | cascade 返回维度，meters 返回价格 |
| 6 | Config Editor API Preview — 切换 CN/Global | 两个数据源都能正常返回 |
| 7 | WYSIWYG 预览 | Calculator 正确渲染 draft 配置 |
| 8 | View Cost Calculation（默认公式） | `N x H x $/hr = $total` |
| 9 | View Cost Calculation（Redis Premium） | Shard x Replicas 公式，价格正确 |
| 10 | Redis tier 切换 | Basic→标准输入; Premium→formula 输入 |
| 11 | VPN Gateway is_base_fee | 基础费无输入框，自动计算 |
| 12 | 端到端 Demo 全流程 | 导入→编辑→预览→发布 |
| 13 | `uv run pytest` | 回归测试全部通过 |

---

## 需确认的事项

| # | 事项 | 影响 | 优先级 |
|---|------|------|--------|
| 1 | ~~`retail_prices` 表字段与 Global API 字段的对应关系~~ ✅ 已确认：CSV 20 列与 Global API 字段完全一致，无语义差异。建表用 snake_case（PostgreSQL 惯例），导入时 camelCase→snake_case，查询返回时转回 camelCase。 | Task 1 字段映射——无需额外映射层 | 高 |
| 2 | ~~CN 数据中 serviceName 的命名规范（是否与 Global 一致）~~ ✅ 已确认：**不一致**。Batch 1 中 4/8 产品有差异（Redis Cache vs Azure Cache for Redis, Azure DDOS Protection vs Azure DDoS Protection, Azure Grafana Service vs Managed Grafana, Azure Database Migration Service vs Database Migration Service）。方案：service_config JSON 新增 `cn_service_name` 可选字段，不匹配时用它查 CN 数据源，省略时 fallback 到 `api_service_name`。 | service_config 需增加 `cn_service_name` 字段 | 高 |
| 3 | ~~CN 数据的更新频率和机制~~ ✅ 已确认：MVP 阶段使用 ACN 同事手动导出的一次性 CSV（46,877 行），直接导入 PostgreSQL 即可，无需缓存层或自动更新机制。数据 ETL pipeline 留到后续阶段设计。 | MVP 无需缓存层，后续再建 ETL | 中 |
| 4 | ~~Batch 1 产品在 CN 数据库中的数据覆盖情况~~ ✅ 已确认：8 个产品全部有数据。Redis Cache 最丰富（609 行，7 region，含 Reservation）；Grafana（4 行，1 region）和 Traffic Manager（8 行，1 region）数据较少但够用。无覆盖缺口，全部可接入。 | MVP 范围无需缩减 | 高 |
| 5 | ~~CN 数据是否有 Reservation / SavingsPlan 类型~~ ✅ 已确认：**均有**。Consumption 26,942 行、SavingsPlanConsumption 7,638 行、Reservation 6,751 行、DevTestConsumption 5,546 行。Batch 1 中 Redis Cache 有 Reservation（264 行，1Y/3Y），其余 7 个仅 Consumption。前端 Savings Options 逻辑无需改动。 | Savings Options 完全可用 | 中 |
| 6 | ~~CN 数据的 `armRegionName` 值~~ ✅ 已确认：共 12 种值。6 个标准 region（chinanorth/2/3, chinaeast/2/3），加上空值（3,546 行，全局服务）、`China`（国家级聚合）、`CN Zone 1/2`（带宽区域）、`Azure Stack CN`、`Zone 1 (China)`（旧格式）。MVP 默认 region 建议 `chinaeast2` 或 `chinanorth3`（数据最多）。路由规则需覆盖 `china*`、`China`、`CN *`、空值等情况。 | region 路由规则需比预想更全面 | 中 |
