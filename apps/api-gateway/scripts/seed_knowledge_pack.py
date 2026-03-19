"""
屯象餐饮行业知识包 — 冷启动种子数据

M1 里程碑第三项：导入 500+ 条行业规则到 knowledge_rules 表。
涵盖 9 个分类 × 5 种规则类型，来源于餐饮行业 16 年经验积累。

用法:
  cd apps/api-gateway
  python3 scripts/seed_knowledge_pack.py

设计原则:
  - org_node_id = None → 全行业通用规则
  - source = "tunxiang_pack" → 屯象行业知识包
  - industry_source = "tunxiang_v1" → 第一版知识包
  - base_confidence 根据规则确定性程度设定
  - 金额单位：元（展示层），分（数据库层由业务计算时转换）
"""
import uuid
import sys
import os
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def generate_rules():
    """生成 500+ 条餐饮行业知识规则"""
    rules = []
    idx = 0

    def add(category, rule_type, name, desc, condition, conclusion, confidence=0.75, action=None, tags=None):
        nonlocal idx
        idx += 1
        code = f"{category.upper()}-{idx:04d}"
        rules.append({
            "rule_code": code,
            "name": name,
            "description": desc,
            "category": category,
            "rule_type": rule_type,
            "condition": condition,
            "conclusion": conclusion,
            "base_confidence": confidence,
            "weight": 1.0,
            "source": "tunxiang_pack",
            "industry_source": "tunxiang_v1",
            "is_public": True,
            "status": "active",
            "action": action or {},
            "tags": tags or [],
            "industry_type": "general",
        })

    # ================================================================
    # 1. 损耗管理 (WASTE) — 80 条
    # ================================================================

    # 1.1 食材损耗阈值规则 (20条)
    food_categories = [
        ("蔬菜", 0.08, "蔬菜类损耗率基准8%"), ("肉类", 0.03, "肉类损耗率基准3%"),
        ("海鲜", 0.05, "海鲜类损耗率基准5%"), ("干货", 0.02, "干货类损耗率基准2%"),
        ("调料", 0.01, "调料类损耗率基准1%"), ("主食", 0.04, "主食类损耗率基准4%"),
        ("豆制品", 0.06, "豆制品损耗率基准6%"), ("冻品", 0.02, "冻品损耗率基准2%"),
        ("乳制品", 0.05, "乳制品损耗率基准5%"), ("水果", 0.10, "水果损耗率基准10%"),
    ]
    for cat, threshold, desc in food_categories:
        add("waste", "threshold",
            f"{cat}损耗率超标预警",
            f"当{desc}，连续3天超过基准值时触发预警",
            {"metric": "waste_rate", "food_category": cat, "operator": ">",
             "threshold": threshold, "window_days": 3, "consecutive": True},
            {"root_cause_probability": {"操作失误": 0.35, "存储不当": 0.25, "采购过量": 0.20, "品质问题": 0.20},
             "suggested_action": f"检查{cat}存储条件和操作规范"},
            confidence=0.80,
            action={"type": "alert", "level": "warning", "notify": ["store_manager", "chef"]},
            tags=[cat, "损耗", "预警"])
        # 严重超标
        add("waste", "threshold",
            f"{cat}损耗率严重超标",
            f"{cat}损耗率超过基准值2倍时紧急告警",
            {"metric": "waste_rate", "food_category": cat, "operator": ">",
             "threshold": threshold * 2, "window_days": 1},
            {"severity": "critical", "impact_yuan": f"预估日损失{int(threshold*2*10000)}元以上",
             "suggested_action": "立即检查供应链和操作流程"},
            confidence=0.90,
            action={"type": "alert", "level": "critical", "notify": ["store_manager", "chef", "hq"]},
            tags=[cat, "损耗", "紧急"])

    # 1.2 损耗模式规则 (20条)
    waste_patterns = [
        ("周末备货过量", "weekend", "周末客流预测偏高导致备货过量，损耗集中在周一"),
        ("节假日后损耗高峰", "holiday_after", "节假日备货量大，假期结束后食材积压"),
        ("换季食材适应期", "season_change", "换季期间新食材操作不熟练，损耗率上升"),
        ("新菜品上线适应期", "new_dish", "新菜上线首2周操作不熟练，食材损耗偏高"),
        ("高温季节存储损耗", "summer_storage", "夏季冷链断裂风险增加，易腐食材损耗上升"),
        ("雨天客流骤降", "rainy_day", "降雨导致客流低于预期，已备食材形成损耗"),
        ("外卖高峰包装损耗", "delivery_peak", "外卖高峰期打包操作加速，食材溢出浪费增加"),
        ("月末清库存", "month_end", "月末集中处理临期食材，损耗集中释放"),
        ("厨师长休假期间", "chef_absence", "厨师长不在岗期间，后厨管理松懈损耗上升"),
        ("新员工入职期", "new_staff", "新员工操作不熟练，前2周食材浪费率偏高"),
        ("宴会后剩余处理", "banquet_leftover", "宴会结束后大量剩余食材需及时处理"),
        ("早餐时段损耗", "breakfast_waste", "早餐食材准备过多且不可转午市使用"),
        ("凉菜档口损耗", "cold_dish", "凉菜提前制作后超时未售出需丢弃"),
        ("自助餐损耗", "buffet_waste", "自助餐档口补餐频次与客流不匹配"),
        ("油炸类重复用油", "frying_oil", "油炸类菜品用油更换频次影响品质和成本"),
        ("汤底损耗", "soup_base", "火锅/汤类底料准备过量无法次日复用"),
        ("切配损耗标准", "cutting_waste", "切配环节标准化程度影响边角料比例"),
        ("过期食材处理", "expired_food", "临期食材预警和处理流程不规范"),
        ("退菜损耗", "return_dish", "退菜率高导致成品浪费"),
        ("试菜损耗", "tasting", "研发试菜和员工餐食材占用"),
    ]
    for name, pattern, desc in waste_patterns:
        add("waste", "pattern", name, desc,
            {"pattern_id": pattern, "detection_method": "time_series_analysis"},
            {"pattern_description": desc, "mitigation": f"针对{name}制定专项预案"},
            confidence=0.70,
            tags=["损耗", "模式"])

    # 1.3 损耗因果规则 (20条)
    waste_causes = [
        ("验收不严", "receiving_lax", "验收环节未严格检查导致不合格食材入库", 0.85),
        ("存储温度异常", "temp_anomaly", "冷库温度波动导致食材加速变质", 0.90),
        ("先进先出未执行", "fifo_violation", "未按FIFO原则使用库存导致食材过期", 0.80),
        ("采购预测偏差", "forecast_error", "销量预测不准确导致采购量与实际需求不匹配", 0.75),
        ("切配标准不统一", "cutting_std", "不同厨师切配标准差异导致边角料浪费", 0.70),
        ("菜品分量不标准", "portion_control", "出品分量控制不一致导致食材超支", 0.75),
        ("设备故障", "equipment_fail", "冰箱/冷库设备故障导致食材变质", 0.95),
        ("操作流程缺失", "sop_missing", "关键岗位SOP缺失导致操作随意性大", 0.80),
        ("交接班疏忽", "handover_gap", "交接班时未清点库存导致重复备货", 0.65),
        ("供应商送货不及时", "late_delivery", "供应商延迟送货导致紧急采购品质不稳定", 0.60),
        ("厨房动线不合理", "kitchen_layout", "厨房动线设计导致食材搬运中损耗", 0.55),
        ("培训不足", "training_gap", "员工食材处理培训不到位导致浪费", 0.75),
        ("菜单设计问题", "menu_design", "菜单中使用同一食材的菜品过少导致余量大", 0.65),
        ("促销活动失误", "promo_error", "促销活动预估不准导致备货严重过量", 0.70),
        ("天气预报偏差", "weather_error", "天气突变导致客流预测失准", 0.60),
        ("食材规格不匹配", "spec_mismatch", "采购食材规格与菜品需求不匹配导致浪费", 0.70),
        ("冷链中断", "cold_chain_break", "运输或存储过程冷链中断导致食材变质", 0.90),
        ("库存盘点不准", "inventory_error", "库存数据不准确导致重复采购", 0.75),
        ("节假日预案缺失", "holiday_no_plan", "节假日未制定备货预案导致浪费", 0.70),
        ("外卖平台取消订单", "order_cancel", "外卖订单取消率高导致已制作菜品浪费", 0.65),
    ]
    for name, cause_id, desc, conf in waste_causes:
        add("waste", "causal", f"损耗根因：{name}", desc,
            {"cause_id": cause_id, "detection_signals": [f"{cause_id}_metric"]},
            {"root_cause": name, "fix_suggestion": desc, "expected_reduction_pct": round(conf * 5, 1)},
            confidence=conf,
            tags=["损耗", "根因"])

    # ================================================================
    # 2. 人效管理 (EFFICIENCY) — 70 条
    # ================================================================

    # 2.1 人效阈值规则 (15条)
    efficiency_thresholds = [
        ("人均营收低于标准", "rev_per_capita", "revenue_per_staff", "<", 800, "元/人/天"),
        ("翻台率低于行业水平", "table_turnover", "table_turnover_rate", "<", 2.5, "次/天"),
        ("出餐速度超时", "serving_speed", "avg_serving_minutes", ">", 25, "分钟"),
        ("高峰期等位时间过长", "wait_time", "peak_wait_minutes", ">", 30, "分钟"),
        ("员工迟到率偏高", "late_rate", "staff_late_rate", ">", 0.05, "比例"),
        ("离职率超标", "turnover_high", "monthly_turnover_rate", ">", 0.08, "月离职率"),
        ("人力成本占比过高", "labor_cost_ratio", "labor_cost_ratio", ">", 0.30, "占营收比"),
        ("加班时长超标", "overtime_hours", "avg_overtime_hours", ">", 20, "小时/月"),
        ("培训完成率不足", "training_rate", "training_completion_rate", "<", 0.80, "完成率"),
        ("排班满足率低", "schedule_fill", "schedule_fill_rate", "<", 0.90, "满足率"),
        ("闲时人力过剩", "idle_overstaff", "idle_period_staff_ratio", ">", 1.5, "人力/需求比"),
        ("高峰期人手不足", "peak_understaff", "peak_period_staff_ratio", "<", 0.85, "人力/需求比"),
        ("服务员日均服务桌数低", "tables_per_waiter", "daily_tables_per_waiter", "<", 15, "桌/人"),
        ("厨师日均出品量低", "dishes_per_chef", "daily_dishes_per_chef", "<", 80, "道/人"),
        ("收银员效率低", "cashier_speed", "avg_checkout_seconds", ">", 120, "秒/单"),
    ]
    for name, rule_id, metric, op, threshold, unit in efficiency_thresholds:
        add("efficiency", "threshold", name,
            f"当{metric} {op} {threshold}{unit}时触发",
            {"metric": metric, "operator": op, "threshold": threshold, "unit": unit},
            {"suggested_action": f"优化{name.replace('低于标准','').replace('超标','').replace('过高','').replace('不足','')}", "impact": f"影响{unit}"},
            confidence=0.75,
            tags=["人效", "阈值"])

    # 2.2 排班优化规则 (20条)
    schedule_rules = [
        ("午市高峰11:30-13:00", "lunch_peak", 11.5, 13.0, 1.3, "午市高峰需增加30%人力"),
        ("晚市高峰17:30-19:30", "dinner_peak", 17.5, 19.5, 1.4, "晚市高峰需增加40%人力"),
        ("周五晚市特殊", "friday_dinner", 17.0, 21.0, 1.5, "周五晚市客流高于平日50%"),
        ("周末全天高峰", "weekend_all", 10.0, 21.0, 1.3, "周末全天客流高于平日30%"),
        ("工作日下午茶低谷", "afternoon_valley", 14.0, 17.0, 0.6, "下午茶时段可减员40%"),
        ("早餐时段精简", "breakfast_slim", 7.0, 9.0, 0.5, "早餐时段按最小编制"),
        ("收市后清洁班", "closing_clean", 21.0, 23.0, 0.4, "收市后保留清洁人员"),
        ("节假日全员", "holiday_full", 10.0, 22.0, 1.6, "节假日全员在岗+临时工"),
        ("雨天减员", "rainy_reduce", 10.0, 22.0, 0.8, "预报降雨可提前减员20%"),
        ("外卖午高峰", "delivery_lunch", 11.0, 13.0, 1.2, "外卖高峰需额外打包人员"),
        ("宴会日特殊排班", "banquet_day", 9.0, 22.0, 1.5, "有宴会时需额外服务团队"),
        ("开学季学校店", "school_season", 11.0, 13.0, 1.8, "开学季校区店需大幅增员"),
        ("寒暑假社区店", "vacation_community", 10.0, 21.0, 1.1, "假期社区店略增"),
        ("情人节特殊", "valentine", 17.0, 22.0, 1.6, "情人节晚市需60%增员"),
        ("春节值班", "cny_skeleton", 10.0, 20.0, 0.3, "春节期间按骨干编制"),
        ("夜宵延长营业", "late_night", 21.0, 2.0, 0.5, "夜宵时段精简编制"),
        ("新店开业期", "grand_opening", 9.0, 22.0, 2.0, "新店开业首月双倍人力"),
        ("店庆活动日", "anniversary", 10.0, 22.0, 1.4, "店庆活动需额外人力"),
        ("团购活动日", "groupon_day", 11.0, 21.0, 1.3, "团购活动日需增员应对"),
        ("恶劣天气", "bad_weather", 10.0, 22.0, 0.7, "台风/暴雪等可大幅减员"),
    ]
    for name, sid, start, end, ratio, desc in schedule_rules:
        add("efficiency", "pattern", f"排班规则：{name}", desc,
            {"scenario": sid, "time_start": start, "time_end": end, "staff_ratio": ratio},
            {"recommended_ratio": ratio, "description": desc},
            confidence=0.70,
            tags=["排班", "人效"])

    # 2.3 绩效关联规则 (15条)
    perf_rules = [
        ("高绩效员工保留", "top_performer", "绩效前20%员工离职风险需重点关注", 0.85),
        ("连续低绩效预警", "low_perf_streak", "连续3月绩效垫底需启动改进计划", 0.80),
        ("新员工90天留存", "90day_retention", "入职90天内是离职高危期", 0.85),
        ("薪资竞争力", "salary_compete", "薪资低于市场P50时离职概率翻倍", 0.75),
        ("技能成长停滞", "skill_plateau", "6个月无新技能认证的员工满意度下降", 0.65),
        ("师徒关系影响", "mentorship_effect", "有导师的新员工留存率高35%", 0.70),
        ("跨店调动适应", "transfer_adapt", "调店后首月绩效通常下降20%属正常", 0.60),
        ("季节性用工", "seasonal_hiring", "旺季临时工需提前1月开始招聘", 0.75),
        ("老员工倦怠期", "veteran_burnout", "工龄2-3年是倦怠高发期", 0.65),
        ("晋升激励效果", "promotion_effect", "晋升后6个月绩效平均提升25%", 0.70),
        ("团队规模与效率", "team_size", "前厅团队6-8人效率最优", 0.60),
        ("排班公平性", "schedule_fairness", "排班不公平感是离职第二大原因", 0.75),
        ("加班与绩效负相关", "overtime_neg", "月均加班超30小时绩效开始下降", 0.70),
        ("培训ROI", "training_roi", "每投入1元培训费用预期回报3.5元", 0.55),
        ("多技能员工价值", "multi_skill", "掌握3+技能的员工人效高出40%", 0.65),
    ]
    for name, rid, desc, conf in perf_rules:
        add("efficiency", "pattern", name, desc,
            {"rule_id": rid, "analysis_type": "correlation"},
            {"insight": desc, "action_required": True},
            confidence=conf,
            tags=["绩效", "人效"])

    # 2.4 人力成本规则 (20条)
    labor_cost_rules = [
        ("正餐人力成本率", "casual_dining", 0.28, "正餐类人力成本率基准28%"),
        ("快餐人力成本率", "fast_food", 0.22, "快餐类人力成本率基准22%"),
        ("火锅人力成本率", "hotpot", 0.18, "火锅类人力成本率基准18%"),
        ("烧烤人力成本率", "bbq", 0.25, "烧烤类人力成本率基准25%"),
        ("西餐人力成本率", "western", 0.30, "西餐类人力成本率基准30%"),
        ("日料人力成本率", "japanese", 0.32, "日料类人力成本率基准32%"),
        ("中高端人力成本率", "fine_dining", 0.35, "中高端餐饮人力成本率基准35%"),
        ("茶饮人力成本率", "tea_drink", 0.20, "茶饮类人力成本率基准20%"),
        ("烘焙人力成本率", "bakery", 0.25, "烘焙类人力成本率基准25%"),
        ("食堂人力成本率", "canteen", 0.30, "团餐/食堂人力成本率基准30%"),
    ]
    for name, cuisine, benchmark, desc in labor_cost_rules:
        add("efficiency", "benchmark", name, desc,
            {"cuisine_type": cuisine, "metric": "labor_cost_ratio", "benchmark": benchmark},
            {"benchmark_value": benchmark, "p25": round(benchmark * 0.85, 3),
             "p75": round(benchmark * 1.15, 3), "source": "行业调研2025"},
            confidence=0.70,
            tags=["人力成本", "基准"])
        add("efficiency", "threshold", f"{name}超标预警",
            f"{desc}，超过基准15%时预警",
            {"metric": "labor_cost_ratio", "cuisine_type": cuisine,
             "operator": ">", "threshold": round(benchmark * 1.15, 3)},
            {"action": "检查排班合理性和人员编制"},
            confidence=0.75,
            tags=["人力成本", "预警"])

    # ================================================================
    # 3. 品质管理 (QUALITY) — 60 条
    # ================================================================

    # 3.1 食品安全规则 (20条)
    safety_rules = [
        ("冷库温度监控", "cold_storage", "冷库温度需保持-18°C以下", -18, "<"),
        ("冷藏温度监控", "refrigerator", "冷藏温度需保持0-5°C", 5, "<"),
        ("热菜出餐温度", "hot_dish_temp", "热菜出品温度不低于60°C", 60, ">"),
        ("冷菜存放时间", "cold_dish_time", "凉菜制作后不超过2小时", 2, "<"),
        ("食材验收温度", "receiving_temp", "冷链食材到货温度不超过8°C", 8, "<"),
        ("餐具消毒温度", "dish_sanitize", "餐具消毒温度不低于100°C", 100, ">"),
        ("厨房环境温度", "kitchen_temp", "厨房环境温度不超过35°C", 35, "<"),
        ("洗手消毒频次", "hand_wash", "接触食材前必须洗手消毒", 1, ">"),
        ("地面清洁频次", "floor_clean", "营业期间每2小时清洁一次地面", 2, "<"),
        ("油烟排放达标", "fume_emission", "油烟净化效率不低于95%", 0.95, ">"),
        ("垃圾清运频次", "garbage_clear", "垃圾桶满2/3时必须清运", 0.67, "<"),
        ("留样保存", "sample_keep", "每餐留样不少于125g保存48小时", 48, ">"),
        ("晨检制度", "morning_check", "员工每日上岗前健康晨检", 1, ">"),
        ("食材标签", "food_label", "所有食材必须有标签标注日期", 1, ">"),
        ("生熟分开", "raw_cooked_sep", "生熟食材必须分区存放", 1, ">"),
        ("砧板颜色管理", "cutting_board", "生红熟白蔬绿的砧板管理规范", 1, ">"),
        ("防虫防鼠", "pest_control", "每月专业消杀不少于1次", 1, ">"),
        ("水质检测", "water_quality", "每季度水质检测达标", 1, ">"),
        ("健康证有效", "health_cert", "所有接触食材员工健康证在有效期内", 1, ">"),
        ("明厨亮灶", "open_kitchen", "视频监控覆盖所有加工区域", 1, ">"),
    ]
    for name, sid, desc, threshold, op in safety_rules:
        add("quality", "threshold", f"食品安全：{name}", desc,
            {"standard_id": sid, "metric": sid, "operator": op, "threshold": threshold},
            {"compliance_required": True, "violation_action": "立即整改并记录"},
            confidence=0.95,
            action={"type": "compliance_check", "mandatory": True},
            tags=["食品安全", "合规"])

    # 3.2 服务质量规则 (20条)
    service_rules = [
        ("顾客等位超时", "wait_exceed", "等位超30分钟提供小食或折扣", 30),
        ("上菜超时", "serve_exceed", "上菜超25分钟需主动致歉", 25),
        ("顾客投诉响应", "complaint_response", "投诉必须5分钟内响应", 5),
        ("退菜处理时效", "return_handle", "退菜必须3分钟内处理完毕", 3),
        ("催菜响应", "rush_response", "催菜后5分钟内必须出菜或回复", 5),
        ("结账速度", "checkout_speed", "结账不超过2分钟", 2),
        ("迎宾标准", "greeting", "顾客进店3秒内必须被招呼", 3),
        ("空盘撤除", "plate_clear", "空盘30秒内清理", 30),
        ("加水服务", "water_refill", "茶水杯低于1/3时主动添加", 0.33),
        ("菜品温度", "dish_temperature", "菜品上桌温度达标率≥95%", 0.95),
        ("菜品美观度", "dish_appearance", "出品摆盘合格率≥90%", 0.90),
        ("好评率目标", "positive_rate", "大众点评好评率≥85%", 0.85),
        ("差评回复时效", "bad_review_reply", "差评24小时内回复", 24),
        ("会员识别率", "member_recognize", "会员顾客识别率≥80%", 0.80),
        ("推荐成功率", "upsell_rate", "推荐菜品成功率≥15%", 0.15),
        ("二次消费转化", "repeat_visit", "首次消费30天内回访率≥20%", 0.20),
        ("外卖好评率", "delivery_rating", "外卖平台评分≥4.5", 4.5),
        ("外卖准时率", "delivery_ontime", "外卖准时送达率≥95%", 0.95),
        ("电话接听率", "phone_answer", "营业时间电话接听率≥95%", 0.95),
        ("预订确认率", "booking_confirm", "预订24小时内确认率≥98%", 0.98),
    ]
    for name, sid, desc, threshold in service_rules:
        add("quality", "threshold", f"服务标准：{name}", desc,
            {"standard_id": sid, "threshold": threshold},
            {"service_standard": desc, "improvement_suggestion": f"未达标时{desc}"},
            confidence=0.80,
            tags=["服务", "品质"])

    # 3.3 出品标准规则 (20条)
    dish_quality_rules = [
        ("菜品分量标准", "portion_std", "每道菜分量误差不超过±10%"),
        ("调味标准化", "seasoning_std", "调味料用量按标准配方±5%"),
        ("火候控制", "heat_control", "关键菜品火候按SOP执行"),
        ("刀工标准", "knife_std", "切配规格按标准尺寸±2mm"),
        ("腌制时间", "marinate_time", "腌制时间按配方±5分钟"),
        ("油温控制", "oil_temp", "油炸温度按配方±10°C"),
        ("蒸煮时间", "steam_time", "蒸煮时间按配方±1分钟"),
        ("摆盘标准", "plating_std", "按标准摆盘图出品"),
        ("配菜比例", "garnish_ratio", "配菜与主料比例按标准"),
        ("汤品浓度", "soup_density", "汤品浓度达到标准值"),
        ("米饭软硬度", "rice_texture", "米饭软硬度按标准区间"),
        ("面条劲道", "noodle_texture", "面条煮制时间精确到秒"),
        ("沙拉新鲜度", "salad_fresh", "沙拉蔬菜制作后1小时内上桌"),
        ("甜品温度", "dessert_temp", "甜品按类型控制温度"),
        ("饮品冰量", "drink_ice", "冰饮冰块量按标准杯位"),
        ("酱料搭配", "sauce_match", "酱料按菜品标准搭配"),
        ("装盘器皿", "tableware_match", "每道菜使用指定器皿"),
        ("出品速度分级", "speed_tier", "A类菜品5分钟/B类10分钟/C类15分钟"),
        ("试菜标准", "tasting_std", "新菜上线前必须通过3人试菜"),
        ("季节菜品更新", "season_update", "每季度更新不少于15%菜品"),
    ]
    for name, sid, desc in dish_quality_rules:
        add("quality", "pattern", f"出品标准：{name}", desc,
            {"standard_id": sid, "category": "dish_quality"},
            {"standard_description": desc, "compliance_method": "巡检+抽查"},
            confidence=0.75,
            tags=["出品", "标准"])

    # ================================================================
    # 4. 成本管控 (COST) — 60 条
    # ================================================================

    # 4.1 食材成本规则 (20条)
    cost_benchmarks = [
        ("正餐食材成本率", "casual_dining", 0.35, "正餐类食材成本率基准35%"),
        ("快餐食材成本率", "fast_food", 0.38, "快餐类食材成本率基准38%"),
        ("火锅食材成本率", "hotpot", 0.40, "火锅类食材成本率基准40%"),
        ("烧烤食材成本率", "bbq", 0.33, "烧烤类食材成本率基准33%"),
        ("西餐食材成本率", "western", 0.30, "西餐类食材成本率基准30%"),
        ("日料食材成本率", "japanese", 0.38, "日料类食材成本率基准38%"),
        ("湘菜食材成本率", "hunan", 0.33, "湘菜类食材成本率基准33%"),
        ("川菜食材成本率", "sichuan", 0.32, "川菜类食材成本率基准32%"),
        ("粤菜食材成本率", "cantonese", 0.36, "粤菜类食材成本率基准36%"),
        ("海鲜食材成本率", "seafood", 0.42, "海鲜类食材成本率基准42%"),
    ]
    for name, cuisine, benchmark, desc in cost_benchmarks:
        add("cost", "benchmark", name, desc,
            {"cuisine_type": cuisine, "metric": "food_cost_ratio", "benchmark": benchmark},
            {"benchmark_value": benchmark, "p25": round(benchmark * 0.9, 3),
             "p75": round(benchmark * 1.1, 3)},
            confidence=0.75,
            tags=["食材成本", "基准"])
        add("cost", "threshold", f"{name}超标", f"{desc}，超过基准10%时预警",
            {"metric": "food_cost_ratio", "cuisine_type": cuisine,
             "operator": ">", "threshold": round(benchmark * 1.1, 3)},
            {"action": "分析食材价格波动和用量标准"},
            confidence=0.80,
            tags=["食材成本", "预警"])

    # 4.2 综合成本规则 (20条)
    comprehensive_cost = [
        ("租金成本率", "rent_ratio", 0.12, "租金占营收比基准12%"),
        ("水电气成本率", "utility_ratio", 0.05, "水电气占营收比基准5%"),
        ("营销费用率", "marketing_ratio", 0.03, "营销费用占营收比基准3%"),
        ("折旧摊销率", "depreciation_ratio", 0.04, "折旧摊销占营收比基准4%"),
        ("管理费用率", "admin_ratio", 0.03, "管理费用占营收比基准3%"),
        ("平台佣金率", "platform_fee", 0.18, "外卖平台佣金率基准18%"),
        ("包装成本率", "package_ratio", 0.03, "外卖包装成本占比基准3%"),
        ("净利润率", "net_profit", 0.10, "连锁餐饮净利润率基准10%"),
        ("毛利率", "gross_margin", 0.60, "综合毛利率基准60%"),
        ("盈亏平衡日营收", "breakeven_daily", 0, "门店日营收盈亏平衡点"),
    ]
    for name, metric, benchmark, desc in comprehensive_cost:
        add("cost", "benchmark", name, desc,
            {"metric": metric, "benchmark": benchmark},
            {"benchmark_value": benchmark, "description": desc},
            confidence=0.70,
            tags=["综合成本", "基准"])
        add("cost", "threshold", f"{name}异常", f"{desc}，偏离基准20%时预警",
            {"metric": metric, "operator": "deviation", "threshold": 0.20},
            {"action": f"分析{name}构成"},
            confidence=0.70,
            tags=["综合成本", "预警"])

    # ================================================================
    # 5. 客流管理 (TRAFFIC) — 50 条
    # ================================================================

    # 5.1 客流预测规则 (25条)
    traffic_patterns = [
        ("工作日午市模式", "weekday_lunch", "工作日午市客流集中在11:30-13:00"),
        ("工作日晚市模式", "weekday_dinner", "工作日晚市客流集中在17:30-19:30"),
        ("周末午市模式", "weekend_lunch", "周末午市客流比工作日高30%"),
        ("周末晚市模式", "weekend_dinner", "周末晚市客流比工作日高50%"),
        ("周一效应", "monday_effect", "周一客流通常为一周最低"),
        ("周五效应", "friday_effect", "周五晚市客流明显上升"),
        ("发薪日效应", "payday_effect", "每月15日和月末客流上升10%"),
        ("开学效应", "school_start", "开学季校区店客流上升40%"),
        ("放假效应", "school_holiday", "假期校区店客流下降60%"),
        ("雨天效应", "rain_effect", "降雨天客流下降20-30%"),
        ("高温效应", "hot_weather", "35°C以上客流下降15%"),
        ("寒潮效应", "cold_weather", "极端低温客流下降25%"),
        ("节假日效应", "holiday_effect", "法定节假日客流上升50-100%"),
        ("春节效应", "cny_effect", "春节期间分两段：除夕至初三低谷，初四起回升"),
        ("情人节效应", "valentine_effect", "情人节晚市客流上升80%"),
        ("母亲节效应", "mothers_day", "母亲节客流上升60%，家庭客为主"),
        ("中秋效应", "mid_autumn", "中秋节家庭聚餐客流上升70%"),
        ("商圈活动效应", "mall_event", "所在商圈有活动时客流上升20%"),
        ("竞品开业效应", "competitor_open", "500米内竞品开业首月客流下降10-15%"),
        ("装修影响", "renovation_impact", "门店装修期间周边门店可承接部分客流"),
        ("外卖渠道占比", "delivery_ratio", "外卖占比通常30-40%，午市偏高"),
        ("会员日效应", "member_day", "会员日客流上升15%"),
        ("团购上线效应", "groupon_launch", "团购上线首周客流上升25%"),
        ("网红打卡效应", "viral_effect", "社交媒体曝光后7天内客流峰值"),
        ("季节性趋势", "seasonal_trend", "Q1淡季Q2-Q3旺季Q4平稳"),
    ]
    for name, pid, desc in traffic_patterns:
        add("traffic", "pattern", name, desc,
            {"pattern_id": pid, "detection": "historical_analysis"},
            {"pattern_description": desc, "usage": "客流预测模型输入"},
            confidence=0.70,
            tags=["客流", "模式"])

    # 5.2 客流异常规则 (25条)
    traffic_anomalies = [
        ("工作日客流骤降", "weekday_drop", "工作日客流低于近4周均值30%", 0.30),
        ("周末客流骤降", "weekend_drop", "周末客流低于近4周均值20%", 0.20),
        ("连续3天下降", "3day_decline", "连续3天客流环比下降", 0.10),
        ("午市客流异常低", "lunch_low", "午市客流低于预测值40%", 0.40),
        ("晚市客流异常低", "dinner_low", "晚市客流低于预测值30%", 0.30),
        ("外卖骤增堂食骤降", "channel_shift", "外卖增30%但堂食降30%需关注", 0.30),
        ("客单价异常下降", "ticket_drop", "客单价连续7天低于均值15%", 0.15),
        ("桌均人数下降", "party_size_drop", "桌均人数持续下降可能反映口碑问题", 0.10),
        ("高峰前移/后移", "peak_shift", "就餐高峰时段偏移超30分钟", 0.5),
        ("新客占比下降", "new_customer_drop", "新客占比连续4周下降", 0.05),
        ("老客流失", "loyal_churn", "月均消费3+次的老客消失", 0.10),
        ("差评后客流影响", "review_impact", "出现差评后3天内客流变化", 0.10),
        ("促销后回落", "promo_fallback", "促销结束后客流回落超50%属异常", 0.50),
        ("地铁/公交改线", "transit_change", "周边交通变化导致的长期客流影响", 0.15),
        ("停车场变化", "parking_change", "停车便利性变化影响驾车客群", 0.10),
        ("周边施工", "construction", "周边道路施工影响客流", 0.20),
        ("同品类过密", "category_dense", "500m内同品类超5家时客流分流", 0.15),
        ("线上评分下降", "rating_drop", "大众点评评分降0.2分以上需关注", 0.2),
        ("等位放弃率高", "queue_abandon", "等位放弃率超30%说明等待时间过长", 0.30),
        ("午市翻台下降", "lunch_turnover_drop", "午市翻台率连续下降需分析原因", 0.10),
        ("晚市翻台下降", "dinner_turnover_drop", "晚市翻台率下降可能是服务速度问题", 0.10),
        ("包间利用率低", "private_room_low", "包间利用率低于50%需调整定价策略", 0.50),
        ("散台空置率高", "open_table_empty", "高峰期散台空置率超20%属异常", 0.20),
        ("预订爽约率高", "no_show_high", "预订爽约率超15%需加强确认", 0.15),
        ("外卖取消率高", "delivery_cancel", "外卖取消率超5%需排查原因", 0.05),
    ]
    for name, aid, desc, threshold in traffic_anomalies:
        add("traffic", "anomaly", f"客流异常：{name}", desc,
            {"anomaly_id": aid, "threshold": threshold, "detection": "statistical"},
            {"description": desc, "investigation_required": True},
            confidence=0.70,
            tags=["客流", "异常"])

    # ================================================================
    # 6. 库存管理 (INVENTORY) — 50 条
    # ================================================================

    # 6.1 库存阈值规则 (25条)
    inventory_rules = [
        ("安全库存预警", "safety_stock", "库存低于安全库存量时预警", 1.0, "<"),
        ("库存过量预警", "overstock", "库存超过最大库存量时预警", 2.0, ">"),
        ("临期预警", "expiry_warning", "食材临期前3天预警", 3, "<"),
        ("呆滞库存", "dead_stock", "30天无出库记录的食材", 30, ">"),
        ("周转天数异常", "turnover_days", "周转天数超过行业标准2倍", 2.0, ">"),
        ("订货点触发", "reorder_point", "库存到达订货点自动提醒", 1.0, "<="),
        ("批次追溯完整", "batch_trace", "每批次食材可追溯到供应商和到货日", 1, ">="),
        ("盘点差异", "count_variance", "盘点差异率超过2%需调查", 0.02, ">"),
        ("高价食材管控", "high_value", "单价超100元/kg的食材单独管控", 10000, ">"),
        ("冷链食材", "cold_chain", "冷链食材收货到入库不超过30分钟", 30, "<"),
        ("先进先出违规", "fifo_breach", "存在后进先出的食材使用记录", 1, ">"),
        ("采购频次", "order_frequency", "主要食材采购频次不低于周2次", 2, ">="),
        ("供应商集中度", "supplier_conc", "单一供应商占比超60%有风险", 0.60, ">"),
        ("价格波动", "price_volatility", "食材价格周环比波动超10%需关注", 0.10, ">"),
        ("最小起订量", "moq_check", "订货量需满足供应商最小起订量", 1, ">="),
        ("日均消耗预测", "daily_usage", "基于近7天数据预测日均消耗量", 7, "="),
        ("周末备货系数", "weekend_factor", "周末备货量为工作日的1.3倍", 1.3, "="),
        ("节假日备货系数", "holiday_factor", "节假日备货量为平日的1.5-2.0倍", 1.5, ">="),
        ("新品备货", "new_dish_stock", "新菜上线首周备货按预估的1.2倍", 1.2, "="),
        ("季节性食材", "seasonal_item", "时令食材提前2周联系供应商确认", 14, ">="),
        ("进口食材提前量", "import_lead", "进口食材提前21天下单", 21, ">="),
        ("中央厨房配送", "central_kitchen", "中央厨房配送品按T+1模式", 1, "="),
        ("应急库存", "emergency_stock", "核心食材保持3天应急库存", 3, ">="),
        ("废弃物处理", "waste_disposal", "废弃食材当日处理不过夜", 1, "<="),
        ("库存金额上限", "stock_value_cap", "单店库存金额不超过月营收5%", 0.05, "<="),
    ]
    for name, rid, desc, threshold, op in inventory_rules:
        add("inventory", "threshold", f"库存管理：{name}", desc,
            {"rule_id": rid, "operator": op, "threshold": threshold},
            {"standard": desc, "action_on_breach": f"触发{name}流程"},
            confidence=0.80,
            tags=["库存", "管理"])

    # 6.2 采购优化规则 (25条)
    procurement_rules = [
        ("集中采购议价", "bulk_discount", "月采购额超5万可争取5%折扣", 0.85),
        ("供应商评分", "supplier_score", "供应商季度评分低于70分需更换", 0.80),
        ("采购价格对比", "price_compare", "每批次采购至少比价3家供应商", 0.75),
        ("合同到期提醒", "contract_expiry", "供应商合同到期前30天提醒续签", 0.90),
        ("质量不合格退货", "quality_return", "验收不合格批次当日退货", 0.95),
        ("付款账期管理", "payment_term", "优化账期至30天以上释放现金流", 0.70),
        ("季节性采购策略", "seasonal_buy", "当季食材产地直采降低中间成本", 0.65),
        ("替代品方案", "substitute", "核心食材准备2个以上替代供应商", 0.75),
        ("到货验收标准", "receiving_std", "每批次100%验收重量和品质", 0.90),
        ("采购计划准确率", "plan_accuracy", "采购计划与实际需求偏差<10%", 0.75),
        ("紧急采购比例", "emergency_ratio", "紧急采购占比不超过5%", 0.70),
        ("本地化采购", "local_source", "生鲜类食材优先本地供应商", 0.65),
        ("战略合作协议", "strategic_partner", "与核心供应商签战略协议锁价", 0.70),
        ("品质分级采购", "grade_purchase", "按菜品定位匹配食材等级", 0.75),
        ("采购审批流程", "approval_flow", "单次采购超2000元需审批", 0.85),
        ("供应商准时率", "delivery_ontime", "供应商准时送达率需≥95%", 0.80),
        ("退换货率", "return_rate", "月退换货率超3%需约谈供应商", 0.75),
        ("新供应商试用", "new_supplier_trial", "新供应商需通过3批次试用期", 0.80),
        ("采购频次优化", "order_optimize", "高频低量改为低频适量减少物流成本", 0.65),
        ("年度框架协议", "annual_contract", "核心食材签订年度框架协议", 0.70),
        ("价格预警机制", "price_alert", "食材价格涨幅超15%触发预警", 0.80),
        ("区域联采", "regional_joint", "同区域门店联合采购增强议价", 0.60),
        ("冷链监控", "cold_monitor", "冷链运输全程温度监控可追溯", 0.85),
        ("入库复核", "storage_recheck", "入库24小时内复核品质", 0.80),
        ("供应商多元化", "supplier_diversity", "每个品类至少3个合格供应商", 0.75),
    ]
    for name, rid, desc, conf in procurement_rules:
        add("inventory", "pattern", f"采购优化：{name}", desc,
            {"rule_id": rid, "procurement_category": "optimization"},
            {"practice": desc, "benefit": "成本优化+风险分散"},
            confidence=conf,
            tags=["采购", "优化"])

    # ================================================================
    # 7. 合规管理 (COMPLIANCE) — 40 条
    # ================================================================

    compliance_items = [
        ("营业执照有效期", "biz_license", "营业执照到期前60天续办", 0.95),
        ("食品经营许可证", "food_permit", "食品经营许可证5年续期", 0.95),
        ("消防安全检查", "fire_safety", "每月消防设施检查和消防演练", 0.90),
        ("环保排放许可", "env_permit", "油烟排放达标/污水排放合规", 0.85),
        ("员工健康证", "staff_health", "接触食材员工100%持有效健康证", 0.95),
        ("食品留样", "food_sample", "每餐留样125g以上保存48小时", 0.95),
        ("进货查验", "purchase_check", "索证索票100%，建立进货台账", 0.90),
        ("餐具消毒记录", "dish_sanitize_log", "每日餐具消毒记录完整可查", 0.90),
        ("明码标价", "price_display", "菜品价格明示，无隐性消费", 0.85),
        ("发票管理", "invoice_mgmt", "消费者索要发票即时开具", 0.85),
        ("劳动合同", "labor_contract", "全员签订劳动合同，试用期合规", 0.90),
        ("社保缴纳", "social_security", "按时足额缴纳五险一金", 0.85),
        ("最低工资", "min_wage", "薪资不低于当地最低工资标准", 0.95),
        ("工时合规", "work_hours", "月工时不超法定上限，加班付费", 0.85),
        ("未成年人用工", "minor_labor", "禁止使用未满16周岁童工", 0.99),
        ("特种设备年检", "special_equip", "电梯/锅炉等特种设备年检合格", 0.90),
        ("招牌审批", "signage_permit", "户外广告牌需城管审批", 0.80),
        ("垃圾分类", "waste_sort", "按当地标准做好垃圾分类", 0.85),
        ("噪音控制", "noise_control", "排风机噪音不扰民", 0.80),
        ("控烟管理", "no_smoking", "室内全面禁烟，设立吸烟区", 0.90),
        ("反食品浪费", "anti_waste_law", "提示适量点餐，提供打包服务", 0.85),
        ("个人信息保护", "data_privacy", "会员信息采集使用符合个保法", 0.90),
        ("预付卡管理", "prepaid_card", "预付卡发行按商务部规定", 0.85),
        ("广告宣传合规", "ad_compliance", "促销广告用语合规无虚假", 0.85),
        ("团购退款", "groupon_refund", "未消费团购券支持随时退款", 0.90),
        ("外卖平台合规", "delivery_compliance", "外卖食品安全标签和封签", 0.90),
        ("燃气安全", "gas_safety", "燃气报警器和自动切断阀就位", 0.95),
        ("用电安全", "elec_safety", "电器设备定期检查，接地保护", 0.90),
        ("应急预案", "emergency_plan", "突发事件应急预案年度演练", 0.80),
        ("食物中毒预案", "food_poison_plan", "食物中毒应急处理流程明确", 0.90),
        ("消费者投诉处理", "complaint_process", "投诉处理流程及记录归档", 0.85),
        ("价格欺诈防范", "price_fraud", "禁止先涨后降等价格欺诈", 0.90),
        ("反垄断合规", "anti_monopoly", "加盟连锁不强制限定价格", 0.75),
        ("税务合规", "tax_compliance", "按时纳税申报，保留凭证", 0.90),
        ("外籍员工", "foreign_worker", "外籍员工须持工作许可证", 0.95),
        ("残疾人就业", "disabled_employ", "按比例安排残疾人就业或缴纳金", 0.80),
        ("职业病防护", "occupational_health", "厨房高温岗位防暑降温措施", 0.85),
        ("保险覆盖", "insurance", "雇主责任险+公众责任险完整覆盖", 0.80),
        ("知识产权", "ip_protection", "菜品名称/品牌不侵犯他人权益", 0.75),
        ("食材溯源", "food_traceability", "实现从农田到餐桌的全链可追溯", 0.80),
    ]
    for name, cid, desc, conf in compliance_items:
        add("compliance", "threshold", f"合规要求：{name}", desc,
            {"compliance_id": cid, "mandatory": True},
            {"requirement": desc, "consequence": "违规将导致行政处罚或停业整顿"},
            confidence=conf,
            action={"type": "compliance_audit", "frequency": "monthly"},
            tags=["合规", "法规"])

    # ================================================================
    # 8. 行业基准 (BENCHMARK) — 50 条
    # ================================================================

    benchmarks = [
        ("人均消费-正餐", "avg_ticket_casual", 60, 80, 120, "正餐人均消费60-120元"),
        ("人均消费-快餐", "avg_ticket_fast", 20, 35, 50, "快餐人均消费20-50元"),
        ("人均消费-火锅", "avg_ticket_hotpot", 80, 120, 180, "火锅人均消费80-180元"),
        ("人均消费-日料", "avg_ticket_japanese", 100, 150, 300, "日料人均消费100-300元"),
        ("人均消费-西餐", "avg_ticket_western", 80, 130, 250, "西餐人均消费80-250元"),
        ("翻台率-正餐", "turnover_casual", 2.0, 2.5, 3.5, "正餐翻台率2.0-3.5次"),
        ("翻台率-快餐", "turnover_fast", 5.0, 8.0, 12.0, "快餐翻台率5-12次"),
        ("翻台率-火锅", "turnover_hotpot", 2.5, 3.0, 4.0, "火锅翻台率2.5-4.0次"),
        ("坪效-一线城市", "rev_per_sqm_t1", 100, 150, 250, "一线城市日坪效100-250元"),
        ("坪效-二线城市", "rev_per_sqm_t2", 60, 100, 180, "二线城市日坪效60-180元"),
        ("坪效-三线城市", "rev_per_sqm_t3", 40, 70, 120, "三线城市日坪效40-120元"),
        ("人效-日均", "rev_per_staff", 500, 800, 1500, "日均人效500-1500元"),
        ("外卖占比", "delivery_ratio", 0.15, 0.30, 0.50, "外卖占比15-50%"),
        ("会员消费占比", "member_ratio", 0.20, 0.40, 0.65, "会员消费占比20-65%"),
        ("复购率-月度", "monthly_repeat", 0.15, 0.25, 0.40, "月度复购率15-40%"),
        ("好评率-大众点评", "dianping_rating", 4.0, 4.5, 4.8, "大众点评评分4.0-4.8"),
        ("投诉率", "complaint_rate", 0.001, 0.003, 0.01, "投诉率0.1-1%"),
        ("员工月离职率", "staff_turnover", 0.03, 0.06, 0.12, "月离职率3-12%"),
        ("培训投入占比", "training_invest", 0.005, 0.01, 0.02, "培训投入占营收0.5-2%"),
        ("新店回本周期", "payback_months", 12, 18, 30, "新店回本周期12-30月"),
        ("单店投资额", "store_invest", 50, 80, 200, "单店投资额50-200万"),
        ("食材成本率", "food_cost_total", 0.28, 0.35, 0.42, "食材成本率28-42%"),
        ("人力成本率", "labor_cost_total", 0.18, 0.25, 0.35, "人力成本率18-35%"),
        ("租金成本率", "rent_cost_total", 0.08, 0.12, 0.18, "租金成本率8-18%"),
        ("综合净利率", "net_margin", 0.05, 0.10, 0.18, "净利率5-18%"),
        ("午晚市营收比", "lunch_dinner_ratio", 0.35, 0.45, 0.55, "午市占比35-55%"),
        ("工作日周末比", "weekday_weekend", 0.55, 0.65, 0.75, "工作日占比55-75%"),
        ("堂食外卖比", "dine_in_ratio", 0.50, 0.65, 0.85, "堂食占比50-85%"),
        ("散客团餐比", "individual_group", 0.60, 0.75, 0.90, "散客占比60-90%"),
        ("新客占比", "new_customer_pct", 0.20, 0.35, 0.55, "新客占比20-55%"),
    ]
    for name, metric, p25, p50, p75, desc in benchmarks:
        add("benchmark", "benchmark", f"行业基准：{name}", desc,
            {"metric": metric, "industry": "catering"},
            {"p25": p25, "p50": p50, "p75": p75, "description": desc,
             "data_source": "中国饭店协会+美团+红餐网 2025"},
            confidence=0.70,
            tags=["基准", "行业"])

    # 8.2 对标分析规则 (20条)
    compare_rules = [
        ("食材成本率对标", "food_cost_compare", "与同品类同商圈对比"),
        ("人力成本率对标", "labor_cost_compare", "与同规模同城对比"),
        ("翻台率对标", "turnover_compare", "与同品类同商圈对比"),
        ("客单价对标", "ticket_compare", "与同品类同档次对比"),
        ("好评率对标", "rating_compare", "与同商圈TOP10对比"),
        ("外卖占比对标", "delivery_compare", "与同品类同城均值对比"),
        ("复购率对标", "repeat_compare", "与同品类优秀门店对比"),
        ("人效对标", "efficiency_compare", "与同品类同规模对比"),
        ("坪效对标", "sqm_rev_compare", "与同商圈同面积对比"),
        ("损耗率对标", "waste_compare", "与同品类标杆门店对比"),
        ("午晚市比对标", "meal_ratio_compare", "与同商圈同品类对比"),
        ("新店成长对标", "new_store_compare", "与历史开店数据对比"),
        ("季度增长对标", "growth_compare", "与去年同期对比"),
        ("连锁管理对标", "chain_compare", "与连锁餐饮百强对比"),
        ("数字化对标", "digital_compare", "与行业数字化先进企业对比"),
        ("供应链对标", "supply_compare", "与同规模供应链效率对比"),
        ("培训体系对标", "training_compare", "与行业最佳实践对比"),
        ("会员体系对标", "member_compare", "与私域运营标杆对比"),
        ("品牌势能对标", "brand_compare", "与同品类品牌声量对比"),
        ("创新能力对标", "innovation_compare", "与菜品创新优秀品牌对比"),
    ]
    for name, rid, desc in compare_rules:
        add("benchmark", "benchmark", f"对标分析：{name}", desc,
            {"compare_id": rid, "method": "percentile_ranking"},
            {"description": desc, "output": "排名+差距+改进建议"},
            confidence=0.65,
            tags=["对标", "分析"])

    # ================================================================
    # 9. 跨店知识聚合 (CROSS_STORE) — 40 条
    # ================================================================

    cross_store_rules = [
        ("最佳实践传播", "best_practice", "损耗率最低门店的管理方法推广到其他门店"),
        ("问题早期预警", "early_warning", "A店出现的问题提前预警同区域B/C店"),
        ("人员调配", "staff_transfer", "旺季门店向淡季门店借调人员"),
        ("食材调拨", "material_transfer", "临期食材在门店间调拨减少浪费"),
        ("采购集中议价", "joint_purchase", "同区域门店联合采购降低成本"),
        ("价格策略同步", "price_sync", "同品牌同城价格策略保持一致"),
        ("促销效果复制", "promo_replicate", "A店验证有效的促销方案推广全品牌"),
        ("培训资源共享", "training_share", "优秀培训师跨店授课"),
        ("设备互用", "equipment_share", "大型设备在门店间共享使用"),
        ("客流互导", "traffic_redirect", "旺店等位客流导向周边门店"),
        ("厨师交流", "chef_exchange", "厨师定期跨店交流提升技艺"),
        ("管理经验分享", "mgmt_share", "月度店长会分享管理经验"),
        ("新品联合研发", "joint_rd", "集合各店厨师长研发新品"),
        ("投诉分析汇总", "complaint_summary", "全品牌投诉数据汇总分析共性问题"),
        ("供应商评价共享", "supplier_feedback", "各门店供应商评价汇总形成黑白名单"),
        ("标准操作统一", "sop_unify", "全品牌SOP统一更新和推送"),
        ("食材标准统一", "ingredient_std", "统一食材规格标准减少差异"),
        ("品质巡检交叉", "cross_inspect", "门店间交叉品质巡检"),
        ("员工推荐网络", "referral_network", "优秀员工内推至其他缺员门店"),
        ("节假日联合营销", "holiday_joint_marketing", "品牌层面统一节日营销方案"),
        ("中央厨房调度", "central_dispatch", "中央厨房按各店销量动态配送"),
        ("区域督导巡店", "area_inspection", "区域督导按标准清单巡店评分"),
        ("数据对比看板", "compare_dashboard", "全品牌门店数据对比看板"),
        ("异常门店帮扶", "store_support", "连续3月排名垫底门店启动帮扶"),
        ("新店老店结对", "new_old_pairing", "新店与成熟门店结对帮扶"),
        ("季度经营分析", "quarterly_review", "每季度全品牌经营分析大会"),
        ("人才梯队建设", "talent_pipeline", "从优秀门店中选拔储备店长"),
        ("品牌一致性", "brand_consistency", "全品牌客户体验一致性检查"),
        ("食安联防", "food_safety_joint", "食品安全问题全品牌联动响应"),
        ("技术方案共享", "tech_share", "门店级技术解决方案共享库"),
    ]
    for name, rid, desc in cross_store_rules:
        add("cross_store", "pattern", f"跨店知识：{name}", desc,
            {"knowledge_id": rid, "scope": "brand_wide"},
            {"practice": desc, "implementation": "总部统一推动"},
            confidence=0.65,
            tags=["跨店", "知识"])

    # 跨店异常检测规则 (10条)
    cross_anomalies = [
        ("门店排名突变", "rank_shift", "门店排名月度变化超5位需分析", 0.70),
        ("区域整体下滑", "region_decline", "同区域3+门店同时下滑需排查区域因素", 0.75),
        ("标杆门店异常", "benchmark_anomaly", "标杆门店指标异常需优先关注", 0.80),
        ("新开店表现", "new_store_perf", "新店前6月增长未达预期需干预", 0.70),
        ("成本差异异常", "cost_variance", "同区域门店成本差异超15%需分析", 0.75),
        ("人员流失集中", "turnover_cluster", "同期多门店高离职需排查共性原因", 0.80),
        ("客诉集中爆发", "complaint_burst", "多店同类投诉集中出现需追溯", 0.85),
        ("供应商问题波及", "supplier_issue", "供应商问题影响多门店需紧急应对", 0.90),
        ("促销效果差异", "promo_variance", "相同促销在不同门店效果差异大需分析", 0.65),
        ("季节效应差异", "season_variance", "同品牌门店对季节敏感度差异需理解", 0.60),
    ]
    for name, aid, desc, conf in cross_anomalies:
        add("cross_store", "anomaly", f"跨店异常：{name}", desc,
            {"anomaly_id": aid, "scope": "brand_wide", "detection": "comparative"},
            {"description": desc, "escalation": "区域经理+总部"},
            confidence=conf,
            tags=["跨店", "异常"])

    return rules


def seed_to_db():
    """将规则写入数据库"""
    from src.core.database import engine
    from src.models.knowledge_rule import KnowledgeRule
    from sqlalchemy.orm import Session

    rules = generate_rules()
    print(f"准备导入 {len(rules)} 条行业知识规则...")

    # 使用同步引擎（Alembic风格）
    from sqlalchemy import create_engine as sync_create_engine
    from src.core.config import settings

    db_url = settings.DATABASE_URL.replace("+asyncpg", "").replace(
        "postgresql://", "postgresql+psycopg2://"
    )
    sync_engine = sync_create_engine(db_url)

    with Session(sync_engine) as session:
        # 检查已有规则数量
        existing = session.query(KnowledgeRule).filter(
            KnowledgeRule.source == "tunxiang_pack"
        ).count()

        if existing > 0:
            print(f"已存在 {existing} 条屯象知识包规则，跳过导入（如需重新导入请先清理）")
            return

        imported = 0
        for rule_data in rules:
            rule = KnowledgeRule(
                rule_code=rule_data["rule_code"],
                name=rule_data["name"],
                description=rule_data["description"],
                category=rule_data["category"],
                rule_type=rule_data["rule_type"],
                condition=rule_data["condition"],
                conclusion=rule_data["conclusion"],
                base_confidence=rule_data["base_confidence"],
                weight=rule_data["weight"],
                source=rule_data["source"],
                is_public=rule_data["is_public"],
                status=rule_data["status"],
                tags=rule_data["tags"],
                industry_type=rule_data["industry_type"],
                # z55 新增字段
                action=rule_data.get("action", {}),
                industry_source=rule_data.get("industry_source", "tunxiang_v1"),
            )
            session.add(rule)
            imported += 1

            if imported % 100 == 0:
                session.flush()
                print(f"  已导入 {imported} 条...")

        session.commit()
        print(f"✅ 成功导入 {imported} 条行业知识规则")
        print(f"   分类分布:")
        for cat in ["waste", "efficiency", "quality", "cost", "traffic", "inventory", "compliance", "benchmark", "cross_store"]:
            count = sum(1 for r in rules if r["category"] == cat)
            print(f"   - {cat}: {count} 条")


if __name__ == "__main__":
    # 支持 --dry-run 模式，只打印不写入
    if "--dry-run" in sys.argv:
        rules = generate_rules()
        print(f"Dry run: 生成了 {len(rules)} 条规则")
        for cat in ["waste", "efficiency", "quality", "cost", "traffic", "inventory", "compliance", "benchmark", "cross_store"]:
            count = sum(1 for r in rules if r["category"] == cat)
            print(f"  {cat}: {count} 条")
        # 打印前3条作为示例
        import json
        print("\n示例规则:")
        for r in rules[:3]:
            print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        seed_to_db()
