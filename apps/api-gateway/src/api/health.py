"""
健康检查API
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from datetime import datetime
import structlog

from src.core.dependencies import get_current_active_user
from src.services.wechat_service import wechat_service
from src.services.feishu_service import feishu_service
from src.services.aoqiwei_service import aoqiwei_service
from src.services.pinzhi_service import pinzhi_service
from src.models import User

logger = structlog.get_logger()

router = APIRouter()


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str
    timestamp: datetime
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    系统健康检查

    检查API服务是否正常运行。用于监控和负载均衡器健康检查。

    **认证要求**: 无需认证

    **使用场景**:
    - 监控系统定期检查服务状态
    - 负载均衡器健康检查
    - 部署后验证服务是否正常启动

    **示例响应**:
    ```json
    {
        "status": "healthy",
        "timestamp": "2024-02-18T10:30:00.000Z",
        "version": "1.0.0"
    }
    ```

    **响应说明**:
    - `status`: 服务状态，始终返回 "healthy"
    - `timestamp`: 当前服务器时间
    - `version`: API版本号
    """
    return HealthResponse(
        status="healthy", timestamp=datetime.now(), version="1.0.0"
    )


@router.get("/ready")
async def readiness_check():
    """
    就绪检查

    检查服务是否准备好接收流量。验证所有依赖服务（数据库、缓存等）是否可用。

    **认证要求**: 无需认证

    **使用场景**:
    - Kubernetes readiness probe
    - 滚动更新时检查新实例是否就绪
    - 确认服务依赖是否全部可用

    **示例响应**:
    ```json
    {
        "status": "ready",
        "checks": {
            "database": "healthy",
            "redis": "healthy"
        }
    }
    ```

    **状态说明**:
    - `ready`: 所有依赖服务正常
    - `not_ready`: 至少一个依赖服务不可用
    """
    from ..core.database import get_db_session
    from sqlalchemy import text
    import redis
    from ..core.config import settings

    checks = {}
    all_healthy = True

    # 检查数据库连接
    try:
        async with get_db_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "healthy"
        logger.debug("数据库连接检查通过")
    except Exception as e:
        checks["database"] = f"unhealthy: {str(e)}"
        all_healthy = False
        logger.error("数据库连接检查失败", error=str(e))

    # 检查Redis连接
    try:
        redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
        redis_client.ping()
        checks["redis"] = "healthy"
        logger.debug("Redis连接检查通过")
    except Exception as e:
        checks["redis"] = f"unhealthy: {str(e)}"
        all_healthy = False
        logger.error("Redis连接检查失败", error=str(e))

    status = "ready" if all_healthy else "not_ready"

    return {
        "status": status,
        "checks": checks,
        "timestamp": datetime.now().isoformat()
    }


@router.get("/live")
async def liveness_check():
    """
    存活检查

    检查服务进程是否存活。用于检测死锁或无响应状态。

    **认证要求**: 无需认证

    **使用场景**:
    - Kubernetes liveness probe
    - 检测服务是否需要重启
    - 监控服务进程状态

    **示例响应**:
    ```json
    {
        "status": "alive"
    }
    ```

    **与健康检查的区别**:
    - `liveness`: 检查进程是否存活（能响应请求）
    - `readiness`: 检查服务是否准备好处理业务请求
    - `health`: 综合健康状态检查
    """
    return {"status": "alive"}


@router.get("/agents", summary="Agent系统健康检查")
async def agents_health():
    """
    检查所有Agent的状态

    验证所有AI Agent是否成功初始化并可用。
    这是Week 1架构重构的关键端点，用于防止静默失败。

    **认证要求**: 无需认证

    **使用场景**:
    - 服务启动后验证所有Agent已加载
    - 监控系统检查Agent可用性
    - 故障排查时确认Agent状态

    **示例响应**:
    ```json
    {
        "status": "healthy",
        "total_agents": 7,
        "agents": {
            "schedule": {"initialized": true, "type": "ScheduleAgent"},
            "order": {"initialized": true, "type": "OrderAgent"},
            ...
        },
        "timestamp": "2026-02-21T18:00:00.000Z"
    }
    ```

    **状态说明**:
    - `healthy`: 所有Agent正常初始化
    - `degraded`: 部分Agent不可用
    - `unhealthy`: 无Agent可用或服务未启动
    """
    try:
        from src.services.agent_service import AgentService

        # 获取AgentService实例
        # 注意: 如果AgentService初始化失败，这里会抛出异常
        agent_service = AgentService()

        # 获取所有Agent状态
        agents_status = agent_service.get_agents_status()

        # 判断整体健康状态
        total_agents = agents_status.get("total_agents", 0)
        if total_agents == 0:
            status = "unhealthy"
        elif total_agents >= 7:  # 期望有7个Agent
            status = "healthy"
        else:
            status = "degraded"

        return {
            "status": status,
            "total_agents": total_agents,
            "agents": agents_status.get("agents", {}),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error("Agent健康检查失败", error=str(e))
        return {
            "status": "unhealthy",
            "total_agents": 0,
            "agents": {},
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/external-systems", summary="外部系统健康检查")
async def external_systems_health(
    current_user: User = Depends(get_current_active_user),
):
    """
    检查所有外部系统的配置和连接状态

    需要认证，返回所有外部系统的健康状态
    """
    logger.info("开始检查外部系统健康状态")

    # 并发检查所有外部系统
    wechat_status = {
        "name": "企业微信",
        "configured": wechat_service.is_configured(),
        "status": "not_configured" if not wechat_service.is_configured() else "configured",
    }

    feishu_status = {
        "name": "飞书",
        "configured": feishu_service.is_configured(),
        "status": "not_configured" if not feishu_service.is_configured() else "configured",
    }

    # 对于Aoqiwei和Pinzhi，执行实际的健康检查
    aoqiwei_status = await aoqiwei_service.health_check()
    aoqiwei_status["name"] = "奥琦韦会员系统"

    pinzhi_status = await pinzhi_service.health_check()
    pinzhi_status["name"] = "品智POS系统"

    # 汇总结果
    systems = {
        "wechat": wechat_status,
        "feishu": feishu_status,
        "aoqiwei": aoqiwei_status,
        "pinzhi": pinzhi_status,
    }

    # 计算总体状态
    total_systems = len(systems)
    configured_systems = sum(1 for s in systems.values() if s.get("configured", False))
    healthy_systems = sum(
        1 for s in systems.values()
        if s.get("status") in ["healthy", "configured"]
    )

    overall_status = "healthy" if healthy_systems == total_systems else "degraded"
    if configured_systems == 0:
        overall_status = "not_configured"
    elif healthy_systems == 0:
        overall_status = "unhealthy"

    return {
        "overall_status": overall_status,
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total": total_systems,
            "configured": configured_systems,
            "healthy": healthy_systems,
        },
        "systems": systems,
    }


@router.get("/wechat", summary="企业微信健康检查")
async def wechat_health(
    current_user: User = Depends(get_current_active_user),
):
    """检查企业微信配置状态"""
    is_configured = wechat_service.is_configured()

    return {
        "name": "企业微信",
        "configured": is_configured,
        "status": "configured" if is_configured else "not_configured",
        "message": "企业微信已配置" if is_configured else "企业微信未配置，请设置环境变量",
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/feishu", summary="飞书健康检查")
async def feishu_health(
    current_user: User = Depends(get_current_active_user),
):
    """检查飞书配置状态"""
    is_configured = feishu_service.is_configured()

    return {
        "name": "飞书",
        "configured": is_configured,
        "status": "configured" if is_configured else "not_configured",
        "message": "飞书已配置" if is_configured else "飞书未配置，请设置环境变量",
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/aoqiwei", summary="奥琦韦健康检查")
async def aoqiwei_health(
    current_user: User = Depends(get_current_active_user),
):
    """检查奥琦韦会员系统配置和连接状态"""
    result = await aoqiwei_service.health_check()
    result["name"] = "奥琦韦会员系统"
    result["timestamp"] = datetime.now().isoformat()
    return result


@router.get("/pinzhi", summary="品智健康检查")
async def pinzhi_health(
    current_user: User = Depends(get_current_active_user),
):
    """检查品智POS系统配置和连接状态"""
    result = await pinzhi_service.health_check()
    result["name"] = "品智POS系统"
    result["timestamp"] = datetime.now().isoformat()
    return result


@router.get("/config/validation", summary="配置验证")
async def config_validation(
    current_user: User = Depends(get_current_active_user),
):
    """
    验证所有配置项

    检查必需和可选配置项是否正确设置
    """
    from src.core.config import settings

    # 必需配置
    required_configs = {
        "DATABASE_URL": bool(settings.DATABASE_URL),
        "REDIS_URL": bool(settings.REDIS_URL),
        "SECRET_KEY": bool(settings.SECRET_KEY),
        "JWT_SECRET": bool(settings.JWT_SECRET),
    }

    # 可选配置 - 企业微信
    wechat_configs = {
        "WECHAT_CORP_ID": bool(settings.WECHAT_CORP_ID),
        "WECHAT_CORP_SECRET": bool(settings.WECHAT_CORP_SECRET),
        "WECHAT_AGENT_ID": bool(settings.WECHAT_AGENT_ID),
    }

    # 可选配置 - 飞书
    feishu_configs = {
        "FEISHU_APP_ID": bool(settings.FEISHU_APP_ID),
        "FEISHU_APP_SECRET": bool(settings.FEISHU_APP_SECRET),
    }

    # 可选配置 - 奥琦韦
    aoqiwei_configs = {
        "AOQIWEI_API_KEY": bool(settings.AOQIWEI_API_KEY),
        "AOQIWEI_BASE_URL": bool(settings.AOQIWEI_BASE_URL),
    }

    # 可选配置 - 品智
    pinzhi_configs = {
        "PINZHI_TOKEN": bool(settings.PINZHI_TOKEN),
        "PINZHI_BASE_URL": bool(settings.PINZHI_BASE_URL),
    }

    # 计算完整性
    wechat_complete = all(wechat_configs.values())
    feishu_complete = all(feishu_configs.values())
    aoqiwei_complete = all(aoqiwei_configs.values())
    pinzhi_complete = all(pinzhi_configs.values())

    return {
        "required": {
            "configs": required_configs,
            "complete": all(required_configs.values()),
        },
        "optional": {
            "wechat": {
                "configs": wechat_configs,
                "complete": wechat_complete,
            },
            "feishu": {
                "configs": feishu_configs,
                "complete": feishu_complete,
            },
            "aoqiwei": {
                "configs": aoqiwei_configs,
                "complete": aoqiwei_complete,
            },
            "pinzhi": {
                "configs": pinzhi_configs,
                "complete": pinzhi_complete,
            },
        },
        "summary": {
            "required_complete": all(required_configs.values()),
            "optional_systems_configured": sum([
                wechat_complete,
                feishu_complete,
                aoqiwei_complete,
                pinzhi_complete,
            ]),
            "total_optional_systems": 4,
        },
        "timestamp": datetime.now().isoformat(),
    }
