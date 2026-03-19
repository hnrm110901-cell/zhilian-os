"""
连锁餐饮岗位标准种子数据
基于行业真实岗位职责文档整理，15个核心岗位 + 5个关键SOP。

运行方式：
    python -m src.seeds.job_standards_seed
"""
import asyncio
import uuid
from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

logger = structlog.get_logger()

# ─────────────────────────────────────────────────────────────────────────────
# 岗位标准种子数据
# ─────────────────────────────────────────────────────────────────────────────

JOB_STANDARDS = [
    {
        "job_code": "ceo",
        "job_name": "CEO / 总经理 / 创始人",
        "job_level": "hq",
        "job_category": "management",
        "report_to_role": "董事会 / 投资人",
        "manages_roles": "运营负责人、供应链负责人、财务负责人、人力负责人、品牌负责人",
        "job_objective": "负责公司整体经营成果，明确品牌战略、增长路径和组织能力建设，确保企业长期可持续发展。",
        "responsibilities": [
            "制定公司中长期战略与年度经营目标",
            "明确品牌定位、目标客群、门店模型和扩张策略",
            "审批重大经营事项：开店、关店、加盟、系统建设、供应链投资",
            "搭建核心管理团队与干部梯队",
            "统筹营收、利润、现金流、安全、品牌资产",
            "推动跨部门协同，处理重大异常和关键危机",
        ],
        "daily_tasks": ["关注经营日报、异常数据、重大投诉、关键项目推进"],
        "weekly_tasks": ["主持经营周会，检查营收、利润、开店、招聘、供应链等关键进度"],
        "monthly_tasks": ["复盘月度经营结果，调整预算、目标与组织策略"],
        "kpi_targets": [
            {"name": "总营收达成率", "description": "全年总营收vs目标", "unit": "%"},
            {"name": "同店增长率", "description": "同店比较增长", "unit": "%"},
            {"name": "净利润率", "description": "净利润占营收比", "unit": "%"},
            {"name": "门店达标率", "description": "达到标准的门店占比", "unit": "%"},
            {"name": "核心干部稳定率", "description": "关键管理岗留存率", "unit": "%"},
        ],
        "experience_years_min": 8,
        "education_requirement": "本科及以上",
        "skill_requirements": ["连锁餐饮经营经验", "战略判断与组织搭建能力", "能看懂单店/区域/总部模型"],
        "common_issues": ["只看规模不看利润", "只抓门店不抓总部系统", "只靠个人盯，不做机制建设"],
        "sort_order": 1,
    },
    {
        "job_code": "coo",
        "job_name": "COO / 运营总经理",
        "job_level": "hq",
        "job_category": "management",
        "report_to_role": "CEO",
        "manages_roles": "区域经理、督导、营运支持、门店体系负责人",
        "job_objective": "将公司战略转化为门店经营结果，建立标准化、可复制、可追责的运营体系。",
        "responsibilities": [
            "负责全国/区域门店经营管理",
            "建立并优化营运标准、巡店机制、整改机制",
            "推动新店筹备、老店提升、弱店帮扶",
            "统筹前厅、后厨、服务、效率、损耗、安全",
            "联动人力、供应链、品牌、财务推动经营改善",
            "建立门店分层管理机制与干部培养机制",
        ],
        "daily_tasks": ["查看门店营业、客诉、食安、人员异常"],
        "weekly_tasks": ["组织营运周例会，推进整改清单"],
        "monthly_tasks": ["复盘区域结果、店长成熟度、门店达标率"],
        "kpi_targets": [
            {"name": "门店营业额达成率", "description": "", "unit": "%"},
            {"name": "门店利润率", "description": "", "unit": "%"},
            {"name": "同店增长率", "description": "", "unit": "%"},
            {"name": "门店标准执行率", "description": "", "unit": "%"},
            {"name": "区域整改闭环率", "description": "", "unit": "%"},
        ],
        "experience_years_min": 5,
        "education_requirement": "本科及以上",
        "skill_requirements": ["5年以上连锁餐饮营运管理经验", "带过多店/区域团队", "熟悉前厅、后厨、排班、督导、品控"],
        "common_issues": ["只巡店不解决问题", "只压指标，不辅导店长", "总部动作多，门店负担重"],
        "sort_order": 2,
    },
    {
        "job_code": "area_manager",
        "job_name": "区域经理 / 区域营运经理",
        "job_level": "region",
        "job_category": "management",
        "report_to_role": "COO / 运营负责人",
        "manages_roles": "店长、区域督导",
        "job_objective": "对所辖区域多家门店的营收、利润、人员和标准执行结果负责。",
        "responsibilities": [
            "负责区域经营目标拆解与达成",
            "巡店检查门店服务、出品、卫生、设备、人员状态",
            "帮助店长解决经营问题、人员问题和现场问题",
            "推动总部制度、营销活动、训练计划在门店落地",
            "做区域经营分析与门店分层管理",
            "培养店长、储备店长、主管梯队",
        ],
        "daily_tasks": ["查看区域经营数据，抽查重点门店"],
        "weekly_tasks": ["完成巡店、门店复盘、店长辅导"],
        "monthly_tasks": ["提交区域经营分析、干部盘点、弱店改善方案"],
        "kpi_targets": [
            {"name": "区域营收达成率", "description": "", "unit": "%"},
            {"name": "区域利润率", "description": "", "unit": "%"},
            {"name": "门店达标率", "description": "", "unit": "%"},
            {"name": "店长稳定率", "description": "", "unit": "%"},
            {"name": "门店整改完成率", "description": "", "unit": "%"},
            {"name": "食安/客诉异常数", "description": "越少越好", "unit": "次"},
        ],
        "experience_years_min": 3,
        "education_requirement": "大专及以上",
        "skill_requirements": ["有门店店长到区域管理成长路径优先", "熟悉餐饮现场管理和经营分析", "能带教店长"],
        "common_issues": ["巡店流于表面", "不敢管店长", "不会做经营分析，只会做检查"],
        "sort_order": 3,
    },
    {
        "job_code": "supervisor",
        "job_name": "营运督导",
        "job_level": "region",
        "job_category": "management",
        "report_to_role": "区域经理 / 营运负责人",
        "manages_roles": "",
        "job_objective": "监督门店标准执行，推动问题发现、整改和复盘，确保品牌可复制。",
        "responsibilities": [
            "按标准检查服务、卫生、出品、陈列、流程执行",
            "输出门店巡检报告和整改清单",
            "跟进整改进度并复查",
            "支持新店开业与重点门店帮扶",
            "参与专项检查：食安、服务、活动执行、设备、库存等",
        ],
        "daily_tasks": ["巡店、拍照取证、反馈问题"],
        "weekly_tasks": ["汇总门店问题排名和整改状态"],
        "monthly_tasks": ["输出区域标准执行分析报告"],
        "kpi_targets": [
            {"name": "巡店完成率", "description": "", "unit": "%"},
            {"name": "问题发现率", "description": "", "unit": "%"},
            {"name": "整改复查率", "description": "", "unit": "%"},
        ],
        "experience_years_min": 2,
        "education_requirement": "大专及以上",
        "skill_requirements": ["熟悉餐饮门店现场管理", "有良好的观察和记录能力", "能出具规范检查报告"],
        "common_issues": ["只发现问题不推动整改", "巡店走过场", "报告不具体"],
        "sort_order": 4,
    },
    {
        "job_code": "store_manager",
        "job_name": "店长",
        "job_level": "store",
        "job_category": "management",
        "report_to_role": "区域经理",
        "manages_roles": "值班经理、前厅经理、厨师长、全体门店员工",
        "job_objective": "对门店整体经营结果负责，包括营收、利润、服务、出品、人员和安全。",
        "responsibilities": [
            "制定并达成门店经营目标",
            "管理和培养门店团队",
            "监督服务标准、出品质量、卫生安全执行",
            "控制食材成本、人力成本、物料消耗",
            "处理客诉和现场突发情况",
            "完成日报、周报、月报等管理报告",
            "执行总部活动和政策落地",
        ],
        "daily_tasks": [
            "主持班前会，布置当日任务",
            "查看昨日营业数据和异常",
            "巡视前厅和后厨",
            "填写门店营业日报",
            "处理客诉和员工问题",
        ],
        "weekly_tasks": [
            "召开门店周例会",
            "检查本周经营数据，对比目标",
            "盘点食材库存",
            "跟进员工培训进度",
        ],
        "monthly_tasks": [
            "完成月度经营复盘报告",
            "做月度人员绩效评估",
            "提交次月经营计划",
        ],
        "kpi_targets": [
            {"name": "营业额达成率", "description": "实际营业额/目标营业额", "unit": "%"},
            {"name": "净利润率", "description": "净利润/营业额", "unit": "%"},
            {"name": "食材成本率", "description": "食材成本/营业额", "unit": "%"},
            {"name": "人工成本率", "description": "人工成本/营业额", "unit": "%"},
            {"name": "客户投诉率", "description": "投诉次数/接待桌数", "unit": "‰"},
            {"name": "员工离职率", "description": "月离职人数/月平均在职人数", "unit": "%"},
            {"name": "日报提交率", "description": "按时提交日报天数/总天数", "unit": "%"},
        ],
        "experience_years_min": 2,
        "education_requirement": "高中及以上",
        "skill_requirements": [
            "有门店管理或主管经验",
            "具备基本财务报表阅读能力",
            "能带团队、会培训下属",
            "有良好的客诉处理能力",
        ],
        "common_issues": [
            "只管现场，不管数据",
            "不会做经营分析",
            "对员工太宽松或太严",
            "不善于向上级汇报问题",
        ],
        "sort_order": 5,
    },
    {
        "job_code": "shift_manager",
        "job_name": "值班经理 / 门店主管",
        "job_level": "store",
        "job_category": "management",
        "report_to_role": "店长",
        "manages_roles": "当班前厅服务员、收银员、传菜员",
        "job_objective": "在当班时段内确保门店服务顺畅、出品及时、客户满意，协助店长管理现场。",
        "responsibilities": [
            "主持当班班前会",
            "监督当班员工服务标准执行",
            "协调前后厅配合，确保出品及时",
            "处理当班客诉和现场突发",
            "记录当班异常情况",
            "完成交接班",
        ],
        "daily_tasks": ["班前准备检查", "当班现场巡视", "交接班记录"],
        "weekly_tasks": ["参加门店周例会", "汇报本周当班问题"],
        "monthly_tasks": ["参与月度绩效评估"],
        "kpi_targets": [
            {"name": "当班客诉次数", "description": "越少越好", "unit": "次"},
            {"name": "上菜及时率", "description": "", "unit": "%"},
            {"name": "当班出勤管理", "description": "", "unit": ""},
        ],
        "experience_years_min": 1,
        "education_requirement": "高中及以上",
        "skill_requirements": ["有一线服务经验", "具备现场协调能力", "责任心强"],
        "common_issues": ["不敢管同事", "遇事推给店长", "记录不规范"],
        "sort_order": 6,
    },
    {
        "job_code": "chef_manager",
        "job_name": "厨师长 / 后厨经理",
        "job_level": "store",
        "job_category": "back_of_house",
        "report_to_role": "店长",
        "manages_roles": "炉台厨师、切配、打荷、凉菜、洗消",
        "job_objective": "负责后厨出品质量、食材成本控制、后厨人员管理和食品安全。",
        "responsibilities": [
            "制定并执行出品标准（口味/摆盘/分量）",
            "控制食材成本，减少浪费和损耗",
            "管理后厨人员排班和培训",
            "监督食品安全和卫生标准",
            "协调食材采购计划",
            "处理后厨突发情况（缺料/设备故障/人员缺席）",
        ],
        "daily_tasks": [
            "检查当日食材库存和新鲜度",
            "主持后厨班前会",
            "监督午/晚高峰出品质量",
            "检查后厨卫生和设备状态",
            "填写食材领料单和损耗记录",
        ],
        "weekly_tasks": ["统计本周食材成本", "检查食材库存，制定补货计划", "后厨员工培训"],
        "monthly_tasks": ["月度食材盘点", "提交成本分析报告", "后厨人员绩效评估"],
        "kpi_targets": [
            {"name": "食材成本率", "description": "食材成本/营业额", "unit": "%"},
            {"name": "食材损耗率", "description": "损耗金额/食材总成本", "unit": "%"},
            {"name": "出品及时率", "description": "在规定时间内上菜率", "unit": "%"},
            {"name": "客诉率（后厨相关）", "description": "因出品问题引起的客诉", "unit": "次/百桌"},
            {"name": "食安检查通过率", "description": "", "unit": "%"},
        ],
        "experience_years_min": 3,
        "education_requirement": "初中及以上",
        "skill_requirements": [
            "具备餐饮烹饪技能",
            "有后厨管理经验",
            "懂食材成本控制",
            "持有健康证",
        ],
        "common_issues": [
            "只管出品不管成本",
            "不会做食材计划导致浪费",
            "对下属太好说话，纪律松散",
            "不记录损耗",
        ],
        "sort_order": 7,
    },
    {
        "job_code": "cashier",
        "job_name": "收银员",
        "job_level": "store",
        "job_category": "front_of_house",
        "report_to_role": "值班经理 / 店长",
        "manages_roles": "",
        "job_objective": "准确、高效处理结账，维护收银安全，提升客户结账体验。",
        "responsibilities": [
            "准确操作POS系统完成收银",
            "核对优惠券/会员折扣/活动规则",
            "开具发票",
            "维护收银台整洁",
            "班次结束核对账目",
            "配合会员营销活动（拉新/储值）",
        ],
        "daily_tasks": ["开机核验POS", "收银操作", "班次结算对账"],
        "weekly_tasks": ["参加门店例会"],
        "monthly_tasks": ["月度账目核对"],
        "kpi_targets": [
            {"name": "收银差错率", "description": "差错次数/总交易次数", "unit": "‰"},
            {"name": "会员新增数", "description": "当月新开会员数", "unit": "个"},
            {"name": "投诉次数", "description": "因收银引起的投诉", "unit": "次"},
        ],
        "experience_years_min": 0,
        "education_requirement": "高中及以上",
        "skill_requirements": ["熟悉POS操作", "数字敏感、细心", "良好的服务意识"],
        "common_issues": ["收银差错", "对优惠规则不熟悉", "结账慢影响体验"],
        "sort_order": 8,
    },
    {
        "job_code": "waiter",
        "job_name": "服务员",
        "job_level": "store",
        "job_category": "front_of_house",
        "report_to_role": "领班 / 值班经理",
        "manages_roles": "",
        "job_objective": "为客人提供热情、专业、标准化的用餐服务，提升客户满意度和复购率。",
        "responsibilities": [
            "迎接引导客人入座",
            "介绍菜品，协助点餐",
            "按标准服务流程提供桌面服务",
            "跟进客人用餐需求",
            "处理简单客诉，升级复杂问题",
            "维护负责区域卫生整洁",
        ],
        "daily_tasks": ["班前仪容仪表检查", "准备服务物品", "按标准服务客人", "维护区域卫生"],
        "weekly_tasks": ["参加周例会和培训"],
        "monthly_tasks": ["参与绩效评估"],
        "kpi_targets": [
            {"name": "顾客满意度", "description": "好评/评价总数", "unit": "%"},
            {"name": "菜品推销成功率", "description": "推销成功次数/推销次数", "unit": "%"},
            {"name": "客诉次数", "description": "因服务引起的投诉", "unit": "次"},
        ],
        "experience_years_min": 0,
        "education_requirement": "初中及以上",
        "skill_requirements": ["良好的服务意识和沟通能力", "熟悉服务礼仪", "体力充沛"],
        "common_issues": ["服务不主动", "菜品知识不足", "处理客诉经验不足"],
        "sort_order": 9,
    },
    {
        "job_code": "cook",
        "job_name": "炉台厨师 / 热菜厨师",
        "job_level": "store",
        "job_category": "back_of_house",
        "report_to_role": "厨师长",
        "manages_roles": "",
        "job_objective": "按出品标准烹饪热菜，保证出品质量和速度。",
        "responsibilities": [
            "按标准食谱和分量烹饪菜品",
            "控制烹饪时间和火候",
            "配合打荷做好备料",
            "维护炉台清洁和设备安全",
            "高峰期保证出菜速度",
        ],
        "daily_tasks": ["开市前备料检查", "按订单标准出菜", "收市清洁炉台"],
        "weekly_tasks": ["参加后厨例会"],
        "monthly_tasks": ["参与技能考核"],
        "kpi_targets": [
            {"name": "出品合格率", "description": "合格出品/总出品", "unit": "%"},
            {"name": "出菜速度", "description": "平均出菜时间", "unit": "分钟"},
            {"name": "浪费率", "description": "废弃原料/使用原料", "unit": "%"},
        ],
        "experience_years_min": 1,
        "education_requirement": "初中及以上",
        "skill_requirements": ["具备基本烹饪技能", "能按标准食谱执行", "持有健康证"],
        "common_issues": ["分量不标准", "出品慢", "不按食谱操作"],
        "sort_order": 10,
    },
    {
        "job_code": "hr_manager",
        "job_name": "人力资源经理 / HRBP",
        "job_level": "hq",
        "job_category": "support_dept",
        "report_to_role": "CEO / HR负责人",
        "manages_roles": "招聘专员、培训专员",
        "job_objective": "建立人才供应链，保障门店人员配置，推动人才成长和文化建设。",
        "responsibilities": [
            "制定人力资源战略和年度计划",
            "主导门店人员招聘和入职",
            "建立培训体系和技能评估",
            "管理绩效考核和薪酬体系",
            "处理劳动关系和离职管理",
            "建立人才梯队和晋升通道",
        ],
        "daily_tasks": ["跟进招聘进度", "处理HR问题"],
        "weekly_tasks": ["汇总人员配置情况", "跟进培训执行"],
        "monthly_tasks": ["月度人员盘点报告", "离职分析", "薪酬核算配合"],
        "kpi_targets": [
            {"name": "招聘到岗率", "description": "按期到岗人数/需求人数", "unit": "%"},
            {"name": "员工离职率", "description": "", "unit": "%"},
            {"name": "培训完成率", "description": "", "unit": "%"},
            {"name": "干部晋升率", "description": "内部晋升占管理岗补充比", "unit": "%"},
        ],
        "experience_years_min": 3,
        "education_requirement": "本科及以上",
        "skill_requirements": ["熟悉劳动法", "有餐饮行业HR经验优先", "具备数据分析能力"],
        "common_issues": ["只做事务性HR", "不懂业务", "招聘质量差"],
        "sort_order": 11,
    },
    {
        "job_code": "trainer",
        "job_name": "培训经理 / 训练专员",
        "job_level": "hq",
        "job_category": "support_dept",
        "report_to_role": "HR经理 / 运营负责人",
        "manages_roles": "",
        "job_objective": "建立标准化培训体系，确保员工能力达到岗位要求，支撑门店可复制扩张。",
        "responsibilities": [
            "开发和维护培训课程（入职/岗位/晋升）",
            "组织新员工培训和技能考核",
            "建立培训档案和学习路径",
            "支持新店筹备培训",
            "评估培训效果，持续优化",
        ],
        "daily_tasks": ["培训执行跟进"],
        "weekly_tasks": ["培训完成度汇报"],
        "monthly_tasks": ["培训效果评估报告", "课程内容更新"],
        "kpi_targets": [
            {"name": "培训覆盖率", "description": "", "unit": "%"},
            {"name": "考核通过率", "description": "", "unit": "%"},
            {"name": "新员工留存率（90天）", "description": "", "unit": "%"},
        ],
        "experience_years_min": 2,
        "education_requirement": "大专及以上",
        "skill_requirements": ["有课程开发经验", "良好的表达和授课能力", "熟悉餐饮业务"],
        "common_issues": ["培训内容脱离实际", "只讲课不考核", "效果难以量化"],
        "sort_order": 12,
    },
    {
        "job_code": "procurement_manager",
        "job_name": "采购经理",
        "job_level": "hq",
        "job_category": "support_dept",
        "report_to_role": "供应链负责人 / COO",
        "manages_roles": "采购专员",
        "job_objective": "在保证食材质量的前提下，以最优成本保障食材及物料的稳定供应。",
        "responsibilities": [
            "建立和管理供应商体系",
            "谈判采购价格和合同",
            "监控食材质量和到货及时率",
            "分析采购成本，推动降本",
            "管理食材规格和标准",
            "处理供应商异常和紧急补货",
        ],
        "daily_tasks": ["处理采购订单", "跟进到货情况"],
        "weekly_tasks": ["供应商沟通", "价格对比分析"],
        "monthly_tasks": ["采购成本分析报告", "供应商评估"],
        "kpi_targets": [
            {"name": "采购成本节约率", "description": "", "unit": "%"},
            {"name": "到货及时率", "description": "", "unit": "%"},
            {"name": "食材质量合格率", "description": "", "unit": "%"},
        ],
        "experience_years_min": 3,
        "education_requirement": "大专及以上",
        "skill_requirements": ["熟悉餐饮食材", "有谈判和合同管理能力", "懂供应链管理"],
        "common_issues": ["只看价格不看质量", "供应商管理混乱", "缺乏数据分析"],
        "sort_order": 13,
    },
    {
        "job_code": "food_safety_manager",
        "job_name": "品控经理 / 食安经理",
        "job_level": "hq",
        "job_category": "support_dept",
        "report_to_role": "COO / 质量负责人",
        "manages_roles": "",
        "job_objective": "建立食品安全管理体系，保障门店食品安全合规，降低食安风险。",
        "responsibilities": [
            "制定食品安全管理制度和SOP",
            "组织食安培训和健康证管理",
            "定期食安巡检和抽检",
            "处理食安投诉和突发事件",
            "对接政府监管部门",
            "管理食材溯源和留样制度",
        ],
        "daily_tasks": ["关注门店食安异常上报"],
        "weekly_tasks": ["食安抽检", "整改跟进"],
        "monthly_tasks": ["食安月报", "培训计划执行检查"],
        "kpi_targets": [
            {"name": "食安事故次数", "description": "越少越好", "unit": "次"},
            {"name": "食安检查通过率", "description": "", "unit": "%"},
            {"name": "健康证覆盖率", "description": "", "unit": "%"},
        ],
        "experience_years_min": 3,
        "education_requirement": "大专及以上（食品相关专业优先）",
        "skill_requirements": ["熟悉食品安全法规", "有食安管理体系建设经验", "良好的沟通和执行推动力"],
        "common_issues": ["制度有但落地差", "检查不到位", "对监管要求不熟悉"],
        "sort_order": 14,
    },
    {
        "job_code": "finance_manager",
        "job_name": "财务经理 / 财务负责人",
        "job_level": "hq",
        "job_category": "support_dept",
        "report_to_role": "CEO / CFO",
        "manages_roles": "成本会计、财务专员",
        "job_objective": "保障公司财务数据准确、税务合规，为经营决策提供财务支持。",
        "responsibilities": [
            "统筹月度/年度财务报表",
            "监控成本、收入、利润核算",
            "管理税务申报和合规",
            "支持经营决策的财务分析",
            "管理资金流和风险",
            "配合审计和对外披露",
        ],
        "daily_tasks": ["资金监控", "异常处理"],
        "weekly_tasks": ["经营数据核对"],
        "monthly_tasks": ["月度财务报告", "税务申报"],
        "kpi_targets": [
            {"name": "账目准确率", "description": "", "unit": "%"},
            {"name": "报表准时率", "description": "", "unit": "%"},
            {"name": "税务合规率", "description": "", "unit": "%"},
        ],
        "experience_years_min": 5,
        "education_requirement": "本科及以上（财务/会计）",
        "skill_requirements": ["持有会计资格证", "熟悉餐饮财务核算", "具备成本分析能力"],
        "common_issues": ["只做账不分析", "成本归集不准确", "与业务脱节"],
        "sort_order": 15,
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# SOP 种子数据（按 job_code 关联）
# ─────────────────────────────────────────────────────────────────────────────

JOB_SOPS = [
    {
        "job_code": "store_manager",
        "sop_type": "pre_shift",
        "sop_name": "开市前检查SOP",
        "steps": [
            {"step_no": 1, "action": "查看昨日营业数据", "standard": "登录系统，查看营业额/客单价/翻台率/成本率", "check_point": "有无异常指标"},
            {"step_no": 2, "action": "检查员工到岗", "standard": "开市前30分钟所有人员到位", "check_point": "出勤率100%"},
            {"step_no": 3, "action": "主持班前会", "standard": "10分钟内，传达目标/关键动作/注意事项", "check_point": "人员精神状态"},
            {"step_no": 4, "action": "巡视前厅", "standard": "检查桌椅/餐具/卫生/设备/陈列", "check_point": "符合标准，无遗漏"},
            {"step_no": 5, "action": "巡视后厨", "standard": "检查食材新鲜度/备料/设备/卫生", "check_point": "食材在保质期内"},
            {"step_no": 6, "action": "确认系统正常", "standard": "POS/点餐系统/收银系统开机正常", "check_point": "无故障"},
        ],
        "duration_minutes": 45,
        "responsible_role": "店长",
    },
    {
        "job_code": "store_manager",
        "sop_type": "post_shift",
        "sop_name": "收市总结SOP",
        "steps": [
            {"step_no": 1, "action": "盘点当日营业数据", "standard": "核对POS营业额与实收金额", "check_point": "差异<50元"},
            {"step_no": 2, "action": "检查后厨收市", "standard": "食材归位/设备关闭/清洁完成", "check_point": "符合食安要求"},
            {"step_no": 3, "action": "检查前厅收市", "standard": "桌椅归位/餐具清洗/地面清洁", "check_point": "符合卫生标准"},
            {"step_no": 4, "action": "填写门店日报", "standard": "在规定时间内提交日报到系统", "check_point": "按时提交"},
            {"step_no": 5, "action": "安全检查", "standard": "水电气关闭/门窗锁好/监控正常", "check_point": "安全无遗漏"},
        ],
        "duration_minutes": 30,
        "responsible_role": "店长",
    },
    {
        "job_code": "chef_manager",
        "sop_type": "pre_shift",
        "sop_name": "后厨开市SOP",
        "steps": [
            {"step_no": 1, "action": "检查冰箱温度和食材新鲜度", "standard": "冷藏<4℃，冷冻<-18℃，食材无异味/变色", "check_point": "不合格品处理"},
            {"step_no": 2, "action": "检查备料完成情况", "standard": "按当日预计销量完成备料，缺口及时补", "check_point": "备料充足率>90%"},
            {"step_no": 3, "action": "检查设备状态", "standard": "炉灶/蒸箱/冰箱/洗碗机正常", "check_point": "设备无故障"},
            {"step_no": 4, "action": "主持后厨班前会", "standard": "传达当日重点菜品/特殊要求/安全提醒", "check_point": "人员到位"},
            {"step_no": 5, "action": "检查后厨卫生", "standard": "台面/地面/设备清洁，无残留食物", "check_point": "符合食安标准"},
        ],
        "duration_minutes": 40,
        "responsible_role": "厨师长",
    },
    {
        "job_code": "chef_manager",
        "sop_type": "emergency",
        "sop_name": "食材短缺应急SOP",
        "steps": [
            {"step_no": 1, "action": "评估缺货影响", "standard": "确认缺少的食材和可能影响的菜品数量", "check_point": "清单明确"},
            {"step_no": 2, "action": "立即通知店长", "standard": "5分钟内报告", "check_point": "及时上报"},
            {"step_no": 3, "action": "启动替代方案", "standard": "同类食材替换或菜品临时下架", "check_point": "客户知情"},
            {"step_no": 4, "action": "联系供应商紧急补货", "standard": "2小时内到货", "check_point": "到货确认"},
            {"step_no": 5, "action": "记录缺货事件", "standard": "填写损耗记录表", "check_point": "记录完整"},
        ],
        "duration_minutes": 15,
        "responsible_role": "厨师长",
    },
    {
        "job_code": "waiter",
        "sop_type": "during_service",
        "sop_name": "标准服务流程SOP",
        "steps": [
            {"step_no": 1, "action": "迎接入座", "standard": "3秒内微笑迎接，引导至合适桌位", "check_point": "热情主动"},
            {"step_no": 2, "action": "递送菜单和点餐", "standard": "介绍特色菜/推荐菜，3分钟内完成点餐", "check_point": "点餐准确"},
            {"step_no": 3, "action": "上菜报菜名", "standard": "每道菜上菜时报菜名，检查摆盘", "check_point": "无错误"},
            {"step_no": 4, "action": "用餐中巡台", "standard": "每5分钟巡视负责区域，主动询问需求", "check_point": "客户满意"},
            {"step_no": 5, "action": "结账送客", "standard": "快速结账，送客到门口，道谢", "check_point": "客户体验"},
        ],
        "duration_minutes": 60,
        "responsible_role": "服务员",
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# 种子写入逻辑
# ─────────────────────────────────────────────────────────────────────────────

async def seed_job_standards(session: AsyncSession) -> dict:
    """写入岗位标准种子数据（幂等：按 job_code 判断是否已存在）"""
    from src.models.job_standard import JobStandard
    from src.models.job_sop import JobSOP

    inserted_standards = 0
    skipped_standards = 0
    inserted_sops = 0
    skipped_sops = 0

    # 先写岗位标准
    for data in JOB_STANDARDS:
        result = await session.execute(
            select(JobStandard).where(JobStandard.job_code == data["job_code"])
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            skipped_standards += 1
            logger.info("跳过已存在岗位标准", job_code=data["job_code"])
            continue

        standard = JobStandard(
            id=uuid.uuid4(),
            **data,
        )
        session.add(standard)
        inserted_standards += 1
        logger.info("写入岗位标准", job_code=data["job_code"], job_name=data["job_name"])

    await session.flush()  # 先刷入，确保 FK 可用

    # 再写 SOP（需要先查到对应的 job_standard_id）
    for sop_data in JOB_SOPS:
        job_code = sop_data["job_code"]
        result = await session.execute(
            select(JobStandard).where(JobStandard.job_code == job_code)
        )
        standard = result.scalar_one_or_none()
        if standard is None:
            logger.warning("找不到对应岗位标准，跳过SOP", job_code=job_code, sop_name=sop_data["sop_name"])
            continue

        # 检查同类型同名 SOP 是否已存在
        result = await session.execute(
            select(JobSOP).where(
                JobSOP.job_standard_id == standard.id,
                JobSOP.sop_type == sop_data["sop_type"],
                JobSOP.sop_name == sop_data["sop_name"],
            )
        )
        existing_sop = result.scalar_one_or_none()
        if existing_sop is not None:
            skipped_sops += 1
            logger.info("跳过已存在SOP", job_code=job_code, sop_name=sop_data["sop_name"])
            continue

        sop = JobSOP(
            id=uuid.uuid4(),
            job_standard_id=standard.id,
            sop_type=sop_data["sop_type"],
            sop_name=sop_data["sop_name"],
            steps=sop_data["steps"],
            duration_minutes=sop_data.get("duration_minutes"),
            responsible_role=sop_data.get("responsible_role"),
        )
        session.add(sop)
        inserted_sops += 1
        logger.info("写入SOP", job_code=job_code, sop_name=sop_data["sop_name"])

    await session.commit()

    return {
        "inserted_standards": inserted_standards,
        "skipped_standards": skipped_standards,
        "inserted_sops": inserted_sops,
        "skipped_sops": skipped_sops,
    }


async def main():
    """独立运行入口"""
    import os
    from dotenv import load_dotenv

    load_dotenv()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL 环境变量未设置")

    # 转换为 asyncpg URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgresql+psycopg2://"):
        database_url = database_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(database_url, echo=False)
    AsyncSession_ = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSession_() as session:
        result = await seed_job_standards(session)

    await engine.dispose()

    print(f"\n岗位标准种子数据写入完成:")
    print(f"  岗位标准 — 新增: {result['inserted_standards']}, 跳过: {result['skipped_standards']}")
    print(f"  SOP      — 新增: {result['inserted_sops']}, 跳过: {result['skipped_sops']}")


if __name__ == "__main__":
    asyncio.run(main())
