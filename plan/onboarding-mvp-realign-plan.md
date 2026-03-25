# 产品接入工作流 + Admin Preview + 数据源对齐（重新对齐 MVP）

## Context

### 项目定位（重新对齐）
本项目是对废弃的 ACN Calculator 的**全面重做**：
- 旧 ACN Calculator：手工维护 `calculatordatamodel.js`，数据无法持续更新，UX 极差
- 新项目：以 Azure Global Retail Prices API 为数据源，配置驱动，支持长期运营维护
- `calculatordatamodel.js` 是**一次性数据来源**（中文名、区域约束、维度参考），已完成提取，不再依赖

### 当前系统架构（已实现）
```
Calculator Frontend (Vanilla JS)
  ↓ POST /explore/cascade, /explore/meters
Explore API (FastAPI)
  ↓ fetch_global_prices()
Azure Global Retail Prices API (https://prices.azure.com)

Admin UI (Alpine.js)
  ↓ /api/v1/admin/*
Admin API → PostgreSQL (service_configs, product_catalog)
                      ↕ JSON 文件 (app/config/service_configs/*.json 降级)
```

**关键事实**：
- Explore API 只用 Azure Global API，PostgreSQL 目前**只存 config 和 catalog**，不存价格数据
- Global API 查询 CN 区域（如 `chinaeast2`）可返回 CNY 价格 — 当前系统实际可用于 CN 定价
- 已有 9 个 service config，28 个产品有中文名（本轮已完成）

---

## MVP 范围（本轮交付）

### IN SCOPE（本轮实现）
1. **Admin UI Onboarding 工作流** — 让 PM 可以在 UI 中完成产品接入（导入模板 → 编辑 → 预览 → 发布）
2. **Admin Config Preview**（新需求）— 在 Admin UI 中预览 service config 在 Calculator 中的实际效果
3. **Batch 1 产品接入示范**（redis-cache 作 demo，验证工作流）

### OUT OF SCOPE（未来迭代）
| 功能 | 原因 |
|------|------|
| 数据源切换到 CN CSV + PostgreSQL | 需要单独的数据管道架构，是独立的 Phase 4 |
| region_constraints 在 cascade 中实际生效 | 需要后端筛选逻辑变更 |
| 多角色审批流程 | MVP 单人操作足够 |
| Batch 2-3 产品接入 | 依赖 Onboarding 工作流完成后自行完成 |

---

## 数据源策略

### 现状
- Global Retail Prices API（`prices.azure.com`）查询 `chinaeast2` 等 CN 区域时返回 CNY 价格
- 数据完整性：CN 特有产品在 Global API 中可能没有数据（已知风险，用 "API 无数据" 标记处理）
- 可靠性：依赖外部 API，60s 内存缓存；缓存未命中实时查询；Global API 失败当前返回 503（无 fallback）

### Config/Catalog Fallback（已有）
```
配置加载: DB (published) → 内存缓存 (TTL 60s) → JSON 文件降级
```

### 未来数据源切换路径（Phase 4，不在本轮）
```
当前: Explore API → Global API
目标: Explore API → 本地 PostgreSQL (CN CSV 导入)
      CN CSV 定期从 azure.cn 下载 → import_data.py → retail_prices 表
      已有: retail_prices 表结构 + import 脚本框架
```

---

## 新功能设计：Admin Config Preview

### 用户诉求
在 Admin UI 编辑 service config 时，能看到该配置在 Calculator UI 中**实际渲染的样子**（下拉菜单、meter 列表、价格布局），而不只是看 JSON。

### 方案设计："在 Calculator 中预览" 按钮

**核心思路**：复用真实 Calculator 前端，不重复实现 UI 组件。
**已确认方式**：新标签页（不用 iframe）。

#### 实现步骤

**Step 1：后端新增草稿 config 查询参数**
```
GET /api/v1/explore/service-config/{service_name}?draft=true
```
- `draft=true` 时从 admin DB 查 draft/published config，不走发布缓存
- 无需额外鉴权（内部工具）

**Step 2：Calculator 前端支持预览模式**
- URL 参数 `?preview=<service_name>`
- 前端检测到该参数时：
  1. 自动将该 service 添加到 estimate
  2. 加载 config 时带 `?draft=true` — 读取草稿配置
  3. 页面顶部显示提示条："预览模式 — 当前使用草稿配置"

**Step 3：Admin UI 新增 Preview 按钮**
- Config Editor 页面顶部加 "在 Calculator 中预览" 按钮
- 点击后：先保存当前草稿 → 新标签页打开 `frontend/?preview=<service_name>`

**涉及文件**：
| 文件 | 改动 |
|------|------|
| `app/api/explore.py` | `GET /service-config/{name}` 新增 `?draft=true` 参数 |
| `frontend/js/api.js` | `fetchServiceConfig()` 支持 `draft` 参数 |
| `frontend/js/app.js` | 检测 `?preview=` URL 参数，自动添加 service |
| `frontend/index.html` | 预览模式提示条 |
| `admin/js/components/config-editor.js` | 新增 "在 Calculator 中预览" 按钮 |

---

## Onboarding 工作流设计

### 后端新增（`app/api/admin.py`）
```
GET  /api/v1/admin/onboarding/templates     — 列出 data/generated_service_configs/ 模板
POST /api/v1/admin/onboarding/import/{slug} — 导入模板 → 清理 _acn_* → 创建 draft
```

导入时自动处理：
1. 移除 `_acn_slug`、`_acn_display_name` 字段
2. 从 `data/slug_to_service_name.json` 查找英文 `service_name`、`display_name_cn`、**`family_key`**
3. 调用 `config_repo.create_config` 创建 draft
4. 如果产品不在 catalog → 按 mapping 表中的 `family_key` 自动添加到对应 family（含 `display_name_cn`）

> **已确认**：Family 归属通过 `slug_to_service_name.json` 中的 `family_key` 字段预定义，导入时无需 PM 手动选择。
> 需为 Batch 1-2 的 14 个 slug 在映射表中补充 `family_key` 字段。

**复用已有端点**（无需修改）：
- `POST /explore/cascade` — 预览级联筛选
- `POST /explore/meters` — 预览 meter 数据
- `PUT /admin/configs/{name}` — 保存编辑
- `POST /admin/configs/{name}/validate` — 校验
- `POST /admin/configs/{name}/publish` — 发布

### 前端新增（Admin UI）

**新路由** `#/onboarding`，新组件 `admin/js/components/onboarding.js`（Alpine.js）：

```
左侧：模板列表                     右侧：接入工作台（3 个 Tab）
──────────────────────────         ──────────────────────────────────────
可用模板（14 个）                   顶部：[在 Calculator 中预览] 按钮
  ○ redis-cache          [导入]
  ○ container-registry   [导入]     Tab 1: 配置编辑
  ○ managed-grafana      [已发布]     └─ 复用现有 config-editor form+JSON 双面板
  ○ site-recovery        [导入]       └─ 高亮提示需人工确认的字段
  ○ ...
                                    Tab 2: API 预览
每个模板显示:                         └─ [测试 Cascade] → 展示可用维度/选项
  - slug + 中文名                     └─ [测试 Meters] → 展示 meter 列表
  - quantity_model                    └─ 辅助填写 meter_labels, meter_order
  - 状态（可导入/draft/已发布）
                                    Tab 3: 发布检查
                                      └─ 自动校验（validate endpoint）
                                      └─ Catalog 状态检查
                                      └─ [发布] 按钮
```

#### 工作流程
```
PM 打开 Admin UI → #/onboarding
  │
  ├── 1. 查看模板列表 → 点击「导入」
  │     └─ 后端自动清理 + 创建 draft + 添加到 catalog（按预定义 family）
  │
  ├── 2. 编辑配置（Tab 1）
  │     └─ 调整 meter_labels、defaults 等
  │
  ├── 3. 实时预览（顶部按钮）
  │     └─ 新标签页打开 Calculator，自动渲染草稿配置效果
  │     └─ 根据实际渲染结果完善配置
  │
  ├── 4. API 预览（Tab 2）
  │     └─ 测试 cascade/meters → 确认数据正确
  │
  └── 5. 发布（Tab 3）
        └─ 校验通过 → 发布 → 自动导出 JSON + 更新缓存
```

---

## 关键文件清单

| 文件 | 类型 | 改动说明 |
|------|------|---------|
| `app/api/admin.py` | 修改 | 新增 2 个 onboarding 端点 |
| `app/api/explore.py` | 修改 | service-config 端点新增 `?draft=true` |
| `admin/js/app.js` | 修改 | 新增 `#/onboarding` 路由 |
| `admin/js/api.js` | 修改 | 新增 onboarding + preview API 函数 |
| `admin/js/components/onboarding.js` | 新建 | 产品上线工作台（Alpine.js） |
| `admin/js/components/config-editor.js` | 修改 | 新增"在 Calculator 中预览"按钮 |
| `admin/index.html` | 修改 | 新增 onboarding 模板 + 导航链接 |
| `frontend/js/app.js` | 修改 | 检测 `?preview=` 参数，自动添加 service |
| `frontend/js/api.js` | 修改 | fetchServiceConfig 支持 draft 模式 |
| `frontend/index.html` | 修改 | 预览模式提示条 |
| `data/slug_to_service_name.json` | 修改 | 为 14 个 slug 补充 `family_key` 字段 |

---

## 验证方式

1. `GET /admin/onboarding/templates` → 返回 14 个模板列表
2. `POST /admin/onboarding/import/redis-cache` → draft config 创建成功，catalog 中出现该产品
3. Admin UI `#/onboarding` → 看到模板列表 → 导入 → Tab 2 测试 cascade/meters 有数据
4. Config Editor 点 "在 Calculator 中预览" → 新标签页打开，estimate card 正确渲染，显示"预览模式"提示条
5. 修改 meter_labels → 保存草稿 → 刷新预览标签页 → 看到改动生效
6. Tab 3 发布 → Calculator 正式加载该产品
7. `uv run pytest` 回归测试全部通过

---

## 开放问题（待团队讨论）

**Q1: 数据源时间表**
何时切换到 CN CSV + PostgreSQL 数据源？当前 Global API 返回 CN 区域 CNY 价格，基本满足需求，但存在网络依赖风险。建议把"定期从 azure.cn 下载 CSV + import"作为 Phase 4 独立任务规划，估计需要 1-2 周独立投入。

**Q2: Preview 鉴权**
`?draft=true` 端点草稿 config 是否需要认证？当前内部工具不鉴权，如果将来 Calculator 面向外部用户，需要在 URL 中传 token 或改用 sessionStorage。

**Q3: Onboarding 与现有 Config 编辑器的关系**
已通过 Onboarding 发布的 config 是否在 `#/configs` 页面管理？**建议**：两者共享 DB 数据，Onboarding 专注首次接入，`#/configs` 负责后续维护/版本回退。

**Q4: Global API 数据完整性**
Batch 1 中哪些产品在 Global API 中**没有 CN 区域数据**？建议在 Onboarding templates 端点中增加异步探测，给每个模板标注"API 有数据 / API 无数据 / 未检测"状态，让 PM 在导入前了解风险。

**Q5: Batch 1 产品接入优先级**
当前 Batch 1 有 9 个产品，建议以 `redis-cache`（最简单，instances_x_hours）作为端到端 demo 验证工作流。团队是否有其他优先需要上线的产品？
