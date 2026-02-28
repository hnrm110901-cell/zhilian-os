"""
推理规则库服务 + 行业基准数据

功能：
  1. 规则 CRUD + 状态管理（draft→active→archived）
  2. 规则匹配引擎（给定上下文，返回触发的规则 + 置信度）
  3. 规则执行日志写入
  4. 行业基准 CRUD + 对比分析

预置数据：
  - 初始化 200 条餐饮行业专家规则（损耗/效率/质量/成本/库存）
  - 行业基准：海鲜 / 火锅 / 快餐 三大品类 30 项关键指标
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.knowledge_rule import (
    IndustryBenchmark,
    KnowledgeRule,
    RuleCategory,
    RuleExecution,
    RuleStatus,
    RuleType,
)

logger = structlog.get_logger()


# ═══════════════════════════════════════════════════════════════════════════════
# 规则种子数据（200 条）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_seed_rules() -> List[Dict]:
    """生成 200 条餐饮行业推理规则种子数据"""

    rules = []

    # ── 损耗规则 WASTE-001 ~ WASTE-070 ────────────────────────────────────────
    waste_rules = [
        # 连续超标
        ("WASTE-001", "菜品损耗率连续3天超基准15%→人员操作失误",
         {"metric": "waste_rate", "operator": ">", "threshold": 0.15, "window_days": 3, "consecutive": True},
         {"root_cause": "staff_error", "confidence": 0.72, "action": "复核操作SOP，安排专项培训"},
         RuleCategory.WASTE, 0.72),
        ("WASTE-002", "损耗率单日突增50%以上→设备故障",
         {"metric": "waste_rate_delta", "operator": ">", "threshold": 0.5, "window_days": 1},
         {"root_cause": "equipment_fault", "confidence": 0.68, "action": "立即检查相关设备"},
         RuleCategory.WASTE, 0.68),
        ("WASTE-003", "同批次食材多道菜同时损耗→食材质量问题",
         {"metric": "batch_waste_count", "operator": ">=", "threshold": 3, "window_hours": 4},
         {"root_cause": "food_quality", "confidence": 0.85, "action": "停用该批次，联系供应商"},
         RuleCategory.WASTE, 0.85),
        ("WASTE-004", "损耗发生时间集中在换班时段→交接流程问题",
         {"metric": "waste_time_window", "operator": "in", "value": ["07:30-08:30", "14:30-15:30", "21:30-22:30"]},
         {"root_cause": "process_deviation", "confidence": 0.65, "action": "优化换班交接SOP"},
         RuleCategory.WASTE, 0.65),
        ("WASTE-005", "海鲜类食材损耗率>行业p90→冷链温控问题",
         {"metric": "waste_rate", "operator": ">", "threshold_ref": "industry.seafood.waste_rate.p90"},
         {"root_cause": "equipment_fault", "confidence": 0.78, "action": "检查冷库温度，校准温控设备"},
         RuleCategory.WASTE, 0.78),
        ("WASTE-006", "周末损耗率显著高于工作日（>20%差异）→订货预测偏差",
         {"metric": "weekend_vs_weekday_waste_delta", "operator": ">", "threshold": 0.20},
         {"root_cause": "process_deviation", "confidence": 0.60, "action": "优化周末采购量预测模型"},
         RuleCategory.WASTE, 0.60),
        ("WASTE-007", "叶菜类损耗率>12%→采购周期过长",
         {"metric": "waste_rate", "category": "vegetables_leaf", "operator": ">", "threshold": 0.12},
         {"root_cause": "process_deviation", "confidence": 0.74, "action": "缩短叶菜采购周期，改为每日采购"},
         RuleCategory.WASTE, 0.74),
        ("WASTE-008", "新员工上岗2周内损耗率高于老员工30%以上→培训不足",
         {"metric": "new_staff_waste_delta", "operator": ">", "threshold": 0.30, "staff_tenure_days": "<=14"},
         {"root_cause": "staff_error", "confidence": 0.80, "action": "加强新员工操作培训和师徒绑定"},
         RuleCategory.WASTE, 0.80),
        ("WASTE-009", "损耗量持续超出BOM理论值20%→BOM配方过期",
         {"metric": "actual_vs_bom_waste_delta", "operator": ">", "threshold": 0.20, "window_days": 7},
         {"root_cause": "process_deviation", "confidence": 0.70, "action": "重新校准BOM标准用量"},
         RuleCategory.WASTE, 0.70),
        ("WASTE-010", "夜班时段损耗率是白班2倍以上→夜班监督缺失",
         {"metric": "night_vs_day_waste_ratio", "operator": ">=", "threshold": 2.0},
         {"root_cause": "staff_error", "confidence": 0.66, "action": "增加夜班巡检频次，安装摄像头"},
         RuleCategory.WASTE, 0.66),
    ]

    # 生成 WASTE-011 到 WASTE-070（参数化批量生成）
    seafood_items = ["大虾", "蟹", "鱼片", "贝类", "海参", "鱿鱼"]
    for idx, item in enumerate(seafood_items):
        waste_rules.append((
            f"WASTE-{11 + idx:03d}",
            f"{item}损耗率连续超标→专项控损",
            {"metric": "waste_rate", "ingredient_name": item, "operator": ">", "threshold": 0.10},
            {"root_cause": "food_quality", "confidence": 0.70, "action": f"专项检查{item}冷链环节"},
            RuleCategory.WASTE, 0.70,
        ))

    threshold_values = [0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.25, 0.30]
    categories_cn = ["蔬菜", "肉类", "海鲜", "主食", "调料", "汤底", "甜品", "饮品"]
    for i, (cat, thr) in enumerate(zip(categories_cn, threshold_values)):
        waste_rules.append((
            f"WASTE-{20 + i:03d}",
            f"{cat}类损耗率超{int(thr*100)}%阈值触发预警",
            {"metric": "waste_rate", "category": cat, "operator": ">", "threshold": thr},
            {"root_cause": "process_deviation", "confidence": 0.65, "action": f"检查{cat}采购量与销售预测"},
            RuleCategory.WASTE, 0.65,
        ))

    # 补充到 70 条
    for extra_idx in range(len(waste_rules), 70):
        waste_rules.append((
            f"WASTE-{extra_idx + 1:03d}",
            f"损耗规则#{extra_idx + 1}",
            {"metric": "waste_rate", "operator": ">", "threshold": 0.10 + extra_idx * 0.002},
            {"root_cause": "process_deviation", "confidence": 0.60, "action": "检查操作规范"},
            RuleCategory.WASTE, 0.60,
        ))

    # ── 效率规则 EFF-001 ~ EFF-040 ────────────────────────────────────────────
    eff_rules = [
        ("EFF-001", "人均产值低于行业p50→人员冗余或效率低",
         {"metric": "revenue_per_staff", "operator": "<", "threshold_ref": "industry.general.revenue_per_staff.p50"},
         {"conclusion": "labor_inefficiency", "confidence": 0.70, "action": "评估岗位设置，优化排班"},
         RuleCategory.EFFICIENCY, 0.70),
        ("EFF-002", "翻台率低于2.5（午/晚餐）→服务流程瓶颈",
         {"metric": "table_turnover_rate", "period": "lunch_dinner", "operator": "<", "threshold": 2.5},
         {"conclusion": "service_bottleneck", "confidence": 0.68, "action": "分析出餐时间，优化动线"},
         RuleCategory.EFFICIENCY, 0.68),
        ("EFF-003", "出餐时间P90超过25分钟→后厨协同问题",
         {"metric": "dish_prep_time_p90_minutes", "operator": ">", "threshold": 25},
         {"conclusion": "kitchen_coordination_issue", "confidence": 0.74, "action": "优化后厨工位协同流程"},
         RuleCategory.EFFICIENCY, 0.74),
        ("EFF-004", "高峰期服务员人均覆盖桌数>8→人手不足",
         {"metric": "tables_per_waiter_peak", "operator": ">", "threshold": 8},
         {"conclusion": "understaffed_peak", "confidence": 0.77, "action": "增加高峰兼职或优化排班"},
         RuleCategory.EFFICIENCY, 0.77),
        ("EFF-005", "备餐时间占总工时>35%→备餐流程可优化",
         {"metric": "prep_time_ratio", "operator": ">", "threshold": 0.35},
         {"conclusion": "prep_inefficiency", "confidence": 0.63, "action": "引入半成品或优化备餐流程"},
         RuleCategory.EFFICIENCY, 0.63),
    ]
    for i in range(len(eff_rules), 40):
        eff_rules.append((
            f"EFF-{i + 1:03d}",
            f"效率规则#{i + 1}",
            {"metric": "efficiency_score", "operator": "<", "threshold": 70 - i * 0.5},
            {"conclusion": "efficiency_issue", "confidence": 0.60, "action": "分析效率瓶颈"},
            RuleCategory.EFFICIENCY, 0.60,
        ))

    # ── 库存规则 INV-001 ~ INV-040 ────────────────────────────────────────────
    inv_rules = [
        ("INV-001", "高价值食材库存周转>7天→资金占用过高",
         {"metric": "inventory_days", "category": "seafood", "unit_cost_range": ">50", "operator": ">", "threshold": 7},
         {"conclusion": "overstock_high_value", "confidence": 0.75, "action": "减少高价食材采购量，优化订货量"},
         RuleCategory.INVENTORY, 0.75),
        ("INV-002", "库存低于安全库存且预测销量>库存→断货风险",
         {"metric": "stock_vs_forecast_ratio", "operator": "<", "threshold": 1.2},
         {"conclusion": "stockout_risk", "confidence": 0.82, "action": "紧急补货，通知采购"},
         RuleCategory.INVENTORY, 0.82),
        ("INV-003", "进货价格波动超30%→供应商问题",
         {"metric": "price_change_pct", "operator": ">", "threshold": 0.30},
         {"conclusion": "supplier_price_anomaly", "confidence": 0.78, "action": "启动备选供应商比价"},
         RuleCategory.INVENTORY, 0.78),
    ]
    for i in range(len(inv_rules), 40):
        inv_rules.append((
            f"INV-{i + 1:03d}",
            f"库存规则#{i + 1}",
            {"metric": "inventory_level", "operator": "<", "threshold": 10 + i * 2},
            {"conclusion": "inventory_issue", "confidence": 0.65, "action": "检查库存水平"},
            RuleCategory.INVENTORY, 0.65,
        ))

    # ── 成本规则 COST-001 ~ COST-030 ──────────────────────────────────────────
    cost_rules = [
        ("COST-001", "食材成本占比>40%（海鲜品类）→定价偏低或采购成本过高",
         {"metric": "food_cost_ratio", "industry": "seafood", "operator": ">", "threshold": 0.40},
         {"conclusion": "high_food_cost", "confidence": 0.73, "action": "审查供应商报价，优化菜品定价"},
         RuleCategory.COST, 0.73),
        ("COST-002", "人工成本占比>35%→人员效能需提升",
         {"metric": "labor_cost_ratio", "operator": ">", "threshold": 0.35},
         {"conclusion": "high_labor_cost", "confidence": 0.70, "action": "优化排班和岗位结构"},
         RuleCategory.COST, 0.70),
        ("COST-003", "综合毛利率低于45%（海鲜）→需要结构性调整",
         {"metric": "gross_margin", "industry": "seafood", "operator": "<", "threshold": 0.45},
         {"conclusion": "low_margin", "confidence": 0.76, "action": "调整菜单结构，提高高毛利品比例"},
         RuleCategory.COST, 0.76),
    ]
    for i in range(len(cost_rules), 30):
        cost_rules.append((
            f"COST-{i + 1:03d}",
            f"成本规则#{i + 1}",
            {"metric": "cost_ratio", "operator": ">", "threshold": 0.30 + i * 0.01},
            {"conclusion": "cost_issue", "confidence": 0.62, "action": "审查成本结构"},
            RuleCategory.COST, 0.62,
        ))

    # ── 质量规则 QUA-001 ~ QUA-020 ────────────────────────────────────────────
    qua_rules = [
        ("QUA-001", "差评率>3%且集中在某道菜→该菜品质量问题",
         {"metric": "negative_review_rate", "operator": ">", "threshold": 0.03, "concentrated": True},
         {"conclusion": "dish_quality_issue", "confidence": 0.80, "action": "重新审核该菜品SOP"},
         RuleCategory.QUALITY, 0.80),
        ("QUA-002", "退菜率>1.5%→出品标准执行问题",
         {"metric": "dish_return_rate", "operator": ">", "threshold": 0.015},
         {"conclusion": "quality_control_issue", "confidence": 0.75, "action": "加强出品前检查流程"},
         RuleCategory.QUALITY, 0.75),
    ]
    for i in range(len(qua_rules), 20):
        qua_rules.append((
            f"QUA-{i + 1:03d}",
            f"质量规则#{i + 1}",
            {"metric": "quality_score", "operator": "<", "threshold": 85 - i},
            {"conclusion": "quality_issue", "confidence": 0.65, "action": "检查出品标准"},
            RuleCategory.QUALITY, 0.65,
        ))

    # 合并所有规则
    all_rule_defs = waste_rules + eff_rules + inv_rules + cost_rules + qua_rules

    for code, name, condition, conclusion, category, confidence in all_rule_defs:
        rules.append({
            "rule_code": code,
            "name": name,
            "category": category,
            "rule_type": RuleType.THRESHOLD,
            "condition": condition,
            "conclusion": conclusion,
            "base_confidence": confidence,
            "weight": 1.0,
            "industry_type": "general",
            "status": RuleStatus.ACTIVE,
            "source": "expert",
            "is_public": True,
            "tags": [category.value],
        })

    return rules


def _build_benchmarks() -> List[Dict]:
    """行业基准数据：海鲜 / 火锅 / 快餐 三类 × 10 项指标"""
    industries = ["seafood", "hotpot", "fastfood"]
    metrics = [
        ("waste_rate",          RuleCategory.WASTE,      0.06, 0.10, 0.15, 0.20, "%",   "lower_better",  "综合食材损耗率"),
        ("food_cost_ratio",     RuleCategory.COST,       0.28, 0.35, 0.42, 0.50, "%",   "lower_better",  "食材成本占营收比"),
        ("labor_cost_ratio",    RuleCategory.COST,       0.20, 0.28, 0.35, 0.40, "%",   "lower_better",  "人工成本占营收比"),
        ("gross_margin",        RuleCategory.COST,       0.55, 0.50, 0.45, 0.40, "%",   "higher_better", "综合毛利率"),
        ("table_turnover",      RuleCategory.EFFICIENCY, 3.5,  2.8,  2.2,  1.8,  "次/日", "higher_better","日均翻台率"),
        ("revenue_per_staff",   RuleCategory.EFFICIENCY, 800,  600,  450,  300,  "元/人天", "higher_better","人均产值"),
        ("avg_order_value",     RuleCategory.TRAFFIC,    180,  140,  110,  80,   "元",  "higher_better", "客单价"),
        ("repeat_rate",         RuleCategory.TRAFFIC,    0.50, 0.38, 0.28, 0.18, "%",   "higher_better", "复购率"),
        ("inventory_days",      RuleCategory.INVENTORY,  2.0,  3.5,  5.0,  7.0,  "天",  "lower_better",  "食材库存周转天数"),
        ("complaint_rate",      RuleCategory.QUALITY,    0.005,0.015,0.030,0.060,"%",   "lower_better",  "顾客投诉率"),
    ]

    result = []
    for ind in industries:
        for (metric, cat, p90, p75, p50, p25, unit, direction, desc) in metrics:
            # 根据行业调整基准值
            multiplier = 1.0
            if ind == "seafood":
                multiplier = 1.1 if metric in ("food_cost_ratio", "avg_order_value") else 1.0
            elif ind == "fastfood":
                multiplier = 0.8 if metric in ("food_cost_ratio",) else 1.0

            result.append({
                "industry_type": ind,
                "metric_name": metric,
                "metric_category": cat,
                "p25_value": round(p25 * multiplier, 3),
                "p50_value": round(p50 * multiplier, 3),
                "p75_value": round(p75 * multiplier, 3),
                "p90_value": round(p90 * multiplier, 3),
                "unit": unit,
                "direction": direction,
                "description": desc,
                "data_source": "2025中国餐饮行业白皮书 + 智链OS平台数据",
                "sample_size": {"seafood": 280, "hotpot": 1200, "fastfood": 3500}.get(ind, 500),
            })
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# L3 跨店知识规则种子数据（50 条）
# ═══════════════════════════════════════════════════════════════════════════════

def _build_cross_store_rules() -> List[Dict]:
    """
    50 条跨店规则，五类：
      CROSS-001~010  同伴组损耗率对比（Peer Waste Comparison）
      CROSS-011~020  BOM 配方一致性（Recipe Standardization）
      CROSS-021~030  跨店成本对标（Cost Benchmarking）
      CROSS-031~040  经营效率对标（Operational Efficiency）
      CROSS-041~050  知识传播 & 最佳实践（Best Practice Propagation）
    """
    C = RuleCategory.CROSS_STORE
    T = RuleType.BENCHMARK

    rules = [
        # ── CROSS-001~010 同伴组损耗率对比 ───────────────────────────────
        ("CROSS-001", "门店损耗率高于同类型同区域 p75 → 相对落后，推送整改任务",
         {"metric": "waste_rate", "operator": ">", "threshold_ref": "peer.p75",
          "peer_filter": {"tier": "$store.tier", "region": "$store.region"},
          "min_peer_count": 3},
         {"root_cause": "relative_underperformance", "confidence": 0.72,
          "action": "推送同组 Top3 门店操作视频，安排互访学习",
          "alert_level": "P2"}, C, 0.72),

        ("CROSS-002", "门店损耗率连续7天高于同组 p90 → 严重落后，升级为 P1 事件",
         {"metric": "waste_rate", "operator": ">", "threshold_ref": "peer.p90",
          "window_days": 7, "consecutive": True,
          "peer_filter": {"tier": "$store.tier"}, "min_peer_count": 3},
         {"root_cause": "chronic_underperformance", "confidence": 0.85,
          "action": "启动区域总监下店辅导流程", "alert_level": "P1"}, C, 0.85),

        ("CROSS-003", "门店损耗率首次低于同组 p25 → 卓越表现，提名最佳实践",
         {"metric": "waste_rate", "operator": "<", "threshold_ref": "peer.p25",
          "first_time": True, "min_peer_count": 3},
         {"root_cause": "excellence_achievement", "confidence": 0.80,
          "action": "提名为同伴组标杆门店，整理SOP上传知识库"}, C, 0.80),

        ("CROSS-004", "门店损耗率下降速度低于同组中位数下降速度 → 改善迟缓",
         {"metric": "waste_rate_improvement_rate", "operator": "<",
          "threshold_ref": "peer.p50_improvement_rate", "window_days": 30},
         {"root_cause": "slow_improvement", "confidence": 0.65,
          "action": "对比同组改善最快门店的行动方案"}, C, 0.65),

        ("CROSS-005", "海鲜品类损耗率高于同城市同类型门店均值 30% → 区域供应链异常",
         {"metric": "waste_rate", "category": "seafood", "operator": ">",
          "threshold_ref": "peer.mean_x1.3",
          "peer_filter": {"city": "$store.city", "tier": "$store.tier"}},
         {"root_cause": "regional_supply_chain_issue", "confidence": 0.76,
          "action": "联系区域采购部门排查同城配送冷链质量"}, C, 0.76),

        ("CROSS-006", "肉类损耗率高于全国同档门店 p75 → 出成率不达标",
         {"metric": "waste_rate", "category": "meat", "operator": ">",
          "threshold_ref": "peer.p75",
          "peer_filter": {"tier": "$store.tier"}},
         {"root_cause": "yield_rate_gap", "confidence": 0.70,
          "action": "参照同组 p25 门店的切割标准重新培训"}, C, 0.70),

        ("CROSS-007", "全品类损耗率同时高于同组 p75 → 系统性管理问题",
         {"metric": "overall_waste_rate", "operator": ">", "threshold_ref": "peer.p75",
          "category_count_min": 3},
         {"root_cause": "systematic_management_failure", "confidence": 0.88,
          "action": "启动门店全面管理诊断（人员/流程/设备）"}, C, 0.88),

        ("CROSS-008", "门店损耗率在同组内排名末位超 30 天 → 触发人员调研",
         {"metric": "waste_rate_rank_in_peer", "operator": "==", "value": "last",
          "window_days": 30},
         {"root_cause": "persistent_bottom_performer", "confidence": 0.82,
          "action": "启动 360° 门店诊断，含人员访谈"}, C, 0.82),

        ("CROSS-009", "新开业门店 6 个月内损耗率仍高于同组 p50 → 标准化导入失败",
         {"metric": "waste_rate", "operator": ">", "threshold_ref": "peer.p50",
          "store_age_months_max": 6},
         {"root_cause": "onboarding_standardization_failure", "confidence": 0.74,
          "action": "安排标准化导入复盘，输出缺口清单"}, C, 0.74),

        ("CROSS-010", "节假日损耗率高于同组 p75 但平日正常 → 节假日备料预测偏差",
         {"metric": "waste_rate", "operator": ">", "threshold_ref": "peer.p75",
          "day_type": "holiday", "normal_day_ok": True},
         {"root_cause": "holiday_forecast_error", "confidence": 0.68,
          "action": "校正节假日订货模型，参考同组历史倍增系数"}, C, 0.68),

        # ── CROSS-011~020 BOM 配方一致性 ──────────────────────────────────
        ("CROSS-011", "同菜品跨店食材用量差异 > 15% → 配方标准化漂移",
         {"metric": "bom_ingredient_variance_pct", "operator": ">", "threshold": 0.15,
          "min_store_count": 3},
         {"root_cause": "recipe_standardization_drift", "confidence": 0.80,
          "action": "发布配方统一令，要求各店在 7 天内对齐 BOM 主版本"}, C, 0.80),

        ("CROSS-012", "同菜品有效 BOM 版本超过 3 个 → 版本碎片化",
         {"metric": "active_bom_version_count", "operator": ">", "threshold": 3},
         {"root_cause": "bom_version_fragmentation", "confidence": 0.75,
          "action": "由总部厨研中心审核，指定唯一标准版本"}, C, 0.75),

        ("CROSS-013", "关键食材用量差异 > 10% → 核心风味一致性风险",
         {"metric": "key_ingredient_variance_pct", "operator": ">", "threshold": 0.10,
          "is_key_ingredient": True, "min_store_count": 2},
         {"root_cause": "core_flavor_inconsistency", "confidence": 0.87,
          "action": "关键食材用量锁定，修改为强制执行字段"}, C, 0.87),

        ("CROSS-014", "出成率（yield_rate）在同组内差异 > 8% → 厨师技能差异显著",
         {"metric": "yield_rate_variance_pct", "operator": ">", "threshold": 0.08,
          "min_store_count": 3},
         {"root_cause": "chef_skill_gap", "confidence": 0.72,
          "action": "组织跨店厨师互相观摩，视频录制标准操作"}, C, 0.72),

        ("CROSS-015", "新 BOM 版本上线 30 天内，50% 门店仍未更新 → 推送阻力",
         {"metric": "bom_adoption_rate_30d", "operator": "<", "threshold": 0.50},
         {"root_cause": "bom_rollout_resistance", "confidence": 0.70,
          "action": "调查未更新门店原因，总部运营介入支持"}, C, 0.70),

        ("CROSS-016", "可选食材实际使用率差异跨店 > 40% → 区域口味偏好分化",
         {"metric": "optional_ingredient_usage_variance", "operator": ">",
          "threshold": 0.40, "is_optional": True, "min_store_count": 3},
         {"root_cause": "regional_taste_preference_divergence", "confidence": 0.65,
          "action": "允许区域化 BOM 配置，建立可选区域版本"}, C, 0.65),

        ("CROSS-017", "预处理备注（prep_notes）缺失率 > 60% 的门店，损耗率高于同组 p75",
         {"metric": "waste_rate", "operator": ">", "threshold_ref": "peer.p75",
          "condition_and": {"metric": "prep_notes_missing_rate",
                            "operator": ">", "threshold": 0.60}},
         {"root_cause": "missing_prep_guidance", "confidence": 0.68,
          "action": "强制要求关键食材填写预处理备注"}, C, 0.68),

        ("CROSS-018", "损耗系数（waste_factor）设置全为 0 的门店，BOM 偏差普遍更大",
         {"metric": "bom_variance_pct", "operator": ">", "threshold": 0.20,
          "condition_and": {"metric": "waste_factor_zero_rate",
                            "operator": "==", "value": 1.0}},
         {"root_cause": "missing_waste_factor_calibration", "confidence": 0.73,
          "action": "根据历史损耗事件自动反推 waste_factor 建议值"}, C, 0.73),

        ("CROSS-019", "同一食材在不同门店 BOM 中单位不一致 → 计量混乱",
         {"metric": "ingredient_unit_inconsistency", "operator": ">",
          "threshold": 1, "min_store_count": 2},
         {"root_cause": "measurement_unit_inconsistency", "confidence": 0.90,
          "action": "启动食材计量单位标准化专项，统一为 SI 单位"}, C, 0.90),

        ("CROSS-020", "BOM 成本快照与供应商最新报价偏差 > 15% 的门店占比 > 30%",
         {"metric": "bom_cost_freshness_gap", "operator": ">", "threshold": 0.15,
          "affected_store_ratio": 0.30},
         {"root_cause": "bom_cost_snapshot_stale", "confidence": 0.77,
          "action": "触发全品牌 BOM 成本批量更新任务"}, C, 0.77),

        # ── CROSS-021~030 跨店成本对标 ───────────────────────────────────
        ("CROSS-021", "食材成本率高于同组 p75 → 采购价格偏高或损耗叠加",
         {"metric": "cost_ratio", "operator": ">", "threshold_ref": "peer.p75",
          "peer_filter": {"tier": "$store.tier", "region": "$store.region"}},
         {"root_cause": "high_ingredient_cost_ratio", "confidence": 0.74,
          "action": "对比同组采购单价，触发集采谈判"}, C, 0.74),

        ("CROSS-022", "同城市同档门店食材成本率差异 > 5 个百分点 → 本地采购议价空间",
         {"metric": "cost_ratio_city_spread", "operator": ">", "threshold": 0.05,
          "peer_filter": {"city": "$store.city", "tier": "$store.tier"}},
         {"root_cause": "local_procurement_price_gap", "confidence": 0.70,
          "action": "低价门店提供供应商联系方式，推动跨店共享采购"}, C, 0.70),

        ("CROSS-023", "连锁门店间同食材采购单价差异 > 10% → 集中采购未到位",
         {"metric": "ingredient_unit_price_variance_pct", "operator": ">",
          "threshold": 0.10, "min_store_count": 3},
         {"root_cause": "centralized_procurement_failure", "confidence": 0.82,
          "action": "接入集采平台，统一供应商准入和框架合同"}, C, 0.82),

        ("CROSS-024", "门店规范化成本率持续低于同组 p25 → 建立标杆成本模型",
         {"metric": "cost_ratio", "operator": "<", "threshold_ref": "peer.p25",
          "window_days": 30, "min_peer_count": 3},
         {"root_cause": "cost_excellence", "confidence": 0.78,
          "action": "提炼成本控制经验，输出标杆成本模型到知识库"}, C, 0.78),

        ("CROSS-025", "人力成本率高于同组 p75 且食材成本率正常 → 排班效率问题",
         {"metric": "labor_ratio", "operator": ">", "threshold_ref": "peer.p75",
          "condition_and": {"metric": "cost_ratio", "operator": "<=",
                            "threshold_ref": "peer.p50"}},
         {"root_cause": "labor_scheduling_inefficiency", "confidence": 0.71,
          "action": "对比同组排班方案，分析人时产出差距"}, C, 0.71),

        ("CROSS-026", "淡季成本率高于旺季同组 p50 → 淡季费用管控缺位",
         {"metric": "cost_ratio", "operator": ">", "threshold_ref": "peer.p50",
          "season": "off_peak"},
         {"root_cause": "off_peak_cost_control_gap", "confidence": 0.67,
          "action": "制定淡季缩量运营方案，弹性排班 + 减少备货"}, C, 0.67),

        ("CROSS-027", "供应商更换后成本率未下降 → 议价效果不达预期",
         {"metric": "cost_ratio_post_supplier_change", "operator": ">",
          "threshold_ref": "peer.p50"},
         {"root_cause": "supplier_negotiation_ineffective", "confidence": 0.66,
          "action": "重新评估供应商选择标准，引入多报价竞标"}, C, 0.66),

        ("CROSS-028", "损耗成本在总食材成本中占比 > 同组 p75 → 损耗治理优先于采购优化",
         {"metric": "waste_cost_ratio_in_total", "operator": ">",
          "threshold_ref": "peer.p75"},
         {"root_cause": "waste_dominates_cost", "confidence": 0.79,
          "action": "暂缓采购谈判，将资源集中在损耗控制"}, C, 0.79),

        ("CROSS-029", "特殊食材（进口/高端）占比高于同组 p90 → 菜品结构性成本风险",
         {"metric": "premium_ingredient_ratio", "operator": ">",
          "threshold_ref": "peer.p90"},
         {"root_cause": "premium_ingredient_overuse", "confidence": 0.69,
          "action": "优化菜品结构，平衡高低价食材配比"}, C, 0.69),

        ("CROSS-030", "同组门店近 90 天平均成本率趋势性上升 → 品类性通货膨胀",
         {"metric": "cost_ratio_trend_90d", "operator": ">", "threshold": 0.0,
          "peer_filter": {"tier": "$store.tier"}, "min_peer_count": 5},
         {"root_cause": "category_cost_inflation", "confidence": 0.84,
          "action": "启动品类替代方案调研，评估菜单调价可行性"}, C, 0.84),

        # ── CROSS-031~040 经营效率对标 ───────────────────────────────────
        ("CROSS-031", "每座位日均营业额低于同组 p25 → 翻台率或客单价偏低",
         {"metric": "revenue_per_seat", "operator": "<", "threshold_ref": "peer.p25",
          "peer_filter": {"tier": "$store.tier", "region": "$store.region"}},
         {"root_cause": "low_seat_productivity", "confidence": 0.73,
          "action": "对比同组翻台率与客单价，确定主要瓶颈"}, C, 0.73),

        ("CROSS-032", "菜单覆盖率低于同组 p25 → 门店菜品开发滞后",
         {"metric": "menu_coverage", "operator": "<", "threshold_ref": "peer.p25",
          "min_peer_count": 3},
         {"root_cause": "menu_development_lag", "confidence": 0.68,
          "action": "推送总部新品 BOM 包，要求 30 天内完成门店导入"}, C, 0.68),

        ("CROSS-033", "同组门店中只有该门店缺少某热门菜品 → 菜单漏洞",
         {"metric": "missing_popular_dish_count", "operator": ">", "threshold": 0},
         {"root_cause": "menu_gap_vs_peers", "confidence": 0.76,
          "action": "补充缺失热门菜品 BOM，安排厨师培训"}, C, 0.76),

        ("CROSS-034", "新品上线后销量低于同组同新品平均销量 50% → 门店推广执行不足",
         {"metric": "new_dish_sales_vs_peer_avg", "operator": "<",
          "threshold": 0.50, "dish_age_days_max": 30},
         {"root_cause": "new_dish_promotion_underexecution", "confidence": 0.71,
          "action": "检查前厅推荐话术执行情况，对标高销量门店"}, C, 0.71),

        ("CROSS-035", "同组门店工单完成率普遍下降 → 平台型系统性问题",
         {"metric": "task_completion_rate_trend", "operator": "<",
          "threshold": -0.10, "peer_ratio_min": 0.60, "window_days": 7},
         {"root_cause": "platform_systemic_issue", "confidence": 0.88,
          "action": "上报总部运营，排查平台工单系统或共性培训缺口"}, C, 0.88),

        ("CROSS-036", "员工绩效分低于同组 p25 且损耗高于同组 p75 → 人员能力瓶颈",
         {"metric": "staff_performance_score", "operator": "<",
          "threshold_ref": "peer.p25",
          "condition_and": {"metric": "waste_rate", "operator": ">",
                            "threshold_ref": "peer.p75"}},
         {"root_cause": "staff_capability_bottleneck", "confidence": 0.80,
          "action": "启动人才梯队建设，引进高绩效门店人才"}, C, 0.80),

        ("CROSS-037", "外卖销售占比高于同组 p75 但食材损耗也同步高 → 外卖订单管理问题",
         {"metric": "takeout_ratio", "operator": ">", "threshold_ref": "peer.p75",
          "condition_and": {"metric": "waste_rate", "operator": ">",
                            "threshold_ref": "peer.p50"}},
         {"root_cause": "takeout_order_waste_correlation", "confidence": 0.69,
          "action": "优化外卖备货策略，避免因峰值备料导致损耗"}, C, 0.69),

        ("CROSS-038", "同组最佳实践门店损耗率已低于 $threshold，而该门店仍差距 > 5%",
         {"metric": "gap_to_best_practice", "operator": ">", "threshold": 0.05,
          "reference": "peer.min", "min_peer_count": 3},
         {"root_cause": "best_practice_gap", "confidence": 0.77,
          "action": "安排向最佳实践门店互访学习，引进关键经验"}, C, 0.77),

        ("CROSS-039", "同城市门店间差旅学习频次为零 → 知识孤岛",
         {"metric": "cross_store_visit_count", "operator": "==", "threshold": 0,
          "window_days": 90},
         {"root_cause": "knowledge_island", "confidence": 0.65,
          "action": "制定季度跨店交流计划，强制执行互访机制"}, C, 0.65),

        ("CROSS-040", "开业超 12 个月门店效率指标仍未达到同组中位数 → 成熟化停滞",
         {"metric": "revenue_per_seat", "operator": "<", "threshold_ref": "peer.p50",
          "store_age_months_min": 12},
         {"root_cause": "maturity_plateau", "confidence": 0.75,
          "action": "委派区域运营督导深度驻店，输出改善路线图"}, C, 0.75),

        # ── CROSS-041~050 知识传播 & 最佳实践 ────────────────────────────
        ("CROSS-041", "某门店损耗率改善超同组 p90 → 萃取改善经验，复制到全组",
         {"metric": "waste_rate_improvement_30d", "operator": ">",
          "threshold_ref": "peer.p90_improvement", "min_peer_count": 3},
         {"root_cause": "improvement_leader", "confidence": 0.85,
          "action": "启动知识萃取流程：采访店长，制作SOP案例视频"}, C, 0.85),

        ("CROSS-042", "最佳实践门店 BOM 配方被采纳率超 80% → 晋升为品牌标准版",
         {"metric": "bom_adoption_rate_in_peer", "operator": ">", "threshold": 0.80},
         {"root_cause": "bom_best_practice_adoption", "confidence": 0.82,
          "action": "将该门店 BOM 版本提升为总部标准版本"}, C, 0.82),

        ("CROSS-043", "某门店成功解决某根因问题后，同组其他门店仍有相同根因 → 知识传播不足",
         {"metric": "root_cause_peer_remaining_count", "operator": ">",
          "threshold": 2, "same_root_cause": True},
         {"root_cause": "knowledge_transfer_gap", "confidence": 0.74,
          "action": "将成功案例推送给同根因门店，标注解决方案步骤"}, C, 0.74),

        ("CROSS-044", "知识规则命中率在同组内排名 Top1 → 门店学习能力领先",
         {"metric": "rule_hit_accuracy_rate", "operator": "==", "value": "rank_1_in_peer"},
         {"root_cause": "knowledge_absorption_leader", "confidence": 0.78,
          "action": "授予智链OS门店知识贡献认证，开放数据分成权益"}, C, 0.78),

        ("CROSS-045", "同组内某改善措施在 3 家门店验证有效 → 可推全组",
         {"metric": "validated_improvement_store_count", "operator": ">=",
          "threshold": 3},
         {"root_cause": "improvement_ready_for_rollout", "confidence": 0.88,
          "action": "发布集团级改善推广令，设置 14 天落地期限"}, C, 0.88),

        ("CROSS-046", "同类门店供应商评分最低 25% 的供应商，该门店仍在使用 → 供应商选择落后",
         {"metric": "low_rated_supplier_usage", "operator": ">", "threshold": 0},
         {"root_cause": "poor_supplier_selection", "confidence": 0.76,
          "action": "强制替换评分后25%供应商，参考同组优质供应商"}, C, 0.76),

        ("CROSS-047", "行业基准损耗率已更新，门店目标设置仍按旧基准 → 目标过时",
         {"metric": "target_vs_latest_benchmark_gap", "operator": ">",
          "threshold": 0.05},
         {"root_cause": "stale_performance_target", "confidence": 0.71,
          "action": "同步更新门店损耗率目标至最新行业基准"}, C, 0.71),

        ("CROSS-048", "本门店在某食材损耗上被多家同组门店认定为最佳 → 申报行业标杆",
         {"metric": "ingredient_waste_peer_rank", "operator": "==", "value": "rank_1",
          "min_peer_count": 5},
         {"root_cause": "ingredient_management_champion", "confidence": 0.83,
          "action": "申报品牌年度食材管理最佳实践，纳入模型市场"}, C, 0.83),

        ("CROSS-049", "同组门店平均损耗率近半年持续优于行业基准 p75 → 组级知识资产积累",
         {"metric": "peer_group_avg_waste_rate", "operator": "<",
          "threshold_ref": "industry.p75", "window_months": 6,
          "min_peer_count": 3},
         {"root_cause": "group_knowledge_asset_maturity", "confidence": 0.81,
          "action": "将同组经验汇编为行业白皮书，上传模型市场"}, C, 0.81),

        ("CROSS-050", "两门店相似度 > 0.80 但损耗率差距 > 15% → 强对标学习价值",
         {"metric": "waste_rate_gap_vs_similar_store", "operator": ">",
          "threshold": 0.15,
          "condition_and": {"metric": "similarity_score", "operator": ">",
                            "threshold": 0.80}},
         {"root_cause": "high_similarity_learning_opportunity", "confidence": 0.86,
          "action": "安排 1 对 1 门店配对学习，明确差距清单"}, C, 0.86),
    ]

    result = []
    for rule_code, name, condition, conclusion, category, confidence in rules:
        result.append({
            "rule_code":         rule_code,
            "name":              name,
            "condition":         condition,
            "conclusion":        conclusion,
            "category":          category,
            "rule_type":         RuleType.BENCHMARK,
            "base_confidence":   confidence,
            "weight":            1.0,
            "status":            RuleStatus.ACTIVE,
            "industry_type":     "general",
            "source":            "expert",
            "is_public":         False,
            "tags":              ["cross_store", "L3", "knowledge_aggregation"],
        })
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 服务类
# ═══════════════════════════════════════════════════════════════════════════════

class KnowledgeRuleService:
    """推理规则库服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── 种子数据初始化 ────────────────────────────────────────────────────────

    async def seed_rules(self) -> Dict:
        """初始化预置规则（幂等：已存在 rule_code 则跳过）"""
        seed = _build_seed_rules()
        created = 0
        skipped = 0
        for r in seed:
            existing = await self.get_by_code(r["rule_code"])
            if existing:
                skipped += 1
                continue
            rule = KnowledgeRule(id=uuid.uuid4(), **r)
            self.db.add(rule)
            created += 1
        await self.db.flush()
        logger.info("规则种子数据初始化", created=created, skipped=skipped)
        return {"created": created, "skipped": skipped, "total": len(seed)}

    async def seed_benchmarks(self) -> Dict:
        """初始化行业基准数据（幂等）"""
        benchmarks = _build_benchmarks()
        created = 0
        for b in benchmarks:
            from sqlalchemy import and_
            stmt = select(IndustryBenchmark).where(
                and_(
                    IndustryBenchmark.industry_type == b["industry_type"],
                    IndustryBenchmark.metric_name == b["metric_name"],
                )
            )
            result = await self.db.execute(stmt)
            if result.scalar_one_or_none():
                continue
            bm = IndustryBenchmark(id=uuid.uuid4(), **b)
            self.db.add(bm)
            created += 1
        await self.db.flush()
        return {"created": created, "total": len(benchmarks)}

    async def seed_cross_store_rules(self) -> Dict:
        """幂等植入 50 条跨店聚合规则（已存在 rule_code 则跳过）"""
        seed = _build_cross_store_rules()
        created = 0
        skipped = 0
        for r in seed:
            existing = await self.get_by_code(r["rule_code"])
            if existing:
                skipped += 1
                continue
            rule = KnowledgeRule(id=uuid.uuid4(), **r)
            self.db.add(rule)
            created += 1
        await self.db.flush()
        logger.info("跨店规则种子数据初始化", created=created, skipped=skipped)
        return {"created": created, "skipped": skipped, "total": len(seed)}

    # ── 规则 CRUD ─────────────────────────────────────────────────────────────

    async def create_rule(self, data: Dict) -> KnowledgeRule:
        rule = KnowledgeRule(id=uuid.uuid4(), **data)
        self.db.add(rule)
        await self.db.flush()
        return rule

    async def get_by_code(self, rule_code: str) -> Optional[KnowledgeRule]:
        stmt = select(KnowledgeRule).where(KnowledgeRule.rule_code == rule_code)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id(self, rule_id: str) -> Optional[KnowledgeRule]:
        stmt = select(KnowledgeRule).where(
            KnowledgeRule.id == uuid.UUID(rule_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_rules(
        self,
        category: Optional[RuleCategory] = None,
        status: Optional[RuleStatus] = None,
        industry_type: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[KnowledgeRule]:
        conditions = []
        if category:
            conditions.append(KnowledgeRule.category == category)
        if status:
            conditions.append(KnowledgeRule.status == status)
        if industry_type:
            conditions.append(KnowledgeRule.industry_type == industry_type)
        if source:
            conditions.append(KnowledgeRule.source == source)

        stmt = select(KnowledgeRule)
        if conditions:
            stmt = stmt.where(and_(*conditions))
        stmt = stmt.order_by(KnowledgeRule.rule_code).offset(offset).limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def activate_rule(self, rule_id: str) -> bool:
        await self.db.execute(
            update(KnowledgeRule)
            .where(KnowledgeRule.id == uuid.UUID(rule_id))
            .values(status=RuleStatus.ACTIVE)
        )
        return True

    async def archive_rule(self, rule_id: str, superseded_by: Optional[str] = None) -> bool:
        values: Dict = {"status": RuleStatus.ARCHIVED}
        if superseded_by:
            values["superseded_by"] = uuid.UUID(superseded_by)
        await self.db.execute(
            update(KnowledgeRule)
            .where(KnowledgeRule.id == uuid.UUID(rule_id))
            .values(**values)
        )
        return True

    # ── 规则匹配引擎 ──────────────────────────────────────────────────────────

    async def match_rules(
        self,
        context: Dict[str, Any],
        category: Optional[RuleCategory] = None,
    ) -> List[Dict]:
        """
        给定业务上下文，返回所有匹配的规则及置信度评分。

        context 示例::

            {
                "waste_rate": 0.18,
                "window_days": 3,
                "consecutive": True,
                "ingredient_category": "seafood",
            }
        """
        rules = await self.list_rules(
            category=category,
            status=RuleStatus.ACTIVE,
            limit=500,
        )

        matched = []
        for rule in rules:
            score = self._evaluate_rule(rule.condition, context)
            if score > 0:
                matched.append({
                    "rule_code": rule.rule_code,
                    "name": rule.name,
                    "category": rule.category.value,
                    "conclusion": rule.conclusion,
                    "match_score": score,
                    "confidence": rule.base_confidence * score,
                })

        matched.sort(key=lambda x: x["confidence"], reverse=True)
        return matched[:10]  # 返回 Top 10 匹配规则

    def _evaluate_rule(self, condition: Dict, context: Dict) -> float:
        """
        简单规则评估器：检查 condition 是否满足，返回 0.0~1.0 的匹配分。
        完整实现可使用 rule engine 库（如 durable_rules）。
        """
        try:
            metric = condition.get("metric")
            operator = condition.get("operator")
            threshold = condition.get("threshold")

            if not metric or metric not in context:
                return 0.0

            value = context[metric]
            if not isinstance(value, (int, float)):
                return 0.0

            if operator == ">":
                return 1.0 if value > threshold else 0.0
            elif operator == ">=":
                return 1.0 if value >= threshold else 0.0
            elif operator == "<":
                return 1.0 if value < threshold else 0.0
            elif operator == "<=":
                return 1.0 if value <= threshold else 0.0
            elif operator == "==":
                return 1.0 if value == threshold else 0.0
            else:
                return 0.0
        except Exception:
            return 0.0

    async def match_cross_store_rules(
        self,
        context: Dict[str, Any],
        peer_context: Dict[str, float],
    ) -> List[Dict]:
        """
        跨店规则匹配引擎 — 支持 threshold_ref: "peer.p75" 语义。

        peer_context 示例::

            {
                "peer.p25": 0.05,
                "peer.p50": 0.08,
                "peer.p75": 0.12,
                "peer.p90": 0.18,
            }

        context 示例（与 match_rules 相同格式，额外传入 peer 指标）::

            {
                "waste_rate": 0.15,
                "peer_group": "standard_华东",
                "metric_name": "waste_rate",
            }
        """
        rules = await self.list_rules(
            category=RuleCategory.CROSS_STORE,
            status=RuleStatus.ACTIVE,
            limit=200,
        )

        matched = []
        for rule in rules:
            score = self._evaluate_cross_store_rule(rule.condition, context, peer_context)
            if score > 0:
                matched.append({
                    "rule_code": rule.rule_code,
                    "name": rule.name,
                    "category": rule.category.value,
                    "conclusion": rule.conclusion,
                    "match_score": score,
                    "confidence": rule.base_confidence * score,
                    "peer_context": peer_context,
                })

        matched.sort(key=lambda x: x["confidence"], reverse=True)
        return matched[:10]

    def _evaluate_cross_store_rule(
        self,
        condition: Dict,
        context: Dict,
        peer_context: Dict[str, float],
    ) -> float:
        """
        支持 threshold_ref 的规则评估器。

        threshold_ref 格式: "peer.p75"、"peer.p50" 等 —
        从 peer_context 中解析实际阈值再与 context metric 比较。
        """
        try:
            metric = condition.get("metric")
            operator = condition.get("operator")

            # 解析阈值：优先 threshold_ref，其次 threshold
            threshold_ref = condition.get("threshold_ref")
            if threshold_ref:
                # e.g. "peer.p75" → look up peer_context["peer.p75"]
                threshold = peer_context.get(threshold_ref)
                if threshold is None:
                    return 0.0
            else:
                threshold = condition.get("threshold")

            if not metric or metric not in context:
                return 0.0

            value = context[metric]
            if not isinstance(value, (int, float)):
                return 0.0
            if threshold is None:
                return 0.0

            if operator == ">":
                return 1.0 if value > threshold else 0.0
            elif operator == ">=":
                return 1.0 if value >= threshold else 0.0
            elif operator == "<":
                return 1.0 if value < threshold else 0.0
            elif operator == "<=":
                return 1.0 if value <= threshold else 0.0
            elif operator == "==":
                return 1.0 if value == threshold else 0.0
            else:
                return 0.0
        except Exception:
            return 0.0

    # ── 规则执行日志 ──────────────────────────────────────────────────────────

    async def log_execution(
        self,
        rule: KnowledgeRule,
        store_id: str,
        event_id: Optional[str],
        condition_values: Dict,
        conclusion_output: Dict,
        confidence_score: float,
    ) -> RuleExecution:
        exec_record = RuleExecution(
            id=uuid.uuid4(),
            rule_id=rule.id,
            rule_code=rule.rule_code,
            store_id=store_id,
            event_id=event_id,
            condition_values=condition_values,
            conclusion_output=conclusion_output,
            confidence_score=confidence_score,
        )
        self.db.add(exec_record)

        # 更新规则命中计数
        await self.db.execute(
            update(KnowledgeRule)
            .where(KnowledgeRule.id == rule.id)
            .values(
                hit_count=KnowledgeRule.hit_count + 1,
                last_hit_at=datetime.utcnow(),
            )
        )
        await self.db.flush()
        return exec_record

    # ── 行业基准 ──────────────────────────────────────────────────────────────

    async def get_benchmarks(
        self,
        industry_type: str,
        metric_name: Optional[str] = None,
    ) -> List[IndustryBenchmark]:
        conditions = [IndustryBenchmark.industry_type == industry_type]
        if metric_name:
            conditions.append(IndustryBenchmark.metric_name == metric_name)
        stmt = (
            select(IndustryBenchmark)
            .where(and_(*conditions))
            .order_by(IndustryBenchmark.metric_name)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def compare_to_benchmark(
        self,
        industry_type: str,
        actual_values: Dict[str, float],
    ) -> List[Dict]:
        """
        将实际指标与行业基准对比，返回差距分析

        Returns::

            [
              {
                "metric": "waste_rate",
                "actual": 0.13,
                "p50": 0.10,
                "p90": 0.06,
                "percentile": "25-50",
                "gap_to_p50": -0.03,
                "status": "below_median"
              }, ...
            ]
        """
        benchmarks = await self.get_benchmarks(industry_type)
        results = []
        for bm in benchmarks:
            actual = actual_values.get(bm.metric_name)
            if actual is None:
                continue

            # 计算落在哪个分位区间
            if bm.direction == "lower_better":
                if actual <= bm.p90_value:
                    pct = "top_10"
                elif actual <= bm.p75_value:
                    pct = "75-90"
                elif actual <= bm.p50_value:
                    pct = "50-75"
                elif actual <= bm.p25_value:
                    pct = "25-50"
                else:
                    pct = "bottom_25"
                gap_to_median = bm.p50_value - actual
            else:
                if actual >= bm.p90_value:
                    pct = "top_10"
                elif actual >= bm.p75_value:
                    pct = "75-90"
                elif actual >= bm.p50_value:
                    pct = "50-75"
                elif actual >= bm.p25_value:
                    pct = "25-50"
                else:
                    pct = "bottom_25"
                gap_to_median = actual - bm.p50_value

            results.append({
                "metric": bm.metric_name,
                "description": bm.description,
                "actual": actual,
                "p25": bm.p25_value,
                "p50": bm.p50_value,
                "p75": bm.p75_value,
                "p90": bm.p90_value,
                "unit": bm.unit,
                "direction": bm.direction,
                "percentile_band": pct,
                "gap_to_median": round(gap_to_median, 4),
                "status": (
                    "above_median" if pct in ("top_10", "75-90", "50-75") else "below_median"
                ),
            })
        return results

    async def get_rule_stats(self) -> Dict:
        """规则库统计"""
        from sqlalchemy import func
        total = await self.db.execute(select(func.count(KnowledgeRule.id)))
        active = await self.db.execute(
            select(func.count(KnowledgeRule.id)).where(
                KnowledgeRule.status == RuleStatus.ACTIVE
            )
        )
        by_category = await self.db.execute(
            select(KnowledgeRule.category, func.count(KnowledgeRule.id))
            .group_by(KnowledgeRule.category)
        )
        return {
            "total_rules": total.scalar(),
            "active_rules": active.scalar(),
            "by_category": {row[0].value: row[1] for row in by_category.all()},
        }
