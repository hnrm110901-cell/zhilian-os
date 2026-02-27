"""
业财税资金一体化（FCT）独立服务入口

单独启动时仅暴露 FCT 公开 API，不依赖智链OS 的 Agent、企业微信、权限等。
与智链OS 的对接通过 HTTP（事件推送 + 查询 API）完成。

启动方式（在 api-gateway 目录下）:
  uvicorn fct_standalone_main:app --host 0.0.0.0 --port 8001

环境变量（至少）:
  DATABASE_URL=postgresql+asyncpg://...
  FCT_API_KEY=your_secret   # 可选；不设则不对请求做 API Key 校验（仅建议内网使用）
  # 若沿用智链OS 的 .env，REDIS_URL/SECRET_KEY/JWT_SECRET 等也需存在，可占位
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.fct_public import router as fct_router

app = FastAPI(
    title="业财税资金一体化服务（FCT）",
    description="独立部署形态：业财事件接入、凭证与总账查询，与智链OS 契约一致。",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 契约与合并形态一致：/api/v1/fct/*
app.include_router(fct_router, prefix="/api/v1/fct", tags=["fct"])

# 独立形态可选：/api/v1/events 作为事件入口（与文档中「独立形态 POST /api/v1/events」一致）
app.include_router(fct_router, prefix="/api/v1", tags=["fct-events"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "fct-standalone"}
