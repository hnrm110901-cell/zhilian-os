"""
智链OS API Gateway
主应用入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
import structlog
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, CollectorRegistry
import time

from src.core.config import settings
# 核心模块
from src.api import health, agents, auth, notifications, stores, mobile, integrations, monitoring, llm, enterprise, voice, neural, adapters, tasks, reconciliation, approval, edge_node, decision_validator, federated_learning, recommendations, agent_collaboration
from src.api.phase5_apis import platform_router, industry_router, supply_chain_router, i18n_router
# 逐步启用的模块
from src.api import dashboard, analytics, audit, multi_store, finance, customer360, wechat_triggers, queue, meituan_queue
# 需要外部适配器的模块 (会在适配器不可用时返回错误)
from src.api import members
# POS模块暂时禁用 (文件为空)
# from src.api import pos
from src.middleware.monitoring import MonitoringMiddleware
from src.middleware.rate_limit import RateLimitMiddleware
from src.middleware.audit_log import AuditLogMiddleware

# 配置结构化日志
logger = structlog.get_logger()

# API文档描述
API_DESCRIPTION = """
## 智链OS (Zhilian Operating System)

中餐连锁品牌门店运营智能体操作系统 - 基于多Agent协同的智能餐厅运营管理系统

### 核心功能

* **智能Agent系统**: 7个专业Agent实现从排班、订单、库存到决策的全流程智能化管理
* **用户认证**: 基于JWT的安全认证系统，支持访问令牌和刷新令牌
* **权限管理**: 细粒度的基于角色的访问控制(RBAC)，支持13种角色
* **决策支持**: KPI分析、业务洞察生成、改进建议
* **实时监控**: 系统健康检查、性能监控

### 认证说明

大部分API端点需要认证。使用以下步骤进行认证：

1. 调用 `/api/v1/auth/login` 获取访问令牌
2. 在后续请求的 `Authorization` 头中包含令牌: `Bearer <access_token>`
3. 访问令牌有效期30分钟，过期后使用刷新令牌获取新的访问令牌

### Agent系统

系统包含7个智能Agent：

* **ScheduleAgent**: 智能排班 - 基于AI的客流预测和自动排班
* **OrderAgent**: 订单协同 - 预定管理、排队系统、智能点单推荐
* **InventoryAgent**: 库存预警 - 实时监控、消耗预测、自动补货提醒
* **ServiceAgent**: 服务质量 - 客户反馈收集、服务质量监控
* **TrainingAgent**: 培训辅导 - 培训需求评估、计划生成、进度追踪
* **DecisionAgent**: 决策支持 - KPI分析、业务洞察、改进建议
* **ReservationAgent**: 预定宴会 - 预定管理、座位分配、宴会管理

### 技术栈

* **后端框架**: FastAPI (Python 3.9+)
* **数据库**: PostgreSQL with SQLAlchemy ORM
* **认证**: JWT (JSON Web Tokens)
* **日志**: Structlog
"""

# 创建FastAPI应用
app = FastAPI(
    title="智链OS API Gateway",
    description=API_DESCRIPTION,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "智链OS团队",
        "email": "support@zhilian-os.com",
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
    ],
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS + ["null"],  # 允许本地文件访问
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加速率限制中间件
app.add_middleware(RateLimitMiddleware)

# 添加审计日志中间件
app.add_middleware(AuditLogMiddleware)

# 添加监控中间件
app.add_middleware(MonitoringMiddleware)

# ==================== Prometheus指标 ====================
# 创建Prometheus指标
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_DURATION = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

ACTIVE_REQUESTS = Gauge(
    'http_requests_active',
    'Number of active HTTP requests'
)

# Prometheus metrics端点
@app.get("/metrics", include_in_schema=False)
async def metrics():
    """
    Prometheus metrics endpoint

    Exposes application metrics in Prometheus format for scraping.
    """
    return Response(
        content=generate_latest(),
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
app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
app.include_router(approval.router, prefix="/api/v1", tags=["approval"])
app.include_router(notifications.router, prefix="/api/v1", tags=["notifications"])
app.include_router(stores.router, prefix="/api/v1", tags=["stores"])
app.include_router(mobile.router, prefix="/api/v1", tags=["mobile"])
app.include_router(integrations.router, prefix="/api/v1", tags=["integrations"])
app.include_router(monitoring.router, prefix="/api/v1", tags=["monitoring"])
app.include_router(llm.router, prefix="/api/v1", tags=["llm"])
app.include_router(enterprise.router, prefix="/api/v1/enterprise", tags=["enterprise"])
app.include_router(voice.router, prefix="/api/v1/voice", tags=["voice"])
app.include_router(neural.router, prefix="/api/v1/neural", tags=["neural"])
app.include_router(adapters.router, tags=["adapters"])
app.include_router(tasks.router, prefix="/api/v1", tags=["tasks"])
app.include_router(reconciliation.router, prefix="/api/v1", tags=["reconciliation"])

# 逐步启用的模块
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["dashboard"])
app.include_router(analytics.router, prefix="/api/v1/analytics", tags=["analytics"])
app.include_router(audit.router, prefix="/api/v1/audit", tags=["audit"])
app.include_router(multi_store.router, prefix="/api/v1/multi-store", tags=["multi_store"])
app.include_router(finance.router, prefix="/api/v1/finance", tags=["finance"])
app.include_router(members.router, prefix="/api/v1/members", tags=["members"])
app.include_router(customer360.router, tags=["customer360"])
app.include_router(wechat_triggers.router, tags=["wechat_triggers"])
app.include_router(queue.router, tags=["queue"])
app.include_router(meituan_queue.router, tags=["meituan_queue"])

# Phase 3: 稳定性加固期 (Stability Reinforcement Period)
app.include_router(edge_node.router, tags=["edge_node"])
app.include_router(decision_validator.router, tags=["decision_validator"])

# Phase 4: 智能优化期 (Intelligence Optimization Period)
app.include_router(federated_learning.router, tags=["federated_learning"])
app.include_router(recommendations.router, tags=["recommendations"])
app.include_router(agent_collaboration.router, tags=["agent_collaboration"])

# Phase 5: 生态扩展期 (Ecosystem Expansion Period)
app.include_router(platform_router, tags=["open_platform"])
app.include_router(industry_router, tags=["industry_solutions"])
app.include_router(supply_chain_router, tags=["supply_chain"])
app.include_router(i18n_router, tags=["internationalization"])

# POS模块暂时禁用 (文件为空)
# app.include_router(pos.router, prefix="/api/v1/pos", tags=["pos"])


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("智链OS API Gateway 启动中...")
    logger.info(f"环境: {settings.APP_ENV}")
    logger.info(f"调试模式: {settings.APP_DEBUG}")

    # Initialize database
    try:
        from src.core.database import init_db
        await init_db()
        logger.info("数据库初始化成功")
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
    logger.info("智链OS API Gateway 关闭中...")

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
