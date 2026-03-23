# 产品配置操作指南

> 本指南面向 Azure.cn 定价计算器的管理人员，介绍如何通过 Admin 后台为新产品添加计算器配置，并使其在前端计算器中生效。
>
> **前置条件**：服务已启动（`DATABASE_URL` 已设置，`uv run uvicorn app.main:app --reload`），可访问 `http://localhost:8000/admin/`。

---

## 第一部分：核心概念

### 1.1 两种定价模型

每个产品配置必须选择一种 `quantity_model`，它决定了前端 UI 的整体渲染方式：

| 模型 | 适用场景 | 前端 UI 表现 |
|------|---------|------------|
| `instances_x_hours` | 按实例数 × 时间计费（虚拟机、缓存、PaaS 实例） | 显示"实例数量"输入框 + 时长选择；价格 = 单价 × 实例数 × 小时数 |
| `per_meter` | 按用量计费，或多个独立计量项（网络、存储、SaaS 按功能收费） | 为每个 meter 显示独立的用量输入行；价格 = Σ(各 meter 单价 × 用量) |

> **判断方法**：如果产品的核心收费逻辑是"开几台机器跑多少小时"，选 `instances_x_hours`；如果核心逻辑是"用了多少单位的某项功能"，选 `per_meter`。

### 1.2 配置字段速查表

| 字段 | 类型 | 前端效果 | 示例 |
|------|------|---------|------|
| `service_name` | string | 必填，与产品目录中的服务名精确匹配 | `"Azure Cache for Redis"` |
| `quantity_model` | string | 决定 UI 布局（见上表） | `"instances_x_hours"` |
| `quantity_label` | string | 实例数量输入框的标签文字 | `"Nodes"`, `"VMs"`, `"Usage"` |
| `dimension_labels` | object | 覆盖 cascade 下拉框的默认标签名 | `{"skuName": "Tier"}` → SKU 下拉改显示 "Tier" |
| `hidden_dimensions` | array | 完全隐藏某些 cascade 下拉框 | `["productName"]` → 隐藏 Product 下拉（当产品只有一个时） |
| `defaults.selections` | object | 页面初始化时的预选值 | `{"armRegionName": "chinanorth3"}` |
| `defaults.hours_per_month` | number | `instances_x_hours` 模式下默认时长（小时） | `730`（约等于每月平均小时数） |
| `sku_groups` | object | 将多个真实 SKU 名称合并为一个虚拟 Tier 名（用于 Tier 下拉包含多产品时） | `{"Standard": ["Standard", "Hybrid Connections"]}` |
| `api_service_name` | string | 当目录名与 Azure Retail Prices API 的 serviceName 不同时使用 | `"Azure App Service"`（目录名是 "App Service"） |
| `excluded_products` | array | 从结果中排除不应显示的 productName 值 | `["Virtual Machines RI"]` |

### 1.3 Cascade 维度说明

前端的级联下拉框按固定顺序排列：**Region → Product → SKU → Pricing Type → Term**。

- 选中某一维度后，其他维度的可选项会自动更新（联动）。
- `hidden_dimensions` 可以隐藏其中任意维度。
- `dimension_labels` 可以改变下拉框的显示标题。

---

## 第二部分：操作流程总览

```
1. 确定产品定价结构
       ↓
2. 选择配置模式并起草 JSON
       ↓
3. 通过 Admin UI / API 新建配置（状态: 草稿）
       ↓
4. 校验配置（无错误）
       ↓
5. 保存草稿
       ↓
6. 发布（状态: 已发布）
       ↓
7. 前端计算器验证
```

操作方式有两种，效果相同：

| 方式 | 适用人群 | 入口 |
|------|---------|------|
| **Admin UI** | 产品经理、运营人员 | `http://localhost:8000/admin/` |
| **Admin API (curl)** | 开发人员、CI/CD | `POST /api/v1/admin/configs` |

---

## 第三部分：实例 1 — Redis Cache（`instances_x_hours`）

### 3.1 产品定价结构分析

Redis Cache 按**实例规格 × 运行小时数**计费。

- **Tier**（层级）：基本 / 标准 / 高级
- **Size**（缓存大小）：基本/标准层 C0–C6，高级层 P1–P5
- **定价单位**：CNY/小时/实例

在 Azure Retail Prices API 中，Tier 和 Size 都体现在 `skuName` 字段，`productName` 只有一个唯一值，可以隐藏。

### 3.2 配置 JSON

```json
{
  "service_name": "Azure Cache for Redis",
  "quantity_model": "instances_x_hours",
  "quantity_label": "实例",
  "dimension_labels": {
    "skuName": "层级 / 规格"
  },
  "hidden_dimensions": ["productName"],
  "defaults": {
    "hours_per_month": 730,
    "selections": {
      "armRegionName": "chinanorth3"
    }
  }
}
```

**字段说明**：
- `dimension_labels.skuName = "层级 / 规格"` — 将默认的 "SKU" 标签改为更直观的 "层级 / 规格"
- `hidden_dimensions: ["productName"]` — 隐藏 Product 下拉（Redis Cache 只有一个 productName，不需要用户选择）
- `defaults.selections.armRegionName` — 页面打开时默认选择的区域

### 3.3 Admin UI 操作步骤

**Step 1：打开配置列表**

访问 `http://localhost:8000/admin/`，在左侧导航栏点击 **"⚙️ 服务配置"** → 点击右上角 **"+ 新建配置"**。

**Step 2：表单模式填写基础字段**

| 字段 | 填写值 |
|------|--------|
| 服务名 (service_name) | `Azure Cache for Redis` |
| 定价模型 (quantity_model) | `instances_x_hours` |
| 数量标签 (quantity_label) | `实例` |
| 默认每月小时数 | `730` |
| 维度标签 (dimension_labels) | `{"skuName": "层级 / 规格"}` |
| 隐藏维度 (hidden_dimensions) | `productName` |

**Step 3：切换到 JSON 模式确认完整配置**

点击 **"JSON 模式"** 按钮，确认编辑框内的 JSON 与上方 [3.2 配置 JSON](#32-配置-json) 一致。可在此直接添加 `defaults.selections`：

```json
"defaults": {
  "hours_per_month": 730,
  "selections": {
    "armRegionName": "chinanorth3"
  }
}
```

**Step 4：校验配置**

点击 **"校验配置"** 按钮。

- ✓ 出现 **"校验通过"** 绿色提示 → 继续下一步
- ✗ 出现错误列表 → 根据提示修正 JSON 后重新校验

**Step 5：保存草稿**

点击 **"保存草稿"** 按钮。状态变为 `draft`，此时配置**尚未对外生效**。

**Step 6：发布**

确认配置无误后，点击 **"发布"** 按钮 → 弹窗确认 → 状态变为 `published`。

> **发布后立即生效**：Admin 系统会更新内存缓存，Explore API 下一次请求即使用新配置，无需重启服务。

### 3.4 Admin API 操作步骤（curl）

```bash
# 1. 创建配置（草稿）
curl -X POST http://localhost:8000/api/v1/admin/configs \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "Azure Cache for Redis",
    "config": {
      "service_name": "Azure Cache for Redis",
      "quantity_model": "instances_x_hours",
      "quantity_label": "实例",
      "dimension_labels": {"skuName": "层级 / 规格"},
      "hidden_dimensions": ["productName"],
      "defaults": {
        "hours_per_month": 730,
        "selections": {"armRegionName": "chinanorth3"}
      }
    },
    "changed_by": "your-name"
  }'

# 2. 校验配置（不保存，可在创建前调用）
curl -X POST "http://localhost:8000/api/v1/admin/configs/Azure%20Cache%20for%20Redis/validate" \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "quantity_model": "instances_x_hours",
      "dimension_labels": {"skuName": "层级 / 规格"},
      "hidden_dimensions": ["productName"],
      "defaults": {"hours_per_month": 730}
    }
  }'
# 期望响应: {"valid": true, "errors": [], "warnings": [...]}

# 3. 发布
curl -X POST "http://localhost:8000/api/v1/admin/configs/Azure%20Cache%20for%20Redis/publish" \
  -H "Content-Type: application/json" \
  -d '{"changed_by": "your-name"}'
# 期望响应: {"status": "published", ...}
```

### 3.5 前端验证

1. 打开 `http://localhost:8000/`
2. 在左侧产品目录找到 **"Azure Cache for Redis"**（如不在目录中，需先通过 Admin → 产品目录 添加）
3. 点击 **"添加到估算"**
4. 确认以下行为：
   - Region 下拉正常显示（不应有 Product 下拉）
   - SKU 下拉标签显示 **"层级 / 规格"**，可选项包含 `C0 Basic`、`C0 Standard` 等
   - 显示 **实例数量** 输入框和 **时长** 选择器
   - 更改规格后价格正确刷新

---

## 第四部分：实例 2 — Managed Grafana（`per_meter` 多 meter）

### 4.1 产品定价结构分析

Managed Grafana 有 **3 个独立计费项**，每项都需要用户填写用量：

| 计费项（meter）| 单位 | 计费方式 |
|--------------|------|---------|
| 实例（Instance）| 个/月 | 月固定费 |
| 活跃用户（Active Users）| 人/月 | 月固定费 |
| 区域冗余（Zone Redundancy）| 个/月 | 月固定费 |

**区域限制**：仅在 `chinanorth3`（中国北部3）可用。

在 Azure Retail Prices API 中，`productName` 只有一个唯一值，可以隐藏。

### 4.2 配置 JSON

```json
{
  "service_name": "Azure Managed Grafana",
  "quantity_model": "per_meter",
  "quantity_label": "用量",
  "dimension_labels": {
    "skuName": "计划"
  },
  "hidden_dimensions": ["productName"],
  "defaults": {
    "selections": {
      "armRegionName": "chinanorth3"
    }
  }
}
```

**字段说明**：
- `quantity_model: "per_meter"` — 前端将为每个 meter（实例、活跃用户、区域冗余）分别显示一行用量输入
- `hidden_dimensions: ["productName"]` — 隐藏 Product 下拉
- `defaults.selections.armRegionName: "chinanorth3"` — 强制默认选中唯一可用区域

> **注意**：`per_meter` 模式下不使用 `hours_per_month`，因为每个 meter 的时间单位由 API 返回数据决定（月费 meter 自动按月计，小时费 meter 自动显示小时输入）。

### 4.3 Admin UI 操作步骤

**Step 1**：导航至 **"⚙️ 服务配置"** → **"+ 新建配置"**

**Step 2**：表单模式填写

| 字段 | 填写值 |
|------|--------|
| 服务名 | `Azure Managed Grafana` |
| 定价模型 | `per_meter` |
| 数量标签 | `用量` |
| 维度标签 | `{"skuName": "计划"}` |
| 隐藏维度 | `productName` |

**Step 3**：切换 JSON 模式，补充 `defaults` 中的区域默认值：

```json
"defaults": {
  "selections": {
    "armRegionName": "chinanorth3"
  }
}
```

**Step 4**：校验 → 保存草稿 → 发布（步骤与实例 1 相同）

### 4.4 Admin API 操作步骤（curl）

```bash
# 1. 创建配置
curl -X POST http://localhost:8000/api/v1/admin/configs \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "Azure Managed Grafana",
    "config": {
      "service_name": "Azure Managed Grafana",
      "quantity_model": "per_meter",
      "quantity_label": "用量",
      "dimension_labels": {"skuName": "计划"},
      "hidden_dimensions": ["productName"],
      "defaults": {
        "selections": {"armRegionName": "chinanorth3"}
      }
    },
    "changed_by": "your-name"
  }'

# 2. 发布
curl -X POST "http://localhost:8000/api/v1/admin/configs/Azure%20Managed%20Grafana/publish" \
  -H "Content-Type: application/json" \
  -d '{"changed_by": "your-name"}'
```

### 4.5 前端验证

1. 打开计算器，添加 **"Azure Managed Grafana"**
2. 确认以下行为：
   - Region 下拉默认选中 "China North 3"，且无 Product 下拉
   - 价格区域显示 **3 行独立用量输入**，对应实例、活跃用户、区域冗余
   - 更改用量后各项价格独立计算并加总

---

## 第五部分：实例 3 — SignalR Service（`per_meter` 极简）

### 5.1 产品定价结构分析

Azure SignalR Service 是**最简单的配置场景**：

- 单一 Tier（标准层）
- 月固定费（按连接数或消息数）
- 无复杂维度选择

在 API 数据中，`productName` 只有一个值，`skuName` 也基本是单一选项，因此可以最大程度隐藏不必要的 UI 元素。

### 5.2 配置 JSON

```json
{
  "service_name": "Azure SignalR Service",
  "quantity_model": "per_meter",
  "quantity_label": "用量",
  "hidden_dimensions": ["productName"],
  "defaults": {
    "selections": {
      "armRegionName": "chinanorth3"
    }
  }
}
```

这是一份**最小化配置**，只声明必要字段，其余使用系统默认值。

### 5.3 Admin UI 操作步骤

**Step 1**：导航至 **"⚙️ 服务配置"** → **"+ 新建配置"**

**Step 2**：表单模式填写

| 字段 | 填写值 |
|------|--------|
| 服务名 | `Azure SignalR Service` |
| 定价模型 | `per_meter` |
| 数量标签 | `用量` |
| 隐藏维度 | `productName` |

**Step 3**：JSON 模式确认，无需添加额外字段

**Step 4**：校验 → 保存草稿 → 发布

### 5.4 Admin API 操作步骤（curl）

```bash
# 创建并发布（两步）
curl -X POST http://localhost:8000/api/v1/admin/configs \
  -H "Content-Type: application/json" \
  -d '{
    "service_name": "Azure SignalR Service",
    "config": {
      "service_name": "Azure SignalR Service",
      "quantity_model": "per_meter",
      "quantity_label": "用量",
      "hidden_dimensions": ["productName"],
      "defaults": {
        "selections": {"armRegionName": "chinanorth3"}
      }
    },
    "changed_by": "your-name"
  }'

curl -X POST "http://localhost:8000/api/v1/admin/configs/Azure%20SignalR%20Service/publish" \
  -H "Content-Type: application/json" \
  -d '{"changed_by": "your-name"}'
```

### 5.5 前端验证

1. 添加 **"Azure SignalR Service"** 到估算
2. 确认只显示 Region 和 SKU 两个下拉，无 Product 下拉
3. per_meter 用量行正确显示，价格计算正常

---

## 第六部分：进阶配置参考

### 6.1 `sku_groups`：虚拟 Tier 合并（Service Bus 示例）

**适用场景**：当一个产品的 Tier 选择实际对应 API 中多个不同的 `skuName` 时。

例如 Service Bus 标准层包含 3 种 meter（Standard 消息、Hybrid Connections、WCF Relay），但用户应该看到的是统一的 "Standard" Tier 入口：

```json
{
  "service_name": "Service Bus",
  "quantity_model": "per_meter",
  "quantity_label": "用量",
  "dimension_labels": {"skuName": "Tier"},
  "hidden_dimensions": ["productName"],
  "sku_groups": {
    "Basic": ["Basic"],
    "Standard": ["Standard", "Hybrid Connections", "WCF Relay"],
    "Premium": ["Premium"]
  },
  "defaults": {
    "selections": {
      "armRegionName": "chinanorth3",
      "skuName": "Standard"
    }
  }
}
```

用户在 Tier 下拉选择 "Standard" 后，系统自动查询 `Standard`、`Hybrid Connections`、`WCF Relay` 三种 skuName 的所有 meter，并合并显示。

### 6.2 `sub_dimensions`：产品名解析（Virtual Machines 示例）

**适用场景**：当 API 的 `productName` 字段包含多个维度的信息（如 "Windows Server Virtual Machines Burstable Tier"），需要拆分成 OS、Tier、Category 等独立下拉框。

```json
{
  "service_name": "Virtual Machines",
  "quantity_model": "instances_x_hours",
  "quantity_label": "VMs",
  "sub_dimensions": {
    "target_field": "product_name",
    "parser": "vm_product_parser",
    "dimensions": [
      {"field": "os", "label": "Operating System", "order": 0, "default": null},
      {"field": "deployment", "label": "Deployment", "order": 1, "default": "Virtual Machines"},
      {"field": "tier", "label": "Tier", "order": 2, "default": "Standard"},
      {"field": "category", "label": "Category", "order": 3, "default": null},
      {"field": "instance_series", "label": "Instance Series", "order": 4, "default": null}
    ]
  },
  "static_subs": ["os", "tier", "category"],
  "hidden_subs": ["deployment"]
}
```

> **注意**：`parser` 字段的值必须是代码中已注册的解析器名称（`vm_product_parser` 或 `appservice_product_parser`）。新产品如需此功能，需要开发人员先注册对应 parser。

### 6.3 `api_service_name`：服务名映射（App Service 示例）

**适用场景**：产品目录中的服务名与 Azure Retail Prices API 中的 `serviceName` 字段不一致。

```json
{
  "service_name": "App Service",
  "api_service_name": "Azure App Service",
  "quantity_model": "instances_x_hours"
}
```

`service_name` 是面向用户的显示名（必须与 `product_catalog.json` 中的名称匹配），`api_service_name` 是 API 查询时的实际过滤值。

如不填写 `api_service_name`，系统默认使用 `service_name` 作为 API 查询值。

### 6.4 `excluded_products`：排除特定产品

**适用场景**：API 返回的 `productName` 包含不应在计算器中显示的内容（如 RI 保留实例、已废弃的产品变体）。

```json
{
  "excluded_products": [
    "Virtual Machines RI",
    "Dedicated Host Reservation"
  ]
}
```

### 6.5 修改已有配置

1. 在配置列表找到目标服务，点击 **"编辑"**
2. 修改 JSON 内容
3. 填写**修改人**和**变更说明**（便于审计）
4. 保存草稿 → 重新发布

**注意**：每次保存都会自动创建版本快照。如需回退，在 **"历史记录"** 页面找到目标版本，点击 **"回退到此版本"**（创建新草稿，需重新发布）。

### 6.6 常见问题排查

| 现象 | 排查方向 |
|------|---------|
| 发布后前端仍显示旧配置 | 检查 `DATABASE_URL` 是否已设置；配置状态是否已变为 `published`；刷新浏览器（非缓存刷新） |
| 下拉框显示 "No options" | 检查 `defaults.selections.armRegionName` 是否填写了该产品实际有数据的区域；检查 `api_service_name` 是否与 API 的 serviceName 匹配 |
| 校验报错 "parser not registered" | `sub_dimensions.parser` 字段的值不在已注册列表中，需要开发人员添加 parser |
| `sku_groups` 中的 SKU 名拼写报警 | 校验器警告 SKU 名未在 retail_prices 中找到（当数据库已接入时），检查大小写和空格是否与 API 返回值完全一致 |
| 配置创建时报 409 冲突 | 该 `service_name` 的配置已存在，在配置列表找到后直接编辑，或先归档旧配置再新建 |

---

## 附录：配置模式速查

| 产品类型 | 推荐模式 | 关键字段 | 参考实例 |
|---------|---------|---------|---------|
| 虚拟机类（按小时付费） | `instances_x_hours` | `sub_dimensions`, `excluded_products` | Virtual Machines |
| PaaS 实例（Redis, Service Plan） | `instances_x_hours` | `dimension_labels`, `hidden_dimensions` | Redis Cache |
| 简单按月付费 | `per_meter` | `hidden_dimensions` | SignalR Service |
| 多计量项产品 | `per_meter` | `hidden_dimensions`, `dimension_labels` | Managed Grafana, Event Grid |
| 多 Tier 含多 SKU | `per_meter` + `sku_groups` | `sku_groups`, `dimension_labels` | Service Bus |
