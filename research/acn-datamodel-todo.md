# ACN DataModel 迁移与产品接入 TODO

**创建日期：** 2026-03-22
**最后更新：** 2026-03-24

> **已接入产品（本文档创建前）：** Virtual Machines, App Service, Power BI Embedded（instances_x_hours）；Azure Firewall, Event Grid, Service Bus（per_meter）。这些不在下方 TODO 中列出。

---

## Phase 0: 迁移工具

- [ ] **编写 Node.js 预处理脚本**: 将 `calculatordatamodel.js` + `calculatorconst.js` 合并执行，导出为标准 JSON (`calculatordatamodel.json`)
- [ ] **编写 Python 提取脚本** (`scripts/extract_acn_datamodel.py`):
  - [ ] 提取 slug → 中文名映射 (含区域约束清洗) → `acn_product_names.json`
  - [ ] 提取每产品维度结构 (Types/Features/Sizes 语义分析) → `acn_dimension_templates/`
  - [ ] 提取已知价格 → `acn_price_validation.json`
- [ ] **修复数据质量问题**: 记录重复 slug (3个), 命名异常 (2个), PriceTier 编码 bug (7处)

## Phase 1: 第一批产品接入（纯配置，~10 个）

### instances_x_hours 产品
- [ ] `redis-cache` — Tier (基本/标准/高级) → Size 选择 → 固定小时价
- [ ] `database-migration` — 简单实例选择

### per_meter 简单产品
- [x] `signalr-service` — 单一 Tier，月费 ✅ 已接入（`signalr_service.json` + `azure_signalr_service.json`，含 meter_labels/order/free_quota）
- [ ] `azure-ddos-protection` — 月费 + 超额
- [ ] `azure-ddos-ipprotection` — 每 IP 月费
- [ ] `managed-grafana` — 3 个独立 meter (实例/用户/冗余)
- [ ] `azure-fluid-relay` — 4 个独立 meter
- [ ] `site-recovery` — 2 个 meter (到客户站点/到 Azure)

### per_meter 含阶梯产品
- [ ] `notification-hub` — Tier (免费/基本/标准) + 阶梯
- [ ] `container-registry` — Tier (基本/标准/高级) + 月费

### 每个产品的接入步骤
- [ ] 创建 `app/config/service_configs/{slug}.json`
- [ ] (如需) 确认 `api_service_name` 映射
- [ ] (如需) 配置 `sku_groups`, `hidden_dimensions`, `dimension_labels`
- [ ] (如需) 配置 `hidden_meters`（子串匹配，过滤不需要展示的 meter）
- [ ] (如需) 配置 `meter_labels`（自定义 meter 显示名，endsWith 匹配）
- [ ] (如需) 配置 `meter_order`（自定义 meter 排序，子串匹配）
- [ ] (如需) 配置 `meter_free_quota`（跨 meter 免费额度，支持 `fixed` / `ref_meter` 模式）
- [ ] 通过 Explore API 验证 cascade/meters 数据正确
- [ ] 与 `acn_price_validation.json` 对比验证 CN 价格

## Phase 2: 第二批产品接入（per_meter 细化，~5 个）

- [ ] `traffic-manager` — 5 个 meter (DNS 查询含阶梯 + 4 个线性 meter)
- [ ] `network-watcher` — 4 个 meter (各有不同阶梯结构)
- [ ] `ip-address` — 3 种部署模型 × 多 Feature，含免费层阶梯
- [x] `load-balancer` — 3 种类型 × 规则费+数据处理 ✅ 已接入（`load_balancer.json`，含 meter_labels/order）
- [ ] `application-gateway-standard-v2` — 2 个独立费用组件 (网关+容量单位)
- [ ] `schedule` — Tier + 用量阶梯

## Phase 3: 第三批产品（需扩展能力）

### 扩展能力开发
- [ ] **设计 multi-component 模型** — 支持一张 estimate card 内多个独立配置组件
  - HDInsight 场景: Head Node / Worker Node / ZooKeeper Node 各自选 VM 规格和数量
  - 方案设计 + service_config 格式扩展 + 前端组件
- [ ] **设计 linked services** — 支持自动关联产品
  - IoT Hub + DPS 场景: 添加 IoT Hub 时自动提示/添加 DPS
  - Container Registry + Additional Storage 场景
- [ ] **azure-front-door 的 sku_groups 方案** — 标准/高级选择 + 多 Type 的 meter 展示

### 产品接入
- [ ] `azure-front-door` — per_meter + 标准/高级分层
- [ ] `hdinsight` — MVP: instances_x_hours; 完整版: multi-component
- [ ] `azure-iot-hub` + `azure-iot-hub-dps` — 分两张 card (MVP) / linked (完整版)
- [ ] `container-registry` + `additional-storage-container-build` — 同上
- [ ] `active-directory-b2c` — 需要专门的定价模型设计

## Phase 4: 数据源切换与验证

- [ ] **CN CSV → PostgreSQL 数据完整性验证** — 对比 datamodel 中的 260 个产品，哪些在 CSV 中有对应数据
- [ ] **建立价格验证管道** — datamodel 已知价格 vs CSV 导入价格，生成差异报告
- [ ] **前端切换到本地 API** — 从 Global Retail Prices API 切换到本地 PostgreSQL 的 Production API
- [ ] **区域约束落地** — 将 datamodel 中提取的区域可用性信息整合到产品筛选逻辑中

## 其他待办

- [ ] 更新 `product_catalog.json` — 整合 datamodel 提取的中文产品名（现已通过 Config Admin API 管理，publish 时自动导出 JSON）
- [ ] 更新 `adding-new-product-guide.md` — 补充 datamodel 迁移工具的使用方法 + 新增配置项说明（hidden_meters, meter_labels, meter_order, meter_free_quota）
- [ ] Storage 类产品调研 — datamodel 中有 54 个 storage 条目，需要归并策略
- [ ] 研究 CN 特有产品 — 部分产品可能在 Global API 中不存在，需特殊处理
