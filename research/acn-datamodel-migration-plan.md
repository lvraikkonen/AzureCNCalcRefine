# ACN calculatordatamodel.js 迁移方案

**撰写日期：** 2026-03-22
**目标：** 从 `calculatordatamodel.js` 提取中文名映射、维度结构、区域可用性等有价值数据，转换为本项目可用的格式

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

### 1.2 命名规范异常

| slug | 问题 | 建议修正 |
|------|------|---------|
| `Azure-Virtual-Desktop` | 大写开头、驼峰 | `azure-virtual-desktop` |
| `Azure Spring Cloud` | 含空格、大写 | `azure-spring-cloud` |

---

## 二、可提取数据及迁移目标

### 2.1 服务 slug → 中文名映射

**来源**: 每个 `"slug": { Name: "中文名" }` 条目
**目标**: `product_catalog.json` 或新的中文名映射文件
**价值**: 直接复用为前端 UI 的产品中文显示名

**注意事项**:
- 部分 Name 中嵌入了区域限制文本（如 "仅适用于中国北部3"），需清洗分离
- 部分 Name 包含产品变体后缀（如 "存储 - 块 Blob - 常规用途v2"），需判断是否合并
- Storage 类产品有 54 个条目，按区域+存储类型+冗余级别细分，需要合理归并

**清洗规则**:
```
原始: "Azure Fluid Relay - 仅适用于中国北部3"
  → display_name: "Azure Fluid Relay"
  → region_constraint: ["chinanorth3"]

原始: "存储 - 块 Blob - 常规用途v2 - "热"和"冷"访问层 - 仅适用于中国东部2和中国北部2"
  → display_name: "存储 - 块 Blob - 常规用途v2 - 热/冷访问层"
  → region_constraint: ["chinaeast2", "chinanorth2"]
```

### 2.2 每产品 UI 维度结构

**来源**: `Types[].Name`, `Features[].Name`, `Sizes[]` 的排列关系
**目标**: 生成 `service_config` JSON 模板

**Types.Name 的 6 种语义模式**:

| 模式 | 代表产品 | 映射到本项目 |
|------|---------|-------------|
| A: Tier 层级 (基本/标准/高级) | redis-cache, service-bus, container-registry | `skuName` 维度 |
| B: "default" 单一类型 | traffic-manager, site-recovery, data-transfer | 无需 Type 维度 |
| C: 功能类别 | network-watcher (4种), azure-monitor (6种) | 需要 `per_meter` 的 Type 分组 |
| D: 部署/平台类型 | batch (Windows/Linux), ip-address (经典/ARM) | `productName` 或自定义维度 |
| E: SKU 名称 | search (S1/S2/S3), cognitive-services | `skuName` 维度 |
| F: 服务名即 Type | signalr-service, managed-grafana | 无需 Type 维度 |

**Features.Name 的 4 种语义模式**:

| 模式 | 代表产品 | 映射到本项目 |
|------|---------|-------------|
| A: "default" 单 Feature | redis-cache, power-bi-embedded | 标准 cascade（无 feature 选择） |
| B: 命名 Meter | service-bus, traffic-manager, azure-firewall | `per_meter` 模式，每个 Feature → 一个 meter 输入 |
| C: VM 系列 | hdinsight, machinelearning | Feature 名 → `skuName` 分组 |
| D: 区域/层级标注 | azure-firewall (含 Standard/Premium) | 需要分离注解和实际名称 |

### 2.3 区域可用性

**来源**: Name/Description 中 "仅适用于" / "仅支持" 文本
**目标**: service_config JSON 中的 `region_constraints` 字段

**区域文本 → 标准化映射**:

| 文本片段 | 标准化值 |
|---------|---------|
| 中国东部 / 中国东部1 | `chinaeast` |
| 中国东部2 | `chinaeast2` |
| 中国东部3 | `chinaeast3` |
| 中国北部 / 中国北部1 | `chinanorth` |
| 中国北部2 | `chinanorth2` |
| 中国北部3 | `chinanorth3` |

**区域标注出现位置（3 层）**:
1. **Service Name 层** — 79 个条目（Storage 54 个 + 非 Storage 25 个）
2. **Feature Name 层** — azure-firewall, hdinsight, machinelearning, cognitive-services 等
3. **Size Description 层** — hdinsight VM 规格描述等

### 2.4 已知价格（用于验证）

**来源**: `Sizes[].PricePerTier` 数值
**目标**: 生成自动化验证测试用例，对比本项目 CN CSV 导入的价格

**提取策略**: 对于 Fixed/Linear 定价，直接提取单价；对于阶梯定价，提取阶梯边界和每阶梯价格。

---

## 三、Types/Features/Sizes 层级到本项目模型的映射规则

### 3.1 映射对照表

| datamodel 层级 | 语义类型 | 本项目对应字段/概念 |
|---------------|---------|-------------------|
| Types.Name = Tier 名 | 产品层级 | cascade 维度 `skuName` 或 `sku_groups` |
| Types.Name = "default" | 无分层 | 无需额外维度 |
| Types.Name = 功能类别 | 多独立计费项 | `per_meter` 模式下的 meter 分组 |
| Features.Name = "default" | 单 meter | 标准 cascade |
| Features.Name = 命名 meter | 多 meter | `per_meter` 模式，每 Feature 映射为一个 meter 输入 |
| Features.Name = VM 系列 | VM 规格组 | `productName` 子维度 |
| Sizes[] = 多规格选择 | 规格/实例选择 | cascade 的 `skuName` 维度 |
| Sizes[] = 单 "default" | 无规格选择 | 无需额外维度 |
| PricePeriod = Hourly | 按小时定价 | `instances_x_hours` 或 `per_meter` hourly |
| PricePeriod = Monthly | 按月定价 | `per_meter` volume |
| PriceTier = Fixed | 固定单价 | `tierMinimumUnits = 0` 单行定价 |
| PriceTier = Linear | 线性 | 同 Fixed |
| PriceTier = Free | 免费 | `unitPrice = 0` |
| PriceTier = 阶梯字符串 | 阶梯定价 | 多行 `tierMinimumUnits` |

### 3.2 quantity_model 推导规则

```
IF Features 全部为 "default" 且 PricePeriod = Hourly:
    → instances_x_hours

ELIF Features 有多个命名 meter 或 PricePeriod 混合 Hourly/Monthly:
    → per_meter

ELIF Features 全部为 "default" 且 PricePeriod = Monthly:
    → 视具体情况: instances_x_hours (if Sizes > 1) or per_meter (if Sizes = 1)
```

### 3.3 dimension_labels / hidden_dimensions 推导规则

```
IF Types.Name 使用 Tier 名 (基本/标准/高级):
    → dimension_labels: { "skuName": "Tier" 或 "层级" }

IF productName 在本产品中只有一个唯一值:
    → hidden_dimensions: ["productName"]
```

---

## 四、迁移脚本设计方案

### 4.1 总体方案

编写 Python 脚本，解析 `calculatordatamodel.js` 和 `calculatorconst.js`，输出：

1. **`acn_product_names.json`** — slug → 中文名 + 区域约束的映射
2. **`acn_dimension_templates/`** — 每产品一个 JSON，描述 Types/Features/Sizes 结构
3. **`acn_price_validation.json`** — 已知价格数据，用于自动化测试

### 4.2 JS 解析策略

由于 `calculatordatamodel.js` 不是标准 JSON（包含 JS 变量引用、注释、尾逗号等），解析选项：

| 方案 | 优点 | 缺点 |
|------|------|------|
| **A: Node.js 直接执行** | 100% 准确，处理所有 JS 语法 | 需要 Node.js 环境 |
| **B: Python + demjson3/json5** | Python 生态内 | 不处理变量引用 (CalculatorConst) |
| **C: Python regex 提取** | 无外部依赖 | 脆弱，难以处理嵌套 |
| **D: Node.js 预处理 → JSON → Python 消费** | 准确 + Python 生态 | 两步流程 |

**推荐方案 D**:

```bash
# Step 1: Node.js 将 JS 对象转为 JSON
node -e "
  eval(require('fs').readFileSync('calculatorconst.js', 'utf8'));
  eval(require('fs').readFileSync('calculatordatamodel.js', 'utf8'));
  // CalculatorData 和 CalculatorConst 已在作用域中
  require('fs').writeFileSync('calculatordatamodel.json', JSON.stringify(CalculatorData, null, 2));
"

# Step 2: Python 脚本消费 JSON
python scripts/extract_acn_datamodel.py calculatordatamodel.json
```

### 4.3 输出格式

#### acn_product_names.json

```json
{
  "redis-cache": {
    "display_name": "Redis 缓存 - 用于 Redis 的 Azure 缓存",
    "display_name_clean": "Redis 缓存",
    "region_constraints": null
  },
  "azure-fluid-relay": {
    "display_name": "Azure Fluid Relay - 仅适用于中国北部3",
    "display_name_clean": "Azure Fluid Relay",
    "region_constraints": ["chinanorth3"]
  },
  "storage-general-purpose-v2-cold-hot-block-blob": {
    "display_name": "存储 - 块 Blob - 常规用途v2 - 热/冷访问层",
    "display_name_clean": "存储 - 块 Blob - 热/冷访问层",
    "region_constraints": ["chinaeast2", "chinanorth2"]
  }
}
```

#### acn_dimension_templates/redis-cache.json

```json
{
  "slug": "redis-cache",
  "display_name": "Redis 缓存",
  "types_semantic": "tier",
  "types": [
    {
      "name": "基本",
      "features_semantic": "default",
      "features": [{
        "name": "default",
        "price_period": "hourly",
        "sizes_count": 7,
        "sizes": [
          { "name": "C0", "description": "缓存大小 250 MB", "price_tier": "fixed", "price": "0.14" },
          { "name": "C1", "description": "缓存大小 1 GB", "price_tier": "fixed", "price": "0.35" }
        ]
      }]
    },
    {
      "name": "标准",
      "features_semantic": "default",
      "features": [{ "name": "default", "price_period": "hourly", "sizes_count": 7 }]
    },
    {
      "name": "高级",
      "features_semantic": "default",
      "features": [{ "name": "default", "price_period": "hourly", "sizes_count": 5 }]
    }
  ],
  "suggested_config": {
    "quantity_model": "instances_x_hours",
    "dimension_labels": { "skuName": "层级" },
    "hidden_dimensions": ["productName"]
  }
}
```

#### acn_price_validation.json

```json
{
  "redis-cache": {
    "currency": "CNY",
    "prices": [
      { "tier": "基本", "size": "C0", "period": "hourly", "price": 0.14, "unit": "per_instance" },
      { "tier": "基本", "size": "C1", "period": "hourly", "price": 0.35, "unit": "per_instance" }
    ]
  }
}
```

---

## 五、CalculatorConst 常量解析

### 5.1 常量分类

| 类别 | 示例 | 数量(约) | 用途 |
|------|------|---------|------|
| VM Size 名称 | `A0Size`→"A0", `D2v3Size`→"D2 v3" | ~150 | Sizes[].Name |
| VM Size 描述 | `A0SizeDesc`→"1个(共用)内核,0.75 GiB RAM" | ~150 | Sizes[].Description |
| App Service 名称 | `appservice_Basic_B1`→"B1" | ~30 | Sizes[].Name |
| App Service 描述 | `appservice_Premium_P1V2Desc`→"3.5 GB 内存" | ~20 | Sizes[].Description |
| MySQL Size | `mysqlMS1Size`→"MS 1" | ~10 | Sizes[].Name |
| Redis Cache Size | `C0Size`→"C0" | 7+7 | Sizes[].Name+Description |
| ExpressRoute 带宽 | `K50Size`→"50Mbps(A0)" | ~10 | Sizes[].Name |
| 数字常量 | `Number50`→"50" | ~20 | 各种数值引用 |
| 其他 | `HoursOneMonth`→744 | ~5 | 计算常量 |

### 5.2 解析策略

常量定义在 `calculatorconst.js` 中，格式为 `key: "value"` 对。Node.js 执行法可以直接解析所有引用。

**需要特别注意的**:
- 部分常量值本身包含中文（`BasicSize: "基本"`、`C0SizeDesc: "缓存大小 250 MB"`）
- `HoursOneMonth: 744` 是数字而非字符串
- 部分常量名在 datamodel 中以组合方式使用（如 `CalculatorConst.appservice_Premium_P1V2Desc`）

---

## 六、24 个重点产品的逐一映射方案

### 6.1 第一批：直接映射（当前架构支持）

#### redis-cache → instances_x_hours

```
datamodel: Types=[基本,标准,高级], Features=[default], Sizes=[C0-C6/P1-P5]
映射到: skuName=Tier选择, 规格通过cascade的skuName自动发现
config: { quantity_model: "instances_x_hours", dimension_labels: {"skuName":"Tier"} }
注意: ACN有3个Tier，Global API可能有5个Tier(含Enterprise/Enterprise Flash)
```

#### notification-hub → per_meter (带阶梯)

```
datamodel: Types=[免费,基本,标准], Features=[default], Sizes含阶梯定价
映射到: skuName=Tier选择, 阶梯通过tierMinimumUnits
config: { quantity_model: "per_meter", dimension_labels: {"skuName":"Tier"} }
```

#### signalr-service → per_meter (简单)

```
datamodel: Types=[标准], Features=[标准], Sizes=单一月费
映射到: 极简配置
config: { quantity_model: "per_meter" }
```

#### container-registry → per_meter (简单月费)

```
datamodel: Types=[基本,标准,高级], Features=[容器注册表-{tier}], Sizes=单一月费
映射到: skuName=Tier
config: { quantity_model: "per_meter", dimension_labels: {"skuName":"Tier"} }
注意: 额外有 container-registry-additional-storage-container-build 条目
```

#### azure-ddos-protection / azure-ddos-ipprotection → per_meter

```
datamodel: Types=[单一], Features=[月费+超额/每IP月费]
映射到: 极简per_meter
config: { quantity_model: "per_meter" }
```

#### managed-grafana → per_meter

```
datamodel: Types=[单一], Features=[实例,活跃用户,区域冗余]
映射到: 3个独立meter输入
config: { quantity_model: "per_meter" }
注意: 区域限制 "仅适用于中国北部3"
```

#### azure-fluid-relay → per_meter

```
datamodel: Types=[单一], Features=[操作输入,操作输出,客户端连接,存储]
映射到: 4个独立meter输入
config: { quantity_model: "per_meter" }
```

#### site-recovery → per_meter

```
datamodel: Types=[default], Features=[到客户站点, 到Azure]
映射到: 2个独立meter
config: { quantity_model: "per_meter" }
```

#### database-migration → instances_x_hours

```
datamodel: Types=[tier?], Features=[default], Sizes=实例规格
映射到: 标准instances_x_hours
config: { quantity_model: "instances_x_hours" }
```

### 6.2 第二批：per_meter 需细化

#### traffic-manager → per_meter

```
datamodel: Types=[default], Features=[DNS查询(阶梯), 健康检查Azure(线性), 快速间隔Azure(线性), 健康检查外部(线性), 快速间隔外部(线性)]
映射到: 5个独立meter, 其中DNS查询有阶梯
config: { quantity_model: "per_meter", hidden_dimensions: ["productName"] }
```

#### network-watcher → per_meter

```
datamodel: Types=[日志,诊断,连接监视,流量分析], Features=[default each]
映射到: 4个meter, 各有不同阶梯结构
config: { quantity_model: "per_meter" }
注意: Types在这里代表不同meter而非tier
```

#### ip-address → per_meter

```
datamodel: Types=[经典,ARM基本,ARM标准], Features=[动态IP,静态IP,IP重映射]
映射到: Types→productName或自定义维度, Features→meter
config: 需要 Types 作为选择维度 + 每Type的meter列表
挑战: 同一产品下Types代表部署模型而非Tier, 需要新的映射方式
```

#### load-balancer → per_meter

```
datamodel: Types=[标准-区局层,标准-全局层,网关], Features=[规则,超额规则,已处理数据]
映射到: Types→skuName, Features→meter
config: { quantity_model: "per_meter", dimension_labels: {"skuName":"类型"} }
挑战: "前5条规则=固定价"的特殊阶梯, 需要验证tier编码是否匹配
```

#### application-gateway-standard-v2 → per_meter

```
datamodel: Types=[固定,容量单位], Features=[default each]
映射到: 2个独立meter (网关时费 + 容量单位时费)
config: { quantity_model: "per_meter", hidden_dimensions: ["productName"] }
```

#### schedule → per_meter

```
datamodel: Types=[免费版,标准版,高级版], Features=[作业单位(阶梯)]
映射到: skuName=Tier + 用量输入
config: { quantity_model: "per_meter", dimension_labels: {"skuName":"版本"} }
```

### 6.3 第三批：需扩展能力

#### azure-front-door → per_meter + multi-type

```
datamodel: Types=[基本费用,出站Edge,出站源,请求定价], 每Type含标准/高级Feature
挑战: 需要先选标准/高级, 再显示对应meter
方案A: 将标准/高级映射为skuName, 4个Type的meter在同一视图显示
方案B: 新增 "sub-type" 概念
推荐: 方案A, 用sku_groups合并
```

#### hdinsight → multi-component

```
datamodel: Types=[default], Features=[VM系列名], Sizes=[VM规格]
挑战: 完整HDInsight需要Head+Worker+Zookeeper多角色, 各自选VM规格和数量
方案: MVP先用instances_x_hours, 后续实现multi_component
```

#### azure-iot-hub + azure-iot-hub-dps → linked services

```
datamodel: 两个独立条目, IoT Hub有Tier选择, DPS按操作数
方案: 分两张estimate card, 后续可实现linked_services自动关联
```

#### container-registry + additional-storage → linked services

```
datamodel: 两个独立条目
方案: 同 IoT Hub, 分两张card
```

#### active-directory-b2c → 复杂多功能

```
datamodel: Types=[MFA(免费/标准), 电话因素, 短信因素, 第三方因素, ...], Features按MAU分层
挑战: 非常复杂的多层级定价, 含免费层+阶梯+按功能分拆
方案: 后续迭代, 需要专门的定价模型设计
```

---

## 七、迁移执行计划

### Phase 1: 提取工具（1-2天）

1. Node.js 脚本: `calculatordatamodel.js` + `calculatorconst.js` → `calculatordatamodel.json`
2. Python 脚本: JSON → 三个输出文件
3. 验证: 确保所有 260 个条目正确提取

### Phase 2: 中文名整合（0.5天）

1. 将 `acn_product_names.json` 中的 clean name 合并到 `product_catalog.json`
2. 对24个重点产品优先处理
3. 处理 slug 命名规范问题

### Phase 3: 配置模板生成（1天）

1. 对第一批（~10个产品）生成 service_config JSON
2. 对每个产品验证: 模板生成 → 与 Global API 数据对比 → 调整配置
3. 用 `acn_price_validation.json` 交叉验证价格

### Phase 4: 价格验证框架（1天）

1. 从 datamodel 提取的 CNY 价格 vs CN CSV 导入的价格
2. 生成差异报告（价格变动、新增产品、下线产品）
3. 建立持续验证机制
