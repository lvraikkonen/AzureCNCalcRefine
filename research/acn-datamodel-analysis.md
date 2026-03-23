# ACN calculatordatamodel.js 深度分析与 Azure Global Calculator 对比

**撰写日期：** 2026-03-22
**数据源：** `prod-config/calculatordatamodel.js` (~69K行), `prod-config/calculatorconst.js`
**对比对象：** Azure Global Pricing Calculator, 本项目 Explore API

---

## 一、calculatordatamodel.js 结构解析

### 1.1 整体架构

~69,000 行 JS 文件，包含约 **180+ 个服务条目**，所有价格完全硬编码。

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

```javascript
var PriceTierEnum = {
    Free: "0",      // 免费
    Linear: "-1",   // 线性计费（单价 × 用量）
    Fixed: "-2",    // 固定单价 × 数量
};
var PricePeriodEnum = {
    Hourly: "0",    // 按小时
    Monthly: "1",   // 按月
};
```

### 1.3 四种定价模式

| PriceTier 值 | 含义 | 计算方式 | 示例 |
|-------------|------|---------|------|
| `"0"` (Free) | 免费 | 费用 = 0 | IoT Hub 免费层 |
| `"-2"` (Fixed) | 固定单价 | 费用 = PricePerTier × 数量 × 时间 | Redis Cache C0: ¥0.14/小时 |
| `"-1"` (Linear) | 线性 | 费用 = PricePerTier × 用量 | Traffic Manager 健康检查: ¥2.38/个 |
| 自定义字符串 | 阶梯定价 | 分段累进计算 | Service Bus 消息: `"0,13,14,100,101,2500"` |

**阶梯定价编码格式：**
- `PriceTier`: 阶梯边界的 min/max 对，如 `"0,13,14,100,101,2500,2501,100000"`
  - 含义：第1阶梯 0-13，第2阶梯 14-100，第3阶梯 101-2500，第4阶梯 2501-100000
- `PricePerTier`: 每阶梯价格，如 `"0,5.21,3.20,1.27"`
  - 含义：第1阶梯免费，第2阶梯 ¥5.21/百万，第3阶梯 ¥3.20/百万，第4阶梯 ¥1.27/百万

---

## 二、24 个待研究产品的定价模式分类

### 2.1 Pattern A：实例 × 小时 (instances_x_hours)

| 产品 slug | 中文名 | Types 语义 | Sizes 语义 | 映射复杂度 |
|-----------|--------|-----------|-----------|-----------|
| redis-cache | Redis 缓存 | Tier (基本/标准/高级) | 缓存大小 (C0-C6, P1-P5) | 低 |
| power-bi-embedded | Power BI Embedded | 单一 "配置类型" | 虚拟内核 (A1-A8) | 低 (已完成) |
| hdinsight | HDInsight | "default" | Features=VM系列, Sizes=VM规格 | 中（multi-component） |

### 2.2 Pattern B：多 Meter 独立计量 (per_meter)

| 产品 slug | 中文名 | Types 语义 | Features 数量 | 特殊点 |
|-----------|--------|-----------|-------------|--------|
| service-bus | 服务总线 | Tier (基本/标准/高级) | 标准层6个meter | 已完成 |
| azure-firewall | Azure 防火墙 | 部署类型 (2种) | 每种含 Standard+Premium | 已完成 |
| traffic-manager | 流量管理器 | "default" | 5个独立meter | Linear+阶梯混合 |
| network-watcher | 网络观察程序 | 4个Type (日志/诊断/连接/流量) | 每Type 1个meter | 各Type阶梯不同 |
| ip-address | 公共 IP 地址 | 3个Type (经典/ARM基本/ARM标准) | 多Feature | 含免费层阶梯 |
| load-balancer | 负载均衡器 | 3个Type (区局层/全局层/网关) | 规则费+数据处理 | "前5条=固定"特殊阶梯 |
| application-gateway-standard-v2 | 应用程序网关V2 | 2个Type (固定+容量单位) | 各1个meter | 两个独立费用组件 |
| azure-front-door | Azure Front Door | 4个Type | 每Type含标准/高级 | 最复杂的 per_meter |
| container-registry | 容器注册表 | Tier (基本/标准/高级) | 月费 | 拆出 additional-storage |
| azure-fluid-relay | Azure Fluid Relay | 单一 | 4个Feature | 简单 |
| managed-grafana | Managed Grafana | 单一 | 3个Feature | 简单 |

### 2.3 Pattern C：简单固定月费

| 产品 slug | 中文名 | 结构 | 复杂度 |
|-----------|--------|------|--------|
| signalr-service | Azure SignalR 服务 | 1个Tier, 月费 | 极低 |
| azure-ddos-protection | Azure DDoS 网络保护 | 月费 + 超额 | 低 |
| azure-ddos-ipprotection | Azure DDoS IP保护 | 每IP月费 | 极低 |
| site-recovery | 站点恢复 | 2个Feature, 线性月费 | 低 |
| database-migration | 数据库迁移服务 | 单一 | 低 |

### 2.4 Pattern D：Tier + Size (类 IoT Hub)

| 产品 slug | 中文名 | 结构 |
|-----------|--------|------|
| azure-iot-hub | Azure IoT 中心 | Tier(基本/标准) → Size(B1-B3/免费-S3), 月费 |
| azure-iot-hub-dps | IoT 中心设备预配服务 | 单独条目, 按操作数 |
| notification-hub | 通知中心 | Tier(免费/基本/标准) → 含阶梯 |
| schedule | 计划程序 | Tier → 多Feature |
| active-directory-b2c | Azure AD B2C | 复杂多功能 |

---

## 三、当前 calculatordatamodel.js 的核心问题

| # | 问题 | 影响 |
|---|------|------|
| 1 | **所有价格硬编码** | 价格更新需手工修改69K行文件并重新部署 |
| 2 | **存在重复键** | `"app-service"` 出现两次(行6和行154)，后者静默覆盖前者 |
| 3 | **语义层级不一致** | 同一 Types/Features/Sizes 层级在不同产品中语义完全不同 |
| 4 | **无区域结构化数据** | 区域限制仅写在 Name/Description 字符串里 |
| 5 | **阶梯定价编码脆弱** | min/max对的字符串格式难以理解和验证 |
| 6 | **不支持 Reservation/SavingsPlan** | 完全缺失这两种定价类型 |
| 7 | **无时间戳/版本** | 不知道价格何时更新 |
| 8 | **常量引用分散** | 大量 `CalculatorConst.xxx` 引用，跨文件依赖 |

---

## 四、与 Azure Global Calculator 的 GAP 分析

### 4.1 架构对比

| 能力 | ACN Prod Config | 本项目 (Explore API) | Azure Global Calculator |
|------|----------------|---------------------|------------------------|
| **价格数据源** | JS硬编码 | Azure Retail Prices API (动态) | Retail Prices API (动态) |
| **配置管理** | 69K行单文件 | 每服务~15行JSON | 每服务独立 calculator slug |
| **维度发现** | 硬编码在 Types/Features 中 | API 动态聚合 | API 动态聚合 |
| **区域支持** | 文字描述 | armRegionName | 完整区域筛选+可用性标记 |
| **Reservation/SavingsPlan** | 不支持 | 支持 | 完整支持 |
| **多组件产品** | 拆为多个独立条目 | 暂不支持 | 原生支持 |
| **关联产品** | 手工拆分 | 暂不支持 | 支持 linked services |
| **阶梯定价** | 自定义字符串编码 | tierMinimumUnits (API标准) | API标准格式 |
| **价格验证** | 无 | 可与CSV对比 | 完整测试管道 |

### 4.2 本项目与 Global Calculator 的对齐程度

| 维度 | 已有 | 还缺 |
|------|------|------|
| 级联筛选 + 动态维度发现 | ✅ | — |
| 本地定价计算 | ✅ | — |
| instances_x_hours 模式 | ✅ | — |
| per_meter 模式 | ✅ | — |
| Reservation/SavingsPlan | ✅ | — |
| sub_dimensions (productName拆解) | ✅ | — |
| sku_groups (虚拟Tier) | ✅ | — |
| **Multi-component (多节点角色)** | ❌ | HDInsight 等需要 |
| **Linked services (关联产品)** | ❌ | IoT Hub+DPS 等 |
| **CN 价格数据源切换** | 部分 | 前端还连 Global API |

---

## 五、calculatordatamodel.js 可提取利用的价值

| 可提取利用的 | 用途 | 不应沿用的 |
|-------------|------|-----------|
| 服务 slug → 中文名映射 | product_catalog.json | 硬编码的价格数值 |
| 每产品 UI 维度结构 | service_config JSON 模板 | Types/Features/Sizes 层级格式 |
| 区域可用性信息 | 区域约束配置 | PriceTier 自定义编码 |
| 已知价格 | 验证测试用例 | 单文件整体架构 |

---

## 六、24 产品接入优先级

### 第一批：纯配置，当前架构完全支持（预计每个 30min）

redis-cache, notification-hub, signalr-service, container-registry, azure-ddos-protection, azure-ddos-ipprotection, managed-grafana, azure-fluid-relay, site-recovery, database-migration

### 第二批：per_meter 模式（预计每个 1h）

traffic-manager, network-watcher, ip-address, load-balancer, application-gateway-standard-v2, schedule

### 第三批：需扩展能力

- azure-front-door — "Type 内含多 tier 选择"
- hdinsight — multi-component + cross-service
- azure-iot-hub + dps — 关联产品
- container-registry + additional-storage — 关联产品
- active-directory-b2c — 复杂多功能定价
