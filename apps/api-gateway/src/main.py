"""
智链OS API Gateway
主应用入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from src.core.config import settings
from src.api import health, agents, auth, notifications, stores, mobile, integrations, monitoring, llm, pos
from src.middleware.monitoring import MonitoringMiddleware

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
            "name": "pos",
            "description": "POS系统 - 品智收银系统集成接口",
        },
    ],
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加监控中间件
app.add_middleware(MonitoringMiddleware)

# 注册路由
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])
app.include_router(notifications.router, prefix="/api/v1", tags=["notifications"])
app.include_router(stores.router, prefix="/api/v1", tags=["stores"])
app.include_router(mobile.router, prefix="/api/v1", tags=["mobile"])
app.include_router(integrations.router, prefix="/api/v1", tags=["integrations"])
app.include_router(monitoring.router, prefix="/api/v1", tags=["monitoring"])
app.include_router(llm.router, prefix="/api/v1", tags=["llm"])
app.include_router(pos.router, prefix="/api/v1/pos", tags=["pos"])


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


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("智链OS API Gateway 关闭中...")

    # Close POS service
    try:
        from src.services.pos_service import pos_service
        await pos_service.close()
        logger.info("POS服务已关闭")
    except Exception as e:
        logger.error("关闭POS服务失败", error=str(e))

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
