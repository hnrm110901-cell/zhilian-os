# 屯象OS 连锁餐饮行业数据字典 v1.0

> 最后更新: 2026-03-12
> 适用范围: 中国连锁餐饮（中餐正餐/快餐/火锅/烘焙/茶饮）
> 金额单位约定: 数据库存储=分(fen)，API输出=元(yuan, 2位小数)

---

## 目录

1. [组织与门店](#1-组织与门店)
2. [菜品与配方(BOM)](#2-菜品与配方bom)
3. [食材与库存](#3-食材与库存)
4. [采购与供应商](#4-采购与供应商)
5. [销售与订单](#5-销售与订单)
6. [损耗与报废](#6-损耗与报废)
7. [人力与排班](#7-人力与排班)
8. [财务与成本](#8-财务与成本)
9. [会员与顾客](#9-会员与顾客)
10. [预订与宴会](#10-预订与宴会)
11. [渠道与平台](#11-渠道与平台)
12. [决策与推送](#12-决策与推送)
13. [价格基准网络](#13-价格基准网络)
14. [枚举值字典](#14-枚举值字典)
15. [行业基准参数](#15-行业基准参数)
16. [数据采集频率规范](#16-数据采集频率规范)

---

## 1. 组织与门店

### 1.1 集团 (groups)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| group_id | varchar(50) PK | Y | 集团编码 | `GRP001` |
| group_name | varchar(200) | Y | 集团名称 | `湘味集团` |
| legal_entity | varchar(200) | Y | 法人主体 | `湖南湘味餐饮管理有限公司` |
| unified_social_credit_code | varchar(18) | Y | 统一社会信用代码 | `91430100MA4L...` |
| industry_type | varchar(30) | Y | 业态 | 见枚举 [industry_type](#141-industry_type-业态) |
| contact_person | varchar(50) | Y | 联系人 | `张总` |
| contact_phone | varchar(20) | Y | 联系电话 | `138xxxx0001` |
| address | text | N | 注册地址 | |
| created_at | timestamptz | Y | 创建时间 | |

### 1.2 品牌 (brands)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| brand_id | varchar(50) PK | Y | 品牌编码 | `BRAND01` |
| group_id | varchar(50) FK | Y | 所属集团 | `GRP001` |
| brand_name | varchar(100) | Y | 品牌名 | `湘菜大王` |
| cuisine_type | varchar(30) | Y | 菜系 | 见枚举 [cuisine_type](#142-cuisine_type-菜系) |
| avg_ticket_yuan | numeric(10,2) | N | 品牌客单价基准(元) | `68.00` |
| target_food_cost_pct | numeric(5,2) | Y | 目标食材成本率(%) | `32.00` |
| target_labor_cost_pct | numeric(5,2) | Y | 目标人力成本率(%) | `25.00` |
| target_rent_cost_pct | numeric(5,2) | N | 目标租金成本率(%) | `10.00` |
| target_waste_pct | numeric(5,2) | Y | 目标损耗率(%) | `3.00` |
| logo_url | text | N | 品牌LOGO | |
| status | varchar(20) | Y | 状态 | active/inactive |
| created_at | timestamptz | Y | | |

### 1.3 门店 (stores)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| store_id | varchar(50) PK | Y | 门店编码 | `STORE001` |
| brand_id | varchar(50) FK | Y | 所属品牌 | `BRAND01` |
| store_name | varchar(100) | Y | 门店名称 | `湘菜大王·万象城店` |
| store_code | varchar(20) UQ | Y | 门店简码 | `WXC01` |
| store_type | varchar(30) | Y | 门店类型 | 见枚举 [store_type](#143-store_type-门店类型) |
| status | varchar(20) | Y | 经营状态 | active/inactive/renovating/preparing/closed |
| city | varchar(50) | Y | 城市 | `上海` |
| district | varchar(50) | N | 区 | `浦东新区` |
| address | text | Y | 详细地址 | `世纪大道1号万象城B1层` |
| latitude | float | N | 纬度 | `31.2304` |
| longitude | float | N | 经度 | `121.4737` |
| area_sqm | numeric(8,2) | Y | 面积(平米) | `280.00` |
| seats | integer | Y | 座位数 | `120` |
| floors | integer | N | 楼层数 | `1` |
| private_rooms | integer | N | 包间数 | `3` |
| opening_date | date | Y | 开业日期 | `2024-06-15` |
| business_hours | jsonb | Y | 营业时间 | `{"mon-fri":"10:00-22:00","sat-sun":"09:30-22:30"}` |
| manager_id | varchar(50) FK | N | 店长 | `EMP001` |
| manager_phone | varchar(20) | N | 店长电话 | |
| monthly_revenue_target | integer | Y | 月营收目标(分) | `50000000` (50万元) |
| daily_customer_target | integer | N | 日客流目标(人次) | `300` |
| cost_ratio_target | numeric(5,2) | Y | 目标综合成本率(%) | `65.00` |
| labor_cost_ratio_target | numeric(5,2) | Y | 目标人力成本率(%) | `25.00` |
| rent_monthly_yuan | numeric(12,2) | N | 月租金(元) | `35000.00` |
| pos_system | varchar(50) | N | POS品牌 | 见枚举 [pos_system](#1414-pos_system-pos系统) |
| pos_store_code | varchar(50) | N | POS中的门店编码 | |
| wechat_corp_id | varchar(50) | N | 企微corpId | |

### 1.4 区域 (regions)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| region_id | varchar(50) PK | Y | 区域编码 | `REGION_EAST` |
| brand_id | varchar(50) FK | Y | 所属品牌 | |
| region_name | varchar(100) | Y | 区域名称 | `华东区` |
| supervisor_id | varchar(50) FK | N | 区域督导 | `EMP050` |
| store_ids | varchar[] | N | 下辖门店 | `{STORE001,STORE002}` |

---

## 2. 菜品与配方(BOM)

### 2.1 食材主档 (ingredient_masters)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| ingredient_id | varchar(50) PK | Y | 食材统一编码 | `ING_LY_001` |
| canonical_name | varchar(100) | Y | 标准名称 | `鲈鱼` |
| aliases | varchar[] | N | 别名 | `{海鲈鱼,花鲈,七星鲈}` |
| category | varchar(30) | Y | 大类 | 见枚举 [ingredient_category](#144-ingredient_category-食材分类) |
| sub_category | varchar(30) | N | 小类 | `淡水鱼` |
| base_unit | varchar(10) | Y | 基本计量单位 | `kg` |
| spec_desc | varchar(100) | N | 规格描述 | `鲜活, 500-700g/条` |
| shelf_life_days | integer | N | 保质期(天) | `2` |
| storage_type | varchar(20) | Y | 存储方式 | 见枚举 [storage_type](#145-storage_type-存储方式) |
| storage_temp_min | numeric(5,1) | N | 最低存储温度(℃) | `0.0` |
| storage_temp_max | numeric(5,1) | N | 最高存储温度(℃) | `4.0` |
| is_traceable | boolean | Y | 是否需要溯源 | `true` (肉类/水产) |
| allergen_tags | varchar[] | N | 过敏原标签 | `{鱼类}` |
| seasonality | varchar[] | N | 旺季月份 | `{3,4,5,9,10}` |
| typical_waste_pct | numeric(5,2) | N | 行业典型损耗率(%) | `8.00` |
| typical_yield_rate | numeric(5,4) | N | 行业典型出成率 | `0.6500` (65%) |
| is_active | boolean | Y | 是否启用 | `true` |

### 2.2 菜品分类 (dish_categories)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| category_id | uuid PK | Y | 分类ID | |
| brand_id | varchar(50) FK | Y | 所属品牌 | |
| name | varchar(50) | Y | 分类名 | `招牌菜` |
| sort_order | integer | Y | 排序 | `1` |
| display_type | varchar(20) | N | 显示方式 | normal/featured/hidden |
| parent_id | uuid FK | N | 父分类(二级分类用) | |

### 2.3 菜品主档 (dish_masters)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| dish_master_id | uuid PK | Y | 集团SKU ID | |
| sku_code | varchar(30) UQ | Y | SKU编码 | `SKU_SCY_001` |
| canonical_name | varchar(100) | Y | 标准菜名 | `酸菜鱼` |
| brand_id | varchar(50) FK | N | null=集团通用 | |
| category_id | uuid FK | Y | 菜品分类 | |
| cuisine_type | varchar(30) | N | 菜系 | `川菜` |
| cooking_method | varchar(30) | N | 烹饪方式 | 见枚举 [cooking_method](#146-cooking_method-烹饪方式) |
| spicy_level | integer | N | 辣度(0-5) | `3` |
| serving_size_g | integer | N | 标准出品克重(g) | `800` |
| preparation_time_min | integer | N | 标准出餐时间(分钟) | `15` |
| kitchen_station | varchar(30) | N | 出品档口 | 见枚举 [kitchen_station](#147-kitchen_station-档口) |
| floor_price_fen | integer | N | 最低售价(分) | `4800` (48元) |
| suggested_price_fen | integer | N | 建议零售价(分) | `6800` |
| allergens | varchar[] | N | 过敏原 | `{鱼类,大豆}` |
| calories_kcal | integer | N | 热量(kcal) | `520` |
| protein_g | numeric(6,1) | N | 蛋白质(g) | `38.5` |
| fat_g | numeric(6,1) | N | 脂肪(g) | `22.0` |
| carb_g | numeric(6,1) | N | 碳水(g) | `15.0` |
| tags | varchar[] | N | 标签 | `{招牌,必点,辣}` |
| photo_url | text | N | 菜品图片 | |
| description | text | N | 菜品描述 | |
| lifecycle_status | varchar(20) | Y | 生命周期 | 见枚举 [dish_lifecycle](#148-dish_lifecycle-菜品生命周期) |
| launch_date | date | N | 上架日期 | |
| sunset_date | date | N | 计划下架日期 | |

### 2.4 品牌菜单定价 (brand_menus)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | | |
| brand_id | varchar(50) FK | Y | 品牌 | |
| dish_master_id | uuid FK | Y | SKU | |
| price_fen | integer | N | null=继承主档价 | `6800` |
| is_available | boolean | Y | 是否上架 | `true` |
| sort_order | integer | N | 菜单排序 | `10` |
| **UQ约束** | | | `(brand_id, dish_master_id)` | |

### 2.5 门店菜单定价 (store_menus)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | | |
| store_id | varchar(50) FK | Y | 门店 | |
| dish_master_id | uuid FK | Y | SKU | |
| price_fen | integer | N | null=继承品牌层 | `7200` (72元,商圈溢价) |
| is_available | boolean | Y | 是否上架 | `true` |
| **UQ约束** | | | `(store_id, dish_master_id)` | |

> **价格解析规则**: store_menus.price_fen ?? brand_menus.price_fen ?? dish_masters.suggested_price_fen

### 2.6 BOM配方模板 (bom_templates)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| bom_id | uuid PK | Y | 配方ID | |
| dish_master_id | uuid FK | Y | 对应SKU | |
| scope | varchar(20) | Y | 作用域 | group/brand/region/store |
| scope_id | varchar(50) | Y | 作用域ID | `STORE001` |
| channel | varchar(20) | Y | 渠道 | dine_in/takeout/all |
| version | varchar(20) | Y | 版本号 | `v3` |
| parent_bom_id | uuid FK | N | 父级BOM(差异化用) | |
| is_delta | boolean | Y | 是否差异BOM | `false` |
| effective_date | date | Y | 生效日期 | `2026-03-01` |
| expiry_date | date | N | 失效日期(null=永久) | |
| yield_rate | numeric(5,4) | Y | 出成率 | `0.6500` |
| standard_portion_g | numeric(8,3) | Y | 标准出品克重(g) | `800.000` |
| total_cost_fen | integer | N | 理论总成本(分, 计算字段) | `2850` |
| prep_time_minutes | integer | N | 备料时长(分钟) | `20` |
| is_active | boolean | Y | 是否启用 | `true` |
| is_approved | boolean | Y | 是否审批通过 | `true` |
| approved_by | varchar(50) | N | 审批人 | |
| approved_at | timestamptz | N | 审批时间 | |
| notes | text | N | 配方备注 | |
| **UQ约束** | | | `(dish_master_id, scope, scope_id, channel, version)` | |

### 2.7 BOM配方明细 (bom_items)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | 行ID | |
| bom_id | uuid FK | Y | 所属配方 | |
| ingredient_id | varchar(50) FK | Y | 食材 | `ING_LY_001` |
| item_action | varchar(10) | Y | 操作(差异BOM) | ADD/OVERRIDE/REMOVE |
| standard_qty | numeric(10,4) | Y | 净用量(基本单位) | `0.3500` (350g鱼肉) |
| raw_qty | numeric(10,4) | N | 毛用量(含损耗) | `0.5400` (540g整鱼) |
| unit | varchar(10) | Y | 单位 | `kg` |
| unit_cost_fen | integer | N | 成本快照(分/单位) | `1800` (18元/kg) |
| waste_factor | numeric(5,4) | N | 损耗系数 | `0.3500` (35%边角料) |
| is_key_ingredient | boolean | Y | 是否关键食材 | `true` |
| prep_notes | text | N | 加工说明 | `去鳞去内脏,片鱼片0.5cm厚` |
| substitutes | jsonb | N | 可替代食材 | `[{"id":"ING_GY_001","name":"桂鱼","ratio":1.0}]` |

---

## 3. 食材与库存

### 3.1 门店库存 (inventory_items)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| item_id | varchar(50) PK | Y | 库存编码 | `INV_001` |
| store_id | varchar(50) FK | Y | 门店 | |
| ingredient_id | varchar(50) FK | Y | 关联食材主档 | `ING_LY_001` |
| name | varchar(100) | Y | 显示名(可能含规格) | `鲈鱼(鲜活 500-700g)` |
| category | varchar(30) | Y | 分类 | seafood |
| unit | varchar(20) | Y | 计量单位 | `kg` |
| current_quantity | numeric(12,4) | Y | 当前库存量 | `25.5000` |
| min_quantity | numeric(12,4) | Y | 安全库存(低于触发预警) | `10.0000` |
| max_quantity | numeric(12,4) | N | 最大库存(防过量采购) | `50.0000` |
| reorder_point | numeric(12,4) | N | 补货点 | `15.0000` |
| reorder_qty | numeric(12,4) | N | 建议补货量 | `20.0000` |
| unit_cost_fen | integer | Y | 最近入库单价(分/单位) | `1800` |
| avg_cost_fen | integer | N | 加权平均成本(分/单位) | `1750` |
| last_purchase_date | date | N | 最近采购日期 | `2026-03-11` |
| last_count_date | date | N | 最近盘点日期 | `2026-03-10` |
| supplier_id | varchar(50) FK | N | 主供应商 | `SUP001` |
| status | varchar(20) | Y | 状态 | normal/low/critical/out_of_stock |
| storage_location | varchar(50) | N | 存放位置 | `冷库A-02` |

### 3.2 库存批次 (inventory_batches)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| batch_id | uuid PK | Y | 批次ID | |
| item_id | varchar(50) FK | Y | 库存项 | `INV_001` |
| store_id | varchar(50) FK | Y | 门店 | |
| purchase_order_id | varchar(50) FK | N | 关联采购单 | `PO20260311001` |
| supplier_id | varchar(50) FK | N | 供应商 | |
| batch_no | varchar(50) | N | 供应商批次号 | `SH20260311-A` |
| received_date | date | Y | 入库日期 | `2026-03-11` |
| production_date | date | N | 生产日期 | `2026-03-11` |
| expiry_date | date | N | 保质期截止 | `2026-03-13` |
| received_qty | numeric(12,4) | Y | 入库数量 | `30.0000` |
| remaining_qty | numeric(12,4) | Y | 剩余数量 | `25.5000` |
| unit_cost_fen | integer | Y | 该批次单价(分) | `1800` |
| quality_grade | varchar(10) | N | 质检等级 | A/B/C |
| inspection_result | varchar(20) | N | 验收结果 | passed/partial_reject/full_reject |
| inspection_notes | text | N | 验收备注 | `鲜度合格，2条规格偏小` |
| status | varchar(20) | Y | 批次状态 | active/depleted/expired/recalled |

### 3.3 库存流水 (inventory_transactions)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | 流水ID | |
| store_id | varchar(50) FK | Y | 门店 | |
| item_id | varchar(50) FK | Y | 库存项 | |
| batch_id | uuid FK | N | 批次(有追溯需求时) | |
| transaction_type | varchar(20) | Y | 类型 | 见枚举 [inv_txn_type](#149-inv_txn_type-库存流水类型) |
| quantity | numeric(12,4) | Y | 数量(正=入库,负=出库) | `-2.5000` |
| unit_cost_fen | integer | N | 本次单价(分) | `1800` |
| total_cost_fen | integer | N | 本次金额(分) | `-4500` |
| quantity_before | numeric(12,4) | N | 操作前库存 | `28.0000` |
| quantity_after | numeric(12,4) | N | 操作后库存 | `25.5000` |
| reference_type | varchar(30) | N | 关联单据类型 | order/purchase_order/waste_event/transfer/count |
| reference_id | varchar(100) | N | 关联单据号 | `PO20260311001` |
| performed_by | varchar(50) | N | 操作人 | `EMP003` |
| transaction_time | timestamptz | Y | 操作时间 | |
| notes | text | N | 备注 | `午市备料出库` |

### 3.4 盘点记录 (inventory_counts)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| count_id | uuid PK | Y | 盘点ID | |
| store_id | varchar(50) FK | Y | 门店 | |
| count_date | date | Y | 盘点日期 | `2026-03-10` |
| count_type | varchar(20) | Y | 类型 | daily_close/weekly/monthly/spot_check |
| item_id | varchar(50) FK | Y | 库存项 | |
| system_qty | numeric(12,4) | Y | 系统账面数 | `26.0000` |
| actual_qty | numeric(12,4) | Y | 实际盘点数 | `25.5000` |
| variance_qty | numeric(12,4) | Y | 差异量 | `-0.5000` |
| variance_cost_fen | integer | N | 差异金额(分) | `-900` |
| variance_reason | varchar(30) | N | 差异原因 | 见枚举 [count_variance_reason](#1410-count_variance_reason) |
| counted_by | varchar(50) | Y | 盘点人 | `EMP003` |
| verified_by | varchar(50) | N | 复核人 | `EMP001` |
| photo_url | text | N | 盘点照片 | |

---

## 4. 采购与供应商

### 4.1 供应商 (suppliers)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| supplier_id | varchar(50) PK | Y | 供应商编码 | `SUP001` |
| name | varchar(200) | Y | 公司名称 | `上海鲜达水产有限公司` |
| short_name | varchar(50) | N | 简称 | `鲜达水产` |
| category | varchar(30) | Y | 供应类型 | 见枚举 [supplier_category](#1411-supplier_category) |
| contact_person | varchar(50) | Y | 联系人 | `王经理` |
| phone | varchar(20) | Y | 电话 | |
| wechat_id | varchar(50) | N | 微信号 | |
| address | text | N | 地址 | |
| city | varchar(50) | N | 城市 | `上海` |
| business_license | varchar(50) | N | 营业执照号 | |
| food_license | varchar(50) | N | 食品经营许可证号 | |
| license_expiry_date | date | N | 许可证到期日 | `2027-06-30` |
| payment_terms | varchar(30) | Y | 结算方式 | 见枚举 [payment_terms](#1412-payment_terms-结算方式) |
| credit_days | integer | N | 账期(天) | `30` |
| delivery_lead_days | integer | N | 配送提前量(天) | `1` |
| min_order_yuan | numeric(10,2) | N | 最低起送金额(元) | `500.00` |
| rating | numeric(3,2) | N | 综合评分(1-5) | `4.35` |
| tier | varchar(10) | N | 供应商等级 | A/B/C/D |
| status | varchar(20) | Y | 状态 | active/inactive/suspended/blacklisted |
| cooperation_start_date | date | N | 合作开始日期 | |
| notes | text | N | 备注 | |

### 4.2 供应商报价 (supplier_quotes)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| quote_id | uuid PK | Y | 报价ID | |
| supplier_id | varchar(50) FK | Y | 供应商 | |
| ingredient_id | varchar(50) FK | Y | 食材 | |
| unit_price_fen | integer | Y | 报价(分/基本单位) | `1800` |
| unit | varchar(10) | Y | 计价单位 | `kg` |
| min_order_qty | numeric(10,2) | N | 最小起订量 | `5.00` |
| valid_from | date | Y | 报价生效日 | `2026-03-01` |
| valid_to | date | N | 报价失效日 | `2026-03-31` |
| quality_grade | varchar(10) | N | 对应品质 | standard/premium |
| notes | text | N | 报价说明 | `活鱼, 500-700g/条` |

### 4.3 采购单 (purchase_orders)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| po_id | varchar(50) PK | Y | 采购单号 | `PO20260311001` |
| store_id | varchar(50) FK | Y | 需求门店 | |
| supplier_id | varchar(50) FK | Y | 供应商 | |
| status | varchar(20) | Y | 状态 | draft/submitted/approved/ordered/in_transit/received/completed/cancelled |
| total_amount_fen | integer | Y | 总金额(分) | `54000` |
| expected_delivery | timestamptz | N | 预计到货 | |
| actual_delivery | timestamptz | N | 实际到货 | |
| delivery_score | integer | N | 准时评分(1-5) | `4` |
| quality_score | integer | N | 质量评分(1-5) | `5` |
| created_by | varchar(50) | Y | 制单人 | `EMP003` |
| approved_by | varchar(50) | N | 审批人 | `EMP001` |
| approved_at | timestamptz | N | 审批时间 | |
| received_by | varchar(50) | N | 收货人 | |
| received_at | timestamptz | N | 收货时间 | |
| notes | text | N | 采购备注 | |

### 4.4 采购单明细 (purchase_order_items)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | 行ID | |
| po_id | varchar(50) FK | Y | 采购单 | |
| ingredient_id | varchar(50) FK | Y | 食材 | `ING_LY_001` |
| ordered_qty | numeric(12,4) | Y | 订购量 | `30.0000` |
| received_qty | numeric(12,4) | N | 实收量 | `29.5000` |
| rejected_qty | numeric(12,4) | N | 拒收量 | `0.5000` |
| unit | varchar(10) | Y | 单位 | `kg` |
| unit_price_fen | integer | Y | 采购单价(分) | `1800` |
| line_amount_fen | integer | Y | 行金额(分) | `54000` |
| reject_reason | varchar(50) | N | 拒收原因 | `规格不符/变质/数量不足` |
| batch_id | uuid FK | N | 入库批次 | |

---

## 5. 销售与订单

### 5.1 订单 (orders)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| order_id | uuid PK | Y | 订单ID | |
| store_id | varchar(50) FK | Y | 门店 | |
| order_no | varchar(50) UQ | Y | 订单号 | `ORD20260312001` |
| sales_channel | varchar(30) | Y | 渠道 | 见枚举 [sales_channel](#1413-sales_channel-销售渠道) |
| order_type | varchar(20) | Y | 类型 | dine_in/takeout/delivery/pre_order |
| table_number | varchar(20) | N | 桌号(堂食) | `A05` |
| guest_count | integer | N | 就餐人数 | `4` |
| customer_name | varchar(50) | N | 顾客姓名 | |
| customer_phone | varchar(20) | N | 顾客电话 | |
| member_id | varchar(50) FK | N | 会员ID | |
| waiter_id | varchar(50) FK | N | 服务员 | `EMP010` |
| status | varchar(20) | Y | 状态 | 见枚举 [order_status](#1415-order_status-订单状态) |
| subtotal_fen | integer | Y | 小计(分) | `27600` |
| discount_fen | integer | N | 优惠金额(分) | `2000` |
| surcharge_fen | integer | N | 附加费:茶位/餐具/服务费(分) | `400` |
| tax_fen | integer | N | 税额(分) | `0` |
| final_amount_fen | integer | Y | 实付(分) | `26000` |
| payment_method | varchar(20) | N | 支付方式 | 见枚举 [payment_method](#1416-payment_method-支付方式) |
| payment_time | timestamptz | N | 支付时间 | |
| platform_order_id | varchar(100) | N | 平台订单号(外卖) | `MT20260312xxxxx` |
| platform_commission_fen | integer | N | 平台佣金(分) | `4680` (18%) |
| delivery_fee_fen | integer | N | 配送费(分) | `500` |
| packaging_fee_fen | integer | N | 打包费(分) | `300` |
| order_time | timestamptz | Y | 下单时间 | |
| confirmed_at | timestamptz | N | 确认时间 | |
| ready_at | timestamptz | N | 出餐完成时间 | |
| completed_at | timestamptz | N | 结账/完成时间 | |
| cancelled_at | timestamptz | N | 取消时间 | |
| cancel_reason | varchar(100) | N | 取消原因 | |
| notes | text | N | 订单备注 | `少辣, 加一副碗筷` |

### 5.2 订单明细 (order_items)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | 行ID | |
| order_id | uuid FK | Y | 订单 | |
| dish_master_id | uuid FK | N | 集团SKU | |
| dish_name | varchar(100) | Y | 菜品名(快照) | `酸菜鱼` |
| quantity | integer | Y | 数量 | `1` |
| unit_price_fen | integer | Y | 单价(分) | `6800` |
| subtotal_fen | integer | Y | 小计(分) | `6800` |
| discount_fen | integer | N | 行级优惠(分) | `0` |
| food_cost_fen | integer | N | 理论食材成本(分) | `2850` |
| gross_margin_pct | numeric(6,4) | N | 毛利率 | `0.5809` (58.09%) |
| customizations | jsonb | N | 口味定制 | `{"spicy":"less","no_cilantro":true}` |
| is_complimentary | boolean | N | 是否赠送 | `false` |
| comp_reason | varchar(50) | N | 赠送原因 | `客诉补偿/VIP赠品` |
| kitchen_status | varchar(20) | N | 厨房状态 | pending/cooking/ready/served |
| kitchen_printed_at | timestamptz | N | 打印厨打时间 | |
| served_at | timestamptz | N | 上菜时间 | |

### 5.3 每日营业汇总 (daily_revenue_summary)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | | |
| store_id | varchar(50) FK | Y | 门店 | |
| biz_date | date | Y | 营业日 | `2026-03-12` |
| order_count | integer | Y | 订单数 | `185` |
| guest_count | integer | N | 客流人次 | `312` |
| dine_in_count | integer | N | 堂食单数 | `120` |
| takeout_count | integer | N | 外卖单数 | `65` |
| gross_revenue_fen | integer | Y | 总营收(分) | `2856000` |
| discount_total_fen | integer | N | 总优惠(分) | `128000` |
| net_revenue_fen | integer | Y | 净营收(分) | `2728000` |
| platform_commission_fen | integer | N | 平台佣金合计(分) | `210600` |
| avg_ticket_fen | integer | N | 客单价(分) | `8750` |
| table_turnover_rate | numeric(5,2) | N | 翻台率(次) | `2.80` |
| peak_hour_start | time | N | 午高峰开始 | `11:30` |
| peak_hour_end | time | N | 午高峰结束 | `13:00` |
| weather | varchar(20) | N | 天气 | `晴/雨/阴` |
| is_holiday | boolean | N | 是否节假日 | `false` |
| **UQ约束** | | | `(store_id, biz_date)` | |

---

## 6. 损耗与报废

### 6.1 损耗事件 (waste_events)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| waste_id | uuid PK | Y | 损耗ID | |
| store_id | varchar(50) FK | Y | 门店 | |
| ingredient_id | varchar(50) FK | Y | 食材 | `ING_LY_001` |
| batch_id | uuid FK | N | 关联批次 | |
| dish_id | uuid FK | N | 关联菜品(加工损耗时) | |
| event_type | varchar(30) | Y | 损耗类型 | 见枚举 [waste_event_type](#1417-waste_event_type-损耗类型) |
| waste_qty | numeric(12,4) | Y | 损耗量 | `1.2000` |
| unit | varchar(10) | Y | 单位 | `kg` |
| unit_cost_fen | integer | Y | 单价(分) | `1800` |
| waste_cost_fen | integer | Y | 损耗金额(分) | `2160` |
| theoretical_qty | numeric(12,4) | N | BOM理论用量(对比用) | `14.7000` |
| actual_qty | numeric(12,4) | N | 实际用量 | `17.2000` |
| variance_qty | numeric(12,4) | N | 差异量 | `2.5000` |
| variance_pct | numeric(6,2) | N | 差异率(%) | `17.01` |
| root_cause | varchar(30) | N | 根因分类 | 见枚举 [waste_root_cause](#1418-waste_root_cause-损耗根因) |
| root_cause_detail | text | N | 根因描述 | `新员工切配克重不稳定` |
| occurred_at | timestamptz | Y | 发生时间 | |
| occurred_period | varchar(20) | N | 发生时段 | morning_prep/lunch/dinner/closing |
| reported_by | varchar(50) | Y | 登记人 | `EMP003` |
| responsible_staff_id | varchar(50) | N | 责任人 | `EMP015` |
| action_taken | text | N | 处理措施 | `已重新培训切配标准` |
| photo_urls | jsonb | N | 照片证据 | `["https://..."]` |
| is_preventable | boolean | N | 是否可避免 | `true` |
| status | varchar(20) | Y | 状态 | pending/analyzed/resolved/closed |
| ai_confidence | numeric(4,3) | N | AI归因置信度(0-1) | `0.850` |
| ai_evidence | jsonb | N | AI归因证据链 | |

### 6.2 每日损耗汇总 (daily_waste_summary)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | | |
| store_id | varchar(50) FK | Y | 门店 | |
| biz_date | date | Y | 营业日 | |
| total_waste_cost_fen | integer | Y | 总损耗金额(分) | `12800` |
| total_waste_events | integer | Y | 损耗事件数 | `8` |
| waste_rate_pct | numeric(5,2) | N | 损耗率(%)=总损耗/总营收 | `4.20` |
| top_waste_ingredient | varchar(100) | N | 最大损耗食材 | `鲈鱼` |
| top_waste_cost_fen | integer | N | 最大损耗金额(分) | `5400` |
| preventable_cost_fen | integer | N | 可避免损耗金额(分) | `8600` |
| root_cause_dist | jsonb | N | 根因分布 | `{"staff_error":4,"spoilage":2,"over_prep":2}` |
| **UQ约束** | | | `(store_id, biz_date)` | |

---

## 7. 人力与排班

### 7.1 员工 (employees)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| employee_id | varchar(50) PK | Y | 员工编码 | `EMP001` |
| store_id | varchar(50) FK | Y | 所属门店 | |
| name | varchar(50) | Y | 姓名 | `张三` |
| phone | varchar(20) | Y | 手机 | |
| id_card_last4 | varchar(4) | N | 身份证后4位 | `1234` |
| position | varchar(30) | Y | 岗位 | 见枚举 [position](#1419-position-岗位) |
| position_level | varchar(10) | N | 级别 | junior/mid/senior/lead |
| department | varchar(30) | N | 部门 | kitchen/floor/admin |
| hire_date | date | Y | 入职日期 | `2025-06-01` |
| contract_type | varchar(20) | N | 合同类型 | full_time/part_time/intern/hourly |
| probation_end_date | date | N | 试用期结束日 | |
| base_salary_yuan | numeric(10,2) | N | 基本月薪(元) | `5500.00` |
| hourly_wage_yuan | numeric(6,2) | N | 时薪(元,兼职用) | `25.00` |
| skills | varchar[] | N | 技能标签 | `{切配,炒锅,凉菜}` |
| certifications | jsonb | N | 证书 | `[{"name":"健康证","expiry":"2027-03"}]` |
| is_active | boolean | Y | 在职 | `true` |
| leave_date | date | N | 离职日期 | |
| leave_reason | varchar(50) | N | 离职原因 | voluntary/terminated/contract_end |
| emergency_contact | varchar(50) | N | 紧急联系人 | |
| emergency_phone | varchar(20) | N | 紧急电话 | |
| performance_score | numeric(4,2) | N | 绩效分(0-100) | `82.50` |
| wechat_user_id | varchar(50) | N | 企微UserID | |

### 7.2 考勤记录 (attendance_logs)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | | |
| store_id | varchar(50) FK | Y | 门店 | |
| employee_id | varchar(50) FK | Y | 员工 | |
| work_date | date | Y | 工作日期 | `2026-03-12` |
| clock_in | timestamptz | Y | 上班打卡 | `2026-03-12T09:02:00` |
| clock_out | timestamptz | N | 下班打卡 | `2026-03-12T17:35:00` |
| break_minutes | integer | N | 休息时长(分钟) | `60` |
| actual_hours | numeric(5,2) | N | 实际工时(小时) | `7.55` |
| overtime_hours | numeric(5,2) | N | 加班工时(小时) | `0.00` |
| status | varchar(20) | Y | 状态 | normal/late/early_leave/absent/leave |
| late_minutes | integer | N | 迟到分钟数 | `2` |
| leave_type | varchar(20) | N | 请假类型 | annual/sick/personal/maternity |
| source | varchar(20) | N | 打卡方式 | fingerprint/face/wechat/manual |
| **UQ约束** | | | `(store_id, employee_id, work_date)` | |

### 7.3 排班表 (schedules)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| schedule_id | uuid PK | Y | 排班ID | |
| store_id | varchar(50) FK | Y | 门店 | |
| schedule_date | date | Y | 日期 | `2026-03-13` |
| total_scheduled | integer | N | 排班人数 | `18` |
| total_hours | numeric(6,1) | N | 总工时 | `126.0` |
| estimated_labor_cost_yuan | numeric(10,2) | N | 预估人力成本(元) | `3150.00` |
| is_published | boolean | Y | 是否发布 | `true` |
| published_by | varchar(50) | N | 发布人 | |
| published_at | timestamptz | N | 发布时间 | |
| **UQ约束** | | | `(store_id, schedule_date)` | |

### 7.4 班次 (shifts)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| shift_id | uuid PK | Y | 班次ID | |
| schedule_id | uuid FK | Y | 排班表 | |
| employee_id | varchar(50) FK | Y | 员工 | |
| shift_type | varchar(20) | Y | 班型 | 见枚举 [shift_type](#1420-shift_type-班型) |
| start_time | time | Y | 开始时间 | `09:00` |
| end_time | time | Y | 结束时间 | `17:00` |
| break_minutes | integer | N | 休息(分钟) | `60` |
| position | varchar(30) | Y | 该班次岗位 | `waiter` |
| is_confirmed | boolean | N | 员工已确认 | `true` |
| is_completed | boolean | N | 已完成 | |
| notes | text | N | 备注 | |

### 7.5 每日人力成本快照 (labor_cost_snapshots)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | | |
| store_id | varchar(50) FK | Y | 门店 | |
| snapshot_date | date | Y | 日期 | `2026-03-12` |
| actual_revenue_yuan | numeric(12,2) | Y | 当日营收(元) | `28560.00` |
| actual_labor_cost_yuan | numeric(12,2) | Y | 当日人工成本(元) | `7568.00` |
| actual_labor_cost_rate | numeric(5,2) | Y | 人力成本率(%) | `26.50` |
| budgeted_labor_cost_yuan | numeric(12,2) | N | 预算(元) | `7140.00` |
| variance_yuan | numeric(12,2) | N | 超支/节约(元) | `428.00` |
| headcount_scheduled | integer | N | 排班人数 | `18` |
| headcount_actual | integer | N | 实到人数 | `17` |
| overtime_hours | numeric(6,2) | N | 加班工时 | `3.50` |
| overtime_cost_yuan | numeric(10,2) | N | 加班费(元) | `262.50` |
| **UQ约束** | | | `(store_id, snapshot_date)` | |

---

## 8. 财务与成本

### 8.1 每日成本真相 (cost_truth_daily)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | | |
| store_id | varchar(50) FK | Y | 门店 | |
| truth_date | date | Y | 日期 | `2026-03-12` |
| revenue_fen | integer | Y | 当日营收(分) | `2856000` |
| theoretical_cost_fen | integer | Y | BOM理论成本(分) | `913920` |
| actual_cost_fen | integer | Y | 实际出库成本(分) | `976320` |
| variance_fen | integer | Y | 差异(分)=实际-理论 | `62400` |
| theoretical_pct | numeric(5,2) | Y | 理论成本率(%) | `32.00` |
| actual_pct | numeric(5,2) | Y | 实际成本率(%) | `34.18` |
| variance_pct | numeric(5,2) | Y | 差异(pp) | `2.18` |
| severity | varchar(10) | Y | 严重度 | ok/watch/warning/critical |
| order_count | integer | N | 当日订单数 | `185` |
| dish_count | integer | N | 涉及菜品数 | `42` |
| top_variance_dish | varchar(100) | N | 最大差异菜品 | `酸菜鱼` |
| top_variance_yuan | numeric(10,2) | N | 最大差异金额(元) | `312.00` |
| mtd_revenue_fen | bigint | N | 月累计营收(分) | `31416000` |
| mtd_actual_cost_fen | bigint | N | 月累计成本(分) | `10681440` |
| mtd_actual_pct | numeric(5,2) | N | 月累计成本率(%) | `33.99` |
| predicted_eom_pct | numeric(5,2) | N | 预测月末成本率(%) | `33.80` |
| target_pct | numeric(5,2) | Y | 目标成本率(%) | `32.00` |
| **UQ约束** | | | `(store_id, truth_date)` | |

### 8.2 菜品级成本明细 (cost_truth_dish_detail)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | | |
| truth_daily_id | uuid FK | Y | 关联日报 | |
| dish_master_id | uuid FK | N | 菜品SKU | |
| dish_name | varchar(100) | Y | 菜品名 | `酸菜鱼` |
| sold_qty | integer | Y | 当日销量(份) | `42` |
| theoretical_cost_fen | integer | Y | 理论成本(分) | `119700` |
| actual_cost_fen | integer | Y | 实际分摊成本(分) | `148500` |
| variance_fen | integer | Y | 差异(分) | `28800` |
| variance_pct | numeric(6,2) | N | 差异率(%) | `24.06` |
| top_ingredients | jsonb | N | 食材级明细 | 见下方结构 |

**top_ingredients JSON结构**:
```json
[{
  "ingredient_id": "ING_LY_001",
  "name": "鲈鱼",
  "unit": "kg",
  "theoretical_qty": 14.7,
  "actual_qty": 17.2,
  "variance_qty": 2.5,
  "variance_cost_fen": 4500,
  "unit_cost_fen": 1800
}]
```

### 8.3 五因归因 (cost_variance_attribution)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | | |
| truth_daily_id | uuid FK | Y | 关联日报 | |
| factor | varchar(20) | Y | 归因因素 | 见枚举 [attribution_factor](#1421-attribution_factor-五因归因) |
| contribution_fen | integer | Y | 贡献金额(分) | `18000` |
| contribution_pct | numeric(5,1) | Y | 贡献占比(%) | `28.8` |
| description | text | Y | 描述 | `鲈鱼采购价上涨 ¥1.5/kg` |
| action | text | Y | 建议操作 | `与供应商重新议价` |
| detail | jsonb | N | 结构化证据 | |
| **UQ约束** | | | `(truth_daily_id, factor)` | |

### 8.4 经营日报 (daily_pnl_summary)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | | |
| store_id | varchar(50) FK | Y | 门店 | |
| biz_date | date | Y | 营业日 | `2026-03-12` |
| **收入** | | | | |
| gross_revenue_fen | integer | Y | 总营收 | `2856000` |
| discount_fen | integer | N | 优惠 | `128000` |
| net_revenue_fen | integer | Y | 净营收 | `2728000` |
| **成本** | | | | |
| food_cost_fen | integer | Y | 食材成本 | `976320` |
| food_cost_pct | numeric(5,2) | N | 食材成本率(%) | `35.79` |
| labor_cost_fen | integer | Y | 人工成本 | `756800` |
| labor_cost_pct | numeric(5,2) | N | 人力成本率(%) | `27.74` |
| rent_cost_fen | integer | N | 租金(日均摊) | `116667` |
| utility_cost_fen | integer | N | 水电气 | `28000` |
| platform_fee_fen | integer | N | 平台佣金 | `210600` |
| packaging_cost_fen | integer | N | 打包费 | `19500` |
| waste_cost_fen | integer | N | 损耗 | `12800` |
| other_cost_fen | integer | N | 其他 | `15000` |
| **利润** | | | | |
| gross_profit_fen | integer | N | 毛利 | `1751680` |
| gross_profit_pct | numeric(5,2) | N | 毛利率(%) | `64.21` |
| operating_profit_fen | integer | N | 经营利润 | `591313` |
| operating_profit_pct | numeric(5,2) | N | 经营利润率(%) | `21.68` |
| **UQ约束** | | | `(store_id, biz_date)` | |

---

## 9. 会员与顾客

### 9.1 会员 (members)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| member_id | varchar(50) PK | Y | 会员编码 | `MBR00001` |
| brand_id | varchar(50) FK | Y | 所属品牌(跨店通用) | |
| phone | varchar(20) UQ | Y | 手机号(唯一标识) | |
| name | varchar(50) | N | 姓名 | |
| gender | varchar(10) | N | 性别 | male/female/unknown |
| birthday | date | N | 生日 | |
| wechat_openid | varchar(100) | N | 微信OpenID | |
| wechat_unionid | varchar(100) | N | 微信UnionID(跨公众号) | |
| register_store_id | varchar(50) FK | N | 注册门店 | |
| register_date | date | Y | 注册日期 | |
| register_source | varchar(30) | N | 注册来源 | wechat_mini/pos/manual/meituan |
| tier | varchar(20) | Y | 等级 | 见枚举 [member_tier](#1422-member_tier-会员等级) |
| lifecycle_state | varchar(20) | Y | 生命周期状态 | 见枚举 [lifecycle_state](#1423-lifecycle_state-会员生命周期) |
| total_orders | integer | N | 累计订单数 | `23` |
| total_spend_fen | bigint | N | 累计消费(分) | `456800` |
| avg_ticket_fen | integer | N | 客单价(分) | `19861` |
| last_order_date | date | N | 最近消费日期 | `2026-03-08` |
| last_store_id | varchar(50) | N | 最近消费门店 | |
| points_balance | integer | N | 积分余额 | `1200` |
| coupon_count | integer | N | 可用优惠券数 | `2` |
| tags | varchar[] | N | 标签 | `{辣爱好者,午市常客}` |
| preferences | jsonb | N | 偏好 | `{"no_cilantro":true,"spicy":"heavy"}` |

### 9.2 RFM画像快照 (member_rfm_snapshots)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | | |
| member_id | varchar(50) FK | Y | 会员 | |
| snapshot_date | date | Y | 快照日期 | |
| recency_days | integer | Y | 最近消费距今(天) | `4` |
| frequency_30d | integer | Y | 近30天消费次数 | `6` |
| monetary_30d_fen | integer | Y | 近30天消费额(分) | `89600` |
| r_score | integer | Y | R分(1-5) | `5` |
| f_score | integer | Y | F分(1-5) | `4` |
| m_score | integer | Y | M分(1-5) | `3` |
| rfm_segment | varchar(30) | Y | 细分 | 见枚举 [rfm_segment](#1424-rfm_segment-rfm细分) |
| churn_risk_pct | numeric(5,2) | N | 流失风险(%) | `8.50` |
| ltv_yuan | numeric(12,2) | N | 预测生命周期价值(元) | `12800.00` |

---

## 10. 预订与宴会

### 10.1 预订 (reservations)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| reservation_id | varchar(50) PK | Y | 预订编号 | `RES_20260312_001` |
| store_id | varchar(50) FK | Y | 门店 | |
| customer_name | varchar(50) | Y | 预订人 | `李女士` |
| customer_phone | varchar(20) | Y | 电话 | |
| member_id | varchar(50) FK | N | 会员(如有) | |
| reservation_type | varchar(20) | Y | 类型 | regular/banquet/private_room |
| reservation_date | date | Y | 预订日期 | `2026-03-15` |
| reservation_time | time | Y | 预订时间 | `18:00` |
| party_size | integer | Y | 人数 | `8` |
| table_number | varchar(20) | N | 桌号 | `VIP-01` |
| room_name | varchar(50) | N | 包间名 | `牡丹厅` |
| estimated_budget_fen | integer | N | 预估消费(分) | `320000` |
| deposit_fen | integer | N | 定金(分) | `50000` |
| deposit_paid | boolean | N | 定金已付 | `true` |
| special_requests | text | N | 特殊要求 | `生日蛋糕, 投影设备` |
| dietary_restrictions | text | N | 忌口 | `1位素食, 1位海鲜过敏` |
| status | varchar(20) | Y | 状态 | pending/confirmed/arrived/seated/completed/cancelled/no_show |
| source | varchar(20) | N | 来源 | phone/wechat/meituan/walk_in |
| arrival_time | timestamptz | N | 到店时间 | |
| cancelled_at | timestamptz | N | 取消时间 | |
| cancel_reason | varchar(100) | N | 取消原因 | |
| no_show_handled | boolean | N | 爽约已处理 | |

---

## 11. 渠道与平台

### 11.1 销售渠道配置 (sales_channel_configs)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | | |
| brand_id | varchar(50) FK | N | null=集团通用 | |
| channel | varchar(30) | Y | 渠道 | 见枚举 [sales_channel](#1413-sales_channel-销售渠道) |
| platform_commission_pct | numeric(6,4) | Y | 平台佣金率 | `0.1800` (18%) |
| delivery_cost_fen | integer | N | 每单配送费(分) | `500` |
| packaging_cost_fen | integer | N | 每单打包费(分) | `300` |
| service_fee_pct | numeric(6,4) | N | 服务费率 | `0.0000` |
| refund_rate_pct | numeric(5,2) | N | 历史退款率(%) | `2.50` |
| avg_delivery_minutes | integer | N | 平均配送时长(分钟) | `35` |
| is_active | boolean | Y | 是否启用 | `true` |
| **UQ约束** | | | `(brand_id, channel)` | |

---

## 12. 决策与推送

### 12.1 决策生命周期 (decision_lifecycle)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| decision_id | uuid PK | Y | 决策ID | |
| store_id | varchar(50) FK | Y | 门店 | |
| decision_date | date | Y | 决策日期 | `2026-03-12` |
| source | varchar(30) | Y | 来源引擎 | cost_truth/unified_brain/waste_guard/labor/inventory |
| title | varchar(100) | Y | 标题 | `食材成本超标 2.2pp` |
| action | text | Y | 建议操作 | `酸菜鱼鱼片克重 380g→350g` |
| expected_saving_yuan | numeric(10,2) | Y | 预期月省(元) | `12800.00` |
| confidence_pct | integer | Y | 置信度(%) | `75` |
| severity | varchar(10) | Y | 严重度 | critical/warning/watch/ok |
| executor | varchar(50) | N | 执行人角色 | `厨师长` |
| deadline_hours | integer | N | 建议完成时限(小时) | `48` |
| category | varchar(20) | Y | 类别 | cost/labor/inventory/waste/revenue |
| status | varchar(20) | Y | 状态 | generated/pushed/viewed/accepted/rejected/executed/measured |
| pushed_at | timestamptz | N | 推送时间 | |
| push_channel | varchar(20) | N | 推送渠道 | wechat/app/sms |
| viewed_at | timestamptz | N | 查看时间 | |
| accepted_at | timestamptz | N | 采纳时间 | |
| rejected_at | timestamptz | N | 拒绝时间 | |
| reject_reason | varchar(100) | N | 拒绝原因 | |
| executed_at | timestamptz | N | 执行完成时间 | |
| measured_at | timestamptz | N | 效果度量时间 | |
| actual_saving_yuan | numeric(10,2) | N | 实际节省(元) | `8200.00` |
| measurement_method | text | N | 度量方法 | `对比执行前后3天鲈鱼用量` |

---

## 13. 价格基准网络

### 13.1 匿名采购价格池 (price_benchmark_pool)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | | |
| ingredient_id | varchar(50) FK | Y | 标准食材 | `ING_LY_001` |
| category | varchar(30) | Y | 分类 | `seafood` |
| city | varchar(50) | Y | 城市 | `上海` |
| unit | varchar(10) | Y | 单位 | `kg` |
| unit_cost_fen | integer | Y | 单价(分) | `1800` |
| quality_grade | varchar(10) | Y | 品质 | standard/premium/economy |
| purchase_month | varchar(7) | Y | 采购月份 | `2026-03` |
| contributor_hash | varchar(64) | Y | 贡献者哈希(脱敏) | `a3f2b8...` |
| **隐私规则** | | | 聚合输出最少需要5家不同contributor | |

### 13.2 基准报告 (price_benchmark_reports)

| 字段 | 类型 | 必填 | 说明 | 示例 |
|------|------|------|------|------|
| id | uuid PK | Y | | |
| store_id | varchar(50) FK | Y | 客户门店 | |
| report_month | varchar(7) | Y | 报告月份 | `2026-03` |
| total_items | integer | Y | 参与对比食材数 | `12` |
| cheap_count | integer | Y | 买便宜了的数量 | `3` |
| fair_count | integer | Y | 合理区间的数量 | `5` |
| expensive_count | integer | Y | 买贵了的数量 | `3` |
| very_expensive_count | integer | Y | 明显买贵的数量 | `1` |
| score | integer | Y | 采购健康分(0-100) | `62` |
| total_saving_potential_yuan | numeric(12,2) | N | 月度节省潜力(元) | `4500.00` |
| annual_saving_potential_yuan | numeric(12,2) | N | 年度节省潜力(元) | `54000.00` |
| generated_at | timestamptz | Y | 生成时间 | |

---

## 14. 枚举值字典

### 14.1 industry_type 业态

| 值 | 说明 | 典型客单价 | 食材成本率基准 |
|---|---|---|---|
| `chinese_formal` | 中餐正餐 | 80-150元 | 30-35% |
| `chinese_fast` | 中式快餐 | 20-40元 | 28-33% |
| `hotpot` | 火锅 | 80-120元 | 35-42% |
| `bbq` | 烧烤 | 60-100元 | 30-38% |
| `japanese` | 日料 | 100-200元 | 35-40% |
| `western` | 西餐 | 80-180元 | 28-33% |
| `bakery` | 烘焙 | 30-60元 | 25-30% |
| `tea_drink` | 茶饮 | 15-35元 | 15-22% |
| `coffee` | 咖啡 | 25-45元 | 18-25% |
| `canteen` | 团餐/食堂 | 15-25元 | 40-50% |

### 14.2 cuisine_type 菜系

| 值 | 说明 |
|---|---|
| `sichuan` | 川菜 |
| `hunan` | 湘菜 |
| `cantonese` | 粤菜 |
| `shandong` | 鲁菜 |
| `jiangsu` | 苏菜 |
| `zhejiang` | 浙菜 |
| `fujian` | 闽菜 |
| `anhui` | 徽菜 |
| `northeastern` | 东北菜 |
| `yunnan` | 云南菜 |
| `guizhou` | 贵州菜 |
| `xinjiang` | 新疆菜 |
| `fusion` | 融合菜 |
| `other` | 其他 |

### 14.3 store_type 门店类型

| 值 | 说明 | 特征 |
|---|---|---|
| `flagship` | 旗舰店 | 面积大, 全品类, 包间 |
| `standard` | 标准店 | 品牌标准面积 |
| `mini` | 小型店/档口 | <80㎡, 快餐/茶饮 |
| `mall` | 商场店 | 商场内, 受营业时间约束 |
| `street` | 街边店 | 独立门面 |
| `community` | 社区店 | 居民区内 |
| `central_kitchen` | 中央厨房 | 生产+配送, 无堂食 |
| `ghost_kitchen` | 纯外卖店 | 无堂食, 仅外卖 |

### 14.4 ingredient_category 食材分类

| 值 | 说明 | 典型损耗率 | 存储方式 |
|---|---|---|---|
| `seafood` | 海鲜/水产 | 5-15% | 冷藏/活养 |
| `meat` | 肉类 | 3-8% | 冷冻/冷藏 |
| `poultry` | 禽类 | 5-10% | 冷冻/冷藏 |
| `vegetable` | 蔬菜 | 8-20% | 冷藏 |
| `fruit` | 水果 | 5-15% | 冷藏 |
| `mushroom` | 菌菇 | 5-12% | 冷藏 |
| `tofu_bean` | 豆制品 | 3-8% | 冷藏 |
| `dry_goods` | 干货 | 1-3% | 常温 |
| `grain` | 米面粮油 | 1-2% | 常温 |
| `oil` | 食用油 | <1% | 常温 |
| `seasoning` | 调味料 | <1% | 常温 |
| `dairy` | 乳制品 | 3-8% | 冷藏 |
| `beverage` | 饮品原料 | 2-5% | 常温/冷藏 |
| `frozen` | 冷冻成品 | 2-5% | 冷冻 |
| `packaging` | 包材 | <1% | 常温 |

### 14.5 storage_type 存储方式

| 值 | 温度范围 | 说明 |
|---|---|---|
| `frozen` | -18℃以下 | 冷冻库 |
| `chilled` | 0-4℃ | 冷藏库 |
| `cool` | 8-15℃ | 阴凉处 |
| `ambient` | 常温 | 干燥通风 |
| `live` | 适温 | 活养池(水产) |

### 14.6 cooking_method 烹饪方式

| 值 | 说明 |
|---|---|
| `stir_fry` | 炒 |
| `deep_fry` | 炸 |
| `steam` | 蒸 |
| `braise` | 焖/烧 |
| `stew` | 炖/煲 |
| `boil` | 煮/涮 |
| `grill` | 烤 |
| `cold_dish` | 凉拌 |
| `raw` | 生食(刺身) |
| `bake` | 烘焙 |
| `smoke` | 烟熏 |
| `mixed` | 复合工艺 |

### 14.7 kitchen_station 档口

| 值 | 说明 | 人员配置 |
|---|---|---|
| `wok` | 炒锅 | 炒锅师傅 |
| `cutting` | 切配/砧板 | 切配员 |
| `steamer` | 蒸档 | 蒸档师傅 |
| `cold` | 冷菜/凉菜 | 冷菜师傅 |
| `dimsum` | 点心 | 点心师 |
| `soup` | 汤煲 | 煲汤师 |
| `bbq` | 烧腊/烧烤 | 烧腊师 |
| `pastry` | 西点/甜品 | 甜品师 |
| `drink` | 饮品 | 调饮师 |
| `prep` | 粗加工 | 粗加工员 |

### 14.8 dish_lifecycle 菜品生命周期

| 值 | 说明 | 允许操作 |
|---|---|---|
| `concept` | 研发中 | 编辑配方 |
| `testing` | 试菜阶段 | 限量销售, 收集反馈 |
| `approved` | 已审批 | 可上架 |
| `active` | 在售 | 正常销售 |
| `seasonal` | 季节性在售 | 按季节自动上下架 |
| `paused` | 暂停销售 | 临时下架(缺原料) |
| `sunset` | 计划下架 | 不再推荐, 允许点单 |
| `retired` | 已下架 | 不可点单 |
| `archived` | 已归档 | 仅历史记录 |

### 14.9 inv_txn_type 库存流水类型

| 值 | 方向 | 说明 |
|---|---|---|
| `purchase` | +入库 | 采购入库 |
| `return_to_supplier` | -出库 | 退货给供应商 |
| `usage` | -出库 | 生产领料/日常消耗 |
| `waste` | -出库 | 报废/损耗 |
| `adjustment_up` | +调增 | 盘盈/调账增加 |
| `adjustment_down` | -调减 | 盘亏/调账减少 |
| `transfer_out` | -出库 | 调拨出(跨店) |
| `transfer_in` | +入库 | 调拨入(跨店) |
| `production_in` | +入库 | 中央厨房成品入库 |
| `production_out` | -出库 | 中央厨房原料领用 |

### 14.10 count_variance_reason 盘点差异原因

| 值 | 说明 |
|---|---|
| `natural_loss` | 自然损耗(挥发/干缩) |
| `unrecorded_waste` | 未登记损耗 |
| `unrecorded_usage` | 未登记领料 |
| `count_error` | 盘点计数错误 |
| `system_error` | 系统数据错误 |
| `theft` | 盗损 |
| `unit_conversion` | 单位换算偏差 |
| `other` | 其他 |

### 14.11 supplier_category 供应商类型

| 值 | 说明 |
|---|---|
| `fresh_seafood` | 海鲜水产 |
| `fresh_meat` | 鲜肉禽蛋 |
| `fresh_vegetable` | 蔬菜水果 |
| `frozen` | 冷冻食品 |
| `dry_goods` | 干货杂粮 |
| `oil_seasoning` | 粮油调味 |
| `beverage` | 酒水饮料 |
| `dairy` | 乳制品 |
| `packaging` | 包装材料 |
| `kitchen_equipment` | 厨房设备 |
| `cleaning` | 清洁用品 |
| `comprehensive` | 综合供应商 |

### 14.12 payment_terms 结算方式

| 值 | 说明 |
|---|---|
| `cod` | 货到付款 |
| `prepaid` | 预付款 |
| `net_7` | 月结7天 |
| `net_15` | 月结15天 |
| `net_30` | 月结30天 |
| `net_60` | 月结60天 |
| `biweekly` | 半月结 |
| `weekly` | 周结 |

### 14.13 sales_channel 销售渠道

| 值 | 说明 | 典型佣金率 |
|---|---|---|
| `dine_in` | 堂食 | 0% |
| `takeout_self` | 自营外卖(小程序) | 0% |
| `meituan` | 美团外卖 | 15-23% |
| `eleme` | 饿了么 | 15-23% |
| `douyin` | 抖音团购 | 2.5-8% |
| `meituan_tuangou` | 美团团购 | 3-10% |
| `dianping` | 大众点评 | 3-10% |
| `self_pickup` | 到店自提 | 0% |
| `group_buy` | 企业团餐 | 0-5% |
| `catering` | 宴会/包场 | 0% |
| `other` | 其他 | 0% |

### 14.14 pos_system POS系统

| 值 | 说明 |
|---|---|
| `tcsl` | 天财商龙 |
| `pinzhi` | 品智收银 |
| `kede` | 科脉 |
| `customer` | 客如云 |
| `meituan_pos` | 美团收银 |
| `hualala` | 哗啦啦 |
| `zhongke` | 中科软 |
| `yipos` | 银豹 |
| `other` | 其他 |
| `none` | 无POS(手工记账) |

### 14.15 order_status 订单状态

| 值 | 说明 | 堂食 | 外卖 |
|---|---|---|---|
| `pending` | 待确认 | 下单 | 下单 |
| `confirmed` | 已确认 | 服务员确认 | 商家接单 |
| `preparing` | 制作中 | 厨房制作 | 厨房制作 |
| `ready` | 已出餐 | 可上菜 | 等待配送 |
| `served` | 已上菜 | 堂食上齐 | - |
| `in_delivery` | 配送中 | - | 骑手取餐 |
| `completed` | 已完成 | 结账 | 确认收货 |
| `cancelled` | 已取消 | 退单 | 退单 |
| `refunded` | 已退款 | 售后退款 | 售后退款 |

### 14.16 payment_method 支付方式

| 值 | 说明 |
|---|---|
| `wechat` | 微信支付 |
| `alipay` | 支付宝 |
| `cash` | 现金 |
| `bank_card` | 银行卡 |
| `member_balance` | 会员储值 |
| `coupon` | 优惠券抵扣 |
| `points` | 积分抵扣 |
| `credit` | 挂账/赊账 |
| `mixed` | 混合支付 |
| `platform` | 平台代收(外卖) |

### 14.17 waste_event_type 损耗类型

| 值 | 说明 | 典型场景 |
|---|---|---|
| `cooking_loss` | 烹饪损耗 | 油炸缩水、炒菜汤汁损失 |
| `cutting_loss` | 切配损耗 | 去皮去骨、边角料 |
| `spoilage` | 变质腐烂 | 过期、冷链断裂 |
| `over_prep` | 备料过量 | 预判客流失误 |
| `drop_damage` | 人为损坏 | 打碎、洒落 |
| `quality_reject` | 来货拒收 | 供应商品质不达标 |
| `transfer_loss` | 运输损耗 | 配送途中损失 |
| `portion_overrun` | 出品超标 | 菜品克重超BOM |
| `customer_return` | 顾客退菜 | 客诉退菜 |
| `inventory_shrink` | 盘亏差异 | 系统与实物不符 |
| `expired` | 到期报废 | 超保质期 |
| `unknown` | 不明原因 | 无法确定 |

### 14.18 waste_root_cause 损耗根因

| 值 | 说明 | 改善方向 |
|---|---|---|
| `staff_skill` | 员工技能不足 | 培训切配/烹饪标准 |
| `staff_error` | 员工操作失误 | 加强SOP执行检查 |
| `over_ordering` | 采购量过大 | 优化采购预测模型 |
| `demand_forecast_error` | 客流预测偏差 | 改进预测算法 |
| `supplier_quality` | 供应商品质问题 | 更换供应商/加强验收 |
| `cold_chain_break` | 冷链断裂 | 检修冷链设备 |
| `storage_error` | 存储不当 | 规范存储SOP |
| `equipment_failure` | 设备故障 | 设备维保 |
| `recipe_issue` | 配方不合理 | 调整BOM标准 |
| `menu_change` | 菜单调整 | 平滑过渡期 |
| `weather_impact` | 天气影响 | 建立天气-备料联动 |
| `holiday_impact` | 节假日影响 | 节日备料模型 |
| `unknown` | 原因不明 | 加强过程记录 |

### 14.19 position 岗位

| 值 | 说明 | 部门 | 典型时薪(元) |
|---|---|---|---|
| `store_manager` | 店长 | 管理 | 35-50 |
| `assistant_manager` | 副店长 | 管理 | 28-40 |
| `head_chef` | 厨师长 | 后厨 | 35-55 |
| `chef` | 炒锅师傅 | 后厨 | 25-40 |
| `sous_chef` | 副厨 | 后厨 | 22-35 |
| `cold_chef` | 冷菜师傅 | 后厨 | 22-30 |
| `prep_cook` | 切配员 | 后厨 | 18-25 |
| `dim_sum_chef` | 点心师 | 后厨 | 22-35 |
| `kitchen_helper` | 厨房帮工 | 后厨 | 15-20 |
| `floor_manager` | 楼面经理 | 前厅 | 25-35 |
| `waiter` | 服务员 | 前厅 | 18-25 |
| `cashier` | 收银员 | 前厅 | 18-22 |
| `host` | 迎宾/领位 | 前厅 | 18-22 |
| `bartender` | 调饮师 | 吧台 | 20-30 |
| `dishwasher` | 洗碗工 | 后勤 | 15-18 |
| `cleaner` | 保洁 | 后勤 | 15-18 |
| `purchaser` | 采购员 | 后勤 | 20-30 |
| `delivery` | 配送员 | 后勤 | 20-30 |

### 14.20 shift_type 班型

| 值 | 典型时段 | 工时 | 说明 |
|---|---|---|---|
| `morning` | 07:00-15:00 | 7h(含1h休) | 早班(含午市) |
| `middle` | 10:00-18:00 | 7h | 中班(跨午晚) |
| `evening` | 15:00-23:00 | 7h | 晚班(含晚市) |
| `full_day` | 09:00-21:00 | 10h(含2h休) | 全天班 |
| `split` | 10:00-14:00,17:00-21:00 | 8h | 两头班(避开空闲) |
| `overtime` | 延长 | 按时计 | 加班 |

### 14.21 attribution_factor 五因归因

| 值 | 中文 | 说明 | 典型占比 | 改善难度 |
|---|---|---|---|---|
| `price_change` | 采购价格变动 | 食材单价上涨/下降 | 15-30% | 中(议价/换供应商) |
| `usage_overrun` | 用量超标 | 实际用量>BOM标准 | 20-40% | 低(培训+SOP) |
| `waste_loss` | 损耗报废 | 变质/过期/操作失误 | 10-25% | 中(流程改善) |
| `yield_variance` | 出成率偏差 | 切配/烹饪出成率低 | 5-15% | 中(技能培训) |
| `mix_shift` | 销售结构变化 | 高成本菜品占比变化 | 10-30% | 高(菜单策略调整) |

### 14.22 member_tier 会员等级

| 值 | 条件 | 权益 |
|---|---|---|
| `normal` | 注册即享 | 基础积分 |
| `silver` | 累计消费满2000元 | 95折/生日券 |
| `gold` | 累计消费满8000元 | 9折/免排队/生日礼 |
| `platinum` | 累计消费满20000元 | 88折/专属客服/优先订座 |
| `diamond` | 累计消费满50000元 | 85折/私宴定制/年度答谢 |

### 14.23 lifecycle_state 会员生命周期

| 值 | 说明 | 触发条件 | 运营策略 |
|---|---|---|---|
| `lead` | 潜客 | 关注未注册 | 注册引导+首单礼 |
| `registered` | 已注册 | 注册未消费 | 新人券推送 |
| `first_order` | 首单完成 | 第1次消费 | 复购引导(7天内) |
| `repeat` | 活跃顾客 | 30天内≥2次消费 | 常规运营 |
| `high_frequency` | 高频顾客 | 30天内≥5次消费 | VIP预备/专属服务 |
| `vip` | VIP | 高频+高消费 | 尊享服务/私域维护 |
| `at_risk` | 流失预警 | 45天未消费 | 唤醒券/关怀短信 |
| `dormant` | 沉睡 | 90天未消费 | 大额唤醒券 |
| `lost` | 已流失 | 180天未消费 | 停止主动触达 |

### 14.24 rfm_segment RFM细分

| 值 | R | F | M | 运营策略 |
|---|---|---|---|---|
| `champion` | 高 | 高 | 高 | 专属服务, 口碑传播 |
| `loyal` | 高 | 高 | 中 | 提升客单价 |
| `potential_loyal` | 高 | 中 | 高 | 增加频次 |
| `new_customer` | 高 | 低 | 低 | 复购引导 |
| `promising` | 中 | 中 | 中 | 常规运营 |
| `needs_attention` | 中 | 低 | 中 | 精准触达 |
| `about_to_sleep` | 低 | 中 | 中 | 唤醒活动 |
| `at_risk` | 低 | 高 | 高 | 紧急挽回 |
| `cant_lose` | 低 | 高 | 低 | VIP关怀 |
| `hibernating` | 低 | 低 | 低 | 低成本触达/放弃 |

---

## 15. 行业基准参数

### 15.1 成本结构基准（占营收%）

| 指标 | 中餐正餐 | 快餐 | 火锅 | 烘焙 | 茶饮 | 说明 |
|------|----------|------|------|------|------|------|
| 食材成本率 | 30-35% | 28-33% | 35-42% | 25-30% | 15-22% | 核心变量 |
| 人力成本率 | 22-28% | 25-32% | 18-24% | 20-28% | 15-22% | 含社保 |
| 房租成本率 | 8-15% | 10-18% | 8-12% | 12-20% | 15-25% | 商场更高 |
| 水电气 | 3-5% | 3-5% | 4-6% | 4-6% | 2-4% | |
| 折旧摊销 | 3-5% | 2-4% | 3-5% | 3-5% | 2-4% | |
| 营销费用 | 2-5% | 3-8% | 2-5% | 3-6% | 5-12% | 含平台佣金 |
| **净利润率** | **8-15%** | **5-12%** | **8-15%** | **10-18%** | **15-25%** | **健康区间** |

### 15.2 运营效率基准

| 指标 | 优秀 | 良好 | 及格 | 需关注 | 单位 |
|------|------|------|------|--------|------|
| 翻台率(正餐午市) | ≥2.5 | 2.0-2.5 | 1.5-2.0 | <1.5 | 次 |
| 翻台率(正餐晚市) | ≥2.0 | 1.5-2.0 | 1.0-1.5 | <1.0 | 次 |
| 人效(月营收/人) | ≥3.5万 | 2.5-3.5万 | 1.8-2.5万 | <1.8万 | 元/人 |
| 坪效(月营收/㎡) | ≥2000 | 1200-2000 | 800-1200 | <800 | 元/㎡ |
| 出餐速度(午市) | ≤12min | 12-18min | 18-25min | >25min | 分钟 |
| 客诉率 | <0.5% | 0.5-1% | 1-2% | >2% | 占订单比 |
| 好评率(外卖) | ≥4.8 | 4.5-4.8 | 4.2-4.5 | <4.2 | 分(满5) |
| 员工月流失率 | <3% | 3-5% | 5-8% | >8% | |
| 食材损耗率 | <2% | 2-3% | 3-5% | >5% | 占食材成本 |
| 盘点差异率 | <0.5% | 0.5-1% | 1-2% | >2% | 占食材成本 |

### 15.3 成本真相严重度阈值

| 差异(pp) | 级别 | 颜色 | 动作 |
|-----------|------|------|------|
| ≤1.0 | ok | 绿色 | 无需处理 |
| 1.0-2.0 | watch | 蓝色 | 关注,下周复查 |
| 2.0-3.0 | warning | 橙色 | 当天排查原因 |
| >3.0 | critical | 红色 | 立即处理,4h内反馈 |

### 15.4 价格基准分类阈值

| 百分位排名 | 分类 | 说明 |
|-----------|------|------|
| ≤25% | cheap | 买便宜了 |
| 25-60% | fair | 合理区间 |
| 60-85% | expensive | 偏贵,建议议价 |
| >85% | very_expensive | 明显偏贵,立即换供应商 |

### 15.5 食材保质期参考

| 食材 | 冷藏(天) | 冷冻(天) | 常温(天) | 备注 |
|------|----------|----------|----------|------|
| 鲜鱼(活) | 1-2 | 30-90 | - | 活养池最佳 |
| 鲜虾 | 1-2 | 60-90 | - | |
| 猪肉(鲜) | 2-3 | 90-180 | - | |
| 鸡肉(鲜) | 1-2 | 90-180 | - | |
| 叶菜 | 2-3 | - | 0.5 | 最易损耗 |
| 根茎菜 | 7-14 | - | 3-5 | 土豆/胡萝卜 |
| 豆腐 | 2-3 | 30 | 0.5 | |
| 大米 | - | - | 90-180 | 干燥通风 |
| 食用油 | - | - | 365 | 避光密封 |
| 酱油/醋 | - | - | 180-365 | 开封后冷藏 |
| 牛奶 | 5-7 | - | - | UHT可常温 |
| 面粉 | - | - | 90-180 | 防潮 |

---

## 16. 数据采集频率规范

| 数据类型 | 采集频率 | 采集方式 | 延迟容忍 | 优先级 |
|----------|----------|----------|----------|--------|
| 订单/销售 | 实时 | POS对接/Webhook | <5分钟 | P0 |
| 库存出入库 | 实时 | POS领料/手动登记 | <30分钟 | P0 |
| 采购入库 | 每批次 | 收货扫码/手动 | <2小时 | P0 |
| 损耗登记 | 发生时 | APP拍照登记 | <4小时 | P0 |
| 考勤打卡 | 实时 | 指纹/人脸/企微 | <1分钟 | P1 |
| 库存盘点 | 每日闭店 | 手动盘点+拍照 | 次日08:00前 | P0 |
| 采购价格 | 每次下单 | 采购单录入 | <24小时 | P1 |
| 会员消费 | 实时 | POS联动 | <5分钟 | P1 |
| 排班计划 | 每日 | 系统生成/人工调整 | 前一天18:00 | P1 |
| 财务对账 | 每日 | 自动/人工核对 | 次日12:00前 | P2 |
| 供应商评分 | 每月 | 系统计算 | 次月5号前 | P2 |
| 营业日报 | 每日 | 自动汇总 | 次日08:00前 | P0 |
| 成本真相日报 | 每日 | 自动计算 | 次日09:00前 | P0 |

---

## 附录: 数据关系图(ER概要)

```
集团(groups)
 └── 品牌(brands) ──┐
      └── 门店(stores)│
           ├── 员工(employees)
           │    └── 考勤(attendance_logs)
           │    └── 班次(shifts) ← 排班(schedules)
           ├── 库存(inventory_items)
           │    ├── 批次(inventory_batches) ← 采购单明细(po_items) ← 采购单(purchase_orders) ← 供应商(suppliers)
           │    ├── 流水(inventory_transactions)
           │    └── 盘点(inventory_counts)
           ├── 订单(orders)
           │    └── 订单明细(order_items) → 菜品SKU(dish_masters)
           ├── 损耗(waste_events) → 食材(ingredient_masters)
           ├── 预订(reservations)
           ├── 成本日报(cost_truth_daily)
           │    ├── 菜品明细(cost_truth_dish_detail)
           │    └── 五因归因(cost_variance_attribution)
           ├── 经营日报(daily_pnl_summary)
           ├── 人力快照(labor_cost_snapshots)
           └── 决策(decision_lifecycle)
      │
      ├── 菜品SKU(dish_masters) → 食材主档(ingredient_masters)
      │    ├── 品牌定价(brand_menus)
      │    ├── 门店定价(store_menus)
      │    └── BOM配方(bom_templates)
      │         └── 配方明细(bom_items) → 食材主档
      ├── 渠道配置(sales_channel_configs)
      └── 供应商报价(supplier_quotes) → 食材主档

会员(members) ← 品牌级, 跨门店通用
 └── RFM快照(member_rfm_snapshots)

价格基准池(price_benchmark_pool) ← 全网匿名, 跨集团
 └── 基准报告(price_benchmark_reports) ← 按门店出
```

---

> **版本记录**
> - v1.0 (2026-03-12): 初版, 覆盖13大模块, 24类枚举, 行业基准参数
