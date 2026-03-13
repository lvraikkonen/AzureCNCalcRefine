# Azure.cn Pricing Calculator

Azure China 定价计算器 — 面向 azure.cn 的定价计算工具，参照 Azure 国际站 Pricing Calculator 的交互模式实现。

> **当前阶段：MVP 概念验证 Demo**
> 前端直连 Azure Global Retail Price API，尚未接入本地数据库。用于验证产品交互模型和定价计算逻辑。

## 快速开始

```bash
# 环境要求：Python 3.12+, uv (https://docs.astral.sh/uv/)

# 安装依赖
uv sync

# 启动开发服务器
uv run uvicorn app.main:app --reload

# 浏览器访问 http://localhost:8000
```

## 项目结构

```
├── app/                          # 后端 (FastAPI)
│   ├── main.py                   # 应用入口，路由挂载 + 静态文件服务
│   ├── api/
│   │   ├── explore.py            # Explore API — 代理 Azure Global Retail Price API
│   │   └── products.py           # 产品目录 API
│   ├── config/
│   │   ├── product_catalog.json  # 服务目录（families → services）
│   │   └── service_configs/      # 各服务的默认配置
│   ├── services/
│   │   ├── global_pricing.py     # Azure Global API 客户端 + 阶梯定价算法
│   │   └── sub_dimensions/       # VM productName 子维度解析器
│   └── schemas/                  # Pydantic 请求/响应模型
│
├── frontend/                     # 前端 (Vanilla JS SPA)
│   ├── index.html
│   ├── css/style.css
│   └── js/
│       ├── app.js                # 应用初始化
│       ├── api.js                # API 客户端
│       ├── state.js              # 状态管理 + 事件总线
│       ├── pricing.js            # 本地定价计算引擎（纯函数）
│       └── components/
│           ├── estimate-card.js  # 估算卡片（级联筛选 + 本地计算 + 价格展示）
│           ├── estimate-list.js  # 估算列表容器
│           ├── service-picker.js # 产品目录导航 + 搜索
│           └── summary-bar.js    # 底部汇总栏
│
├── plan/                         # 实现计划文档
├── tests/                        # 测试
└── pyproject.toml
```

## 架构

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

这一设计在 MVP 阶段尤为重要 — Azure Global Retail Price API 延迟 500ms-2s，本地缓存 + 本地计算将交互延迟降到接近 0。

### 数据流（MVP）

```
前端 → FastAPI (explore.py) → Azure Global Retail Price API（实时代理）
```

### 数据流（未来生产环境）

```
Airflow DAG（每日） → ETL → PostgreSQL (retail_prices 表)
前端 → FastAPI → 本地 DB 查询（~10ms）
```

前端代码设计为**数据源无关** — 只依赖后端 API schema，后端从 Azure API 取还是从本地 DB 查，对前端透明。

## 核心 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/explore/service-config/{service_name}` | GET | 服务默认配置 |
| `/api/v1/explore/cascade` | POST | 级联筛选（支持 VM 子维度） |
| `/api/v1/explore/meters` | POST | Meter 分层定价（全部 type/term） |
| `/api/v1/products/catalog` | GET | 产品目录 |
| `/api/v1/products/search` | GET | 产品搜索 |

## 前端功能清单

- [x] 产品目录导航（分类侧栏 + 搜索）
- [x] 级联筛选（Region → OS → Tier → Instance Series → SKU）
- [x] 本地定价计算（阶梯定价、Reservation 总期价/月价转换）
- [x] Savings 单选按钮（PAYG / Savings Plan / Reservation，显示折扣百分比）
- [x] 数量输入模式切换（PAYG 显示时长 Hours/Days/Months，RI/SP 仅显示实例数）
- [x] 卡片折叠摘要（配置摘要 + Upfront/Monthly 双价格）
- [x] 卡片底部价格汇总（Upfront + Monthly + PAYG 对比价）
- [x] 从配置文件加载默认值（"Add to estimate" 后自动预填完整卡片）
- [ ] 底部汇总栏增强（Upfront + Monthly）
- [ ] 附加关联服务（Managed Disks / Storage / Bandwidth）

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
- **前端**: Vanilla HTML/JS/CSS（ES Modules，无构建工具）
- **数据源（MVP）**: Azure Global Retail Price API（实时代理）
- **数据源（生产）**: PostgreSQL + SQLAlchemy + Alembic（待接入）
- **包管理**: uv
- **测试**: pytest
