# 利用 ACN Legacy Datamodel 提升项目体验

## Context

当前项目使用 Azure Global Retail Prices API 作为数据源，架构成熟（两阶段计算模型、级联筛选、本地定价引擎），但面向 azure.cn 中国市场时存在明显体验缺口：

- **28 个产品全部没有中文名**（`display_name_cn: null`）
- **部分产品描述是占位符**（如 "ftcsdgvyldsabfhugjnkml"）
- **无区域可用性约束**（`region_constraints: null`）
- **仅 9 个产品有 service_config**，其余无法提供预填默认值

而废弃的 ACN Calculator 的 `calculatordatamodel.js`（69K 行、260 个服务条目）包含完整的中文产品名、中文描述、区域限制、维度结构和 CNY 价格数据。

**目标**：通过提取和整合 legacy 数据，快速弥补以上缺口，使项目在产品发现、中文本地化、区域准确性方面对齐甚至超越 Global Calculator。

---

## 实现方案

### Step 1: JS → JSON 转换（基础，后续所有步骤依赖此输出）

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

### Step 2: Python 提取脚本（结构化提取有价值的元数据）

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

**输出 3**: `data/acn_price_validation.json` — 已知 CNY 价格（用于未来数据源切换时的验证）

### Step 3: 应用中文名和描述到 Product Catalog

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

### Step 4: 批量生成 Service Config 模板

**创建**: `scripts/generate_service_configs.py`

读取 `data/acn_dimension_templates/`，按映射规则自动生成 draft config：

| Legacy 结构 | 推导规则 |
|------------|---------|
| Types = Tier 名（基本/标准/高级）| `dimension_labels: {"skuName": "Tier"}` |
| 单一 productName | `hidden_dimensions: ["productName"]` |
| Features 全 "default" + Hourly | `quantity_model: "instances_x_hours"` |
| 多命名 Features 或 Monthly | `quantity_model: "per_meter"` |

**输出到** `data/generated_service_configs/`（非 `app/config/service_configs/`），需人工审核后采用。

审核流程：生成 → 人工调整 → 复制到 `app/config/service_configs/` → 通过 Explore API 验证 → Admin API publish。

优先级（对应 acn-datamodel-todo.md）：
- **Batch 1**（10 个简单产品）：redis-cache, database-migration, azure-ddos-*, managed-grafana, azure-fluid-relay, site-recovery, notification-hub, container-registry
- **Batch 2**（5 个 per_meter 细化）：traffic-manager, network-watcher, ip-address, application-gateway-v2, schedule
- **Batch 3**（需架构扩展）：azure-front-door, hdinsight, iot-hub+dps, active-directory-b2c

### Step 5: 价格验证框架（数据源切换时使用）✅ 已完成

**创建**: `scripts/price_drift_report.py`

---

## Step 6: 产品接入工作流（当前阶段）

Step 1-5 已完成提取和模板生成。接下来是逐个产品审核、修正、发布。

### 6.1 生成模板与生产 Config 的 GAP

生成的模板约 **40% 完成度**，需人工修正以下内容：

| 问题 | 说明 | 每产品耗时 |
|------|------|-----------|
| 移除 `_acn_*` 字段 | `_acn_slug`、`_acn_display_name` 是生成元数据 | 自动化 |
| 修正 `service_name` | 生成的部分使用中文名，需改为英文 catalog 名 | 自动化（映射表已有） |
| 确认 `api_service_name` | Azure API 的 serviceName 可能与 catalog 名不同 | 2 min（查 API） |
| 补充 `meter_labels` | per_meter 产品需要人工可读的 meter 显示名 | 5-10 min |
| 补充 `meter_order` | 生成的是中文 feature 名，需改为 API 中的英文 meter 名 | 5-10 min |
| 补充 `hidden_dimensions` | 单一 productName 的产品需隐藏 | 2 min |
| 完善 `defaults` | 添加默认 skuName/tier 选择 | 2 min |

### 6.2 Admin UI 产品接入工作流（核心新功能）

**目标**：在 Admin UI 中新增「产品上线」页面，PM/运营可以直接在 UI 中完成：导入模板 → 编辑清理 → API 预览 → 发布上线。

#### 后端新增

**新增端点** `app/api/admin.py`：

```
GET  /api/v1/admin/onboarding/templates     — 列出 data/generated_service_configs/ 中的可用模板
POST /api/v1/admin/onboarding/import/{slug}  — 导入模板：自动清理 _acn_* 字段 + 修正 service_name → 创建 draft config
```

导入时自动处理：
1. 读取 `data/generated_service_configs/{slug}.json`
2. 移除 `_acn_slug`、`_acn_display_name`
3. 从 `data/slug_to_service_name.json` 查找英文 `service_name`
4. 创建 draft config（调用已有 `config_repo.create_config`）
5. 如果产品不在 catalog 中，自动添加到对应 family（含 `display_name_cn`）

**复用已有端点**（无需修改）：
- `POST /explore/cascade` — 预览级联筛选
- `POST /explore/meters` — 预览 meter 数据
- `PUT /admin/configs/{name}` — 保存编辑
- `POST /admin/configs/{name}/validate` — 校验
- `POST /admin/configs/{name}/publish` — 发布

#### 前端新增

**新增路由** `#/onboarding`：

**新增组件** `admin/js/components/onboarding.js`：

页面分两个区域：

**左侧：模板列表**
- 显示所有可用模板（从 `/admin/onboarding/templates` 获取）
- 每个模板显示：slug、中文名、quantity_model、状态（可导入 / 已导入为 draft / 已发布）
- 「导入」按钮 → 调用 `/admin/onboarding/import/{slug}` → 自动创建 draft

**右侧：接入工作台**（选中一个已导入的 draft 后显示）

分 3 个 Tab：

**Tab 1: 配置编辑**
- 复用现有 config-editor 的 form+JSON 双面板
- 顶部高亮提示需要人工确认的字段（meter_labels、meter_order、defaults）

**Tab 2: API 预览**
- 「测试 Cascade」按钮 → 调用 `POST /explore/cascade`（空 selections）→ 展示可用维度和选项
- 「测试 Meters」按钮 → 选定 region/product/sku 后调用 `POST /explore/meters` → 展示 meter 列表
- 展示结果辅助 PM 填写 meter_labels、meter_order、hidden_meters

**Tab 3: 发布检查**
- 自动校验（调用 validate endpoint）
- Catalog 状态检查（是否已在产品目录中）
- 「发布」按钮

#### 工作流程

```
PM 打开 Admin UI → #/onboarding
  │
  ├── 1. 查看模板列表 → 点击「导入」
  │     └─ 后端自动清理 + 创建 draft + 添加到 catalog
  │
  ├── 2. 编辑配置（Tab 1）
  │     └─ 调整 meter_labels、defaults 等
  │
  ├── 3. API 预览（Tab 2）
  │     └─ 测试 cascade/meters → 确认数据正确
  │     └─ 根据 meter 列表完善配置
  │
  └── 4. 发布（Tab 3）
        └─ 校验通过 → 发布 → 自动导出 JSON + 更新缓存
```

### 6.4 产品接入优先级

**Batch 1 — 简单产品（预计每个 15-30 min）**

| slug | service_name | quantity_model | 备注 |
|------|-------------|---------------|------|
| redis-cache | Azure Cache for Redis | instances_x_hours | Tier 选择，已在 catalog |
| container-registry | Container Registry | per_meter | Tier + 月费 |
| managed-grafana | Managed Grafana | per_meter | 3 个 meter，已在 catalog |
| site-recovery | Site Recovery | per_meter | 2 个 meter |
| azure-ddos-protection | Azure DDoS Protection | per_meter | 月费 + 超额 |
| azure-ddos-ipprotection | Azure DDoS IP Protection | per_meter | 每 IP 月费 |
| azure-fluid-relay | Azure Fluid Relay | per_meter | 4 个 meter |
| notification-hub | Notification Hubs | per_meter | Tier + 阶梯 |
| database-migration | Database Migration Service | instances_x_hours | 简单实例选择 |

**Batch 2 — per_meter 细化（预计每个 30-60 min）**

| slug | service_name | 备注 |
|------|-------------|------|
| traffic-manager | Traffic Manager | 5 meter，DNS 有阶梯 |
| network-watcher | Network Watcher | 4 meter，各有不同阶梯 |
| ip-address | Public IP Addresses | 3 种部署模型 |
| application-gateway-standard-v2 | Application Gateway | 2 个费用组件 |
| schedule | Scheduler | Tier + 用量阶梯 |

**Batch 3 — 需架构扩展（暂缓）**
- azure-front-door, hdinsight, iot-hub+dps, active-directory-b2c

### 6.5 Catalog 中尚需添加的产品

当前 catalog 有 28 个产品。Batch 1-2 中部分产品不在 catalog 中，需要通过 Admin API 添加：

需要添加到 catalog 的（通过 `POST /admin/catalog/services`）：
- Container Registry → databases family
- Site Recovery → management family（需新建 family）
- Azure DDoS Protection → networking family
- Azure Fluid Relay → web family
- Notification Hubs → integration family
- Database Migration Service → databases family
- Traffic Manager → networking family
- Network Watcher → networking family
- Public IP Addresses → networking family
- Scheduler → integration family

---

## 依赖关系

```
Step 1-5 (已完成) ──→ Step 6.2 (clean 脚本)
                  ──→ Step 6.3 (逐产品接入，按 Batch 1 → 2 → 3 顺序)
```

---

## 涉及的关键文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/convert_acn_datamodel.js` | ✅ 已完成 | Node.js JS→JSON 转换器 |
| `scripts/extract_acn_metadata.py` | ✅ 已完成 | Python 元数据提取 |
| `scripts/apply_cn_names.py` | ✅ 已完成 | 应用中文名到 catalog |
| `scripts/generate_service_configs.py` | ✅ 已完成 | 批量生成 config 模板 |
| `scripts/price_drift_report.py` | ✅ 已完成 | 价格对比报告 |
| `app/api/admin.py` | **修改** | 新增 2 个 onboarding 端点（list templates, import） |
| `admin/js/app.js` | **修改** | 新增 `#/onboarding` 路由 |
| `admin/js/api.js` | **修改** | 新增 onboarding API 函数 |
| `admin/js/components/onboarding.js` | **新建** | 产品上线工作台组件 |
| `admin/index.html` | **修改** | 新增 onboarding 页面模板 + 导航链接 |

---

## 验证方式

1. **Step 1-3**: ✅ 已验证（257 条目提取，28 产品中文名已填充，306 测试通过）
2. **Step 6.2 后端**:
   - `GET /admin/onboarding/templates` 返回 14 个模板列表
   - `POST /admin/onboarding/import/redis-cache` → 成功创建 draft config + catalog entry
3. **Step 6.2 前端**:
   - 打开 `#/onboarding` → 看到模板列表
   - 点击「导入」→ config 创建为 draft
   - Tab 1 编辑 → Tab 2 预览 cascade/meters → Tab 3 发布
   - 前端 Add to estimate → 新产品卡片正常渲染
4. **回归测试**: `uv run pytest` 确保后端测试仍全部通过

---

## 讨论问题（QA）

### Q1: 生成的模板和 Azure Global API 数据不匹配怎么办？
Legacy datamodel 中的产品结构（Types/Features/Sizes）是 ACN 特有的硬编码数据，和 Azure Global Retail Prices API 的维度结构可能不同。例如：
- Legacy 中 Redis Cache 有 3 个 Tier（基本/标准/高级），Global API 可能有 5 个（含 Enterprise/Enterprise Flash）
- Legacy 中的 meter 名称是中文，Global API 返回英文

**建议方案**：生成的模板只作为**起点参考**（quantity_model、dimension_labels 等结构性建议），具体的 meter_labels、meter_order、sku_groups 等值需要在 Admin UI 的 API 预览 Tab 中查看实际 API 返回后再填写。

### Q2: 产品不在 Global API 中有数据怎么办？
某些 ACN 特有产品可能在 Global Retail Prices API 中没有对应数据（例如中国特有的区域性产品）。这些产品在 MVP 阶段无法通过 Explore API 获取定价数据。

**建议方案**：
- 模板列表中显示「API 无数据」标记（在 templates endpoint 中可以异步探测）
- 这些产品暂不接入，等 Phase 4 数据源切换到 CN CSV + PostgreSQL 后再处理

### Q3: 是否需要审核/审批流程？
当前 Admin 的 draft → publish 是单人操作。是否需要多角色审批（如 PM 提交 → Dev 审核 → 发布）？

**当前建议**：MVP 阶段保持单人操作（draft → publish），未来可扩展：
- 增加 `status: "pending_review"` 状态
- 发布前需要另一人确认
- 与企业 SSO/RBAC 集成

### Q4: Onboarding 页面和现有 Config 编辑器的关系？
两者是否会功能重叠？已通过 onboarding 导入的 config 是否还能在原来的 `#/configs` 页面编辑？

**建议方案**：
- Onboarding 页面专注于**首次接入**流程（模板选择 → 清理 → 预览 → 发布）
- 发布后的 config 在 `#/configs` 页面管理（后续编辑、版本回退等）
- 两者共享同一套 DB 数据，onboarding 只是在 config-editor 基础上增加了模板导入和 API 预览能力

### Q5: slug_to_service_name.json 映射表如何维护？
当前映射表只覆盖了 28 个已有 catalog 产品。新接入的产品需要手工添加映射。

**建议方案**：
- Onboarding 导入时，如果映射表中没有该 slug，允许用户在 UI 中手动输入 `service_name` 和 `display_name_cn`
- 导入成功后自动回写到映射表（或直接存 DB）

### Q6: 区域约束（region_constraints）目前只是标记，前端/后端有没有实际使用？
目前 `region_constraints` 已经写入了 `product_catalog.json`，但前端筛选和后端 cascade 并未使用这个字段。

**建议方案**：
- 本轮先完成数据标记（已做）
- 后续迭代中：
  - 前端在 service-picker 中显示区域标签（"仅限中国东部2"）
  - 后端 cascade 根据选定 region 过滤不可用的产品/SKU
  - 需要确认区域约束的粒度：是 service 级别还是 meter/SKU 级别

### Q7: data/generated_service_configs/ 这些文件是否需要版本控制？
这些是脚本生成的中间产物，不是生产代码。

**建议方案**：
- `data/` 目录加入 `.gitignore`（中间产物不入库）
- 或者保留在 git 中作为参考，但标注为 generated
- 最终生产 config 在 `app/config/service_configs/` 中（已在 git 中）
