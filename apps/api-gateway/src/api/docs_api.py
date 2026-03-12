"""
开发者文档 API — Phase 2 Month 2
- GET  /api/v1/open/docs/endpoints    静态端点目录（含请求/响应示例）
- GET  /api/v1/open/docs/auth-guide   鉴权方式说明
- POST /api/v1/open/sandbox/register  沙箱账号快速创建
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db

logger = structlog.get_logger()

docs_router = APIRouter(prefix="/api/v1/open/docs", tags=["developer_docs"])
sandbox_router = APIRouter(prefix="/api/v1/open/sandbox", tags=["developer_docs"])

# ── 静态端点目录 ───────────────────────────────────────────────────────────────

ENDPOINT_CATALOG: List[Dict[str, Any]] = [
    # ── Level 1: 数据同步 ──────────────────────────────────────────────────────
    {
        "level": 1,
        "key": "sync_orders",
        "name": "订单同步",
        "method": "POST",
        "path": "/api/v1/open/data/orders",
        "description": "批量同步 POS/外卖平台订单到屯象，支持创建和更新两种模式（幂等）",
        "tier_required": "free",
        "request_params": [
            {"name": "orders", "type": "Array<Order>", "required": True, "description": "订单列表，最多 100 条/批"},
            {"name": "orders[].order_id", "type": "string", "required": True, "description": "外部系统订单 ID（用于幂等）"},
            {"name": "orders[].store_id", "type": "string", "required": True, "description": "门店 ID"},
            {"name": "orders[].total_amount", "type": "number", "required": True, "description": "订单总额（元）"},
            {"name": "orders[].status", "type": "string", "required": True, "description": "订单状态：pending/completed/cancelled"},
        ],
        "response_example": {
            "code": 200,
            "message": "订单同步成功",
            "data": {"synced_count": 5, "errors": []},
            "timestamp": "2026-03-07T10:00:00"
        },
        "code_examples": {
            "python": (
                "import requests, hmac, hashlib, time, json\n\n"
                "API_KEY = 'zlos_your_api_key'\n"
                "API_SECRET = 'your_api_secret'\n\n"
                "orders = [{\n"
                "    'order_id': 'ORD_001',\n"
                "    'store_id': 'STORE001',\n"
                "    'total_amount': 188.0,\n"
                "    'status': 'completed'\n"
                "}]\n\n"
                "body = json.dumps({'orders': orders})\n"
                "ts = str(int(time.time()))\n"
                "sig = hmac.new(API_SECRET.encode(), f'{ts}:{body}'.encode(), hashlib.sha256).hexdigest()\n\n"
                "resp = requests.post(\n"
                "    'https://api.zhilian-os.com/v1/open/data/orders',\n"
                "    data=body,\n"
                "    headers={\n"
                "        'Content-Type': 'application/json',\n"
                "        'X-API-Key': API_KEY,\n"
                "        'X-Timestamp': ts,\n"
                "        'X-Signature': sig,\n"
                "    }\n"
                ")\n"
                "print(resp.json())"
            ),
            "nodejs": (
                "const axios = require('axios');\n"
                "const crypto = require('crypto');\n\n"
                "const API_KEY = 'zlos_your_api_key';\n"
                "const API_SECRET = 'your_api_secret';\n\n"
                "async function syncOrders(orders) {\n"
                "  const body = JSON.stringify({ orders });\n"
                "  const ts = Math.floor(Date.now() / 1000).toString();\n"
                "  const sig = crypto.createHmac('sha256', API_SECRET)\n"
                "    .update(`${ts}:${body}`).digest('hex');\n\n"
                "  const resp = await axios.post(\n"
                "    'https://api.zhilian-os.com/v1/open/data/orders',\n"
                "    body,\n"
                "    { headers: { 'Content-Type': 'application/json',\n"
                "                 'X-API-Key': API_KEY,\n"
                "                 'X-Timestamp': ts,\n"
                "                 'X-Signature': sig } }\n"
                "  );\n"
                "  return resp.data;\n"
                "}"
            ),
            "curl": (
                "TS=$(date +%s)\n"
                "BODY='{\"orders\":[{\"order_id\":\"ORD_001\",\"store_id\":\"STORE001\",\"total_amount\":188.0,\"status\":\"completed\"}]}'\n"
                "SIG=$(echo -n \"${TS}:${BODY}\" | openssl dgst -sha256 -hmac \"$API_SECRET\" | awk '{print $2}')\n\n"
                "curl -X POST https://api.zhilian-os.com/v1/open/data/orders \\\n"
                "  -H 'Content-Type: application/json' \\\n"
                "  -H \"X-API-Key: $API_KEY\" \\\n"
                "  -H \"X-Timestamp: $TS\" \\\n"
                "  -H \"X-Signature: $SIG\" \\\n"
                "  -d \"$BODY\""
            ),
        },
    },
    {
        "level": 1,
        "key": "sync_members",
        "name": "会员同步",
        "method": "POST",
        "path": "/api/v1/open/data/members",
        "description": "同步会员信息、积分、消费记录到屯象会员体系",
        "tier_required": "free",
        "request_params": [
            {"name": "members", "type": "Array<Member>", "required": True, "description": "会员列表，最多 200 条/批"},
            {"name": "members[].phone", "type": "string", "required": True, "description": "手机号（主键）"},
            {"name": "members[].name", "type": "string", "required": True, "description": "姓名"},
            {"name": "members[].points", "type": "integer", "required": False, "description": "积分余额"},
        ],
        "response_example": {
            "code": 200,
            "message": "会员同步成功",
            "data": {"synced_count": 20, "errors": []},
            "timestamp": "2026-03-07T10:00:00"
        },
        "code_examples": {
            "python": "# 参见订单同步示例，替换 endpoint 和 body 即可\nbody = json.dumps({'members': [{'phone': '13800138000', 'name': '张三', 'points': 500}]})",
            "nodejs": "// 参见订单同步示例，替换 body 即可\nconst body = JSON.stringify({ members: [{ phone: '13800138000', name: '张三', points: 500 }] });",
            "curl": "# 参见订单同步示例，替换 endpoint 和 BODY 即可",
        },
    },
    # ── Level 2: 智能决策 ──────────────────────────────────────────────────────
    {
        "level": 2,
        "key": "predict_sales",
        "name": "销量预测",
        "method": "GET",
        "path": "/api/v1/open/ai/predict-sales",
        "description": "基于历史订单数据预测指定日期的菜品销量，支持指定菜品过滤",
        "tier_required": "basic",
        "request_params": [
            {"name": "store_id", "type": "string", "required": True, "description": "门店 ID（query param）"},
            {"name": "date", "type": "string", "required": True, "description": "预测日期，格式 YYYY-MM-DD"},
            {"name": "dish_ids", "type": "string", "required": False, "description": "菜品 ID 逗号分隔（可选）"},
        ],
        "response_example": {
            "code": 200,
            "message": "销量预测成功",
            "data": {
                "dish_001": {"dish_name": "招牌鱼头", "predicted_sales": 35},
                "dish_002": {"dish_name": "红烧肉", "predicted_sales": 28},
            },
            "timestamp": "2026-03-07T10:00:00"
        },
        "code_examples": {
            "python": (
                "resp = requests.get(\n"
                "    'https://api.zhilian-os.com/v1/open/ai/predict-sales',\n"
                "    params={'store_id': 'STORE001', 'date': '2026-03-08'},\n"
                "    headers={'X-API-Key': API_KEY, 'X-Timestamp': ts, 'X-Signature': sig}\n"
                ")\n"
                "print(resp.json()['data'])"
            ),
            "nodejs": "const resp = await axios.get('/api/v1/open/ai/predict-sales', { params: { store_id: 'STORE001', date: '2026-03-08' }, headers });",
            "curl": "curl -G https://api.zhilian-os.com/v1/open/ai/predict-sales -d store_id=STORE001 -d date=2026-03-08 -H \"X-API-Key: $API_KEY\" ...",
        },
    },
    {
        "level": 2,
        "key": "suggest_purchase",
        "name": "采购建议",
        "method": "GET",
        "path": "/api/v1/open/ai/suggest-purchase",
        "description": "基于库存水位和销量预测，生成明日食材采购清单",
        "tier_required": "basic",
        "request_params": [
            {"name": "store_id", "type": "string", "required": True, "description": "门店 ID"},
            {"name": "date", "type": "string", "required": True, "description": "采购日期 YYYY-MM-DD"},
        ],
        "response_example": {
            "code": 200,
            "message": "采购建议生成成功",
            "data": [
                {"item": "鲈鱼", "quantity": 20, "unit": "条"},
                {"item": "猪五花", "quantity": 15, "unit": "kg"},
            ],
            "timestamp": "2026-03-07T10:00:00"
        },
        "code_examples": {
            "python": "# 同 predict-sales，替换路径和参数",
            "nodejs": "// 同 predict-sales，替换路径和参数",
            "curl": "# 同 predict-sales，替换路径和参数",
        },
    },
    # ── Level 3: 营销能力 ──────────────────────────────────────────────────────
    {
        "level": 3,
        "key": "customer_profile",
        "name": "客户画像",
        "method": "GET",
        "path": "/api/v1/open/marketing/customer/{customer_id}/profile",
        "description": "获取顾客 RFM 画像：历史消费、流失风险、价值评分、常点菜品",
        "tier_required": "pro",
        "request_params": [
            {"name": "customer_id", "type": "string", "required": True, "description": "顾客手机号（路径参数）"},
        ],
        "response_example": {
            "code": 200,
            "message": "客户画像获取成功",
            "data": {
                "customer_id": "13800138000",
                "order_count": 12,
                "value_score": 68.5,
                "churn_risk": 0.15,
                "segment": "high_value",
                "favorite_dishes": ["招牌鱼头", "红烧肉"],
            },
            "timestamp": "2026-03-07T10:00:00"
        },
        "code_examples": {
            "python": (
                "resp = requests.get(\n"
                "    f'https://api.zhilian-os.com/v1/open/marketing/customer/13800138000/profile',\n"
                "    headers=signed_headers()\n"
                ")"
            ),
            "nodejs": "const resp = await axios.get(`/api/v1/open/marketing/customer/${customerId}/profile`, { headers });",
            "curl": "curl https://api.zhilian-os.com/v1/open/marketing/customer/13800138000/profile -H \"X-API-Key: $API_KEY\" ...",
        },
    },
    {
        "level": 3,
        "key": "coupon_strategy",
        "name": "发券策略",
        "method": "POST",
        "path": "/api/v1/open/marketing/coupon-strategy",
        "description": "AI 根据场景和目标客群生成差异化优惠券方案，含预期转化率和 ROI",
        "tier_required": "pro",
        "request_params": [
            {"name": "scenario", "type": "string", "required": True, "description": "场景：traffic_decline/new_product_launch/member_day/default"},
            {"name": "target_segment", "type": "string", "required": True, "description": "目标客群：high_value/at_risk/new/potential"},
            {"name": "store_id", "type": "string", "required": True, "description": "门店 ID"},
        ],
        "response_example": {
            "code": 200,
            "message": "优惠券策略生成成功",
            "data": {
                "coupon_type": "满减券",
                "amount": 30.0,
                "threshold": 150.0,
                "valid_days": 7,
                "expected_conversion": 0.25,
                "expected_roi": 3.5,
            },
            "timestamp": "2026-03-07T10:00:00"
        },
        "code_examples": {
            "python": (
                "resp = requests.post(\n"
                "    'https://api.zhilian-os.com/v1/open/marketing/coupon-strategy',\n"
                "    json={'scenario': 'traffic_decline', 'target_segment': 'at_risk', 'store_id': 'STORE001'},\n"
                "    headers=signed_headers(body_json)\n"
                ")"
            ),
            "nodejs": "const resp = await axios.post('/api/v1/open/marketing/coupon-strategy', { scenario: 'traffic_decline', target_segment: 'at_risk', store_id: 'STORE001' }, { headers });",
            "curl": "curl -X POST https://api.zhilian-os.com/v1/open/marketing/coupon-strategy -d '{\"scenario\":\"traffic_decline\",\"target_segment\":\"at_risk\",\"store_id\":\"STORE001\"}' ...",
        },
    },
    # ── Level 4: 高级能力 ──────────────────────────────────────────────────────
    {
        "level": 4,
        "key": "query_sop",
        "name": "SOP 知识库查询",
        "method": "POST",
        "path": "/api/v1/open/advanced/sop-query",
        "description": "自然语言查询餐饮运营 SOP 最佳实践，返回步骤、预期效果、置信度",
        "tier_required": "enterprise",
        "request_params": [
            {"name": "scenario", "type": "string", "required": True, "description": "场景描述，自然语言"},
            {"name": "context.user_role", "type": "string", "required": False, "description": "角色：store_manager/chef/waiter"},
            {"name": "context.urgency", "type": "string", "required": False, "description": "紧急程度：low/medium/high"},
        ],
        "response_example": {
            "code": 200,
            "message": "SOP查询成功",
            "data": {
                "sop_id": "SOP_PEAK_FLOW_001",
                "title": "晚高峰翻台优化SOP",
                "relevance_score": 0.92,
                "confidence": 0.87,
                "key_steps": ["提前30分钟备餐", "安排专职收台员", "15分钟结账提醒"],
                "estimated_time_minutes": 45,
            },
            "timestamp": "2026-03-07T10:00:00"
        },
        "code_examples": {
            "python": (
                "resp = requests.post(\n"
                "    'https://api.zhilian-os.com/v1/open/advanced/sop-query',\n"
                "    json={'scenario': '晚高峰翻台效率低，如何优化？', 'context': {'urgency': 'high'}},\n"
                "    headers=signed_headers(body_json)\n"
                ")"
            ),
            "nodejs": "const resp = await axios.post('/api/v1/open/advanced/sop-query', { scenario: '晚高峰翻台效率低', context: { urgency: 'high' } }, { headers });",
            "curl": "curl -X POST https://api.zhilian-os.com/v1/open/advanced/sop-query -d '{\"scenario\":\"晚高峰翻台效率低\"}' ...",
        },
    },
]

# ── 鉴权说明（静态）──────────────────────────────────────────────────────────

AUTH_GUIDE = {
    "title": "API 鉴权方式",
    "summary": "屯象开放平台使用 API Key + HMAC-SHA256 请求签名，防止重放攻击和篡改。",
    "steps": [
        {
            "step": 1,
            "title": "获取凭证",
            "description": "在开放平台注册开发者账号，获取 api_key 和 api_secret（仅注册时返回一次）。",
        },
        {
            "step": 2,
            "title": "构造签名",
            "description": "将请求时间戳（Unix 秒）和请求体拼接：message = f'{timestamp}:{body}'，使用 api_secret 做 HMAC-SHA256，得到十六进制签名。",
            "code_python": (
                "import hmac, hashlib, time\n\n"
                "def sign(body: str, secret: str) -> tuple[str, str]:\n"
                "    ts = str(int(time.time()))\n"
                "    sig = hmac.new(secret.encode(), f'{ts}:{body}'.encode(), hashlib.sha256).hexdigest()\n"
                "    return ts, sig"
            ),
            "code_nodejs": (
                "const crypto = require('crypto');\n\n"
                "function sign(body, secret) {\n"
                "  const ts = Math.floor(Date.now() / 1000).toString();\n"
                "  const sig = crypto.createHmac('sha256', secret).update(`${ts}:${body}`).digest('hex');\n"
                "  return { ts, sig };\n"
                "}"
            ),
        },
        {
            "step": 3,
            "title": "携带请求头",
            "description": "每次请求携带以下 3 个 Header：",
            "headers": [
                {"name": "X-API-Key", "value": "your_api_key", "description": "开发者 API Key（zlos_ 前缀）"},
                {"name": "X-Timestamp", "value": "1741334400", "description": "请求时间戳（Unix 秒），有效窗口 ±5 分钟"},
                {"name": "X-Signature", "value": "abc123...", "description": "HMAC-SHA256 签名（十六进制字符串）"},
            ],
        },
        {
            "step": 4,
            "title": "处理响应",
            "description": "所有响应统一格式：{ code, message, data, timestamp }。code=200 成功，其他为错误码。",
            "error_codes": [
                {"code": 401, "message": "Unauthorized", "reason": "API Key 无效或签名错误"},
                {"code": 429, "message": "Too Many Requests", "reason": "超过速率限制（按套餐限制）"},
                {"code": 403, "message": "Forbidden", "reason": "当前套餐不支持该能力层级"},
                {"code": 400, "message": "Bad Request", "reason": "请求参数校验失败"},
            ],
        },
    ],
}


# ── Endpoints ──────────────────────────────────────────────────────────────────

@docs_router.get("/endpoints")
async def get_endpoint_catalog(level: Optional[int] = None):
    """获取结构化端点目录，可按 Level 过滤"""
    catalog = ENDPOINT_CATALOG if level is None else [e for e in ENDPOINT_CATALOG if e["level"] == level]
    grouped: Dict[int, List] = {}
    for ep in catalog:
        grouped.setdefault(ep["level"], []).append(ep)
    return {
        "total": len(catalog),
        "levels": sorted(grouped.keys()),
        "by_level": {
            str(lvl): {"count": len(eps), "endpoints": eps}
            for lvl, eps in sorted(grouped.items())
        },
    }


@docs_router.get("/auth-guide")
async def get_auth_guide():
    """返回鉴权方式完整说明"""
    return AUTH_GUIDE


# ── Sandbox ────────────────────────────────────────────────────────────────────

class SandboxRegisterRequest(BaseModel):
    name: str
    email: str


@sandbox_router.post("/register")
async def register_sandbox(
    body: SandboxRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    沙箱账号快速创建。
    沙箱 Key 以 zlos_sbx_ 开头，调用时返回模拟数据，不写入生产数据库。
    """
    # 同邮箱检查（沙箱同一邮箱只能注册一次，以 _sbx 后缀区分）
    sandbox_email = f"{body.email}__sbx"
    existing = await db.execute(
        text("SELECT 1 FROM isv_developers WHERE email = :email LIMIT 1"),
        {"email": sandbox_email},
    )
    if existing.first() is not None:
        raise HTTPException(status_code=409, detail="该邮箱已有沙箱账号，无需重复申请")

    developer_id = f"sbx_{uuid.uuid4().hex[:12]}"
    api_key = f"zlos_sbx_{secrets.token_urlsafe(24)}"
    api_secret = secrets.token_urlsafe(36)
    secret_hash = hashlib.sha256(api_secret.encode()).hexdigest()
    key_id = f"key_{uuid.uuid4().hex[:12]}"
    now = datetime.utcnow()

    await db.execute(
        text("""
            INSERT INTO isv_developers (id, name, email, company, tier, is_verified, created_at)
            VALUES (:id, :name, :email, NULL, 'free', false, :now)
        """),
        {"id": developer_id, "name": body.name, "email": sandbox_email, "now": now},
    )
    await db.execute(
        text("""
            INSERT INTO isv_api_keys (id, developer_id, key_name, api_key, api_secret_hash,
                                      rate_limit_rpm, is_active, is_sandbox, created_at)
            VALUES (:id, :dev_id, 'sandbox', :api_key, :secret_hash,
                    60, true, true, :now)
        """),
        {
            "id": key_id,
            "dev_id": developer_id,
            "api_key": api_key,
            "secret_hash": secret_hash,
            "now": now,
        },
    )
    await db.commit()

    logger.info("sandbox_registered", developer_id=developer_id, email=body.email)

    return {
        "developer_id": developer_id,
        "api_key": api_key,
        "api_secret": api_secret,
        "is_sandbox": True,
        "note": "沙箱账号：调用所有端点均返回模拟数据，不影响生产环境。api_secret 仅此一次展示，请妥善保存。",
        "rate_limit_rpm": 60,
        "base_url": "https://sandbox.zhilian-os.com/v1",
    }
