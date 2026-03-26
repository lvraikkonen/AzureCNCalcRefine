# ACN calculatordatamodel.js 深度分析

**撰写日期：** 2026-03-22
**更新日期：** 2026-03-26（对齐 6 种 Global API 定价模式分类）
**数据源：** `prod-config/calculatordatamodel.js` (~69K行), `prod-config/calculatorconst.js`
**对比对象：** Azure Global Pricing Calculator, 本项目 Explore API

---

## 一、calculatordatamodel.js 结构解析

### 1.1 整体架构

~69,000 行 JS 文件，包含约 **260 个服务条目**（257 个唯一 slug），所有价格完全硬编码。

```
CalculatorData.Services = {
    "service-slug": {
        Name: "中文显示名",
        Types: [{
            Name: "层级/类型名",
            Features: [{
                Name: "feature/meter名",
                PricePeriod: PricePeriodEnum.Hourly | Monthly,
                PriceUnit: "个",
                MinUnit: "0",
                MaxUnit: "N",
                Sizes: [{
                    Name: "规格名",
                    Description: "描述",
                    PriceTier: PriceTierEnum.Free | Fixed | Linear | "阶梯字符串",
                    PricePerTier: "价格" | "阶梯价格字符串",
                    MinUnit/MaxUnit/PriceUnit: "用量范围和单位"
                }]
            }]
        }]
    }
}
```

### 1.2 定价枚举

| PriceTier 值 | 含义 | 计算方式 | 示例 |
|-------------|------|---------|------|
| `"0"` (Free) | 免费 | 费用 = 0 | IoT Hub 免费层 |
| `"-2"` (Fixed) | 固定单价 | 费用 = PricePerTier × 数量 × 时间 | Redis Cache C0: ¥0.14/小时 |
| `"-1"` (Linear) | 线性 | 费用 = PricePerTier × 用量 | Traffic Manager: ¥2.38/个 |
| 自定义字符串 | 阶梯定价 | 分段累进计算 | Service Bus: `"0,13,14,100,101,2500"` |

阶梯编码格式：
- `PriceTier`: 阶梯边界 min/max 对（如 `"0,13,14,100,101,2500,2501,100000"`）
- `PricePerTier`: 每阶梯价格（如 `"0,5.21,3.20,1.27"`）

### 1.3 Types/Features/Sizes 的语义多义性

**这三个层级在不同产品中语义完全不同**，这是 legacy datamodel 最大的设计缺陷：

| 层级 | 可能的含义 | 例子 |
|------|-----------|------|
| **Types** | Tier 层级 | redis-cache: 基本/标准/高级 |
| | 冗余方式 | storage: LRS/GRS/RA-GRS |
| | 网关/SKU 规格 | vpn-gateway: VpnGw1AZ/VpnGw2AZ |
| | 计费模型 | cosmos-db: Autoscale/Standard |
| | 工作负载类型 | sql-database: 常规用途/业务关键 |
| | 无意义占位 | container-instances: "default" |
| **Features** | 无意义占位 | redis-cache: "default" |
| | 独立 meter | traffic-manager: DNS queries, health checks |
| | VM 系列 | hdinsight: Ev3 系列, F 系列 |
| | 费用组件 | vpn-gateway: base fee + S2S + P2S |
| | 计算 + 存储混合 | sql-database: 许可证价格, 附加存储, 备份 |
| **Sizes** | 实例规格 | redis-cache: C0-C6, P1-P5 |
| | VM SKU | hdinsight: E2 v3, E4 v3 |
| | vCore 数 | sql-database: vCore 4, vCore 8 |
| | 无意义占位 | notification-hub: "default" |

---

## 二、Legacy 结构到 6 种 Global API 定价模式的映射

> 详细的 Global API 定价模式分析见 `research/product-pricing-patterns.md`

### 2.1 分类器检测信号

提取脚本 `extract_acn_metadata.py` 通过以下信号将 legacy 产品分类到 6 种模式：

| 检测信号 | Legacy 数据特征 | 指向模式 |
|---------|----------------|---------|
| Features 全 "default" + 全 Hourly | `PricePeriod="0"`, `Feature.Name="default"` | **A** (instances_x_hours) |
| 同 Type 下有多 Size 的 Hourly Feature + Monthly Feature | 计算(多Size,时费) + 存储(单Size,月费) | **C** (compute_plus_storage) |
| ≥2 个 Feature 的 PriceUnit 含 vCPU/GiB | `PriceUnit="vCPU/月"` + `"GB/月"` | **D** (resource_dimensions) |
| Features 有 "default"(基础费) + 命名(附加费) | 混合 | **E** (sku_base_plus_meter) |
| Features 全命名 + PricePeriod 统一 | fallback | **B** (per_meter) |
| 无法从单 slug 检测 | 需外部标注 | **F** (cross_service_composite) |

### 2.2 257 产品的 Pattern 分布

```
Pattern A (instances_x_hours):       36 products (14%)
Pattern B (per_meter):              193 products (75%)
Pattern C (compute_plus_storage):    13 products  (5%)
Pattern D (resource_dimensions):      6 products  (2%)
Pattern E (sku_base_plus_meter):      9 products  (4%)
Pattern F (cross_service_composite):  —  (需外部标注，无法从 legacy 单 slug 检测)
```

### 2.3 Batch 1-2 产品的模式分类

**Batch 1 — 全部是 Pattern A 或 B（已生成模板）**

| slug | Pattern | quantity_model | Legacy 结构 |
|------|---------|---------------|-------------|
| redis-cache | A | instances_x_hours | Types=Tier, Features=default, Sizes=C0-C6/P1-P5 |
| database-migration | A | instances_x_hours | Types=Tier, Features=default, Sizes=vCore |
| azure-ddos-protection | B | per_meter | Features=[每月费用, 超额费用] |
| azure-ddos-ipprotection | B | per_meter | Features=[公共IP资源每月费用] |
| managed-grafana | B | per_meter | Features=[操作输入, 活跃用户, 区域冗余] |
| azure-fluid-relay | B | per_meter | Features=[操作输入, 操作输出, 连接分钟, 存储] |
| site-recovery | B | per_meter | Features=[到客户站点, 到Azure] |
| notification-hub | B | per_meter | Types=Tier(免费/基本/标准), 含阶梯定价 |
| container-registry | B | per_meter | Types=Tier(基本/标准/高级), 月费 |

**Batch 2**

| slug | Pattern | 说明 |
|------|---------|------|
| traffic-manager | B | 5 个 meter，DNS 有阶梯 |
| network-watcher | B | 4 个 Type 各含 1 个 meter |
| ip-address | B | 3 种部署模型 × 多 Feature |
| application-gateway-standard-v2 | B | 2 个费用组件 |
| schedule | B | Tier + 用量阶梯 |

**Batch 3（需架构扩展，暂缓）**

| slug | Pattern | 说明 |
|------|---------|------|
| hdinsight | F | 跨服务（服务费 + VM 费）+ 多节点角色 |
| azure-databricks | F | DBU + VM 费 + 外部映射表 |
| sql-database-* | C | 计算 + 存储混合（DTU 日费 + vCore 时费 + 存储月费） |
| cosmos-db | C | RU/s + 节点 + 存储 |
| azure-front-door | B (复杂) | Type 内含标准/高级选择 |
| azure-iot-hub | F | 关联产品（Hub + DPS） |
| active-directory-b2c | E (复杂) | 多功能定价 |

---

## 三、Legacy DataModel 的核心问题

| # | 问题 | 影响 |
|---|------|------|
| 1 | **所有价格硬编码** | 价格更新需手工修改 69K 行文件 |
| 2 | **存在重复键** | `"app-service"` 等 3 个 slug 重复 |
| 3 | **语义层级不一致** | Types/Features/Sizes 在不同产品中含义不同 |
| 4 | **无区域结构化数据** | 区域限制仅写在 Name/Description 字符串里 |
| 5 | **阶梯定价编码脆弱** | min/max 对的字符串格式难以理解和验证 |
| 6 | **不支持 Reservation/SavingsPlan** | 完全缺失 |
| 7 | **无跨服务关联** | 每个 slug 自包含，无法表示 Pattern F |
| 8 | **无多组件支持** | HDInsight 的 Head/Worker/ZooKeeper 无法在单条目中表示 |

---

## 四、与 Azure Global Calculator 的 GAP 分析

| 能力 | ACN Legacy | 本项目 (Explore API) | Azure Global Calculator |
|------|-----------|---------------------|------------------------|
| **价格数据源** | JS 硬编码 | Global Retail Prices API (动态) | Retail Prices API (动态) |
| **配置管理** | 69K 行单文件 | 每服务 ~15 行 JSON + DB + Admin UI | 每服务独立 calculator slug |
| **维度发现** | 硬编码在 Types/Features 中 | API 动态聚合 | API 动态聚合 |
| **区域支持** | 文字描述 | armRegionName | 完整区域筛选 + 可用性标记 |
| **Reservation/SavingsPlan** | 不支持 | ✅ 支持 | 完整支持 |
| **Pattern A (实例×时)** | ✅ | ✅ | ✅ |
| **Pattern B (per_meter)** | ✅ | ✅ | ✅ |
| **Pattern C (计算+存储)** | 部分(混合在 Features 中) | ❌ 未实现 | ✅ |
| **Pattern D (资源维度)** | 部分 | ❌ 未实现 | ✅ |
| **Pattern E (SKU 基础费+附加)** | ✅ | ⚠️ per_meter 近似 | ✅ |
| **Pattern F (跨服务复合)** | ❌ 无法表示 | ❌ 未实现 | ✅ |
| **多组件产品** | 拆为多条目 | ❌ 暂不支持 | 原生支持 |
| **关联产品** | 手工拆分 | ❌ 暂不支持 | 支持 linked services |

---

## 五、Legacy DataModel 可提取利用的价值

| 可提取 | 用途 | 提取状态 |
|--------|------|---------|
| slug → 中文名映射 | `product_catalog.json` | ✅ 已完成 (Step 3) |
| 区域可用性 | `region_constraints` 字段 | ✅ 已完成 (Step 2-3) |
| 维度结构 | service_config 模板参考 | ✅ 已完成 (Step 2-4) |
| 定价模式分类 | 6 种 Pattern 标注 | ✅ 已完成 (脚本升级) |
| CNY 价格 | 数据源切换时 sanity check | ✅ 已提取 (Step 5, 未使用) |

| 不应沿用的 | 原因 |
|-----------|------|
| 硬编码价格数值 | 价格来自 Global API / 未来 CN CSV |
| Types/Features/Sizes 层级格式 | 语义不一致，已映射到标准 config 格式 |
| PriceTier 自定义编码 | 已转换为标准 tierMinimumUnits |
| 单文件整体架构 | 已转为每产品独立 JSON + DB 管理 |

**Legacy datamodel 是一次性参考数据来源，不进入生产数据流。**
