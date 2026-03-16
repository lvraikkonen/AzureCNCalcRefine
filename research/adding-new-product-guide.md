# 新增产品接入指南

> 编写日期：2026-03-16
> 以 Virtual Machines（5 个子维度）和 App Service（2 个子维度）为参照

---

## 总览

每接入一个新产品，核心工作分 **4 层**：

| 层 | 文件 | 做什么 |
|----|------|--------|
| 1. 调研 | 手动 / 脚本 | 了解 API 返回的 productName 模式和定价类型 |
| 2. 后端 - 解析器 | `app/services/sub_dimensions/` | 将 productName 拆解为子维度 |
| 3. 后端 - 配置 | `app/config/service_configs/` | JSON 声明服务元数据 |
| 4. 前端 | `frontend/js/components/estimate-card.js` | 通常**零改动**（已数据驱动） |

下面按步骤展开。

---

## Step 0: 调研 — 理解产品的 API 数据

使用 Explore API 或直接查询 Azure Retail Prices API，收集目标产品的原始数据。

```bash
# 示例：查询 SQL Database 的所有行
curl "https://prices.azure.com/api/retail/prices?\$filter=serviceName eq 'SQL Database'" | python -m json.tool | head -100
```

重点关注：

| 关注点 | 说明 | 示例 |
|--------|------|------|
| **serviceName** | API 中的精确名称，可能与 catalog 中不同 | catalog 显示 `App Service`，API 需要 `Azure App Service` |
| **productName 模式** | 有哪些 productName？能拆出哪些子维度？ | `Azure App Service Premium v3 Plan - Linux` → os + tier |
| **需要排除的 productName** | 非计算/非核心产品 | `Azure App Service Domain` |
| **type 取值** | Consumption / Reservation / SavingsPlanConsumption | App Service 没有 SavingsPlan |
| **unitOfMeasure** | 定价单位 | `1 Hour`、`1/Month`、`10K` |
| **tierMinimumUnits** | 是否有阶梯定价 | Storage 类产品常见 |

将调研结果记录到 `research/` 目录备查。

---

## Step 1: 创建 productName 解析器

**文件**：`app/services/sub_dimensions/<service>_parser.py`

参照 `vm_parser.py`（复杂）或 `appservice_parser.py`（简单），实现：

### 1a. 定义数据类

```python
@dataclass(frozen=True)
class XxxParsedProduct:
    original: str
    # 每个子维度一个字段
    os: str
    tier: str
    # ...
    excluded: bool  # 是否排除（非核心产品）
```

### 1b. 实现解析函数

```python
def parse_xxx_product_name(name: str) -> XxxParsedProduct:
    """将 productName 字符串解析为子维度。"""
    # 1. 检测并剥离后缀（如 OS）
    # 2. 剥离前缀
    # 3. 提取各子维度
    # 4. 白名单校验（推荐）— 不在已知值集中的视为 excluded
    ...
```

**建议**：如果子维度取值是有限集合（如 App Service 的 8 个 tier），使用**白名单**过滤。这样 API 返回的未知产品会自动被排除，下拉框保持干净。

### 1c. 编写单元测试

在 `tests/` 中添加测试，覆盖所有已知 productName 模式和需要排除的产品。

---

## Step 2: 注册解析器

**文件**：`app/services/sub_dimensions/__init__.py`

### 2a. 创建 Parser 类

```python
class XxxProductNameParser(SubDimensionParser):
    _SUB_DIMS = [
        SubDimensionDef(field="os", label="Operating System", attr="os", order=0),
        SubDimensionDef(field="tier", label="Tier", attr="tier", order=1),
        # ...更多子维度
    ]

    def target_field(self) -> str:
        return "product_name"

    def parse(self, value: str) -> XxxParsedProduct:
        return parse_xxx_product_name(value)

    def sub_dimension_definitions(self) -> list[SubDimensionDef]:
        return self._SUB_DIMS

    def is_excluded(self, parsed: object) -> bool:
        return isinstance(parsed, XxxParsedProduct) and parsed.excluded

    def normalize_value(self, field: str, raw_value: object) -> str | None:
        # 如需特殊映射（如 VM 的 tier=None → "Standard"），在此处理
        if raw_value is None or raw_value == "":
            return None
        return str(raw_value)
```

### 2b. 加入注册表

```python
_REGISTRY: dict[str, SubDimensionParser] = {
    "Virtual Machines": VmProductNameParser(),
    "App Service": AppServiceProductNameParser(),
    "Xxx Service": XxxProductNameParser(),          # ← 新增
}
```

注册表的 key 是 **catalog 中的服务名**（即前端发送的 `serviceName`），不是 API 中的名称。

---

## Step 3: 创建服务配置 JSON

**文件**：`app/config/service_configs/<service_slug>.json`

文件名规则：服务名小写 + 空格替换为下划线（如 `app_service.json`、`sql_database.json`）。

```jsonc
{
  // ── 名称映射 ──
  "service_name": "Xxx Service",           // catalog 中的名称
  "api_service_name": "Azure Xxx Service", // Azure API 中的 serviceName（如一致可省略）

  // ── 子维度定义 ──
  "sub_dimensions": {
    "target_field": "product_name",
    "parser": "xxx_product_parser",
    "dimensions": [
      { "field": "os",   "label": "Operating System", "order": 0 },
      { "field": "tier", "label": "Tier",              "order": 1 }
    ]
  },

  // ── 排除产品 ──
  "excluded_products": ["Azure Xxx Service Domain"],

  // ── 前端行为 ──
  "quantity_model": "instances_x_hours",
  "quantity_label": "Instances",     // 数量输入框的标签（VM 用 "VMs"）
  "static_subs": ["os", "tier"],     // 始终显示完整选项的子维度（从 preload 取）
  "hidden_subs": [],                 // 隐藏的子维度（VM 隐藏 "deployment"）

  // ── 默认值 ──
  "defaults": {
    "hours_per_month": 730,
    "selections": { "armRegionName": "westus" },
    "sub_selections": { "os": "Windows", "tier": "Standard" }
  }
}
```

### 各字段说明

| 字段 | 必填 | 说明 |
|------|------|------|
| `service_name` | 是 | 与产品目录中的名称一致 |
| `api_service_name` | 否 | 仅当 API serviceName 与 catalog 不同时需要（如 App Service） |
| `quantity_label` | 否 | 默认 `"VMs"`，按产品含义设置（Instances / Databases / ...） |
| `static_subs` | 否 | 默认取 `dimensions` 中的全部 field。静态子维度始终显示全量选项 |
| `hidden_subs` | 否 | 默认 `[]`。需要参与筛选但不显示给用户的子维度 |
| `defaults.selections` | 否 | 主维度默认值（region 等） |
| `defaults.sub_selections` | 否 | 子维度默认值 |

---

## Step 4: 前端（通常无需改动）

前端已完全数据驱动，以下行为由配置控制：

| 行为 | 数据来源 |
|------|----------|
| 显示哪些子维度下拉框 | 后端 cascade 返回的 `sub_dimensions` |
| 哪些子维度是静态/动态 | `serviceConfig.static_subs` |
| 哪些子维度隐藏 | `serviceConfig.hidden_subs` |
| 数量标签 | `serviceConfig.quantity_label` |
| 卡片图标 | `SERVICE_ICONS` 映射 |

**唯一需要手动添加的**：如果新产品需要自定义图标，在 `estimate-card.js` 顶部的 `SERVICE_ICONS` 中加一行：

```js
const SERVICE_ICONS = {
  'Virtual Machines': '🖥️',
  'App Service': '🌐',
  'SQL Database': '🗄️',   // ← 新增
};
```

不加也可以，会使用默认图标 `📦`。

---

## 完整 Checklist

以接入 `SQL Database` 为例：

- [ ] **调研**：查询 API，记录 productName 模式、type 取值、排除项
- [ ] **创建** `app/services/sub_dimensions/sqldatabase_parser.py`
  - [ ] `SqlDatabaseParsedProduct` 数据类
  - [ ] `parse_sqldatabase_product_name()` 解析函数
  - [ ] 白名单校验
- [ ] **注册** `app/services/sub_dimensions/__init__.py`
  - [ ] `SqlDatabaseProductNameParser` 类
  - [ ] 加入 `_REGISTRY`
- [ ] **配置** `app/config/service_configs/sql_database.json`
  - [ ] `api_service_name`（如需映射）
  - [ ] `sub_dimensions`、`static_subs`、`hidden_subs`
  - [ ] `quantity_label`、`defaults`
- [ ] **图标**（可选）`estimate-card.js` → `SERVICE_ICONS`
- [ ] **测试** `tests/test_sqldatabase_parser.py`
- [ ] **验证**：启动服务，从目录添加产品，检查下拉框、定价、savings 选项

---

## 常见问题

### Q: 如果产品不需要子维度怎么办？

某些简单产品的 productName 直接就是唯一值，不需要拆解。此时：
- 不创建 parser，不注册到 `_REGISTRY`
- 仍然创建 JSON 配置（设置 `quantity_label`、`defaults` 等）
- cascade 流程会正常工作，只是没有子维度下拉框

### Q: 如果 API serviceName 和 catalog 名称一致？

不需要设置 `api_service_name`，`_resolve_api_service_name()` 会直接使用 `service_name`。

### Q: 如何判断子维度应该是 static 还是 dynamic？

- **Static**：选项集固定，不随其他维度变化（如 os、tier）→ 放入 `static_subs`
- **Dynamic**：选项集随上游选择变化（如 VM 的 instance_series 随 category 变化）→ 不放入 `static_subs`

### Q: 定价模型不是 instances × hours 怎么办？

当前 `quantity_model` 字段已预留但尚未实现差异化逻辑。如果遇到按月计费（`1/Month`）或按量计费（`10K`）的产品，需要在 `pricing.js` 的 `calculateLocalPrice()` 中扩展计算逻辑。

---

## 实例：无子维度产品（Power BI Embedded）

某些产品结构极为简单：只有一个 productName，不需要子维度拆解。Power BI Embedded 就是典型案例：

| 特征 | 值 |
|------|-----|
| productName | 1 个：`Power BI Embedded` |
| skuName | 8 个：A1–A8 |
| type | 仅 Consumption |
| unitOfMeasure | `1 Hour` |
| tierMinimumUnits | 0.0（无阶梯） |
| Reservation / SavingsPlan | 无 |

### 接入步骤

这类产品只需 **配置**，无需编写解析器：

1. **产品目录** — `product_catalog.json` 中添加到对应 family
2. **服务配置** — 创建 `service_configs/power_bi_embedded.json`，不包含 `sub_dimensions`、`api_service_name`
3. **图标**（可选）— `estimate-card.js` 中添加 `SERVICE_ICONS` 条目

不需要：parser、`__init__.py` 注册、`explore.py` 改动、`pricing.js` 改动。

### 配置文件示例

```json
{
  "service_name": "Power BI Embedded",
  "quantity_label": "Nodes",
  "static_subs": [],
  "hidden_subs": [],
  "defaults": {
    "hours_per_month": 730,
    "selections": { "armRegionName": "eastus" }
  }
}
```

---

## 已知限制：多计量单位产品

某些产品（如 Event Grid）包含多个 meter，且各 meter 的 `unitOfMeasure` 不同：

| meter | unitOfMeasure |
|-------|---------------|
| Operations | `100K` |
| Advanced Filtering | `1M` |
| MQTT Messages | `1M` |
| Namespace | `1 Hour` |

当前前端的数量输入模型是「数量 × 小时」，假定所有 meter 共享同一个数量输入。对于多计量单位产品，用户需要为每个 meter 分别输入用量，这需要 UI 层面的扩展支持。此类产品暂时无法接入。
