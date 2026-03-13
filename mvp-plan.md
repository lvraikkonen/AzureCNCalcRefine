# MVP 计划

## MVP 范围

MVP 对应 implement-plan.md 的 Phase 1-3，目标是**所有 105 个服务均可走通"浏览 → 配置 → 查价"流程**。

### 包含
- 数据导入流程（CSV → PostgreSQL）
- 产品目录 API（分类浏览 + 搜索）
- 级联配置 API（5 维度双向约束筛选）
- Meter 列表 API（含阶梯定价 tiers）
- 基础价格计算 API

### 不包含（Phase 4+）
- 子维度拆解（access_tier/redundancy 独立下拉框）
- Meter 增强（display_label / category / default_quantity）
- 服务配置模板系统（JSON 配置文件）
- Excel 导出
- 前端 Demo UI

---

## 探索工具设计：`scripts/explore_global_api.py`

### 目标
提供一个 CLI 工具，交互式查询 Azure Global Retail Prices API，辅助持续调研数据结构、验证子维度假设、对比中国区数据。

### 功能模块

#### 1. 按服务查询 + 维度分布汇总
```bash
python scripts/explore_global_api.py service "Virtual Machines" --region eastus
```
输出：
- productName 分布（DISTINCT 值 + 行数）
- skuName 分布
- type/term 分布
- unitOfMeasure 分布

#### 2. 级联探索（模拟级联筛选）
```bash
python scripts/explore_global_api.py cascade "Storage" --region eastus --product "Blob Storage"
```
输出五个维度的可选值列表，模拟 configurations API 的行为。

#### 3. productName/skuName 子维度模式分析
```bash
python scripts/explore_global_api.py subdimensions "Storage" --field sku_name
```
输出：
- 所有 DISTINCT 值
- 自动检测的分词模式
- 提取的子维度候选值

#### 4. Meter/Tier 结构查看
```bash
python scripts/explore_global_api.py meters "Storage" --product "Blob Storage" --sku "Hot LRS" --region eastus
```
输出该配置下所有 meter 及其 tiers。

#### 5. Global vs CN 数据对比
```bash
python scripts/explore_global_api.py compare "Virtual Machines" --product "Virtual Machines Dv3 Series"
```
对比同一产品在 Global API 和中国区 CSV 中的维度覆盖差异。

### 依赖
- `httpx`: HTTP 客户端（调用 Azure Global API）
- `rich`: 终端美化输出（表格、树形结构）

### API 端点
- Azure Global: `https://prices.azure.com/api/retail/prices`
- 分页: OData 格式，`$filter` 参数，`NextPageLink` 分页

---

## 讨论要点

### 1. 子维度方案选型
- **推荐：延迟级联**（子维度未全选时不约束后端）
- 备选：前缀级联（部分选择时 LIKE 过滤），增加后端复杂度
- 关键判断：对 UX 的影响是否可接受？

### 2. Meter 推导策略
- 自动推导（keyword-based 分类 + unitOfMeasure 映射）覆盖 ~80% 场景
- 剩余 ~20% 需要服务级 meter_overrides（JSON 配置）
- 问题：自动分类的误判率？需要用真实数据验证

### 3. 优先覆盖的服务列表
按用户使用频率和数据复杂度排序：

| 优先级 | 服务 | 原因 |
|--------|------|------|
| P0 | Virtual Machines | 最常用，sub_dimensions: OS + Series |
| P0 | Storage | 最复杂的阶梯定价，sub_dimensions: AccessTier + Redundancy |
| P1 | SQL Database | 高频，多 meter |
| P1 | Azure Database for MySQL | 中国区常用 |
| P1 | Azure Cosmos DB | 多子产品类型 |
| P2 | App Service | 中等复杂度 |
| P2 | Azure Functions | instances_x_hours 模型 |
| P3 | 其余 ~98 个服务 | 通用 5 维度 + 原始 meter，可用但 UX 粗糙 |
