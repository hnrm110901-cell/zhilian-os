"""
行业成本基准线种子数据

基于 2025 年中国餐饮行业白皮书 + 头部连锁企业公开数据整理。
每个菜系 × 每个指标提供 p25/p50/p75/p90 四档基准。

用途：
  - CostTruth Engine 自动对比门店成本率 vs 行业基准
  - Agent 决策建议中引用"行业标杆"数据
  - 前端 BFF 展示"你在行业中的位置"

运行方式：
    python -m src.seeds.industry_benchmarks_seed
"""

import asyncio
import uuid
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.constants.industry_standards import CuisineType

logger = structlog.get_logger()

# ─────────────────────────────────────────────────────────────────────────────
# 基准数据来源标注
# ─────────────────────────────────────────────────────────────────────────────
DATA_SOURCE = "2025中国餐饮行业白皮书 + 头部连锁财报 + 屯象客户数据"
VALID_UNTIL = datetime(2027, 12, 31)  # 基准数据有效期至 2027 年底

# ─────────────────────────────────────────────────────────────────────────────
# 行业基准数据
# 格式: (industry_type, metric_name, category, p25, p50, p75, p90, unit, direction, description)
# direction: lower_better = 越低越好, higher_better = 越高越好
# ─────────────────────────────────────────────────────────────────────────────

BENCHMARKS = [
    # ═══════════════════════════════════════════════════════════════════════════
    # 湘菜 (hunan) — 种子客户"尝在一起"所属菜系
    # ═══════════════════════════════════════════════════════════════════════════
    (CuisineType.HUNAN, "food_cost_ratio", "cost", 30.0, 33.0, 36.0, 38.0, "%", "lower_better",
     "食材成本占营收比，湘菜主料猪肉/辣椒/淡水鱼为主，季节波动中等"),
    (CuisineType.HUNAN, "labor_cost_ratio", "cost", 19.0, 22.0, 25.0, 28.0, "%", "lower_better",
     "人力成本占营收比，含社保公积金"),
    (CuisineType.HUNAN, "rent_cost_ratio", "cost", 7.0, 10.0, 13.0, 16.0, "%", "lower_better",
     "租金成本占营收比"),
    (CuisineType.HUNAN, "utility_cost_ratio", "cost", 2.5, 3.5, 4.5, 5.5, "%", "lower_better",
     "水电燃气成本占营收比"),
    (CuisineType.HUNAN, "waste_rate", "waste", 2.0, 3.5, 5.0, 7.0, "%", "lower_better",
     "食材损耗率（报损金额/食材总采购额）"),
    (CuisineType.HUNAN, "table_turnover_rate", "efficiency", 2.0, 2.8, 3.5, 4.2, "次/天", "higher_better",
     "日均翻台率"),
    (CuisineType.HUNAN, "avg_ticket_size", "traffic", 45.0, 58.0, 72.0, 90.0, "元/人", "higher_better",
     "客均消费"),
    (CuisineType.HUNAN, "staff_turnover_monthly", "efficiency", 3.0, 5.0, 8.0, 12.0, "%", "lower_better",
     "月度员工离职率"),
    (CuisineType.HUNAN, "food_safety_pass_rate", "compliance", 85.0, 92.0, 96.0, 99.0, "%", "higher_better",
     "食安检查通过率"),
    (CuisineType.HUNAN, "gross_profit_margin", "cost", 55.0, 62.0, 67.0, 72.0, "%", "higher_better",
     "毛利率（(营收-食材成本)/营收）"),
    (CuisineType.HUNAN, "net_profit_margin", "cost", 3.0, 8.0, 12.0, 16.0, "%", "higher_better",
     "净利润率"),

    # ═══════════════════════════════════════════════════════════════════════════
    # 海鲜 (seafood) — 种子客户"徐记海鲜"所属菜系
    # ═══════════════════════════════════════════════════════════════════════════
    (CuisineType.SEAFOOD, "food_cost_ratio", "cost", 36.0, 40.0, 44.0, 48.0, "%", "lower_better",
     "海鲜食材成本高，鲜活海鲜损耗大"),
    (CuisineType.SEAFOOD, "labor_cost_ratio", "cost", 17.0, 20.0, 23.0, 26.0, "%", "lower_better",
     "海鲜加工需要专业技能，人工成本中等偏高"),
    (CuisineType.SEAFOOD, "rent_cost_ratio", "cost", 6.0, 9.0, 12.0, 15.0, "%", "lower_better",
     "海鲜餐厅通常选址中高端商圈"),
    (CuisineType.SEAFOOD, "utility_cost_ratio", "cost", 3.0, 4.0, 5.0, 6.0, "%", "lower_better",
     "海鲜鱼缸/冷库耗电高"),
    (CuisineType.SEAFOOD, "waste_rate", "waste", 3.0, 5.0, 7.0, 10.0, "%", "lower_better",
     "活鲜死亡率+加工损耗率"),
    (CuisineType.SEAFOOD, "table_turnover_rate", "efficiency", 1.5, 2.2, 2.8, 3.5, "次/天", "higher_better",
     "海鲜正餐翻台率偏低"),
    (CuisineType.SEAFOOD, "avg_ticket_size", "traffic", 80.0, 120.0, 160.0, 220.0, "元/人", "higher_better",
     "海鲜客单价高"),
    (CuisineType.SEAFOOD, "staff_turnover_monthly", "efficiency", 3.0, 5.0, 7.0, 10.0, "%", "lower_better",
     "月度员工离职率"),
    (CuisineType.SEAFOOD, "food_safety_pass_rate", "compliance", 88.0, 94.0, 97.0, 99.0, "%", "higher_better",
     "海鲜食安要求更严格"),
    (CuisineType.SEAFOOD, "gross_profit_margin", "cost", 48.0, 55.0, 60.0, 65.0, "%", "higher_better",
     "海鲜毛利率中等，靠客单价撑利润"),
    (CuisineType.SEAFOOD, "net_profit_margin", "cost", 2.0, 6.0, 10.0, 14.0, "%", "higher_better",
     "净利润率"),

    # ═══════════════════════════════════════════════════════════════════════════
    # 川菜 (sichuan)
    # ═══════════════════════════════════════════════════════════════════════════
    (CuisineType.SICHUAN, "food_cost_ratio", "cost", 28.0, 32.0, 35.0, 38.0, "%", "lower_better",
     "川菜调料占比高但单价低，主料以猪肉/牛肉为主"),
    (CuisineType.SICHUAN, "labor_cost_ratio", "cost", 18.0, 21.0, 24.0, 27.0, "%", "lower_better",
     "川菜标准化程度较高，人力成本可控"),
    (CuisineType.SICHUAN, "waste_rate", "waste", 2.0, 3.0, 4.5, 6.0, "%", "lower_better",
     "川菜食材标准化好，损耗相对较低"),
    (CuisineType.SICHUAN, "table_turnover_rate", "efficiency", 2.2, 3.0, 3.8, 4.5, "次/天", "higher_better",
     "川菜出餐快，翻台率高"),
    (CuisineType.SICHUAN, "avg_ticket_size", "traffic", 40.0, 55.0, 68.0, 85.0, "元/人", "higher_better",
     "川菜客单价中等"),
    (CuisineType.SICHUAN, "gross_profit_margin", "cost", 58.0, 65.0, 70.0, 75.0, "%", "higher_better",
     "川菜毛利率较高"),
    (CuisineType.SICHUAN, "net_profit_margin", "cost", 4.0, 9.0, 13.0, 17.0, "%", "higher_better",
     "净利润率"),

    # ═══════════════════════════════════════════════════════════════════════════
    # 火锅 (hotpot)
    # ═══════════════════════════════════════════════════════════════════════════
    (CuisineType.HOTPOT, "food_cost_ratio", "cost", 34.0, 38.0, 42.0, 46.0, "%", "lower_better",
     "火锅食材种类多，鲜切毛肚/鹅肠等高成本"),
    (CuisineType.HOTPOT, "labor_cost_ratio", "cost", 14.0, 18.0, 22.0, 25.0, "%", "lower_better",
     "火锅后厨人力需求少，人力成本行业最低"),
    (CuisineType.HOTPOT, "waste_rate", "waste", 2.0, 3.5, 5.0, 7.0, "%", "lower_better",
     "火锅备料标准化好，但鲜切食材保质期短"),
    (CuisineType.HOTPOT, "table_turnover_rate", "efficiency", 2.0, 2.8, 3.5, 4.5, "次/天", "higher_better",
     "火锅用餐时间长但客单价高"),
    (CuisineType.HOTPOT, "avg_ticket_size", "traffic", 60.0, 85.0, 110.0, 140.0, "元/人", "higher_better",
     "火锅客单价中高"),
    (CuisineType.HOTPOT, "gross_profit_margin", "cost", 50.0, 58.0, 63.0, 68.0, "%", "higher_better",
     "毛利率"),
    (CuisineType.HOTPOT, "net_profit_margin", "cost", 5.0, 10.0, 14.0, 18.0, "%", "higher_better",
     "火锅人力成本低，净利润率行业靠前"),

    # ═══════════════════════════════════════════════════════════════════════════
    # 快餐 (fast_food)
    # ═══════════════════════════════════════════════════════════════════════════
    (CuisineType.FAST_FOOD, "food_cost_ratio", "cost", 26.0, 30.0, 34.0, 37.0, "%", "lower_better",
     "快餐食材标准化程度最高，规模采购优势明显"),
    (CuisineType.FAST_FOOD, "labor_cost_ratio", "cost", 22.0, 25.0, 28.0, 32.0, "%", "lower_better",
     "快餐需要更多一线人手，人力成本占比最高"),
    (CuisineType.FAST_FOOD, "waste_rate", "waste", 1.5, 2.5, 4.0, 5.5, "%", "lower_better",
     "标准化出品，损耗最低"),
    (CuisineType.FAST_FOOD, "table_turnover_rate", "efficiency", 4.0, 6.0, 8.0, 12.0, "次/天", "higher_better",
     "快餐翻台率行业最高"),
    (CuisineType.FAST_FOOD, "avg_ticket_size", "traffic", 18.0, 25.0, 32.0, 42.0, "元/人", "higher_better",
     "快餐客单价低，靠翻台率"),
    (CuisineType.FAST_FOOD, "gross_profit_margin", "cost", 60.0, 66.0, 72.0, 78.0, "%", "higher_better",
     "快餐毛利率高"),
    (CuisineType.FAST_FOOD, "net_profit_margin", "cost", 2.0, 6.0, 10.0, 14.0, "%", "higher_better",
     "净利润率，快餐靠规模取胜"),

    # ═══════════════════════════════════════════════════════════════════════════
    # 粤菜 (cantonese)
    # ═══════════════════════════════════════════════════════════════════════════
    (CuisineType.CANTONESE, "food_cost_ratio", "cost", 32.0, 35.0, 38.0, 42.0, "%", "lower_better",
     "粤菜注重食材品质，成本率中上"),
    (CuisineType.CANTONESE, "labor_cost_ratio", "cost", 20.0, 24.0, 27.0, 30.0, "%", "lower_better",
     "粤菜工序多，对厨师要求高"),
    (CuisineType.CANTONESE, "waste_rate", "waste", 2.5, 4.0, 5.5, 7.5, "%", "lower_better",
     "粤菜食材品种多，损耗控制难度中等"),
    (CuisineType.CANTONESE, "table_turnover_rate", "efficiency", 1.8, 2.5, 3.2, 4.0, "次/天", "higher_better",
     "粤菜正餐翻台率中等"),
    (CuisineType.CANTONESE, "avg_ticket_size", "traffic", 60.0, 80.0, 100.0, 140.0, "元/人", "higher_better",
     "粤菜客单价中高"),
    (CuisineType.CANTONESE, "gross_profit_margin", "cost", 52.0, 60.0, 65.0, 70.0, "%", "higher_better",
     "毛利率"),
    (CuisineType.CANTONESE, "net_profit_margin", "cost", 3.0, 7.0, 11.0, 15.0, "%", "higher_better",
     "净利润率"),

    # ═══════════════════════════════════════════════════════════════════════════
    # 黔菜 (guizhou) — 种子客户"最黔线"所属菜系
    # ═══════════════════════════════════════════════════════════════════════════
    (CuisineType.GUIZHOU, "food_cost_ratio", "cost", 29.0, 32.0, 35.0, 38.0, "%", "lower_better",
     "黔菜食材以酸汤/折耳根/腊肉为特色，原料成本中等"),
    (CuisineType.GUIZHOU, "labor_cost_ratio", "cost", 18.0, 21.0, 24.0, 27.0, "%", "lower_better",
     "黔菜工序相对简单，人力成本中等"),
    (CuisineType.GUIZHOU, "waste_rate", "waste", 2.0, 3.5, 5.0, 6.5, "%", "lower_better",
     "黔菜腌制/发酵类食材保质期长，损耗中等"),
    (CuisineType.GUIZHOU, "table_turnover_rate", "efficiency", 2.0, 2.8, 3.5, 4.2, "次/天", "higher_better",
     "翻台率"),
    (CuisineType.GUIZHOU, "avg_ticket_size", "traffic", 45.0, 60.0, 75.0, 95.0, "元/人", "higher_better",
     "客均消费"),
    (CuisineType.GUIZHOU, "gross_profit_margin", "cost", 56.0, 64.0, 68.0, 73.0, "%", "higher_better",
     "毛利率"),
    (CuisineType.GUIZHOU, "net_profit_margin", "cost", 4.0, 8.0, 12.0, 16.0, "%", "higher_better",
     "净利润率"),

    # ═══════════════════════════════════════════════════════════════════════════
    # 烧烤 (bbq)
    # ═══════════════════════════════════════════════════════════════════════════
    (CuisineType.BBQ, "food_cost_ratio", "cost", 32.0, 35.0, 38.0, 42.0, "%", "lower_better",
     "烧烤食材种类多，串串类损耗大"),
    (CuisineType.BBQ, "labor_cost_ratio", "cost", 16.0, 19.0, 22.0, 25.0, "%", "lower_better",
     "烧烤人力需求适中"),
    (CuisineType.BBQ, "waste_rate", "waste", 2.5, 4.0, 6.0, 8.0, "%", "lower_better",
     "烧烤备料标准化较难，损耗中等偏高"),
    (CuisineType.BBQ, "table_turnover_rate", "efficiency", 1.5, 2.2, 3.0, 3.8, "次/天", "higher_better",
     "烧烤消费时间长，翻台率较低"),
    (CuisineType.BBQ, "avg_ticket_size", "traffic", 50.0, 70.0, 90.0, 120.0, "元/人", "higher_better",
     "烧烤+酒水客单价中高"),
    (CuisineType.BBQ, "gross_profit_margin", "cost", 52.0, 60.0, 65.0, 70.0, "%", "higher_better",
     "毛利率"),
    (CuisineType.BBQ, "net_profit_margin", "cost", 5.0, 10.0, 14.0, 18.0, "%", "higher_better",
     "烧烤租金低+人力低，净利润率不错"),

    # ═══════════════════════════════════════════════════════════════════════════
    # 粉面 (noodle)
    # ═══════════════════════════════════════════════════════════════════════════
    (CuisineType.NOODLE, "food_cost_ratio", "cost", 24.0, 28.0, 32.0, 35.0, "%", "lower_better",
     "粉面主料成本低，辅料简单"),
    (CuisineType.NOODLE, "labor_cost_ratio", "cost", 17.0, 20.0, 23.0, 26.0, "%", "lower_better",
     "粉面操作简单，人力需求少"),
    (CuisineType.NOODLE, "waste_rate", "waste", 1.5, 2.5, 3.5, 5.0, "%", "lower_better",
     "粉面食材保质期较长，损耗低"),
    (CuisineType.NOODLE, "table_turnover_rate", "efficiency", 5.0, 7.0, 9.0, 12.0, "次/天", "higher_better",
     "粉面用餐时间短，翻台率高"),
    (CuisineType.NOODLE, "avg_ticket_size", "traffic", 12.0, 18.0, 25.0, 35.0, "元/人", "higher_better",
     "粉面客单价低"),
    (CuisineType.NOODLE, "gross_profit_margin", "cost", 62.0, 68.0, 74.0, 80.0, "%", "higher_better",
     "粉面毛利率行业最高"),
    (CuisineType.NOODLE, "net_profit_margin", "cost", 3.0, 8.0, 12.0, 16.0, "%", "higher_better",
     "净利润率"),

    # ═══════════════════════════════════════════════════════════════════════════
    # 通用 (general) — 未分类菜系的默认基准
    # ═══════════════════════════════════════════════════════════════════════════
    (CuisineType.GENERAL, "food_cost_ratio", "cost", 30.0, 33.0, 36.0, 40.0, "%", "lower_better",
     "行业综合食材成本率"),
    (CuisineType.GENERAL, "labor_cost_ratio", "cost", 18.0, 22.0, 26.0, 30.0, "%", "lower_better",
     "行业综合人力成本率"),
    (CuisineType.GENERAL, "rent_cost_ratio", "cost", 7.0, 10.0, 13.0, 16.0, "%", "lower_better",
     "行业综合租金成本率"),
    (CuisineType.GENERAL, "utility_cost_ratio", "cost", 2.5, 3.5, 4.5, 5.5, "%", "lower_better",
     "行业综合能源成本率"),
    (CuisineType.GENERAL, "waste_rate", "waste", 2.0, 3.5, 5.0, 7.0, "%", "lower_better",
     "行业综合损耗率"),
    (CuisineType.GENERAL, "table_turnover_rate", "efficiency", 2.0, 3.0, 4.0, 5.5, "次/天", "higher_better",
     "行业综合翻台率"),
    (CuisineType.GENERAL, "avg_ticket_size", "traffic", 35.0, 55.0, 75.0, 100.0, "元/人", "higher_better",
     "行业综合客单价"),
    (CuisineType.GENERAL, "staff_turnover_monthly", "efficiency", 3.0, 5.0, 8.0, 12.0, "%", "lower_better",
     "行业综合月度离职率"),
    (CuisineType.GENERAL, "food_safety_pass_rate", "compliance", 85.0, 92.0, 96.0, 99.0, "%", "higher_better",
     "行业综合食安通过率"),
    (CuisineType.GENERAL, "gross_profit_margin", "cost", 55.0, 62.0, 68.0, 74.0, "%", "higher_better",
     "行业综合毛利率"),
    (CuisineType.GENERAL, "net_profit_margin", "cost", 3.0, 8.0, 12.0, 16.0, "%", "higher_better",
     "行业综合净利润率"),

    # ═══════════════════════════════════════════════════════════════════════════
    # 以下菜系数据量较少，使用 GENERAL 基准微调（确保 CuisineType 全覆盖）
    # 未来有更多实际客户数据后持续精化
    # ═══════════════════════════════════════════════════════════════════════════

    # 鲁菜 (shandong) — 用料讲究，偏正餐
    (CuisineType.SHANDONG, "food_cost_ratio", "cost", 31.0, 34.0, 37.0, 40.0, "%", "lower_better",
     "鲁菜用料考究，食材成本中上"),
    (CuisineType.SHANDONG, "labor_cost_ratio", "cost", 19.0, 22.0, 25.0, 28.0, "%", "lower_better",
     "鲁菜工序复杂，人力成本中等"),
    (CuisineType.SHANDONG, "waste_rate", "waste", 2.5, 4.0, 5.5, 7.0, "%", "lower_better",
     "鲁菜食材品类多，损耗中等"),
    (CuisineType.SHANDONG, "gross_profit_margin", "cost", 54.0, 62.0, 66.0, 71.0, "%", "higher_better",
     "毛利率"),
    (CuisineType.SHANDONG, "net_profit_margin", "cost", 3.0, 7.0, 11.0, 15.0, "%", "higher_better",
     "净利润率"),

    # 苏菜/淮扬菜 (jiangsu) — 精工细作，客单价高
    (CuisineType.JIANGSU, "food_cost_ratio", "cost", 32.0, 35.0, 38.0, 42.0, "%", "lower_better",
     "淮扬菜注重食材精选，成本中上"),
    (CuisineType.JIANGSU, "labor_cost_ratio", "cost", 21.0, 24.0, 27.0, 30.0, "%", "lower_better",
     "淮扬菜刀工精细，人力成本较高"),
    (CuisineType.JIANGSU, "waste_rate", "waste", 2.0, 3.5, 5.0, 6.5, "%", "lower_better",
     "损耗率"),
    (CuisineType.JIANGSU, "gross_profit_margin", "cost", 52.0, 60.0, 65.0, 70.0, "%", "higher_better",
     "毛利率"),
    (CuisineType.JIANGSU, "net_profit_margin", "cost", 2.0, 6.0, 10.0, 14.0, "%", "higher_better",
     "净利润率"),

    # 浙菜 (zhejiang) — 注重鲜味
    (CuisineType.ZHEJIANG, "food_cost_ratio", "cost", 31.0, 34.0, 37.0, 40.0, "%", "lower_better",
     "浙菜用料较讲究，食材成本中上"),
    (CuisineType.ZHEJIANG, "labor_cost_ratio", "cost", 20.0, 23.0, 26.0, 29.0, "%", "lower_better",
     "浙菜工序适中"),
    (CuisineType.ZHEJIANG, "waste_rate", "waste", 2.0, 3.5, 5.0, 6.5, "%", "lower_better",
     "损耗率"),
    (CuisineType.ZHEJIANG, "gross_profit_margin", "cost", 54.0, 62.0, 66.0, 71.0, "%", "higher_better",
     "毛利率"),
    (CuisineType.ZHEJIANG, "net_profit_margin", "cost", 3.0, 7.0, 11.0, 15.0, "%", "higher_better",
     "净利润率"),

    # 闽菜 (fujian) — 汤类为主，海鲜较多
    (CuisineType.FUJIAN, "food_cost_ratio", "cost", 33.0, 36.0, 39.0, 43.0, "%", "lower_better",
     "闽菜海鲜/高汤比重大，食材成本偏高"),
    (CuisineType.FUJIAN, "labor_cost_ratio", "cost", 19.0, 22.0, 25.0, 28.0, "%", "lower_better",
     "人力成本中等"),
    (CuisineType.FUJIAN, "waste_rate", "waste", 2.5, 4.0, 5.5, 7.5, "%", "lower_better",
     "海鲜类损耗偏高"),
    (CuisineType.FUJIAN, "gross_profit_margin", "cost", 50.0, 58.0, 63.0, 68.0, "%", "higher_better",
     "毛利率"),
    (CuisineType.FUJIAN, "net_profit_margin", "cost", 2.0, 6.0, 10.0, 14.0, "%", "higher_better",
     "净利润率"),

    # 徽菜 (anhui) — 重油重色，食材保质期较长
    (CuisineType.ANHUI, "food_cost_ratio", "cost", 29.0, 32.0, 35.0, 38.0, "%", "lower_better",
     "徽菜食材以腌制/干货为主，成本中等"),
    (CuisineType.ANHUI, "labor_cost_ratio", "cost", 18.0, 21.0, 24.0, 27.0, "%", "lower_better",
     "人力成本中等"),
    (CuisineType.ANHUI, "waste_rate", "waste", 1.5, 3.0, 4.5, 6.0, "%", "lower_better",
     "腌制/干货食材保质期长，损耗较低"),
    (CuisineType.ANHUI, "gross_profit_margin", "cost", 56.0, 64.0, 68.0, 73.0, "%", "higher_better",
     "毛利率"),
    (CuisineType.ANHUI, "net_profit_margin", "cost", 4.0, 8.0, 12.0, 16.0, "%", "higher_better",
     "净利润率"),

    # 茶点/早茶 (dim_sum) — 品种极多，手工为主
    (CuisineType.DIM_SUM, "food_cost_ratio", "cost", 30.0, 33.0, 36.0, 40.0, "%", "lower_better",
     "茶点食材品种多但单价低"),
    (CuisineType.DIM_SUM, "labor_cost_ratio", "cost", 24.0, 27.0, 30.0, 34.0, "%", "lower_better",
     "茶点手工制作多，人力成本行业最高"),
    (CuisineType.DIM_SUM, "waste_rate", "waste", 3.0, 4.5, 6.0, 8.0, "%", "lower_better",
     "品种多导致每样备量少，损耗中等偏高"),
    (CuisineType.DIM_SUM, "gross_profit_margin", "cost", 55.0, 62.0, 67.0, 72.0, "%", "higher_better",
     "毛利率"),
    (CuisineType.DIM_SUM, "net_profit_margin", "cost", 2.0, 5.0, 9.0, 13.0, "%", "higher_better",
     "净利润率较低（人力拉高）"),

    # 团餐/食堂 (cafeteria) — 量大价低，标准化极高
    (CuisineType.CAFETERIA, "food_cost_ratio", "cost", 35.0, 40.0, 44.0, 48.0, "%", "lower_better",
     "团餐食材成本占比高（客单低）"),
    (CuisineType.CAFETERIA, "labor_cost_ratio", "cost", 15.0, 18.0, 21.0, 24.0, "%", "lower_better",
     "团餐标准化极高，人力成本最低"),
    (CuisineType.CAFETERIA, "waste_rate", "waste", 3.0, 5.0, 7.0, 10.0, "%", "lower_better",
     "团餐大锅菜剩余较多，损耗偏高"),
    (CuisineType.CAFETERIA, "gross_profit_margin", "cost", 45.0, 52.0, 58.0, 64.0, "%", "higher_better",
     "毛利率偏低"),
    (CuisineType.CAFETERIA, "net_profit_margin", "cost", 3.0, 6.0, 10.0, 14.0, "%", "higher_better",
     "净利润率"),

    # 烘焙 (bakery) — 高毛利，损耗高
    (CuisineType.BAKERY, "food_cost_ratio", "cost", 22.0, 26.0, 30.0, 34.0, "%", "lower_better",
     "烘焙原料成本低（面粉/黄油/糖）"),
    (CuisineType.BAKERY, "labor_cost_ratio", "cost", 20.0, 24.0, 28.0, 32.0, "%", "lower_better",
     "烘焙需要技术工人，人力成本中上"),
    (CuisineType.BAKERY, "waste_rate", "waste", 4.0, 6.0, 8.0, 12.0, "%", "lower_better",
     "烘焙产品保质期短，报废率行业最高"),
    (CuisineType.BAKERY, "gross_profit_margin", "cost", 62.0, 70.0, 75.0, 80.0, "%", "higher_better",
     "烘焙毛利率行业顶尖"),
    (CuisineType.BAKERY, "net_profit_margin", "cost", 3.0, 8.0, 13.0, 18.0, "%", "higher_better",
     "净利润率"),
]

# ─────────────────────────────────────────────────────────────────────────────
# RuleCategory 映射（category string → RuleCategory enum）
# ─────────────────────────────────────────────────────────────────────────────
CATEGORY_MAP = {
    "cost": "cost",
    "waste": "waste",
    "efficiency": "efficiency",
    "traffic": "traffic",
    "compliance": "compliance",
    "benchmark": "benchmark",
}


async def seed_industry_benchmarks(session: AsyncSession) -> dict:
    """写入行业基准种子数据（幂等：按 industry_type + metric_name 判断）"""
    from src.models.knowledge_rule import IndustryBenchmark, RuleCategory

    inserted = 0
    skipped = 0

    for row in BENCHMARKS:
        industry_type, metric_name, cat_str, p25, p50, p75, p90, unit, direction, description = row

        # 检查是否已存在
        result = await session.execute(
            select(IndustryBenchmark).where(
                IndustryBenchmark.industry_type == industry_type.value,
                IndustryBenchmark.metric_name == metric_name,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            skipped += 1
            continue

        category = RuleCategory(CATEGORY_MAP.get(cat_str, "benchmark"))

        benchmark = IndustryBenchmark(
            id=uuid.uuid4(),
            industry_type=industry_type.value,
            metric_name=metric_name,
            metric_category=category,
            p25_value=p25,
            p50_value=p50,
            p75_value=p75,
            p90_value=p90,
            unit=unit,
            direction=direction,
            data_source=DATA_SOURCE,
            sample_size=500,
            valid_until=VALID_UNTIL,
            description=description,
        )
        session.add(benchmark)
        inserted += 1
        logger.info("写入行业基准", industry_type=industry_type.value, metric=metric_name)

    await session.commit()

    return {"inserted": inserted, "skipped": skipped, "total": len(BENCHMARKS)}


async def main():
    """独立运行入口"""
    import os
    from dotenv import load_dotenv

    load_dotenv()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL 环境变量未设置")

    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql+psycopg2://"):
        database_url = database_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url, echo=False)
    AsyncSession_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSession_() as session:
        result = await seed_industry_benchmarks(session)

    await engine.dispose()

    print(f"\n行业基准种子数据写入完成:")
    print(f"  新增: {result['inserted']}, 跳过: {result['skipped']}, 总计: {result['total']}")


if __name__ == "__main__":
    asyncio.run(main())
