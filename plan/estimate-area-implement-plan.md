# 估算区 (Estimate Area) 实现计划

## Context

导航区已完成，接下来实现核心的估算区。当前已有一个 MVP 版的 `estimate-card.js`（567 行），支持基本的级联筛选和通过 API 计算价格。但与生产环境的 Azure Calculator 相比，缺少**本地计算、Savings 单选按钮、数量输入切换、折叠摘要、价格分项展示**等关键功能。

核心改造目标：将"每次变更都调 API"的架构改为"**级联筛选调 API + 选定 Instance 后本地计算**"的两阶段模型。

---

## 任务列表（按依赖顺序）

### Task 1: 两阶段计算模型（基础，最高优先级）
**复杂度: L** | 无依赖

**目标**: Instance 选定后，一次性拉取 meters 缓存到前端，后续数量/定价模式变更全部本地计算。

**文件变更**:

| 文件 | 动作 | 说明 |
|------|------|------|
| `frontend/js/pricing.js` | **新建** | 前端定价计算引擎（纯函数，无 DOM 依赖） |
| `frontend/js/api.js` | 修改 | 新增 `fetchMeters()` |
| `frontend/js/state.js` | 修改 | item 扩展 `metersCache`, `metersCacheKey`, `upfrontCost` |
| `frontend/js/components/estimate-card.js` | 修改 | 重构计算流程 |

**pricing.js 核心函数**:
- `calculateTieredCost(tiers, usage)` — 移植自后端 `global_pricing.py:67-90`，阶梯累进算法
- `calculateLocalPrice(metersCache, type, term, quantity, hoursPerMonth)` — 返回 `{ monthlyCost, upfrontCost, paygCost, meters[] }`
  - Consumption: `unitPrice × hoursPerMonth × quantity`（unit="1 Hour"时）
  - Reservation: `tiers[0].unitPrice × quantity`（总期价），monthlyCost = total / months
  - SavingsPlan: 同 Consumption 逻辑，费率更低
- `getAvailableSavingsOptions(metersCache)` — 从缓存中提取可用 type/term 组合及折扣率

**estimate-card.js 流程变更**:
```
维度变更 → triggerCascade() → POST /cascade → 自动选定
  → 如果 region+product+sku 变了 → fetchMeters() 一次 → 缓存 → recalculateLocal()
  → 如果缓存命中 → recalculateLocal()

数量/定价模式变更 → recalculateLocal()（纯 JS，无 API 调用）
```

**移除**: `triggerCalculator()` 方法（不再需要实时调 `/calculator`）

---

### Task 2: Savings Options 单选按钮 UI
**复杂度: M** | 依赖 Task 1

**目标**: 将 savings 下拉框替换为分组单选按钮（PAYG / Savings Plan / Reservation），显示动态折扣百分比。

**文件变更**:

| 文件 | 动作 | 说明 |
|------|------|------|
| `frontend/js/components/estimate-card.js` | 修改 | `renderSavingsDropdown()` → `renderSavingsRadio()` |
| `frontend/css/style.css` | 修改 | 新增 `.savings-section`, `.savings-radio`, `.savings-discount` 样式 |

**UI 结构**:
```
Compute (D2 v3)
● Pay as you go

Savings plan ⓘ
○ 1 year savings plan (~31% discount)
○ 3 year savings plan (~53% discount)

Reservations ⓘ
○ 1 year reserved (~40% discount)
○ 3 year reserved (~62% discount)
```

- 折扣 % 从 `pricing.js` 的 `getAvailableSavingsOptions()` 获取
- 切换单选按钮 → 调用 `recalculateLocal()`，不调 API
- 只渲染有数据的分组

---

### Task 3: 数量输入模式切换
**复杂度: S** | 依赖 Task 2

**目标**: PAYG 显示 `[实例数] × [时长] [单位▾]`；SP/RI 只显示 `[实例数]`。

**文件变更**:

| 文件 | 动作 | 说明 |
|------|------|------|
| `frontend/js/components/estimate-card.js` | 修改 | 重写 `renderQuantity()` |
| `frontend/js/state.js` | 修改 | item 新增 `hoursUnit` 字段（'hours'/'days'/'months'） |
| `frontend/css/style.css` | 修改 | 时长单位下拉样式 |

**逻辑**:
- `type === 'Consumption'` → 显示实例数 + 时长 + 单位选择
- 其他 → 只显示实例数
- 单位换算：Hours 直传, Days × 24, Months × 730
- 切换定价模式时自动显示/隐藏时长输入

---

### Task 4: 卡片折叠摘要头部
**复杂度: S** | 依赖 Task 1

**目标**: 折叠态显示完整配置摘要 + upfront/monthly 双价格。

**文件变更**:

| 文件 | 动作 | 说明 |
|------|------|------|
| `frontend/js/components/estimate-card.js` | 修改 | 新增 `renderHeaderSummary()` |
| `frontend/css/style.css` | 修改 | `.card-summary-text`, `.card-cost-upfront` |

**摘要格式**:
- PAYG: `1 D2 v3 x 730 Hours (Pay as you go) | Monthly: $70.08`
- RI: `2 D2 v3 (1 Year Reserved) | Upfront: $xxx | Monthly: $xx.xx`

---

### Task 5: 卡片底部价格汇总
**复杂度: S** | 依赖 Task 1

**目标**: 在 meter breakdown 下方显示 upfront/monthly 分项汇总。

**文件变更**:

| 文件 | 动作 | 说明 |
|------|------|------|
| `frontend/js/components/estimate-card.js` | 修改 | 新增 `renderPriceSummary()` |
| `frontend/css/style.css` | 修改 | `.price-summary`, `.price-summary-row` |

---

### Task 6: 从配置文件加载默认值
**复杂度: M** | 依赖 Task 1

**目标**: "Add to estimate" 后立即显示预填的完整估算卡片。

**文件变更**:

| 文件 | 动作 | 说明 |
|------|------|------|
| `app/api/explore.py` | 修改 | 新增 `GET /service-config/{service_name}` 端点 |
| `app/config/service_configs/virtual_machines.json` | 修改 | 扩展 defaults（region, default_instance 等） |
| `frontend/js/api.js` | 修改 | 新增 `fetchServiceConfig()` |
| `frontend/js/components/estimate-card.js` | 修改 | `initCard()` 改为从配置加载默认值 |

**流程**:
```
Add to estimate → fetchServiceConfig() → 应用默认 selections/subSelections
→ cascade → 自动选中 default_instance → fetchMeters → 本地计算 → 渲染完整卡片
```

---

### Task 7: 底部汇总栏增强
**复杂度: S** | 依赖 Task 1

**文件变更**:

| 文件 | 动作 | 说明 |
|------|------|------|
| `frontend/js/state.js` | 修改 | 新增 `getTotalUpfrontCost()` |
| `frontend/js/components/summary-bar.js` | 修改 | 显示 upfront + monthly |
| `frontend/index.html` | 修改 | summary bar HTML 结构 |
| `frontend/js/app.js` | 修改 | 传递新 DOM 元素 |

---

### Task 8: 附加关联服务（可后续单独迭代）
**复杂度: L** | 依赖 Task 1, 6

**目标**: VM 卡片下方添加 Managed Disks / Storage transactions / Bandwidth 折叠子面板。

**文件变更**:

| 文件 | 动作 | 说明 |
|------|------|------|
| `frontend/js/components/related-service.js` | **新建** | 轻量级子估算组件 |
| `app/config/service_configs/virtual_machines.json` | 修改 | 添加 `related_services` 配置 |
| `frontend/js/components/estimate-card.js` | 修改 | 渲染关联服务区域 |
| `frontend/css/style.css` | 修改 | 关联服务折叠样式 |

---

## 依赖关系图

```
Task 1 (两阶段模型)  ← 基础，必须最先做
  ├── Task 2 (Savings Radio)  ← 需要 metersCache
  │     └── Task 3 (数量切换)  ← 需要 savings radio
  ├── Task 4 (折叠摘要)       ← 需要 upfront/monthly
  ├── Task 5 (底部价格)       ← 需要本地计算结果
  ├── Task 6 (默认值)         ← 需要 meters 流程
  ├── Task 7 (汇总栏)         ← 需要 upfront in state
  └── Task 8 (关联服务)       ← 需要 Task 1 + 6，可单独迭代
```

**建议实现顺序**: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

---

## 架构演进备注（MVP → 生产）

当前 MVP 阶段直连 Azure Global Retail Price API，未落库。本计划中的前端改造（Task 1-8）设计为**数据源无关**，未来切换到本地 DB 时前端代码可完全复用。

```
MVP (当前):
  前端 → FastAPI (explore.py) → Azure Global Retail Price API (实时)
                                 ↑ 每次 cascade/meters 都是实时调外部 API
                                 ↑ 延迟高 (~500ms-2s), 有 rate limit 风险

生产 (未来):
  Airflow DAG (每日) → ETL → PostgreSQL (retail_prices 表)
  前端 → FastAPI (explore.py) → 本地 DB 查询 (~10ms)
```

**关键设计原则**：

1. **前端只依赖后端 API schema，不关心数据来源** — `fetchMeters()` 调用 `/explore/meters`，返回 `MeterGroup[]`。后端从 Azure API 取还是从本地 DB 查，对前端透明。
2. **Task 1 在 MVP 阶段更有必要** — 外部 API 延迟高，本地缓存 meters + 本地计算可以显著减少等待。生产阶段 DB 查询虽快，本地计算仍有价值（减少请求数、提升交互流畅度）。
3. **后端切换路径清晰** — 当前 `explore.py` 中的 `fetch_global_prices()` 是唯一的数据获取入口。未来只需将其替换为 SQLAlchemy 查询，路由层和前端均不需要改动。

**生产阶段待规划的工作**（不在本轮 MVP 范围内）：

- ETL Pipeline：Airflow DAG，每日拉取 Azure Retail Price API 全量数据
- 数据库模型：`retail_prices` 表设计，索引策略（`pg_trgm` 模糊搜索已预留）
- 数据一致性：增量更新 vs 全量替换策略，`product_catalog` 物化视图刷新
- 监控告警：ETL 失败告警，数据时效性检查

---

## 关键风险

1. **Reservation 价格语义**: `unitPrice` 是承诺期**总价**（非月价），JS 端必须一致处理：`monthlyCost = unitPrice × qty / termMonths`
2. **SavingsPlan 语义**: 与 Consumption 同为小时计费（`unitPrice × hours × qty`），只是费率更低
3. **meters 端点数据量**: 单个 VM instance 的全 type/term meter 数据约 3-5 组、十几行，缓存无压力

## ToDo List — 进度追踪 & 讨论

> 在每个条目后标注状态和负责人，讨论意见直接追加在对应条目下方。
> 状态：⬜ 待讨论 | 🟡 讨论中 | ✅ 已确认 | 🚧 开发中 | ✔️ 已完成 | ❌ 否决

### 方案确认（需线下对齐）

- ✅ **[设计] 两阶段模型是否采纳？** — 级联筛选走 API + 本地计算 vs 保持全程 API
  - 讨论点：前端缓存 meters 后断网 / 过期如何处理？是否需要 TTL？
  - 结论：**采纳**。MVP 阶段直连 Azure Global Retail Price API，延迟高（500ms-2s），本地缓存 meters + 本地计算更有必要。前端只依赖 `/explore/meters` 的 schema，数据源透明。未来切换到本地 DB（ETL + Airflow DAG + PostgreSQL）时，前端代码完全复用，后端仅需将 `fetch_global_prices()` 替换为 SQLAlchemy 查询。
- ⬜ **[设计] Reservation unitPrice 语义对齐** — 确认后端 meters 端点返回的是承诺期总价
  - 需要对照实际数据验证：`unitPrice × qty` = 总费用，`monthlyCost = total / termMonths`
  - 结论：_待填写_
- ✅ **[设计] Savings Radio vs Dropdown** — 是否替换为单选按钮分组
  - 讨论点：移动端空间是否足够？折扣百分比的显示精度（取整 vs 一位小数）
  - 结论：使用Radio Button可以，折扣百分比只需取整(约等于符号)
- ✅ **[设计] 数量输入模式** — PAYG 时长单位切换（Hours/Days/Months）是否需要
  - 讨论点：Azure 国际站有此功能，但 MVP 是否必要
  - 结论：MVP也需要进行市场单位切换（Hours/Days/Months）
- ⬜ **[设计] Task 6 默认值加载** — 是否新增后端端点 `GET /service-config/` 还是前端硬编码
  - 讨论点：后端返回 vs 前端 SERVICE_DEFAULTS 扩展，哪个更灵活
  - 结论：_待填写_
- ⬜ **[设计] Task 8 关联服务** — 是否纳入本轮迭代
  - 讨论点：Managed Disks / Bandwidth 等子面板复杂度高，建议拆为独立迭代
  - 结论：_待填写_

### 开发任务追踪

| # | 任务 | 复杂度 | 状态 | 负责人 | 备注 |
|---|------|--------|------|--------|------|
| 1 | 两阶段计算模型 — `pricing.js` + meters 缓存 + `recalculateLocal()` | L | ✔️ | — | 基础任务，已完成 |
| 2 | Savings Radio UI — 分组单选按钮 + 折扣百分比 | M | ✔️ | — | 已完成 |
| 3 | 数量输入模式切换 — PAYG 时长 vs RI 仅实例数 | S | ✔️ | — | 已完成 |
| 4 | 卡片折叠摘要头部 — 配置摘要 + 双价格 | S | ✔️ | — | 已完成 |
| 5 | 卡片底部价格汇总 — upfront/monthly 分项 | S | ✔️ | — | 已完成 |
| 6 | 从配置文件加载默认值 — 预填卡片 | M | ✔️ | — | 已完成 |
| 7 | 底部汇总栏增强 — upfront + monthly | S | ✔️ | — | 已完成 |
| 8 | 附加关联服务 — Disks/Storage/Bandwidth 子面板 | L | ⬜ | — | 依赖 Task 1+6，可独立迭代 |
| 9 | Pattern B 产品支持 — per-meter 数量模型 + 维度标签/隐藏 | L | ✔️ | — | Azure Firewall、Event Grid 已接入 |
| 10 | 5 Year Reservation 支持 | S | ✔️ | — | SAVINGS_OPTIONS + termToMonths() 动态化 |
| 11 | Per-SKU meter 过滤/分组 — 按 tier 控制显示哪些 meter | M | ⬜ | — | 依赖 Task 9。Event Grid: Standard Operations 仅属于 Basic tier，Standard tier 不应显示 |

### 讨论记录

> 按日期追加讨论纪要，格式：`[YYYY-MM-DD] 参与人 — 结论摘要`

- [2026-03-13] — Task 1 两阶段模型确认采纳。MVP 直连 Azure API 延迟高，本地计算价值更大。前端改造设计为数据源无关，未来生产阶段切换到 ETL + Airflow DAG + PostgreSQL 时前端可完全复用。新增「架构演进备注」章节记录 MVP→生产的边界。
- [2026-03-16] — Task 9 Pattern B 产品支持完成。新增 `per_meter` 数量模型，支持每个 meter 独立输入用量（含 hourly meter 的 units×hours 分解）。新增 `dimension_labels`（自定义维度标签）和 `hidden_dimensions`（隐藏单值维度）配置。Azure Firewall 和 Event Grid 已通过纯配置接入。同时修复 5 Year Reservation 支持（Task 10），将 `termToMonths()` 和 savings 标签逻辑动态化。

---

## 验证方式

1. 启动服务 `uv run uvicorn app.main:app --reload`
2. 浏览器打开，点击 "Add to estimate" 添加 Virtual Machines
3. 验证级联筛选正常，选定 Instance 后切换 PAYG/RI/SP 价格即时更新（无 loading spinner）
4. 验证数量输入变更即时反映价格
5. 验证折叠态摘要显示正确
6. `uv run pytest` 确保后端测试仍全部通过
