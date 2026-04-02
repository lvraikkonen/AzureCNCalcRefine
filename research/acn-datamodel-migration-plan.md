# ACN calculatordatamodel.js 迁移方案

**撰写日期：** 2026-03-22
**更新日期：** 2026-03-26（Step 1-5 已完成，分类器升级为 6 模式）
**状态：** 提取阶段全部完成，进入产品接入阶段

---

## 一、数据模型全量统计

| 指标 | 数值 |
|------|------|
| 文件总行数 | 68,936 |
| 服务条目总数 | 260 |
| 去重后唯一 slug | 257 |
| 重复 slug | 3 (`app-service`, `api-management`, `storage-queues-gpv2-east3`) |
| 违反命名规范的 slug | 2 (`Azure-Virtual-Desktop`, `Azure Spring Cloud`) |
| 含区域限制注解的条目 | 79 (30%) |
| CalculatorConst 引用总次数 | 2,250 |
| CalculatorConst 唯一标识符 | 380 |

### 1.1 重复 slug 详情

| slug | 出现行 | Name | 原因 |
|------|--------|------|------|
| `app-service` | 6 | 应用服务 - Windows | 正常 |
| `app-service` | 154 | 应用程序配置 - 中国东部2 | **数据错误** — 应为 `app-configuration` |
| `api-management` | 58544 | API 管理 (月定价) | 同产品拆分为两种计费周期 |
| `api-management` | 58744 | API 管理 (时定价) | 同上 |
| `storage-queues-gpv2-east3` | 40027/40421 | 存储 - 队列 | 完全重复 |

---

## 二、定价模式分类（6 种 Pattern）

> 完整的 Global API 定价模式分析见 `research/product-pricing-patterns.md`

### 2.1 分类器逻辑 (`extract_acn_metadata.py`)

从 legacy Types/Features/Sizes 结构推导 6 种 Global API 定价模式：

```python
classify_pricing_pattern(types) → "A" | "B" | "C" | "D" | "E" | "F"

if Features 全 "default" + 全 Hourly           → A (instances_x_hours)
if 同 Type 有多 Size Hourly + Monthly Feature  → C (compute_plus_storage)
if ≥2 Feature 含 vCPU/GiB 资源维度单位         → D (resource_dimensions)
if Features 有 "default" + 命名混合             → E (sku_base_plus_meter)
else                                            → B (per_meter)
# F 无法从单 slug 检测 → 需外部标注
```

### 2.2 全量分布

| Pattern | 名称 | 数量 | 占比 |
|---------|------|------|------|
| A | instances_x_hours | 36 | 14% |
| B | per_meter | 193 | 75% |
| C | compute_plus_storage | 13 | 5% |
| D | resource_dimensions | 6 | 2% |
| E | sku_base_plus_meter | 9 | 4% |

---

## 三、可提取数据及格式

### 3.1 slug → 中文名 + 区域约束 ✅ 已完成

**输出**: `data/acn_product_names.json`

清洗规则：从 Name 中正则提取 "仅适用于/仅支持" + 区域名

```json
{
  "azure-fluid-relay": {
    "display_name_raw": "Azure Fluid Relay - 仅适用于中国北部3",
    "display_name_clean": "Azure Fluid Relay",
    "region_constraints": ["chinanorth3"]
  }
}
```

区域映射：中国东部→chinaeast, 中国东部2→chinaeast2, 中国东部3→chinaeast3, 中国北部→chinanorth, 中国北部2→chinanorth2, 中国北部3→chinanorth3

区域标注出现在 3 层：Service Name (79 条目) → Feature Name (VM/HDInsight) → Size Description

### 3.2 维度模板 ✅ 已完成

**输出**: `data/acn_dimension_templates/{slug}.json`

每产品一个 JSON，包含：
- `types_semantic`: single / tier / category / default / service
- `pricing_pattern`: A-F
- `suggested_config`: quantity_model, dimension_labels, hidden_dimensions
- Types/Features/Sizes 结构摘要

### 3.3 Service Config 模板 ✅ 已完成

**输出**: `data/generated_service_configs/{slug}.json`

生产格式的 config 模板，包含：
- 英文 `service_name`（从 `slug_to_service_name.json` 映射）
- 正确的 `quantity_model`（基于 6 模式分类）
- `sku_groups`（英文 Tier 名）、`dimension_labels`、`hidden_dimensions`
- `meter_order`（中文名，需手动替换为 API 英文 meter 名）
- `defaults`（默认 region = chinaeast2）
- `_legacy_reference` 段（legacy 结构摘要 + CNY 参考价格，发布前删除）

### 3.4 CNY 价格 ✅ 已完成

**输出**: `data/acn_price_validation.json`

用于 Phase 4 数据源切换时的 sanity check。MVP 阶段不使用。

---

## 四、Types/Features/Sizes → service_config 映射规则

### 4.1 映射对照表

| datamodel 层级 | 语义类型 | 本项目对应 |
|---------------|---------|-----------|
| Types.Name = Tier 名 | 产品层级 | `sku_groups` |
| Types.Name = "default" | 无分层 | 无额外维度 |
| Types.Name = 功能类别 | 多独立计费项 | `per_meter` 的 Type 分组 |
| Types.Name = SKU 规格 | 网关/SKU 选择 | cascade `skuName` |
| Features.Name = "default" | 单 meter | 标准 cascade |
| Features.Name = 命名 meter | 多 meter | `per_meter`，每 Feature → meter 输入 |
| Features.Name = VM 系列 | VM 规格组 | `productName` 子维度 |
| Sizes[] 多规格 | 实例选择 | cascade `skuName` |
| Sizes[] 单 "default" | 无规格选择 | 无额外维度 |
| PricePeriod = Hourly | 按小时 | `instances_x_hours` 或 hourly meter |
| PricePeriod = Monthly | 按月 | `per_meter` volume |
| PriceTier = Fixed/Linear | 固定/线性 | 单行定价 |
| PriceTier = 阶梯字符串 | 阶梯 | 多行 `tierMinimumUnits` |

### 4.2 quantity_model 推导规则（升级版，6 模式）

```
IF Features 全 "default" AND PricePeriod 全 Hourly:
    → Pattern A: instances_x_hours

IF 同 Type 下有多 Size 的 Hourly Feature + Monthly Feature:
    → Pattern C: compute_plus_storage (per_meter 近似)

IF ≥2 Feature 的 PriceUnit 含 vCPU/GiB:
    → Pattern D: resource_dimensions (per_meter 近似)

IF Features 有 "default"(基础费) + 命名(附加费):
    → Pattern E: sku_base_plus_meter (per_meter 近似)

ELSE:
    → Pattern B: per_meter
```

### 4.3 slug → service_name 映射

**文件**: `data/slug_to_service_name.json`

由于 legacy slug 和项目 service_name 不一致（且存在多对一关系），需要手工维护映射表。当前覆盖 Batch 1 全部 + 已有 catalog 产品共 35 个映射。

多对一关系示例：
- `virtual-machines-linux` + `virtual-machines-windows` → Virtual Machines
- `storage-*` (54 slugs) → Storage Accounts / Managed Disks

---

## 五、执行状态

| Phase | 状态 | 说明 |
|-------|------|------|
| **Phase 0: 提取工具** | ✅ 完成 | Step 1-5 全部完成，分类器已升级为 6 模式 |
| **Phase 1: Batch 1** | 🟡 模板已生成 | 9 个模板在 `data/generated_service_configs/`，待 Admin 工作流导入 |
| **Phase 2: Batch 2** | ⬜ 未开始 | 5 个 per_meter 产品，依赖 Batch 1 工作流验证 |
| **Phase 3: 架构扩展** | ⬜ 未开始 | Pattern C/F 产品需新 quantity_model |
| **Phase 4: 数据源切换** | ⬜ 未开始 | CN CSV → ETL → PostgreSQL |

---

## 六、CalculatorConst 常量

### 6.1 常量分类

| 类别 | 数量(约) | 示例 |
|------|---------|------|
| VM Size 名称 | ~150 | `D2v3Size`→"D2 v3" |
| VM Size 描述 | ~150 | `A0SizeDesc`→"1个(共用)内核,0.75 GiB RAM" |
| App Service 名称/描述 | ~50 | `appservice_Basic_B1`→"B1" |
| Redis Cache Size | 14 | `C0Size`→"C0" |
| 其他 | ~30 | `HoursOneMonth`→744 |

**已通过 Step 1 (Node.js `eval()`) 全部解析并内联到 `calculatordatamodel.json`。**

---

## 七、关联文档

- `research/acn-datamodel-analysis.md` — Legacy 结构深度分析 + 6 模式映射
- `research/acn-datamodel-todo.md` — 产品接入进度追踪
- `research/product-pricing-patterns.md` — Global API 定价模式分类（6 种，20+ 产品调研）
- `plan/MVP-plan.md` — MVP 范围、Admin 工作流、实现计划
