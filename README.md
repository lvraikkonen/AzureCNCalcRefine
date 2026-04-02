# Azure.cn Pricing Calculator

Azure China 定价计算器 — 面向 azure.cn 的定价计算工具，参照 Azure 国际站 Pricing Calculator 的交互模式实现，接入 CN 真实价格数据。

## 快速开始

```bash
# 环境要求：Python 3.12+, uv (https://docs.astral.sh/uv/), PostgreSQL

# 安装依赖
uv sync

# 数据库迁移
uv run alembic upgrade head

# 导入 CN 定价数据（从 CSV）
uv run python scripts/import_data.py

# 启动开发服务器
uv run uvicorn app.main:app --reload

# 浏览器访问 http://localhost:8000
```

## 项目结构

```
├── app/                              # 后端 (FastAPI)
│   ├── main.py                       # 应用入口，路由挂载 + 静态文件服务
│   ├── api/
│   │   ├── explore.py                # Explore API — 级联筛选 + Meter 查询（当前代理 Global API）
│   │   ├── admin.py                  # Admin API — 配置 CRUD + 版本历史 + draft/publish
│   │   └── products.py               # 产品目录 API
│   ├── config/
│   │   └── product_catalog.json      # 产品目录（families → services，含中文名）
│   ├── services/
│   │   ├── global_pricing.py         # Azure Global API 客户端（开发/调试用）
│   │   └── sub_dimensions/           # VM productName 子维度解析器
│   ├── models/                       # SQLAlchemy ORM 模型
│   └── schemas/                      # Pydantic 请求/响应模型
│
├── frontend/                         # Calculator 前端 (Vanilla JS SPA)
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── app.js                    # 应用初始化，检测 ?preview= 参数
│       ├── api.js                    # API 客户端
│       ├── state.js                  # 状态管理 + 事件总线
│       ├── pricing.js                # 本地定价计算引擎（纯函数）
│       └── components/
│           ├── estimate-card.js      # 估算卡片（级联筛选 + 本地计算 + 价格展示）
│           ├── estimate-list.js      # 估算列表容器
│           ├── service-picker.js     # 产品目录导航 + 搜索
│           └── summary-bar.js        # 底部汇总栏
│
├── admin/                            # Admin UI (Alpine.js)
│   ├── index.html
│   └── js/
│       ├── app.js
│       ├── api.js
│       └── components/
│           ├── config-list.js        # 配置列表（含"从模板导入"入口）
│           └── config-editor.js      # 配置编辑器（form + JSON + API 预览 Tab）
│
├── data/
│   └── generated_service_configs/    # ACN Datamodel 提取的 14 个产品配置模板
│
├── scripts/
│   ├── import_data.py                # CN 价格数据导入（CSV → PostgreSQL）
│   └── extract_legacy_chinese.py     # 从 calculatordatamodel.js 提取中文内容（计划中）
│
├── plan/                             # 实现计划文档
│   └── MVP-plan.md                   # 当前 MVP 计划（含产品路线图）
├── research/                         # 技术研究文档
├── tests/                            # 测试
└── pyproject.toml
```

## 架构

### 三层数据架构

```
┌─ 配置数据 (How to present) ──────────────────────────────────────┐
│ 内容: quantity_model, display_maps, meter_overrides, defaults     │
│ 来源: Admin UI → service_configs (PostgreSQL + JSON 双写)         │
└──────────────────────────────────────────────────────────────────┘

┌─ CN 价格数据 (What does it cost — China) ────────────────────────┐
│ 内容: meter_id, retail_price, unit_price, tier_min_units          │
│ 来源: CN 数据库 → CN 价格 API（MVP P0）                           │
└──────────────────────────────────────────────────────────────────┘

┌─ Global 价格数据 (开发/调试) ────────────────────────────────────┐
│ 来源: Azure Global Retail Prices API (prices.azure.com)           │
│ 用途: 开发调试 + 对照验证（当前 Explore API 使用此数据源）          │
└──────────────────────────────────────────────────────────────────┘
```

### 当前系统架构

```
Calculator Frontend (Vanilla JS)
  ↓ POST /explore/cascade, /explore/meters
Explore API (FastAPI)
  ↓ fetch_global_prices()
Azure Global Retail Prices API (prices.azure.com)   ← 当前数据源（MVP P0 切换为 CN API）

Admin UI (Alpine.js)
  ↓ /api/v1/admin/*
Admin API → PostgreSQL (service_configs + product_catalog)
```

### 两阶段计算模型

前端采用"**级联筛选调 API + 选定 Instance 后本地计算**"的两阶段架构：

```
阶段 1 — 维度选择（需要 API）
  用户选择 Region/OS/Instance
  → POST /explore/cascade（级联筛选，自动收窄选项）
  → POST /explore/meters（获取全部 type/term 的 meter 定价数据，缓存到前端）

阶段 2 — 价格计算（纯本地）
  切换 PAYG / Reserved / Savings Plan → 即时计算，无 API 调用
  修改数量 / 时长                     → 即时计算，无 API 调用
```

### Per-Product JSON 配置

每个产品有一个 JSON 配置（存储在 `service_configs` 表），控制 Calculator UI 的展示内容：

```
JSON 控制"内容"                        代码控制"结构"
──────────────────────────────────     ──────────────────────────────
display_maps（显示名映射）               5 种渲染模板（按 quantity_model 选择）
meter_overrides（计量覆盖）               级联筛选算法
product_sub_dimensions（子维度）          本地定价计算引擎
quantity_formula（计算公式 + 自定义输入）   View Cost Calculation 渲染
defaults（默认值）                        API 交互逻辑
visible_when（条件显示）
```

**`quantity_formula` — 计算公式配置：**

每个产品都能展示 "View Cost Calculation"（可折叠）。简单产品用 `quantity_model` 的默认公式（无需 JSON 配置），复杂产品在 JSON 中显式定义：

```
默认公式（VM、App Service 等）:          自定义公式（Redis Premium）:
  1 Instance × 730 Hours × $0.19/hr       1 Shard × (1 Primary + 1 Built-in
  = $137.24                                + 0 Additional) = 2 Nodes
                                          2 Nodes × 1 Instance × 730 Hours
                                          × $0.28/hr = $404.42
```

**5 种 `quantity_model` 与渲染模板：**

| quantity_model | 适用产品 | 状态 |
|---------------|---------|------|
| `instances_x_hours` | VM, App Service, Redis | ✅ 已有 |
| `per_meter` | Service Bus, Firewall, VPN Gateway | ✅ 已有 |
| `compute_plus_storage` | SQL Database, MySQL | ⏳ Phase 2 |
| `resource_dimensions` | Container Instances | ⏳ Phase 2 |
| `cross_service_composite` | HDInsight | ⏳ Phase 3 |

## 核心 API

### Explore API（级联筛选 + 定价）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/explore/service-config/{service_name}` | GET | 产品 JSON 配置（含 draft 模式） |
| `/api/v1/explore/cascade` | POST | 级联筛选（支持 VM 子维度） |
| `/api/v1/explore/meters` | POST | Meter 分层定价（全部 type/term） |

### Admin API（配置管理）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/admin/configs` | GET/POST | 列出 / 创建配置 |
| `/api/v1/admin/configs/{id}` | GET/PUT/DELETE | 配置 CRUD |
| `/api/v1/admin/configs/{id}/publish` | POST | 发布草稿 |
| `/api/v1/admin/configs/{id}/history` | GET | 版本历史 |
| `/api/v1/admin/onboarding/templates` | GET | 可用模板列表（计划中） |
| `/api/v1/admin/onboarding/import/{slug}` | POST | 从模板导入（计划中） |

### Products API（产品目录）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/products/catalog` | GET | 完整产品目录（families + services） |
| `/api/v1/products/search` | GET | 产品关键词搜索 |

## 功能清单

### Calculator 前端

- [x] 产品目录导航（分类侧栏 + 搜索）
- [x] 级联筛选（Region → OS → Tier → Instance Series → SKU）
- [x] 本地定价计算（阶梯定价、Reservation 总期价/月价转换）
- [x] Savings 单选按钮（PAYG / Savings Plan / Reservation，显示折扣百分比）
- [x] 数量输入模式切换（PAYG 显示时长 Hours/Days/Months，RI/SP 仅显示实例数）
- [x] 卡片折叠摘要（配置摘要 + Upfront/Monthly 双价格）
- [x] 底部汇总栏（Upfront + Monthly）
- [x] 从 JSON 配置加载默认值

### Admin UI

- [x] 配置列表（draft / published 状态）
- [x] 配置编辑器（表单 + JSON 双面板）
- [x] 版本历史浏览
- [x] draft/publish 工作流
- [ ] 从模板导入（MVP P0）
- [ ] API 预览 Tab（MVP P0）
- [ ] WYSIWYG Calculator 预览（MVP P1）

### 数据接入

- [x] Azure Global Retail Prices API（开发/调试）
- [x] PostgreSQL service_configs（9 个产品配置）
- [ ] CN 价格 API（MVP P0 — 从 CN 数据库构建）
- [ ] Legacy datamodel 中文内容提取（MVP P1）

## 开发

```bash
# 运行测试
uv run pytest

# 运行单个测试文件
uv run pytest tests/test_vm_parser.py

# 开发服务器（自动重载）
uv run uvicorn app.main:app --reload
```

## 技术栈

- **后端**: Python 3.12 + FastAPI + uvicorn
- **数据库**: PostgreSQL + SQLAlchemy + Alembic
- **前端 (Calculator)**: Vanilla HTML/JS/CSS（ES Modules，无构建工具）
- **前端 (Admin)**: Alpine.js
- **价格数据源（当前）**: Azure Global Retail Price API（实时代理）
- **价格数据源（MVP P0）**: CN 数据库 → CN 价格 API
- **包管理**: uv
- **测试**: pytest
