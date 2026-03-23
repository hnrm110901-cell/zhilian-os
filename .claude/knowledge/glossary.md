# 连锁餐饮行业术语表

> 更新于 2026-03-22 | 屯象OS专用术语 + 行业通用术语

---

## A

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 安全库存 | Safety Stock | 防止断供的最低库存量，通常为 1-3 天用量 | InventoryAgent 预警阈值 |
| 暗厨 | Dark Kitchen | 仅做外卖、无堂食的厨房 | 暂不支持 |

## B

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| BOM | Bill of Materials | 物料清单，记录一道菜需要的所有食材及用量 | models/bom.py |
| 包厢 | Private Room | 独立用餐空间，通常有最低消费 | BanquetAgent |
| 备餐量 | Prep Quantity | 根据预估客流提前准备的食材量 | ScheduleAgent + InventoryAgent |
| 爆品 | Hero Item | 点击率/毛利最高的招牌菜 | menu_ranker service |

## C

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 翻台率 | Table Turnover | 每张桌子每天的使用次数 | KPI 核心指标 |
| 坪效 | Revenue per sqm | 每平方米产生的营收 | PerformanceAgent |
| 人效 | Revenue per Staff | 每人产生的营收 | PerformanceAgent |
| 客单价 | Average Ticket | 每桌/每人平均消费金额 | OrderAgent |
| 成本率 | Cost Ratio | 某成本占营收的百分比(食材率/人力率) | CostTruth model |

## D

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 动销率 | Sell-through Rate | 有销售记录的 SKU 占全部 SKU 的比例 | 菜品优化指标 |
| 到店率 | Store Visit Rate | 线上曝光到实际到店的转化率 | 私域运营指标 |

## F

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 分 | Fen/Cent | 金额最小单位(1元=100分)，DB存储单位 | 全局约定：DB存分，API返回元 |

## G

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 沽清/86 | 86'd (sold out) | 某菜品售罄，厨房通知前厅停售 | OrderAgent 菜品状态 |
| 毛利率 | Gross Margin | (营收-食材成本)/营收 ×100% | FCTAgent |

## H

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 后厨动线 | Kitchen Flow | 食材从入库到出品的物理路线 | QualityAgent |
| 回头客率 | Repeat Rate | 30天内再次消费的顾客比例 | PrivateDomainAgent RFM |

## J

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 净料率 | Yield Rate | 原料去除废料后可用部分的比例 | 损耗计算核心参数 |
| 加工损耗 | Processing Loss | 初加工(切配)过程中的食材损失 | WasteEvent model |

## K

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 客流量 | Traffic | 一定时间内到店消费的顾客数 | 预测模型输入 |
| 扣点 | Commission Rate | 外卖平台从订单中抽取的比例(15-23%) | 外卖利润计算 |

## L

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 留样 | Food Sample Retention | 每餐留样125g/48h，食安法规要求 | ComplianceAgent |
| 流失客 | Churned Customer | 90天以上未消费的顾客 | PrivateDomainAgent S5 |

## M

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 明档 | Open Kitchen Display | 顾客可见的厨房操作区 | 前厅体验 |
| 满减 | Discount Threshold | 外卖平台"满X减Y"促销 | 营销ROI计算 |

## P

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 排队等位 | Queue/Waitlist | 满座时顾客等待空桌 | ReservationAgent |
| POS | Point of Sale | 收银/点餐系统 | api-adapters 6个适配器 |

## Q

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 前厅后厨比 | FOH:BOH Ratio | 前厅与后厨人员配比，通常 1:1 到 1.2:1 | ScheduleAgent |

## R

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| RFM | Recency/Frequency/Monetary | 客户价值分层模型 | PrivateDomainAgent 核心 |
| 日结 | Daily Closing | 每日营业结束后的对账和盘点 | OpsAgent 日结流程 |

## S

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 三大成本 | Three Major Costs | 食材+人力+租金，合计占营收 60-70% | 成本控制核心 |
| 上座率 | Occupancy Rate | 已使用座位/总座位 ×100% | 实时运营指标 |
| 时段系数 | Period Multiplier | 不同时段的客流权重(午市0.4/晚市0.5) | 排班模型 |
| 损耗率 | Waste Rate | 损耗金额/营业收入 ×100% | WasteEvent + CostTruth |

## T

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 退菜率 | Return Rate | 退菜次数/总出品次数，反映出品质量 | QualityAgent 指标 |
| 堂食 | Dine-in | 到店用餐（区别于外卖/自提） | OrderAgent 订单来源 |

## W

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 万元用工成本 | Labor Cost per ¥10K Revenue | 每万元营收需要的人力成本 | 人效衡量指标 |

## X

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 先进先出 | FIFO | 先入库的食材先使用，防止过期 | InventoryAgent 存储策略 |

## Y

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 验收标准 | Receiving Standard | 食材到货时的品质/重量/温度检查标准 | SupplierAgent |

## Z

| 术语 | 英文 | 定义 | 屯象OS关联 |
|------|------|------|-----------|
| 中央厨房 | Central Kitchen | 统一加工配送的集中厨房 | 连锁标准化核心设施 |
| 自提 | Pickup | 顾客线上下单到店取餐 | OrderAgent 订单来源 |

---

## 屯象OS 专有术语

| 术语 | 定义 |
|------|------|
| StoreMemory | 门店运营记忆，记录峰值模式/异常模式/历史快照 |
| CostTruth | 成本真相引擎，每日快照对比理论成本vs实际成本 |
| NeuralEvent | 事件溯源日志，记录所有 Agent 决策和系统事件 |
| BFF | Backend For Frontend，按角色聚合的后端接口 |
| Z组件 | 屯象设计系统的基础UI组件（ZCard/ZKpi/ZBadge等） |

---

*下次建议更新：2026-06-22（随新术语出现持续更新）*
