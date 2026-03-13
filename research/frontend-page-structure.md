# Azure Pricing Calculator 前端页面结构调研

基于 Azure Global Pricing Calculator 生产环境页面的分析，梳理页面构成、交互逻辑及实施方案。

---

## 一、页面总体结构

页面自上而下分为三大区域：

| 区域 | 说明 |
|------|------|
| 导航区 | 标题栏 + Tab 栏 + 搜索栏 + 产品目录 |
| 估算区 | 一个或多个估算卡片，每张对应一个被添加的服务 |
| 汇总区 | 所有估算项的总费用汇总（待后续调研） |

---

## 二、导航区

### 2.1 页面标题栏
- 标题 + 副标题 slogan
- 我们简化为 Azure.cn 品牌 + 中文标题即可

### 2.2 功能 Tab 栏
- 原版四个 Tab：Products / Estimate templates / Saved estimates / FAQs
- MVP 仅实现 **Products** Tab，其余后续扩展

### 2.3 产品搜索栏
- 全宽搜索框，支持模糊搜索
- 搜索是全局的，不受左侧分类筛选影响
- 搜索结果替代右侧卡片区域；清空搜索框后恢复当前分类视图
- 对应后端 `GET /api/v1/products/search`

### 2.4 产品目录区（左侧分类 + 右侧产品卡片网格）

**左侧：Service Family 分类列表**
- 竖向排列的分类（Popular / Compute / Networking / Storage ...）
- 单选排他，默认选中 "Popular"
- 数据来源：`product_catalog.json` 中的 `families[]`

**右侧：产品卡片网格（3列）**
- 每张卡片：产品图标 + 产品名称 + 简短描述 + "Add to estimate" 按钮
- 选中 "Popular" 时展示 `popular: true` 的产品；选中具体 family 时展示该 family 下的 services
- 数据来源：`product_catalog.json`

---

## 三、产品目录配置文件

### 3.1 文件位置
`app/config/product_catalog.json`

### 3.2 结构设计

```jsonc
{
  "families": [
    {
      "key": "compute",
      "label": "Compute",
      "order": 1,
      "services": [
        {
          "service_name": "Virtual Machines",
          "description": "Provision Windows and Linux VMs in seconds",
          "icon": "virtual-machines",
          "popular": true
        },
        {
          "service_name": "App Service",
          "description": "Quickly create powerful cloud apps for web and mobile",
          "icon": "app-service",
          "popular": true
        }
      ]
    },
    {
      "key": "networking",
      "label": "Networking",
      "order": 2,
      "services": [ ]
    }
  ]
}
```

### 3.3 设计要点
- **两层结构**：family → services，扁平清晰
- `service_name` 必须与价格 API 中的 serviceName 精确一致，是串联产品目录与后续 cascade 接口的关键
- `popular: true` 标记热门产品，前端筛选组装 Popular 列表
- `icon` 为字符串 ID（如 `"virtual-machines"`），前端维护图标映射
- `order` 控制排列顺序

### 3.4 初始化方式
- 编写一次性脚本，调用 Global Retail Prices API 扫描所有 serviceFamily 和 serviceName 的组合，生成初始 JSON 骨架
- 人工补充 description、icon、popular 标记并审核

### 3.5 与 service_configs 的关系
```
product_catalog.json    → 全局产品目录（导航区用）
service_configs/*.json  → 单个服务的配置细节（估算区配置面板用）
```
两者职责分离，通过 `service_name` 字段关联。

---

## 四、估算区

### 4.1 估算卡片结构（以 Virtual Machines 为例）

从上到下分为以下层次：

#### (1) 顶部摘要栏（折叠态头部）
```
▲ Virtual Machines | ⓘ | 1 D2 v3 (2 vCPUs, 8GB RAM) x 730 Hours (Pay as... | 📋 🗑 | Upfront: $0.00 | Monthly: $70.08
```
- 展示：服务名 + 当前配置摘要 + 复制/删除按钮 + 价格
- 整个估算卡片可折叠，折叠后只显示此行
- 纯前端状态

#### (2) 配置区 — 主维度下拉框（第一行）
| Region | Operating System | Type | Tier |
|--------|-----------------|------|------|
| East US | Linux | Ubuntu | Standard |

- Region 为主级联维度（armRegionName）
- OS / Type / Tier 为 VM 的 productName 子维度
- 视觉上与 Region 平级排列，但逻辑上是子维度

#### (3) 配置区 — 筛选 + Instance 选择器（第二行）
| Category | Instance Series | INSTANCE（可搜索下拉）|
|----------|----------------|---------------------|
| All | All | D2 v3: 2 vCPUs, 8 GB RAM, 50 GB... $0.096/hour |

- Category 和 Instance Series 为子维度
- **INSTANCE 是核心控件**：可搜索的下拉框，展示规格摘要 + 单价
- Instance 规格信息（vCPU/RAM/存储）不在价格 API 中，需额外数据源（待后续研究）
- MVP 阶段 Instance 下拉先展示 SKU 名称 + 单价，不含详细规格

#### (4) 数量输入
```
[1] Virtual machines  ×  [730] [Hours ▾]
```
- 输入控件随定价模式切换：

| 定价模式 | 输入控件 |
|---------|---------|
| PAYG (Consumption) | `[实例数] × [时长] [Hours▾]` |
| Savings Plan | `[实例数]` |
| Reservation | `[实例数]` |

- 时长单位可选 Hours/Days/Months，前端统一换算为 hours
- 对应后端 `CalculatorItem.quantity` 和 `hours_per_month`

#### (5) Savings Options（定价模式选择）
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
- 单选互斥：PAYG / Savings Plan / Reservation
- 默认选中 PAYG
- 折扣百分比动态计算：`1 - (SP_or_RI_price / PAYG_price)`
- 前端从本地缓存的 meter 数据直接计算，无需调 API

#### (6) 价格展示
- 左侧：当前 meter（如 Compute）的费用
- 右侧：该估算项总计
- 区分 Upfront cost 和 Monthly cost

#### (7) 附加关联服务（折叠区）
```
▽ Managed Disks         $0.00
▽ Storage transactions  $0.00
▽ Bandwidth             $0.00
```
- VM 的关联服务，默认折叠且费用 $0.00
- 展开后各自有独立的配置面板
- 每个关联服务本质是一个独立的「小估算项」，有自己的级联配置和计算逻辑
- 配置在 `service_configs/virtual_machines.json` 的 `related_services` 中人工维护

#### (8) 底部汇总
```
Upfront cost:  $0.00
Monthly cost:  $70.08
```

---

## 五、前端计算架构：两阶段模型

### 5.1 阶段一：API 筛选（需要调后端）

级联维度选择时调用 API：
```
Region → OS → Tier → Category → Series → Instance
```
每次切换维度，调 `POST /cascade` 获取更新后的选项列表。

### 5.2 阶段二：本地计算（不调后端）

Instance 确定后，数量/时长/定价模式的变更全部在前端本地完成：
- 切换 PAYG / SP / RI → 本地切换 meter 数据集并重算
- 改数量 / 时长 → 本地重算
- 折扣百分比 → 本地对比计算

### 5.3 数据流

```
用户切换维度选项      →  POST /cascade（级联筛选，更新选项）
用户选定 Instance    →  POST /meters（一次性拉取所有 type/term 的 meter 数据，前端缓存）
用户改数量/切换定价   →  前端本地计算（从缓存的 meter 数据计算价格）
用户导出/查看汇总     →  POST /calculator（服务端批量验证计算）
```

### 5.4 为什么这样设计
- 一个 VM 实例的所有 meter 数据量很小（Consumption + 1yr/3yr RI + 1yr/3yr SP，约 3~5 个 meter，十几行数据）
- 前端缓存后，切换定价模式、改数量时可即时更新价格，体验丝滑
- `/calculator` 定位为**服务端验证 + 批量计算**，用于最终汇总和导出，而非实时交互

### 5.5 前端需要实现的计算逻辑
- 阶梯定价计算（与后端 `calculate_tiered_cost` 相同算法的 JS 版本）
- 折扣百分比计算：`discount = 1 - (selected_price / payg_price)`
- 时长单位换算（Hours / Days / Months → hours）

---

## 六、"Add to estimate" 交互流程

用户在导航区点击 "Add to estimate" 后，不是看到空白配置面板，而是一个**已填好默认值、算好价格的完整估算卡片**。

### 6.1 完整流程

```
用户点击 "Add to estimate"
  │
  ├─ 1. 读取该服务的默认配置（service_configs/*.json）
  │     Region / OS / Tier / Category / Series 等默认值
  │
  ├─ 2. POST /cascade（带默认 selections + sub_selections）
  │     → 返回各维度选项列表
  │
  ├─ 3. 自动选中配置文件指定的默认 Instance
  │
  ├─ 4. POST /meters（拉取该 Instance 全部 meter 数据）
  │     → 前端缓存，本地计算出 PAYG 默认价格
  │
  └─ 5. 渲染完整的估算卡片，用户看到即是可用状态
```

### 6.2 默认值配置（service_configs 扩展）

```jsonc
{
  "service_name": "Virtual Machines",
  "defaults": {
    "region": "China North 3",
    "hours_per_month": 730,
    "quantity": 1,
    "type": "Consumption",
    "default_instance": "D2 v3"
  },
  "sub_dimensions": {
    "dimensions": [
      { "field": "os", "default": "Linux" },
      { "field": "deployment", "default": "Virtual Machines" },
      { "field": "tier", "default": "Standard" },
      { "field": "category", "default": null },
      { "field": "instance_series", "default": null }
    ]
  },
  "related_services": [
    {
      "key": "managed_disks",
      "label": "Managed Disks",
      "service_name": "Storage",
      "default_collapsed": true,
      "default_quantity": 0
    },
    {
      "key": "storage_transactions",
      "label": "Storage transactions",
      "service_name": "Storage",
      "default_collapsed": true,
      "default_quantity": 0
    },
    {
      "key": "bandwidth",
      "label": "Bandwidth",
      "service_name": "Bandwidth",
      "default_collapsed": true,
      "default_quantity": 0
    }
  ]
}
```

- `default: null` 表示 "All"（不过滤）
- `default_instance` 指定默认选中的实例（方案 A）
- `region` 对 Azure.cn 版本应默认为国内区域

---

## 七、待后续研究

| 事项 | 说明 |
|------|------|
| Instance 规格数据 | vCPU/RAM/存储等结构化数据不在价格 API 中，需研究 Azure Resource SKUs API 或维护规格表 |
| 汇总区 | 页面底部的多估算项总费用汇总区域，待调研 |
| 多估算项交互 | 多个估算卡片之间的排序、复制、删除等交互细节 |
| 导出功能 | Excel 导出的具体内容和格式 |
| 搜索实现 | 产品搜索的具体匹配策略和结果展示方式 |
