"""
屯象OS API Gateway
主应用入口 — 餐饮人的好伙伴
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
import structlog
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    GCCollector,
    Gauge,
    Histogram,
    PlatformCollector,
    ProcessCollector,
    Counter,
    CollectorRegistry,
    generate_latest,
)
import time

from src.core.config import settings
# 核心模块
from src.api import health, agents, auth, notifications, stores, mobile, integrations, monitoring, llm, enterprise, voice, neural, adapters, tasks, reconciliation, approval, embedding, raas, model_marketplace, human_in_the_loop, hardware_integration, pos, dishes, benchmark, dish_master, alerts_webhook
from src.api import pos_sync
from src.api import roles as roles_api
from src.api import merchants
from src.api import prep_suggestion, soldout, agent_configs
from src.api.phase5_apis import platform_router, industry_router, supply_chain_router, i18n_router
# 逐步启用的模块
from src.api import dashboard, analytics, audit, multi_store, finance, customer360, wechat_triggers, queue, meituan_queue, meituan_reservation
# 需要外部适配器的模块 (会在适配器不可用时返回错误)
from src.api import members, blindbox
from src.api import edge_node, decision_validator, recommendations, agent_collaboration
# Phase 1: CRUD API
from src.api import employees, inventory, schedules, reservations, kpis, orders
# Phase 1 本体层 — BOM 版本化配方管理
from src.api import bom
# Phase 2 本体层 API — 推理层 / 企微 Action FSM / 自然语言查询
from src.api import ontology, wechat_actions
# Phase 3 — 数据主权 / 连锁扩展 / 推理规则库 / 损耗事件
from src.api import data_security, chain_expansion, knowledge_rules, waste_events
# Phase 4 — L2 融合层（多源食材ID规范化）
from src.api import fusion
# Phase 5 — L3 跨店知识聚合（同伴组 + 物化指标 + 图同步）
from src.api import l3_knowledge
# Phase 6 — L4 推理层（全维度规则推理 + 因果图谱 + 健康诊断）
from src.api import l4_reasoning
# Phase 7 — L5 行动层（行动派发 + WeChat FSM + 任务创建 + 反馈闭环）
from src.api import l5_action
# Phase 8 — 多阶段工作流引擎（Day N 晚上 17:00-22:00 规划 Day N+1）
from src.api import workflow
from src.api import ai_evolution_dashboard
from src.api import compliance
from src.api import quality
from src.api import scheduler
from src.api import agent_memory
from src.api import event_sourcing
from src.api import voice_ws
from src.api import vector_index
from src.api import forecast
from src.api import cross_store_insights
from src.api import report_templates
from src.api import competitive_analysis
from src.api import federated
from src.api import export_jobs
from src.api import backups
from src.api import private_domain
from src.api import ops
from src.api import daily_hub
from src.api import banquet
from src.api import banquet_lifecycle
from src.api import banquet_agent
from src.api import external_factors
from src.api import pos_webhook
from src.api import bulk_import
from src.api import hq_dashboard
from src.api import dish_rd_agent
from src.api import supplier_agent
from src.api import daily_ops
from src.api import job_standard
from src.api import org_hierarchy
from src.api import ai_pillars
from src.api import ai_accuracy
from src.api import dashboard_preferences
from src.api import governance
from src.api import workforce
# ARCH-004 可信执行层 / FEAT-004 动态菜单 / ARCH-003 门店记忆层 / 本体论 L2 API / FCT 公开接口
from src.api import execution, menu, store_memory, ontology_api, fct_public
# Phase 1 — 运营智能层：渠道毛利 API
from src.api import channel_profit
from src.api import performance_compute
# Phase P1 — 预订Agent: 渠道中台 + 客户风控
from src.api import channel_analytics, customer_risk
# Phase P2 — 预订Agent: 宴会销控引擎
from src.api import banquet_sales_api
# Phase P3 — 预订Agent: EO执行引擎（宴小猪能力）
from src.api import event_orders
# Phase P4 — 预订Agent: AI智能整合（屯象独有）
from src.api import reservation_ai
# Onboarding Engine — 企业诊断与数据入库
from src.api import onboarding
# Month 1 (P0) — 外部集成：电子发票 / 饿了么 / 支付对账
from src.api import e_invoice
from src.api import eleme
from src.api import payment_reconciliation
# Month 2 (P0+P1) — 抖音 / 食品安全 / 健康证
from src.api import douyin
from src.api import food_safety
from src.api import health_certificates
# Month 3 (P1+P2) — 供应商B2B / 大众点评 / 银行对账
from src.api import supplier_b2b
from src.api import dianping
from src.api import bank_reconciliation
# Batch 1 — 数据融合层：集成中心 / 全渠道营收 / 三角对账
from src.api import integration_hub
from src.api import omni_channel
from src.api import tri_reconciliation
# Batch 2 — 智能决策层：供应商智能 / 评论行动 / 合规引擎
from src.api import supplier_intelligence
from src.api import review_action
from src.api import compliance_engine
# Batch 3 — 自动化闭环层：智能采购 / 日清日结 / 指挥中心
from src.api import auto_procurement
from src.api import financial_closing
from src.api import command_center
from src.middleware.monitoring import MonitoringMiddleware
from src.middleware.rate_limit import RateLimitMiddleware
from src.middleware.audit_log import AuditLogMiddleware
from src.middleware.security_headers import SecurityHeadersMiddleware
from src.middleware.store_access import StoreAccessMiddleware
from src.middleware.hr_operation_audit import HROperationAuditMiddleware

# 配置结构化日志
logger = structlog.get_logger()

# API文档描述
API_DESCRIPTION = """
## 屯象OS (TUN XIANG Operating System)

> 餐饮人的好伙伴 — AI驱动的经营决策系统

### 产品定位: AI数字总经理 (RaaS - Result as a Service)

**不卖软件，卖结果** — 年薪只要几万块的数字总经理

屯象OS是一个AI Native的餐饮RaaS系统，定位为"AI数字总经理"，
拥有行业Top10%管理经验，24小时不休息，永不离职，持续学习进化。

### 核心价值主张

* **帮你省钱**: 每月砍掉一个人工成本，省下1000块钱的烂菜叶
* **帮你赚钱**: 提升客流量、客单价、复购率，增加营收15-25%
* **一周见效**: 不是三年后的愿景，是一周内看到的效果
* **按效果付费**: 省下成本的20%，增加营收的15%作为服务费

### 屯象智脑 Agent 系统

7个专业Agent实现从排班、订单、库存到决策的全流程智能化管理

* **ScheduleAgent**: 智能排班 · 基于AI的客流预测和自动排班
* **OrderAgent**: 订单协同 · 预定管理、排队系统、智能点单推荐
* **InventoryAgent**: 库存预警 · 实时监控、消耗预测、自动补货提醒
* **ServiceAgent**: 服务质量 · 客户反馈收集、服务质量监控
* **TrainingAgent**: 培训辅导 · 培训需求评估、计划生成、进度追踪
* **DecisionAgent**: 决策支持 · KPI分析、业务洞察、改进建议
* **ReservationAgent**: 预定宴会 · 预定管理、座位分配、宴会管理

### 认证说明

大部分API端点需要认证：

1. 调用 `/api/v1/auth/login` 获取访问令牌
2. 在后续请求的 `Authorization` 头中包含令牌: `Bearer <access_token>`
3. 访问令牌有效期30分钟，过期后使用刷新令牌获取新的访问令牌

### 技术栈

* **后端框架**: FastAPI (Python 3.9+)
* **数据库**: PostgreSQL with SQLAlchemy ORM
* **认证**: JWT (JSON Web Tokens)
* **AI能力**: 联邦学习、神经符号双规、多模态交互
"""

# 创建FastAPI应用
app = FastAPI(
    title="屯象OS API Gateway",
    description=API_DESCRIPTION,
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "屯象OS团队",
        "email": "support@tunxiang-os.com",
    },
    license_info={
        "name": "MIT License",
    },
    openapi_tags=[
        {
            "name": "health",
            "description": "系统健康检查和状态监控",
        },
        {
            "name": "auth",
            "description": "用户认证和授权 - 登录、注册、令牌管理、用户信息",
        },
        {
            "name": "agents",
            "description": "智能Agent系统 - 7个专业Agent的操作接口",
        },
        {
            "name": "approval",
            "description": "审批流管理 - Human-in-the-loop决策审批、信任度评分、决策统计",
        },
        {
            "name": "notifications",
            "description": "通知管理 - 系统通知、消息推送",
        },
        {
            "name": "stores",
            "description": "门店管理 - 门店信息、配置管理",
        },
        {
            "name": "mobile",
            "description": "移动端API - 移动应用专用接口",
        },
        {
            "name": "integrations",
            "description": "外部系统集成 - 第三方系统对接接口",
        },
        {
            "name": "monitoring",
            "description": "系统监控 - 错误追踪、性能监控、日志查询",
        },
        {
            "name": "llm",
            "description": "LLM配置 - 大语言模型配置和测试",
        },
        {
            "name": "enterprise",
            "description": "企业集成 - 企业微信、飞书消息推送和用户管理",
        },
        {
            "name": "voice",
            "description": "语音交互 - Shokz骨传导耳机集成、语音命令、语音通知",
        },
        {
            "name": "neural",
            "description": "神经系统 - 事件处理、语义搜索、联邦学习、系统状态",
        },
        {
            "name": "adapters",
            "description": "API适配器 - 第三方系统集成（天财商龙、美团SAAS、奥琦韦、品智）",
        },
        {
            "name": "tasks",
            "description": "任务管理 - 任务创建、指派、完成、查询",
        },
        {
            "name": "reconciliation",
            "description": "对账管理 - POS对账、差异预警、对账确认",
        },
        {
            "name": "pos",
            "description": "POS系统 - 品智收银系统集成接口",
        },
        {
            "name": "members",
            "description": "会员系统 - 奥琦韦会员管理接口",
        },
        {
            "name": "dashboard",
            "description": "数据可视化 - 大屏数据接口",
        },
        {
            "name": "multi_store",
            "description": "多门店管理 - 门店对比、区域汇总、绩效排名",
        },
        {
            "name": "finance",
            "description": "财务管理 - 财务报表、预算管理、成本核算",
        },
        {
            "name": "analytics",
            "description": "高级分析 - 预测分析、异常检测、关联分析",
        },
        {
            "name": "audit",
            "description": "审计日志 - 操作日志、用户活动、系统统计",
        },
        {
            "name": "edge_node",
            "description": "边缘节点 - 边缘计算、离线模式、网络状态管理",
        },
        {
            "name": "decision_validator",
            "description": "决策验证 - AI决策双重验证、规则引擎、异常检测",
        },
        {
            "name": "federated_learning",
            "description": "联邦学习 - 多门店模型训练、隐私保护、模型聚合",
        },
        {
            "name": "recommendations",
            "description": "智能推荐 - 个性化菜品推荐、动态定价、精准营销",
        },
        {
            "name": "agent_collaboration",
            "description": "Agent协同 - 跨Agent决策协调、冲突解决、全局优化",
        },
        {
            "name": "open_platform",
            "description": "开放平台 - 第三方开发者接入、插件市场、收入分成",
        },
        {
            "name": "industry_solutions",
            "description": "行业解决方案 - 火锅/烧烤/快餐等行业模板、最佳实践",
        },
        {
            "name": "supply_chain",
            "description": "供应链整合 - 供应商直连、自动询价比价、供应链金融",
        },
        {
            "name": "internationalization",
            "description": "国际化 - 多语言支持、多币种支持、本地化运营",
        },
        {
            "name": "embedding",
            "description": "嵌入模型 - 语义理解、相似度计算、智能推荐",
        },
        {
            "name": "raas",
            "description": "RaaS定价 - 按效果付费、基线指标、效果指标、月度账单",
        },
        {
            "name": "model_marketplace",
            "description": "模型交易市场 - 行业模型购买、数据贡献分成、网络效应",
        },
        {
            "name": "human_in_the_loop",
            "description": "人机协同审批 - 风险分级、信任阶段、审批流程、决策统计",
        },
        {
            "name": "hardware_integration",
            "description": "硬件集成 - 树莓派5边缘节点、Shokz设备、语音交互、离线模式",
        },
    ],
)

# 安全响应头（最外层，确保所有响应都带安全头）
app.add_middleware(SecurityHeadersMiddleware)

# GZip 压缩（响应体 > 1KB 自动压缩）
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# 添加速率限制中间件
app.add_middleware(RateLimitMiddleware)

# 添加审计日志中间件
app.add_middleware(AuditLogMiddleware)

# HR操作审计中间件（记录所有HR写操作）
app.add_middleware(HROperationAuditMiddleware)

# 门店/品牌访问隔离中间件（支持 X-Tenant-ID Header）
app.add_middleware(StoreAccessMiddleware)

# 添加监控中间件
app.add_middleware(MonitoringMiddleware)

# ==================== Prometheus指标 ====================
# 使用独立Registry，避免测试进程中重复导入导致默认Registry重复注册
METRICS_REGISTRY = CollectorRegistry()
ProcessCollector(registry=METRICS_REGISTRY)
PlatformCollector(registry=METRICS_REGISTRY)
GCCollector(registry=METRICS_REGISTRY)

# 创建Prometheus指标
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status'],
    registry=METRICS_REGISTRY,
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint'],
    registry=METRICS_REGISTRY,
)

ACTIVE_REQUESTS = Gauge(
    'http_requests_active',
    'Number of active HTTP requests',
    registry=METRICS_REGISTRY,
)

# Prometheus metrics端点
@app.get("/metrics", include_in_schema=False)
async def metrics():
    """
    Prometheus metrics endpoint

    Exposes application metrics in Prometheus format for scraping.
    """
    return Response(
        content=generate_latest(METRICS_REGISTRY),
        media_type=CONTENT_TYPE_LATEST
    )

# Prometheus中间件
@app.middleware("http")
async def prometheus_middleware(request, call_next):
    """
    Prometheus metrics middleware

    Records HTTP request metrics for Prometheus monitoring.
    """
    # 跳过metrics端点本身
    if request.url.path == "/metrics":
        return await call_next(request)

    # 增加活跃请求计数
    ACTIVE_REQUESTS.inc()

    # 记录请求开始时间
    start_time = time.time()

    try:
        # 处理请求
        response = await call_next(request)

        # 记录请求指标
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status=response.status_code
        ).inc()

        # 记录请求时长
        duration = time.time() - start_time
        REQUEST_DURATION.labels(
            method=request.method,
            endpoint=request.url.path
        ).observe(duration)

        return response

    finally:
        # 减少活跃请求计数
        ACTIVE_REQUESTS.dec()

# 注册路由 - 核心模块
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(roles_api.router, prefix="/api/v1", tags=["roles"])
app.include_router(merchants.router, prefix="/api/v1", tags=["merchants"])
app.include_router(agent_configs.router, prefix="/api/v1", tags=["agent-configs"])
app.include_router(prep_suggestion.router, tags=["prep-suggestion"])
app.include_router(soldout.router, tags=["soldout"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
app.include_router(approval.router, prefix="/api/v1", tags=["approval"])
app.include_router(notifications.router, prefix="/api/v1", tags=["notifications"])
# store_health 须在 stores 之前注册，避免 /stores/{store_id} 把 "health" 当成 store_id 拦截
from src.api import store_health
app.include_router(store_health.router, prefix="/api/v1", tags=["store_health"])
app.include_router(stores.router, prefix="/api/v1", tags=["stores"])
app.include_router(mobile.router, prefix="/api/v1", tags=["mobile"])
app.include_router(integrations.router, prefix="/api/v1", tags=["integrations"])
app.include_router(monitoring.router, prefix="/api/v1", tags=["monitoring"])
app.include_router(alerts_webhook.router, tags=["alerts"])
app.include_router(llm.router, prefix="/api/v1", tags=["llm"])
app.include_router(enterprise.router, prefix="/api/v1/enterprise", tags=["enterprise"])
app.include_router(voice.router, prefix="/api/v1/voice", tags=["voice"])
app.include_router(neural.router, prefix="/api/v1/neural", tags=["neural"])
app.include_router(adapters.router, tags=["adapters"])
app.include_router(pos_sync.router, tags=["pos-sync"])
app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])
app.include_router(reconciliation.router, prefix="/api/v1", tags=["reconciliation"])
app.include_router(dishes.router, prefix="/api/v1", tags=["dishes"])
app.include_router(dish_master.router, tags=["dish-master"])
app.include_router(benchmark.router, prefix="/api/v1", tags=["benchmark"])

# 逐步启用的模块
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])
app.include_router(analytics.router, tags=["analytics"])
app.include_router(audit.router, prefix="/api/v1/audit", tags=["audit"])
app.include_router(multi_store.router, prefix="/api/v1/multi-store", tags=["multi_store"])
app.include_router(finance.router, prefix="/api/v1/finance", tags=["finance"])
app.include_router(members.router, prefix="/api/v1/members", tags=["members"])
app.include_router(blindbox.router, prefix="/api/v1", tags=["blindbox"])
app.include_router(customer360.router, tags=["customer360"])
app.include_router(wechat_triggers.router, tags=["wechat_triggers"])
app.include_router(queue.router, tags=["queue"])
app.include_router(meituan_queue.router, tags=["meituan_queue"])
app.include_router(meituan_reservation.router, tags=["meituan_reservation"])

# Phase 3: 稳定性加固期 (Stability Reinforcement Period)
app.include_router(edge_node.router, tags=["edge_node"])
app.include_router(decision_validator.router, tags=["decision_validator"])

# Phase 4: 智能优化期 (Intelligence Optimization Period)
app.include_router(federated.router)
app.include_router(recommendations.router, tags=["recommendations"])
app.include_router(agent_collaboration.router, tags=["agent_collaboration"])

# Phase 5: 生态扩展期 (Ecosystem Expansion Period)
app.include_router(platform_router, tags=["open_platform"])
app.include_router(industry_router, tags=["industry_solutions"])
app.include_router(supply_chain_router, tags=["supply_chain"])
app.include_router(i18n_router, tags=["internationalization"])
# app.include_router(i18n_router, tags=["internationalization"])

# Embedding Model (嵌入模型)
app.include_router(embedding.router, tags=["embedding"])

# RaaS (Result-as-a-Service)
app.include_router(raas.router, tags=["raas"])

# Model Marketplace (模型交易市场)
app.include_router(model_marketplace.router, tags=["model_marketplace"])

# Human-in-the-Loop (人机协同审批)
app.include_router(human_in_the_loop.router, tags=["human_in_the_loop"])

# Hardware Integration (硬件集成 - 树莓派5 + Shokz)
app.include_router(hardware_integration.router, tags=["hardware_integration"])

# AI三支柱 — Skill Registry + Effect Loop + BusinessContext
app.include_router(ai_pillars.router, tags=["ai-pillars"])

# POS模块
app.include_router(pos.router, prefix="/api/v1/pos", tags=["pos"])
# Phase 1: CRUD API
app.include_router(employees.router, prefix="/api/v1", tags=["employees"])
app.include_router(inventory.router, prefix="/api/v1", tags=["inventory"])
app.include_router(schedules.router, prefix="/api/v1", tags=["schedules"])
app.include_router(reservations.router, prefix="/api/v1", tags=["reservations"])
app.include_router(kpis.router, prefix="/api/v1", tags=["kpis"])
app.include_router(orders.router, prefix="/api/v1", tags=["orders"])
# Phase 1 本体层 — BOM 版本化配方管理
app.include_router(bom.router, tags=["bom"])
# Phase 2 本体层 — 推理层 / 企微 Action FSM / 自然语言查询
app.include_router(ontology.router, tags=["ontology"])
app.include_router(wechat_actions.router, tags=["wechat_actions"])
# Phase 3 — 数据主权 / 连锁扩展 / 推理规则库
app.include_router(data_security.router, tags=["data_security"])
app.include_router(chain_expansion.router, tags=["chain_expansion"])
app.include_router(knowledge_rules.router)
# Phase 3 — 损耗事件 CRUD（PostgreSQL + Neo4j 双写）
app.include_router(waste_events.router, tags=["waste_events"])
# Phase 4 — L2 融合层（多源食材 ID 规范化 + 置信度加权）
app.include_router(fusion.router, tags=["fusion"])
# Phase 5 — L3 跨店知识聚合（同伴组 + 物化指标 + 图同步）
app.include_router(l3_knowledge.router, tags=["l3_knowledge"])
# Phase 6 — L4 推理层（全维度规则推理 + 因果图谱 + 健康诊断）
app.include_router(l4_reasoning.router, tags=["l4_reasoning"])
# Phase 7 — L5 行动层（行动派发 + WeChat FSM + 任务创建 + 反馈闭环）
app.include_router(l5_action.router, tags=["l5_action"])
# Phase 8 — 多阶段工作流引擎（6 阶段规划 + 快速初版 + 版本链 + deadline 管理）
app.include_router(workflow.router, tags=["workflow"])
app.include_router(ai_evolution_dashboard.router, tags=["ai_evolution"])
app.include_router(compliance.router)
app.include_router(quality.router)
app.include_router(scheduler.router, tags=["scheduler"])
app.include_router(agent_memory.router, tags=["agent_memory"])
app.include_router(event_sourcing.router, tags=["event_sourcing"])
app.include_router(voice_ws.router, tags=["voice_ws"])
app.include_router(vector_index.router, tags=["vector_index"])
app.include_router(forecast.router, tags=["forecast"])
app.include_router(cross_store_insights.router, tags=["cross_store_insights"])
app.include_router(report_templates.router, prefix="/api/v1", tags=["report_templates"])
app.include_router(competitive_analysis.router)
app.include_router(export_jobs.router)
app.include_router(backups.router)
app.include_router(private_domain.router, tags=["private_domain"])
from src.api import signal_bus_api
app.include_router(signal_bus_api.router, tags=["signal_bus"])
from src.api import briefing_api
app.include_router(briefing_api.router, tags=["briefing"])
from src.api import hq_briefing_api
app.include_router(hq_briefing_api.router, tags=["hq_briefing"])
app.include_router(ops.router, prefix="/api/v1/ops", tags=["ops"])
app.include_router(daily_hub.router, tags=["daily_hub"])
app.include_router(workforce.router, tags=["workforce"])
# Phase 9 — 宴会熔断引擎（吉日感知 + BEO 单 + 采购/排班加成 + 资源冲突检测）
app.include_router(banquet.router, tags=["banquet"])
# Banquet Lifecycle — 7 阶段销售漏斗 + 锁台冲突 + 销控日历
app.include_router(banquet_lifecycle.router, tags=["banquet_lifecycle"])
# Banquet Agent Phase 9 — CRM+线索+订单+5个Agent（跟进/报价/排期/执行/复盘）
app.include_router(banquet_agent.router, tags=["banquet-agent"])
# External Factors — 统一外部因子查询（天气/节假日/吉日/商圈事件）
app.include_router(external_factors.router, tags=["external_factors"])
app.include_router(pos_webhook.router, tags=["pos_webhook"])
app.include_router(bulk_import.router, tags=["bulk_import"])
app.include_router(hq_dashboard.router, prefix="/api/v1", tags=["hq_dashboard"])
app.include_router(dish_rd_agent.router, tags=["dish-rd"])
app.include_router(supplier_agent.router, tags=["supplier-agent"])
# Phase 12 — 经营智能体（营收异常 / KPI健康度 / 订单预测 / Top3决策 / 场景识别）
from src.api import business_intel
app.include_router(business_intel.router, tags=["business-intel"])
# Phase 12B — 人员智能体（排班优化 / 绩效评分 / 人力成本 / 考勤预警 / 人员配置）
from src.api import people_agent
app.include_router(people_agent.router, tags=["people-agent"])

from src.api import ops_flow_agent
app.include_router(ops_flow_agent.router, tags=["ops-flow-agent"])

from src.api import agent_okr
app.include_router(agent_okr.router, tags=["agent-okr"])

from src.api import agent_collab
app.include_router(agent_collab.router, tags=["agent-collab"])

from src.api import fct_advanced
app.include_router(fct_advanced.router, tags=["fct-advanced"])
app.include_router(ai_accuracy.router, prefix="/api/v1", tags=["ai_accuracy"])
app.include_router(governance.router, prefix="/api/v1", tags=["governance"])
app.include_router(dashboard_preferences.router, prefix="/api/v1", tags=["dashboard_preferences"])

# 营销 Agent — 顾客画像 / 发券策略 / 活动管理
from src.api import marketing_agent
app.include_router(marketing_agent.router, tags=["marketing_agent"])

# aPaaS 开放平台 — ISV 开发者自助注册 + 能力目录
from src.api import open_platform
app.include_router(open_platform.router, tags=["open_platform"])

# aPaaS 开发者文档 + 沙箱 — Phase 2 Month 2
from src.api.docs_api import docs_router, sandbox_router
app.include_router(docs_router, tags=["developer_docs"])
app.include_router(sandbox_router, tags=["developer_docs"])

# aPaaS ISV 生命周期管理 — Phase 2 Month 3
from src.api import isv_management
app.include_router(isv_management.router, tags=["isv_management"])

# aPaaS 插件市场 — Phase 3 Month 4
from src.api import plugin_marketplace
app.include_router(plugin_marketplace.router, tags=["plugin_marketplace"])

# aPaaS 收入分成 — Phase 3 Month 5
from src.api import revenue_sharing
app.include_router(revenue_sharing.router, tags=["revenue_sharing"])

# aPaaS 平台分析 + 评分 — Phase 3 Month 6
from src.api import platform_analytics
app.include_router(platform_analytics.router, tags=["platform_analytics"])

# aPaaS Webhook 事件订阅 — Phase 4 Month 10
from src.api import webhooks
app.include_router(webhooks.router, tags=["webhooks"])

# aPaaS API 计量计费 — Phase 4 Month 11
from src.api import api_billing
app.include_router(api_billing.router, tags=["api_billing"])

# aPaaS ISV 开发者控制台 — Phase 4 Month 12
from src.api import developer_console
app.include_router(developer_console.router, tags=["developer_console"])

# 业财税资金 Agent — Phase 5 Month 1: 经营事件中心 + 利润归因基础
from src.api import business_events
app.include_router(business_events.router, tags=["business_events"])

# 业财税资金 Agent — Phase 5 Month 2: 税务智能引擎 + 现金流预测
from src.api import tax_cashflow
app.include_router(tax_cashflow.router, tags=["finance_agent"])

# 业财税资金 Agent — Phase 5 Month 3: 结算风控引擎 + 角色驾驶舱
from src.api import settlement_risk, role_dashboards
app.include_router(settlement_risk.router, tags=["settlement_risk"])
app.include_router(role_dashboards.router, tags=["role_dashboards"])

# 业财税资金 Agent — Phase 5 Month 4: 预算管理 + 财务预警体系
from src.api.budget_alerts import budget_router, alerts_router
app.include_router(budget_router)
app.include_router(alerts_router)

# 业财税资金 Agent — Phase 5 Month 5: 财务健康评分系统
from src.api import finance_health
app.include_router(finance_health.router)

# 业财税资金 Agent — Phase 5 Month 6: CFO工作台·多店财务综合驾驶舱
from src.api import cfo_dashboard
app.include_router(cfo_dashboard.router)

# 业财税资金 Agent — Phase 5 Month 7: 智能财务预测引擎
from src.api import financial_forecast
app.include_router(financial_forecast.router)

# 业财税资金 Agent — Phase 5 Month 8: 财务异常检测引擎
from src.api import financial_anomaly
app.include_router(financial_anomaly.router)

# 业财税资金 Agent — Phase 5 Month 9: 多店财务对标排名引擎
from src.api import performance_ranking
app.include_router(performance_ranking.router)

# 业财税资金 Agent — Phase 5 Month 10: 财务智能建议引擎
from src.api import financial_recommendation
app.include_router(financial_recommendation.router)

# Phase 6 Month 1: 菜品盈利能力分析引擎
from src.api import dish_profitability
app.include_router(dish_profitability.router)

# Phase 6 Month 2: 菜单优化建议引擎
from src.api import menu_optimization
app.include_router(menu_optimization.router)

# Phase 6 Month 3: 菜品成本预警引擎
from src.api import dish_cost_alert
app.include_router(dish_cost_alert.router)

# Phase 6 Month 4: 跨店菜品对标引擎
from src.api import dish_benchmark
app.include_router(dish_benchmark.router)

# Phase 6 Month 5: 菜品智能定价引擎
from src.api import dish_pricing
app.include_router(dish_pricing.router)

# Phase 6 Month 6: 菜品生命周期管理引擎
from src.api import dish_lifecycle
app.include_router(dish_lifecycle.router)

# Phase 6 Month 7: 菜品销售预测引擎
from src.api import dish_forecast
app.include_router(dish_forecast.router)

# Phase 6 Month 8: 菜品综合健康评分引擎
from src.api import dish_health
app.include_router(dish_health.router)

# Phase 6 Month 9: 菜品营收归因引擎
from src.api import dish_attribution
app.include_router(dish_attribution.router)

# Phase 6 Month 10: 菜品组合矩阵分析引擎
from src.api import menu_matrix
app.include_router(menu_matrix.router)

# Phase 6 Month 11: 菜品成本压缩机会引擎
from src.api import cost_compression
app.include_router(cost_compression.router)

# Phase 6 Month 12: 菜品经营综合月报引擎
from src.api import dish_monthly_summary
app.include_router(dish_monthly_summary.router)

# ARCH-004 可信执行层（折扣申请 / 审批 / 审计日志 / 回滚）
app.include_router(execution.router)
# FEAT-004 动态菜单权重引擎（Top-N 推荐 + 5因子评分）
app.include_router(menu.router)
# ARCH-003 门店记忆层（记忆快照 + 手动刷新）
app.include_router(store_memory.router)
# Palantir 本体论 L2 API
app.include_router(ontology_api.router)
# FCT 公开接口（独立部署形态，API Key 认证）
app.include_router(fct_public.router, prefix="/api/v1/fct-public", tags=["fct_public"])
# Phase 1 — 运营智能层：渠道毛利看板
app.include_router(channel_profit.router)
# Phase 2 — 绩效计算引擎
app.include_router(performance_compute.router)
app.include_router(onboarding.router)
# Phase P1 — 预订Agent: 渠道中台 + 客户风控
app.include_router(channel_analytics.router, prefix="/api/v1", tags=["channel-analytics"])
app.include_router(customer_risk.router, prefix="/api/v1", tags=["customer-risk"])
# Phase P2 — 宴会销控引擎
app.include_router(banquet_sales_api.router, prefix="/api/v1", tags=["banquet-sales"])
# Phase P3 — EO执行引擎
app.include_router(event_orders.router, prefix="/api/v1", tags=["event-orders"])
# Phase P4 — 预订AI助手
app.include_router(reservation_ai.router, prefix="/api/v1", tags=["reservation-ai"])

# 替换易订 — R1 客户自助预订H5 / R3 桌台平面图 / R4 AI邀请函
from src.api import public_reservation, floor_plan, invitation
# 预订数据分析引擎 — 8维度深度分析
from src.api import reservation_analytics
app.include_router(public_reservation.router, tags=["public_reservation"])
app.include_router(floor_plan.router, tags=["floor_plan"])
app.include_router(invitation.router, tags=["invitation"])
app.include_router(reservation_analytics.router, tags=["reservation_analytics"])

# 全链路用餐旅程（预订→到店→用餐→离店→售后）
from src.api import dining_journey
app.include_router(dining_journey.router, tags=["dining_journey"])

# P0 补齐 — 餐段配置 + 预排菜（替代易订PRO缺口）
from src.api import meal_period_config, pre_order
app.include_router(meal_period_config.router, tags=["meal_period_config"])
app.include_router(pre_order.router, tags=["pre_order"])

# P1 补齐 — 预订单/锁位单 + 销售业绩 + 营销触达 + RFM配置
from src.api import reservation_receipt, sales_performance, marketing_touchpoint, rfm_config
app.include_router(reservation_receipt.router, tags=["reservation_receipt"])
app.include_router(sales_performance.router, tags=["sales_performance"])
app.include_router(marketing_touchpoint.router, tags=["marketing_touchpoint"])
app.include_router(rfm_config.router, tags=["rfm_config"])

# P2 补齐 — 客户资源分配 + 来电记录/路线发送
from src.api import customer_allocation, call_record
app.include_router(customer_allocation.router, tags=["customer_allocation"])
app.include_router(call_record.router, tags=["call_record"])

# 全链路闭环桥接
from src.api import lifecycle
app.include_router(lifecycle.router, tags=["lifecycle"])

# Sprint 1 — CDP 统一消费者身份
from src.api import cdp
app.include_router(cdp.router, tags=["cdp"])
# Sprint 3 — MemberAgent + BossAgent
from src.api import member_agent
app.include_router(member_agent.router, tags=["cdp-agent"])
# Sprint 4 — 裂变引擎 + FloorAgent + MenuAgent + 增收月报
from src.api import growth_agent
app.include_router(growth_agent.router, tags=["cdp-growth"])
# Sprint 5 — CostAgent + KitchenAgent + StoreAgent
from src.api import ops_intelligence
app.include_router(ops_intelligence.router, tags=["cdp-ops"])
# Sprint 6 — PeopleAgent + OntologyAgent + TenantReplicator
from src.api import platform_agent
app.include_router(platform_agent.router, tags=["cdp-platform"])
# CDP 监控仪表盘
from src.api import cdp_monitor
app.include_router(cdp_monitor.router, tags=["cdp-monitor"])

# P0 — 食材成本真相引擎
from src.api import cost_truth
app.include_router(cost_truth.router, tags=["cost_truth"])
# P1 — Unified Brain 每日1决策
from src.api import unified_brain
app.include_router(unified_brain.router, tags=["unified_brain"])
# P2 — 跨客户食材价格基准网络
from src.api import price_benchmark
app.include_router(price_benchmark.router, tags=["price_benchmark"])

# BFF 聚合路由（角色驱动前端，4种角色各一个聚合端点）
from src.api import bff
app.include_router(bff.router, tags=["bff"])

# v2.0 MVP — 决策中枢（Top3 + 手动推送 + 场景识别）
from src.api import decision_hub, monthly_report
app.include_router(decision_hub.router, tags=["decision_hub"])
app.include_router(monthly_report.router, tags=["monthly_report"])

# Phase 9 — Edge Hub（门店边缘硬件层：主机/设备/耳机绑定/告警）
from src.api import edge_hub
app.include_router(edge_hub.router, tags=["edge_hub"])

# v2.0 MVP #3 — 损耗Top5排名（含¥归因）
from src.api import waste_guard
app.include_router(waste_guard.router, tags=["waste_guard"])

# HR模块 — 薪酬/假勤/审批/招聘/绩效/合同/报表（部分 API 文件尚未实现，跳过缺失项）
try:
    from src.api import payroll as payroll_api
    from src.api import hr_leave
    from src.api import hr_recruitment
    from src.api import hr_performance
    from src.api import hr_dashboard as hr_dashboard_api
    from src.api import hr_employee
    from src.api import hr_attendance
    from src.api import hr_schedule
    from src.api import hr_lifecycle
    from src.api import hr_commission
    from src.api import hr_reward_penalty
    from src.api import hr_social_insurance
    from src.api import hr_growth
    from src.api import hr_import
    from src.api import hr_exit_interview
    from src.api import hr_settlement
    from src.api import hr_training
    from src.api import hr_report
    from src.api import hr_sensitive
    from src.api import hr_rules
    from src.api import hr_payslip
    from src.api import hr_employee_self_service
    from src.api import hr_approval
    from src.api import hr_audit as hr_audit_api
    from src.api import im_sync, im_callback, im_self_service
    from src.api import hr_batch
    from src.api import hr_ai
    from src.api import hr_decision_flywheel
    app.include_router(payroll_api.router, prefix="/api/v1", tags=["payroll"])
    app.include_router(hr_leave.router, prefix="/api/v1", tags=["hr_leave"])
    app.include_router(hr_recruitment.router, prefix="/api/v1", tags=["hr_recruitment"])
    app.include_router(hr_performance.router, prefix="/api/v1", tags=["hr_performance"])
    app.include_router(hr_dashboard_api.router, prefix="/api/v1", tags=["hr_dashboard"])
    app.include_router(hr_employee.router, prefix="/api/v1", tags=["hr_employee"])
    app.include_router(hr_attendance.router, prefix="/api/v1", tags=["hr_attendance"])
    app.include_router(hr_schedule.router, prefix="/api/v1", tags=["hr_schedule"])
    app.include_router(hr_lifecycle.router, prefix="/api/v1", tags=["hr_lifecycle"])
    app.include_router(hr_commission.router, prefix="/api/v1", tags=["hr_commission"])
    app.include_router(hr_reward_penalty.router, prefix="/api/v1", tags=["hr_reward_penalty"])
    app.include_router(hr_social_insurance.router, prefix="/api/v1", tags=["hr_social_insurance"])
    app.include_router(hr_growth.router, prefix="/api/v1", tags=["hr_growth"])
    app.include_router(hr_import.router, prefix="/api/v1", tags=["hr_import"])
    app.include_router(hr_exit_interview.router, prefix="/api/v1", tags=["hr_exit_interview"])
    app.include_router(hr_settlement.router, prefix="/api/v1", tags=["hr_settlement"])
    app.include_router(hr_training.router, prefix="/api/v1", tags=["hr_training"])
    app.include_router(hr_report.router, prefix="/api/v1", tags=["hr_report"])
    app.include_router(hr_sensitive.router, prefix="/api/v1", tags=["hr_sensitive"])
    app.include_router(hr_rules.router, prefix="/api/v1", tags=["hr_rules"])
    app.include_router(hr_payslip.router, prefix="/api/v1", tags=["hr_payslip"])
    app.include_router(hr_employee_self_service.router, prefix="/api/v1", tags=["hr_employee_self_service"])
    app.include_router(hr_approval.router, prefix="/api/v1", tags=["hr_approval"])
    app.include_router(hr_audit_api.router, prefix="/api/v1", tags=["hr_audit"])
    app.include_router(im_sync.router, prefix="/api/v1", tags=["im_sync"])
    app.include_router(im_callback.router, prefix="/api/v1", tags=["im_callback"])
    app.include_router(im_self_service.router, prefix="/api/v1", tags=["im_self_service"])
    app.include_router(hr_batch.router, prefix="/api/v1", tags=["hr_batch"])
    app.include_router(hr_ai.router, prefix="/api/v1", tags=["hr_ai"])
    app.include_router(hr_decision_flywheel.router, prefix="/api/v1", tags=["decision_flywheel"])
except ImportError as _e:
    import structlog as _sl
    _sl.get_logger().warning("HR API 模块未实现，跳过注册", error=str(_e))

# Month 1 (P0) — 外部集成
app.include_router(e_invoice.router, prefix="/api/v1", tags=["e-invoices"])
app.include_router(eleme.router, tags=["eleme"])
app.include_router(payment_reconciliation.router, prefix="/api/v1", tags=["payment-reconciliation"])
# Month 2 (P0+P1) — 抖音 / 食品安全 / 健康证
app.include_router(douyin.router, prefix="/api/v1", tags=["douyin"])
app.include_router(food_safety.router, tags=["food-safety"])
app.include_router(health_certificates.router, prefix="/api/v1", tags=["health-certs"])
# Month 3 (P1+P2) — 供应商B2B / 大众点评 / 银行对账
app.include_router(supplier_b2b.router, prefix="/api/v1", tags=["supplier-b2b"])
app.include_router(dianping.router, prefix="/api/v1", tags=["dianping"])
app.include_router(bank_reconciliation.router, prefix="/api/v1", tags=["bank-reconciliation"])
# Batch 1 — 数据融合层
app.include_router(integration_hub.router, tags=["integration-hub"])
app.include_router(omni_channel.router, tags=["omni-channel"])
app.include_router(tri_reconciliation.router, prefix="/api/v1", tags=["tri-reconciliation"])
# Batch 2 — 智能决策层
app.include_router(supplier_intelligence.router, tags=["supplier-intelligence"])
app.include_router(review_action.router, tags=["review-actions"])
app.include_router(compliance_engine.router, tags=["compliance-engine"])
# Batch 3 — 自动化闭环层
app.include_router(auto_procurement.router, prefix="/api/v1", tags=["auto-procurement"])
app.include_router(financial_closing.router, tags=["financial-closing"])
app.include_router(command_center.router, tags=["command-center"])
# 日清日结 + 周复盘
app.include_router(daily_ops.router)
# 岗位标准化知识库 + 员工成长
app.include_router(job_standard.router)
# 组织层级 + 多层配置继承
app.include_router(org_hierarchy.router)
# M2 HR Foundation — HRAgent v1 + REST API
from src.api import hr as hr_api
app.include_router(hr_api.router, prefix="/api/v1/hr", tags=["HR"])
# 企微考勤Webhook（无需认证，外部系统回调）
from src.api.webhooks.wechat_attendance import router as wechat_attendance_router
app.include_router(wechat_attendance_router, prefix="/api/v1", tags=["webhooks"])

# 业财税资金一体化（FCT）
if getattr(settings, "FCT_ENABLED", False):
    try:
        from src.api import fct
        app.include_router(fct.router, prefix="/api/v1/fct", tags=["fct"])
    except ImportError:
        logger.warning("FCT_ENABLED=True 但 src/api/fct.py 不存在，FCT 模块未加载")


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("屯象OS API Gateway 启动中...")
    logger.info(f"环境: {settings.APP_ENV}")
    logger.info(f"调试模式: {settings.APP_DEBUG}")

    # 启动企微 Action 升级巡检（Phase 2 M2.2）
    try:
        from src.services.wechat_action_fsm import get_wechat_fsm
        fsm = get_wechat_fsm()
        await fsm.start_escalation_monitor(interval_seconds=60)
        logger.info("企微 Action 升级巡检已启动")
    except Exception as e:
        logger.warning("企微 Action 升级巡检启动失败（非致命）", error=str(e))

    # Initialize database
    try:
        from src.core.database import init_db
        await init_db()
        logger.info("数据库初始化成功")

        # 加载多租户 Schema 映射
        from src.core.database import reload_schema_map_from_db
        await reload_schema_map_from_db()
    except Exception as e:
        logger.error("数据库初始化失败", error=str(e))
        # Don't fail startup if database is not available
        # This allows the API to run without database for testing

    # Start scheduler for automated tasks
    try:
        from src.services.scheduler import get_scheduler
        scheduler = get_scheduler()
        await scheduler.start()
        logger.info("定时任务调度器启动成功")
    except Exception as e:
        logger.error("定时任务调度器启动失败", error=str(e))

    # 初始化推理规则库种子数据（Phase 3 M3.3）
    try:
        from src.core.database import get_db as _get_db
        from src.services.knowledge_rule_service import KnowledgeRuleService
        async for db in _get_db():
            svc = KnowledgeRuleService(db)
            rules_result = await svc.seed_rules()
            bench_result = await svc.seed_benchmarks()
            cross_result = await svc.seed_cross_store_rules()
            await db.commit()
            logger.info(
                "推理规则库初始化完成",
                rules_created=rules_result.get("created", 0),
                benchmarks_created=bench_result.get("created", 0),
                cross_store_created=cross_result.get("created", 0),
            )
            break
    except Exception as e:
        logger.warning("推理规则库初始化失败（非致命）", error=str(e))

    # 注册 PostgreSQL→Neo4j 本体同步管道（Phase 1 M1.3）
    try:
        from src.core.database import async_session_factory
        from src.services.ontology_sync_pipeline import register_sync_listeners
        register_sync_listeners(async_session_factory)
        logger.info("Neo4j 本体同步管道注册成功")
    except Exception as e:
        logger.warning("Neo4j 本体同步管道注册失败（非致命）", error=str(e))

    # Initialize Redis cache
    try:
        from src.services.redis_cache_service import redis_cache
        await redis_cache.initialize()
        logger.info("Redis缓存服务启动成功")
    except Exception as e:
        logger.error("Redis缓存服务启动失败", error=str(e))


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("屯象OS API Gateway 关闭中...")

    # Stop scheduler
    try:
        from src.services.scheduler import get_scheduler
        scheduler = get_scheduler()
        await scheduler.stop()
        logger.info("定时任务调度器已停止")
    except Exception as e:
        logger.error("停止定时任务调度器失败", error=str(e))

    # Close member service
    try:
        from src.services.member_service import member_service
        await member_service.close()
        logger.info("会员服务已关闭")
    except Exception as e:
        logger.error("关闭会员服务失败", error=str(e))

    # Close POS service
    try:
        from src.services.pos_service import pos_service
        await pos_service.close()
        logger.info("POS服务已关闭")
    except Exception as e:
        logger.error("关闭POS服务失败", error=str(e))

    # Close Redis cache
    try:
        from src.services.redis_cache_service import redis_cache
        await redis_cache.close()
        logger.info("Redis缓存服务已关闭")
    except Exception as e:
        logger.error("关闭Redis缓存服务失败", error=str(e))

    # Close database connections
    try:
        from src.core.database import close_db
        await close_db()
        logger.info("数据库连接已关闭")
    except Exception as e:
        logger.error("关闭数据库连接失败", error=str(e))


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理"""
    from src.core.monitoring import error_monitor, ErrorSeverity, ErrorCategory

    # 记录错误到监控系统
    error_id = error_monitor.log_error(
        message=str(exc),
        severity=ErrorSeverity.ERROR,
        category=ErrorCategory.SYSTEM,
        exception=exc,
        context={
            "method": request.method,
            "path": str(request.url),
        },
        request_id=getattr(request.state, "request_id", None),
        endpoint=request.url.path,
    )

    logger.error("未处理的异常", error_id=error_id, exc_info=exc)

    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": str(exc) if settings.APP_DEBUG else "服务器内部错误",
            "error_id": error_id,
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.APP_DEBUG,
    )
