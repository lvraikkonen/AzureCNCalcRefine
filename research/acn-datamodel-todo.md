# ACN DataModel 迁移与产品接入 TODO

**创建日期：** 2026-03-22
**最后更新：** 2026-03-26

> **已接入产品（不在下方 TODO 中）：** Virtual Machines, App Service, Power BI Embedded（Pattern A）；Azure Firewall, Event Grid, Service Bus, SignalR, Load Balancer（Pattern B）。

---

## Phase 0: 提取工具 ✅ 已完成

- [x] Node.js 预处理脚本 (`scripts/convert_acn_datamodel.js`): JS → JSON
- [x] Python 提取脚本 (`scripts/extract_acn_metadata.py`):
  - [x] 提取 slug → 中文名映射 + 区域约束 → `acn_product_names.json`
  - [x] 提取维度结构 + 6 模式分类器 → `acn_dimension_templates/`
  - [x] 提取 CNY 价格 → `acn_price_validation.json`
- [x] 数据质量问题已记录（3 重复 slug, 2 命名异常）
- [x] 中文名应用到 `product_catalog.json` (`scripts/apply_cn_names.py`)
- [x] 价格对比框架 (`scripts/price_drift_report.py`)

**2026-03-26 升级：**
- [x] 分类器从 2 模式（A/B）升级为 6 模式（A-F）
- [x] 模板生成器 (`scripts/generate_service_configs.py`) 升级：英文 service_name、`_legacy_reference`、Pattern 标注
- [x] `slug_to_service_name.json` 补充 7 个 Batch 1 缺失映射

---

## Phase 1: Batch 1 产品接入（9 个，Pattern A + B）

> 模板已生成至 `data/generated_service_configs/`，需通过 Admin UI 导入 → 编辑 → API 预览 → 发布。
> 接入工作流见 `plan/MVP-plan.md` 和 `plan/acn-datamodel-onboarding-plan.md`。

### Pattern A (instances_x_hours)
- [ ] `redis-cache` — Azure Cache for Redis — Tier(Basic/Standard/Premium) + Size(C0-C6,P1-P5) — **端到端 demo 首选**
- [ ] `database-migration` — Database Migration Service — Tier(Standard/Premium) + vCore

### Pattern B (per_meter)
- [ ] `azure-ddos-protection` — Azure DDoS Protection — 2 meter (月费 + 超额)
- [ ] `azure-ddos-ipprotection` — Azure DDoS IP Protection — 1 meter (每 IP 月费)
- [ ] `managed-grafana` — Managed Grafana — 3 meter (操作/用户/冗余)，仅 chinanorth3
- [ ] `azure-fluid-relay` — Azure Fluid Relay — 4 meter (Input/Output/连接/存储)，仅 chinanorth3
- [ ] `site-recovery` — Site Recovery — 2 meter (到客户站点/到 Azure)
- [ ] `notification-hub` — Notification Hubs — Tier(Free/Basic/Standard) + 阶梯
- [ ] `container-registry` — Container Registry — Tier(Basic/Standard/Premium) + 月费

### 每个产品的接入步骤
1. [ ] 确认 Global API 有 CN 区域数据（查 `api_service_name`）
2. [ ] 通过 Admin UI 导入模板（或手动创建 draft config）
3. [ ] API 预览 Tab 查看 cascade/meters 数据
4. [ ] 根据 API 数据调整 `meter_labels`、`meter_order`、`hidden_meters`
5. [ ] Calculator 预览确认 UI 正确
6. [ ] 发布 + 回归测试

---

## Phase 2: Batch 2 产品接入（5 个，Pattern B 细化）

- [ ] `traffic-manager` — Traffic Manager — 5 meter (DNS 阶梯 + 4 线性)
- [ ] `network-watcher` — Network Watcher — 4 meter (各有不同阶梯)
- [ ] `ip-address` — Public IP Addresses — 3 部署模型 × 多 Feature
- [ ] `application-gateway-standard-v2` — Application Gateway — 2 费用组件
- [ ] `schedule` — Scheduler — Tier + 用量阶梯

---

## Phase 3: 需架构扩展的产品（暂缓）

### Pattern C (compute_plus_storage) — 需新 quantity_model
- [ ] SQL Database — DTU(`1/Day`) + vCore(`1 Hour`) + Storage(`GB/Month`)
- [ ] Azure Database for MySQL — Compute + Storage + IOPS + Backup
- [ ] Azure Database for PostgreSQL — 同 MySQL
- [ ] Azure Cosmos DB — RU/s + 节点 + 存储

### Pattern F (cross_service_composite) — 需跨服务查询
- [ ] HDInsight — 服务费 + VM 费 + 多节点角色
- [ ] Azure Databricks — DBU + VM 费 + 外部映射表（最复杂）

### 其他
- [ ] `azure-front-door` — Pattern B 复杂变体（Type 内含标准/高级选择）
- [ ] `azure-iot-hub` + `azure-iot-hub-dps` — 关联产品
- [ ] `active-directory-b2c` — Pattern E 复杂变体

---

## Phase 4: 数据源切换（独立规划）

- [ ] CN CSV → ETL → PostgreSQL (`retail_prices` 表)
- [ ] `explore.py`: `fetch_global_prices()` → 本地 DB 查询
- [ ] `price_drift_report.py` 验证价格一致性
- [ ] `region_constraints` 在 cascade 中实际生效
