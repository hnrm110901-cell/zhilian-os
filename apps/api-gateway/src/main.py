"""
智链OS API Gateway
主应用入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from src.core.config import settings
from src.api import health, agents

# 配置结构化日志
logger = structlog.get_logger()

# 创建FastAPI应用
app = FastAPI(
    title="智链OS API Gateway",
    description="中餐连锁品牌门店运营智能体智链操作系统 API网关",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(agents.router, prefix="/api/v1/agents", tags=["agents"])


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("智链OS API Gateway 启动中...")
    logger.info(f"环境: {settings.APP_ENV}")
    logger.info(f"调试模式: {settings.APP_DEBUG}")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("智链OS API Gateway 关闭中...")


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """全局异常处理"""
    logger.error("未处理的异常", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": str(exc) if settings.APP_DEBUG else "服务器内部错误",
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
