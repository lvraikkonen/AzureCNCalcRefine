# Azure.cn Pricing Calculator - 实现方案

## Context

重做 Azure.cn 站点的产品价格计算器模块，功能对标 Azure 国际版 Pricing Calculator。用户角色为后端工程师，核心交付后端逻辑、数据库设计、API 实现，前端仅需简易 demo UI。

**技术栈**: Python + FastAPI + PostgreSQL
**第一期范围**: 核心计算器（不含登录/保存/分享）
**数据源**: `https://prices.azure.cn/api/retail/pricesheet/download?api-version=2023-06-01-preview` → CSV 文件 (46877 行, CNY)

---

## 数据分析摘要

| 维度 | 数值 |
|------|------|
| 总记录数 | 46,877 |
| Service Family | 20 个 (Compute 28818, Storage 6114, Databases 4671 等) |
| Service Name | 105 个 (Virtual Machines 23623, Storage 5869, SQL Database 1566 等) |
| 区域 | 6 个实际区域 (chinaeast/2/3, chinanorth/2/3) + 5 个逻辑区域 |
| 定价类型 | 4 种: Consumption, DevTestConsumption, Reservation, SavingsPlanConsumption |
| Term | 2 种: 1 Year, 3 Years |
| 计量单位 | 40 种 (1 Hour 最多34619, 1 GB/Month 1800 等) |
| 支持阶梯定价 | 是 (tierMinimumUnits > 0, 如 Storage Hot LRS 按 0/51200/512000 GB 分段) |

---

## 1. 项目目录结构

```
AzureCNCalcRefine/
├── README.md
├── pyproject.toml                  # 项目依赖 (poetry/pip)
├── alembic.ini                     # 数据库迁移配置
├── alembic/
│   ├── env.py
│   └── versions/                   # 迁移脚本
├── app/
│   ├── __init__.py
│   ├── main.py                     # FastAPI 入口, CORS, 路由挂载
│   ├── config.py                   # 配置 (数据库URL, 数据路径等)
│   ├── database.py                 # SQLAlchemy engine, session
│   ├── models/
│   │   ├── __init__.py
│   │   ├── pricing.py              # retail_prices 表模型
│   │   └── product_meta.py         # product_catalog 物化视图/表模型
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── product.py              # 产品列表/搜索请求响应 schema
│   │   ├── configuration.py        # 配置选项请求响应 schema
│   │   ├── estimate.py             # 估算请求响应 schema
│   │   └── common.py               # 通用 schema (分页等)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── products.py             # 产品目录 API
│   │   ├── configuration.py        # 产品配置选项 API
│   │   ├── pricing.py              # 价格计算 API
│   │   └── export.py               # 导出 API
│   ├── services/
│   │   ├── __init__.py
│   │   ├── product_service.py      # 产品目录业务逻辑
│   │   ├── config_service.py       # 配置维度推导逻辑
│   │   ├── pricing_service.py      # 价格计算核心逻辑
│   │   └── export_service.py       # Excel/CSV 导出逻辑
│   └── data_pipeline/
│       ├── __init__.py
│       ├── downloader.py           # 从 Azure.cn API 下载 CSV
│       ├── parser.py               # CSV 解析与清洗
│       └── importer.py             # 导入 PostgreSQL
├── scripts/
│   ├── import_data.py              # 一键导入脚本入口
│   └── refresh_data.py             # 定时刷新脚本
├── frontend/                       # 简易 demo UI
│   ├── index.html                  # 单页面入口
│   ├── app.js                      # 核心交互逻辑
│   └── style.css                   # 基础样式
├── tests/
│   ├── __init__.py
│   ├── test_product_api.py
│   ├── test_configuration_api.py
│   ├── test_pricing_api.py
│   └── test_data_pipeline.py
└── sample-data/
    └── AzureRetailPrices.csv       # 已下载的原始数据
```

---

## 2. 数据库设计

### 核心表: `retail_prices`

存储 CSV 原始定价数据，直接映射 CSV 列。

```sql
CREATE TABLE retail_prices (
    id              BIGSERIAL PRIMARY KEY,
    currency_code   VARCHAR(10) NOT NULL DEFAULT 'CNY',
    tier_min_units  DECIMAL(20,6) NOT NULL DEFAULT 0,
    retail_price    DECIMAL(20,6) NOT NULL,
    unit_price      DECIMAL(20,6) NOT NULL,
    arm_region_name VARCHAR(50),
    location        VARCHAR(50),
    effective_start_date TIMESTAMP,
    meter_id        VARCHAR(100),
    meter_name      VARCHAR(200),
    product_id      VARCHAR(50),
    sku_id          VARCHAR(50),
    product_name    VARCHAR(300),
    sku_name        VARCHAR(200),
    service_name    VARCHAR(200) NOT NULL,
    service_family  VARCHAR(100) NOT NULL,
    unit_of_measure VARCHAR(50),
    type            VARCHAR(50) NOT NULL,       -- Consumption/Reservation/SavingsPlanConsumption/DevTestConsumption
    arm_sku_name    VARCHAR(200),
    term            VARCHAR(20),                -- '1 Year' / '3 Years' / NULL
    is_primary_meter_region BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
```

### 索引设计

```sql
-- 核心查询: 按服务浏览产品
CREATE INDEX idx_rp_service_family ON retail_prices (service_family);
CREATE INDEX idx_rp_service_name ON retail_prices (service_name);

-- 级联筛选: serviceName + region + productName + skuName + type
CREATE INDEX idx_rp_cascade ON retail_prices (service_name, arm_region_name, product_name, type);

-- 价格查询: 精确匹配到具体 SKU + region + type
CREATE INDEX idx_rp_price_lookup ON retail_prices (product_name, sku_name, arm_region_name, type, term);

-- 产品搜索 (模糊匹配)
CREATE INDEX idx_rp_product_name_trgm ON retail_prices USING gin (product_name gin_trgm_ops);
CREATE INDEX idx_rp_service_name_trgm ON retail_prices USING gin (service_name gin_trgm_ops);

-- 数据去重
CREATE UNIQUE INDEX idx_rp_unique_row ON retail_prices (meter_id, sku_id, arm_region_name, type, tier_min_units, term)
    WHERE meter_id IS NOT NULL;
```

### 物化视图: `product_catalog`

从 retail_prices 聚合出产品目录（供产品列表展示用）。

```sql
CREATE MATERIALIZED VIEW product_catalog AS
SELECT DISTINCT
    service_name,
    service_family,
    -- 去掉 serviceName 中的 Series/Plan 等后缀得到简洁名称
    service_name AS display_name,
    MIN(effective_start_date) AS available_since,
    array_agg(DISTINCT arm_region_name) FILTER (WHERE arm_region_name NOT IN ('', 'China', 'CN Zone 1', 'CN Zone 2', 'Zone 1 (China)', 'Azure Stack CN')) AS available_regions,
    COUNT(DISTINCT product_name) AS product_variant_count
FROM retail_prices
WHERE is_primary_meter_region = TRUE
GROUP BY service_name, service_family
ORDER BY service_family, service_name;

CREATE UNIQUE INDEX idx_pc_service ON product_catalog (service_name);
```

> **注意**: 需要启用 `pg_trgm` 扩展以支持模糊搜索: `CREATE EXTENSION IF NOT EXISTS pg_trgm;`

---

## 3. API 设计

### 3.1 产品目录 API

**GET /api/v1/products/categories**
返回所有 serviceFamily 分组及其下 serviceName 列表。

```json
// Response
{
  "categories": [
    {
      "name": "Compute",
      "service_count": 12,
      "services": [
        {"service_name": "Virtual Machines", "product_count": 240},
        {"service_name": "Azure App Service", "product_count": 15},
        ...
      ]
    },
    ...
  ]
}
```

**GET /api/v1/products/search?q={keyword}&category={serviceFamily}&page=1&page_size=20**
搜索产品，支持按关键字和分类过滤。

```json
// Response
{
  "items": [
    {
      "service_name": "Virtual Machines",
      "service_family": "Compute",
      "available_regions": ["chinaeast", "chinaeast2", ...],
      "product_variant_count": 240
    }
  ],
  "total": 105,
  "page": 1,
  "page_size": 20
}
```

### 3.2 产品配置 API (级联筛选核心)

**POST /api/v1/products/{service_name}/configurations**
给定一个产品(service_name)和已有的部分选择，返回每个维度的可选值。这是级联筛选的核心 API。

```json
// Request
{
  "selections": {
    "arm_region_name": "chinaeast2",
    "type": "Consumption"
  }
}

// Response
{
  "service_name": "Virtual Machines",
  "dimensions": [
    {
      "field": "arm_region_name",
      "label": "Region",
      "options": ["chinaeast", "chinaeast2", "chinaeast3", "chinanorth", "chinanorth2", "chinanorth3"],
      "selected": "chinaeast2"
    },
    {
      "field": "product_name",
      "label": "Product",
      "options": ["Virtual Machines Dv3 Series", "Virtual Machines Dv4 Series", ...],
      "selected": null
    },
    {
      "field": "sku_name",
      "label": "SKU / Size",
      "options": ["D2 v3", "D4 v3", "D8 v3", ...],
      "selected": null
    },
    {
      "field": "type",
      "label": "Pricing Model",
      "options": ["Consumption", "Reservation", "SavingsPlanConsumption"],
      "selected": "Consumption"
    },
    {
      "field": "term",
      "label": "Term",
      "options": ["1 Year", "3 Years"],
      "selected": null,
      "visible": false  // 仅当 type 为 Reservation 或 SavingsPlan 时可见
    }
  ]
}
```

### 3.3 价格计算 API

**POST /api/v1/pricing/calculate**
根据完整配置 + 用量计算价格。

```json
// Request
{
  "items": [
    {
      "id": "item-1",
      "service_name": "Virtual Machines",
      "selections": {
        "arm_region_name": "chinaeast2",
        "product_name": "Virtual Machines Dv3 Series",
        "sku_name": "D2 v3",
        "type": "Consumption"
      },
      "quantity": 2,
      "usage": {
        "hours_per_month": 730
      }
    },
    {
      "id": "item-2",
      "service_name": "Storage",
      "selections": {
        "arm_region_name": "chinaeast2",
        "product_name": "General Block Blob v2",
        "sku_name": "Hot LRS"
      },
      "quantity": 1,
      "usage": {
        "storage_gb": 1000,
        "write_operations_10k": 100,
        "read_operations_10k": 500
      }
    }
  ]
}

// Response
{
  "items": [
    {
      "id": "item-1",
      "service_name": "Virtual Machines",
      "display_name": "Virtual Machines Dv3 Series - D2 v3",
      "region": "chinaeast2",
      "unit_price": 0.678302,
      "unit_of_measure": "1 Hour",
      "monthly_cost": 990.32,          // 0.678302 * 730 * 2
      "upfront_cost": 0,
      "currency": "CNY",
      "cost_breakdown": [
        {"meter": "D2 v3/D2s v3", "quantity": 1460, "unit_price": 0.678302, "subtotal": 990.32}
      ]
    },
    {
      "id": "item-2",
      "service_name": "Storage",
      "display_name": "General Block Blob v2 - Hot LRS",
      "region": "chinaeast2",
      "monthly_cost": 149.94,
      "upfront_cost": 0,
      "currency": "CNY",
      "cost_breakdown": [
        {"meter": "Hot LRS Data Stored", "quantity": 1000, "unit_price": 0.140564, "subtotal": 140.56, "note": "First 51200 GB"},
        {"meter": "Hot LRS Write Operations", "quantity": 100, "unit_price": 0.042453, "subtotal": 4.25},
        {"meter": "Hot Read Operations", "quantity": 500, "unit_price": 0.014151, "subtotal": 7.08}
      ]
    }
  ],
  "total_monthly_cost": 1140.26,
  "total_upfront_cost": 0,
  "currency": "CNY"
}
```

### 3.4 产品 Meter 列表 API

**POST /api/v1/products/{service_name}/meters**
给定产品配置，返回该配置下的所有计量项（meter），用于前端展示用量输入表单。

```json
// Request
{
  "selections": {
    "arm_region_name": "chinaeast2",
    "product_name": "General Block Blob v2",
    "sku_name": "Hot LRS"
  }
}

// Response
{
  "meters": [
    {
      "meter_name": "Hot LRS Data Stored",
      "unit_of_measure": "1 GB/Month",
      "tiers": [
        {"min_units": 0, "unit_price": 0.140564},
        {"min_units": 51200, "unit_price": 0.134938},
        {"min_units": 512000, "unit_price": 0.129317}
      ],
      "default_quantity": 0
    },
    {
      "meter_name": "Hot LRS Write Operations",
      "unit_of_measure": "10K",
      "tiers": [{"min_units": 0, "unit_price": 0.042453}],
      "default_quantity": 0
    },
    {
      "meter_name": "Hot Read Operations",
      "unit_of_measure": "10K",
      "tiers": [{"min_units": 0, "unit_price": 0.014151}],
      "default_quantity": 0
    },
    ...
  ]
}
```

### 3.5 导出 API

**POST /api/v1/export/excel**
接收完整估算数据，生成 Excel 文件下载。

```json
// Request: 同 /pricing/calculate 的请求体
// Response: Excel 文件流 (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
```

---

## 4. 核心算法: 级联筛选

> **详细分析文档**: [data-modeling.md](./data-modeling.md) — 包含级联筛选算法深度分析、数据三层结构、索引策略、Azure 国际版真实 API 数据对比、阶梯定价、各产品场景演示等。

级联筛选是计算器的核心交互——用户选择 Region 后，Product 列表自动收窄；选择 Product 后，SKU 列表收窄，以此类推。

**算法**:
```
输入: service_name, selections = {field: value, ...}
输出: 每个维度的可选值列表

1. base_query = SELECT * FROM retail_prices WHERE service_name = :service_name
     AND is_primary_meter_region = TRUE
     AND type NOT IN ('DevTestConsumption')  -- 默认排除开发测试价格

2. 定义维度顺序: dimensions = [arm_region_name, product_name, sku_name, type, term]

3. 对于每个 dimension D:
     filtered_query = base_query
     对于每个已选择的其他维度 D' (D' != D):
         filtered_query = filtered_query AND D' = selections[D']
     D.options = SELECT DISTINCT D FROM filtered_query

4. 处理条件可见性:
     - term: 仅当 type IN ('Reservation', 'SavingsPlanConsumption') 时可见
     - DevTestConsumption: 仅当用户明确选择时显示
```

SQL 实现示例（获取 sku_name 可选值）:
```sql
SELECT DISTINCT sku_name
FROM retail_prices
WHERE service_name = 'Virtual Machines'
  AND is_primary_meter_region = TRUE
  AND type != 'DevTestConsumption'
  AND arm_region_name = 'chinaeast2'       -- 已选
  AND product_name = 'Virtual Machines Dv3 Series'  -- 已选
  AND type = 'Consumption'                  -- 已选
ORDER BY sku_name;
```

---

## 5. 数据导入流程

```
scripts/import_data.py:
  1. 调用 downloader.py: 请求 Azure.cn API → 获取 CSV 下载 URL → 下载 CSV 文件
  2. 调用 parser.py: 读取 CSV → 清洗数据 (日期格式转换、空值处理、类型校验)
  3. 调用 importer.py:
     a. 创建临时表 retail_prices_staging
     b. COPY CSV 数据到 staging 表 (高速批量导入)
     c. 事务内: TRUNCATE retail_prices → INSERT FROM staging (或 UPSERT)
     d. REFRESH MATERIALIZED VIEW product_catalog
     e. 清理 staging 表
  4. 记录导入日志 (行数、耗时、数据版本)
```

---

## 6. 前端 Demo UI 结构

单页应用 (`frontend/index.html`), 用原生 HTML + JS + 少量 CSS，通过 FastAPI 静态文件挂载。

布局:
```
┌─────────────────────────────────────────────┐
│  Azure.cn Pricing Calculator                │
├──────────┬──────────────────────────────────┤
│ 分类导航  │  搜索框 [___________________]    │
│          │                                  │
│ Compute  │  产品卡片列表                     │
│ Storage  │  ┌──────┐ ┌──────┐ ┌──────┐     │
│ Database │  │VM    │ │App   │ │Cloud │     │
│ Network  │  │[Add] │ │[Add] │ │[Add] │     │
│ AI+ML    │  └──────┘ └──────┘ └──────┘     │
│ ...      │                                  │
├──────────┴──────────────────────────────────┤
│  Your Estimate  [Tab1] [Tab2] [+]  [Export] │
├─────────────────────────────────────────────┤
│  ┌ Virtual Machines ──────────── ¥990.32 ┐  │
│  │ Region: [▾chinaeast2]                 │  │
│  │ Product: [▾Dv3 Series]                │  │
│  │ SKU: [▾D2 v3]                         │  │
│  │ Pricing: [▾Consumption]               │  │
│  │ Quantity: [2]  Hours/month: [730]      │  │
│  │ Monthly: ¥990.32  Upfront: ¥0         │  │
│  └───────────────────────────────────────┘  │
│  ┌ Storage ───────────────────── ¥149.94 ┐  │
│  │ ...                                   │  │
│  └───────────────────────────────────────┘  │
├─────────────────────────────────────────────┤
│  Total Monthly Cost: ¥1,140.26              │
└─────────────────────────────────────────────┘
```

---

## 7. 开发阶段

### Phase 1: 基础设施 (Day 1)
- 初始化项目结构、pyproject.toml 依赖
- 配置 FastAPI + SQLAlchemy + Alembic
- 数据库连接与 retail_prices 表创建
- CSV 数据导入脚本完成并验证

### Phase 2: 产品目录 API (Day 2)
- 物化视图 product_catalog 创建
- GET /api/v1/products/categories
- GET /api/v1/products/search
- 单元测试

### Phase 3: 级联配置 API (Day 2-3)
- POST /api/v1/products/{service_name}/configurations (核心)
  - 基础 5 维度级联筛选
  - sub_dimensions 元数据：对已配置服务的 sku_name/product_name 解析子维度（access_tier + redundancy 等），返回 sub_dimensions 字段供前端本地级联
  - 子维度解析规则：Storage 空格分割、MySQL 正则、Cosmos DB 查表、VM 去后缀（详见 data-modeling.md 第十章）
- POST /api/v1/products/{service_name}/meters
  - 基础 meter 列表 + 阶梯定价 tiers
  - 增强字段：display_label（去 sku 前缀清洗）、category（primary/secondary/hidden）、default_quantity（从 unitOfMeasure 推导）、input_unit
  - quantity_model 返回（per_meter / instances_x_hours / units_x_hours）
  - tier description 自动生成（"First 50 TB" / "Over 500 TB"）
- 级联筛选逻辑实现与测试

### Phase 4: 价格计算 API (Day 3-4)
- POST /api/v1/pricing/calculate
- 阶梯定价计算逻辑
- Reservation/SavingsPlan 的 upfront + monthly 拆分
- 多产品汇总计算

### Phase 5: 导出 + Demo UI (Day 4-5)
- POST /api/v1/export/excel (openpyxl)
- 前端 demo UI 实现
- 端到端测试

### Phase 6: 服务配置模板系统
- 创建 `app/config/service_configs/` 目录
- `_default.json`: 通用默认配置（unit_defaults 映射表、label_cleanup 规则、meter 分类关键词）
- `storage.json`: sku_name → access_tier + redundancy（split_first_space 解析器）
- `virtual_machines.json`: product_name → os + series（vm_product_parser）
- `mysql.json`: product_name → deployment + tier + series（mysql_product_parser）
- `cosmos_db.json`: product_name → capacity_mode（cosmos_product_parser / 查表）
- 配置加载服务 `app/services/service_config.py`：按 service_name slug 查找 JSON，未找到 fallback 到 _default.json
- 集成到 configurations API（sub_dimensions 字段）和 meters API（display_label, category, default_quantity 字段）
- 未配置的服务行为不变，保持向后兼容

### Phase 7: 数据本地化与性能优化

当前 MVP 阶段的 cascade/calculator 端点直接调用 Azure Global Retail Prices 外部 API（`https://prices.azure.com/api/retail/prices`），每次下拉框变更触发一次外部请求，导致交互延迟明显（通常 1-3 秒/次）。需要改为本地数据查询以提升响应速度。

**改造内容**:
- 将 Azure.cn CSV 定价数据（~47k 行）导入本地 PostgreSQL `retail_prices` 表（表结构已设计好，见第 2 节）
- 改造 `app/services/global_pricing.py`：将 `fetch_global_prices()` 从外部 API 调用改为 SQLAlchemy 本地查询
- 利用已设计的索引（`idx_rp_cascade`, `idx_rp_price_lookup`）加速级联筛选和价格计算
- 预期效果：cascade 响应时间从 1-3s 降至 <50ms，calculator 从 2-5s 降至 <100ms
- 实现定时刷新脚本（`scripts/refresh_data.py`），支持增量更新

---

## 8. 关键依赖

```
fastapi>=0.100.0
uvicorn[standard]
sqlalchemy>=2.0
psycopg2-binary
alembic
pydantic>=2.0
openpyxl              # Excel 导出
httpx                 # 异步 HTTP (下载 CSV)
python-multipart      # 文件上传支持
```

---

## 9. 验证方式

1. **数据导入**: `python scripts/import_data.py` → 检查 PostgreSQL 行数 = 46877
2. **API 测试**: `uvicorn app.main:app --reload` → Swagger UI (`/docs`) 手动测试各 API
3. **级联筛选验证**: 选 VM → chinaeast2 → Dv3 Series → D2 v3 → Consumption → 确认返回 price=0.678302
4. **价格计算验证**: VM D2v3 chinaeast2, 2台 730小时 → monthly = ¥990.32
5. **阶梯定价验证**: Storage Hot LRS 1000GB → 第一段 0~51200GB 价格 0.140564
6. **导出验证**: 导出 Excel 文件, 内容与页面一致
7. **前端 Demo**: 完整走通 "浏览→添加→配置→计算→导出" 流程
