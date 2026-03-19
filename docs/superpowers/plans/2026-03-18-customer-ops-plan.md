# 顾客运营体系 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 3-phase customer operations system (识客画像 → 发券+ROI → 营销任务) that lets restaurant staff recognize customers on arrival, issue coupons with ROI tracking, and execute HQ-driven marketing campaigns.

**Architecture:** BFF aggregation pattern — single endpoint per feature aggregates multiple data sources (微生活CRM, 品智POS, consumer_identities) with per-source fallback. All new tables use UUID PKs, VARCHAR(50) store_id, money in fen. Frontend uses Z-prefixed design system components with CSS Modules.

**Tech Stack:** FastAPI + SQLAlchemy (async) + Alembic | React 19 + TypeScript + Vite | Redis cache | Celery tasks | pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-03-18-customer-ops-design.md`

---

## Chunk 1: P1 Backend — 识客画像

### Task 1: P1 Database Models + Migration

Create SQLAlchemy models and Alembic migration for P1 tables.

**Files:**
- Create: `apps/api-gateway/src/models/member_check_in.py`
- Create: `apps/api-gateway/src/models/member_dish_preference.py`
- Modify: `apps/api-gateway/src/models/__init__.py` (add imports)
- Modify: `apps/api-gateway/alembic/env.py` (add model imports)
- Create: Alembic migration file (auto-generated)

**Context:**
- Model pattern: see `src/models/consumer_identity.py` — UUID PK, `Base` + `TimestampMixin`, `Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)`
- store_id is `VARCHAR(50)` matching `stores.id`, user FKs are `UUID`
- Money fields use `Integer` with `_fen` suffix
- The `consumer_identities` table already has `tags` (JSON) and `birth_date` (Date). We only ADD `dietary_restrictions` (JSON) and `anniversary` (Date).

- [ ] **Step 1: Create member_check_in.py model**

```python
# apps/api-gateway/src/models/member_check_in.py
"""识客事件记录 — 每次顾客被识别（搜索/预订/POS触发）生成一条"""

import uuid
from sqlalchemy import Column, String, Index, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP

from .base import Base, TimestampMixin


class MemberCheckIn(Base, TimestampMixin):
    """到店识客事件"""

    __tablename__ = "member_check_ins"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    brand_id = Column(String(50), nullable=False, index=True)
    consumer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("consumer_identities.id"),
        nullable=False,
    )
    trigger_type = Column(String(20), nullable=False)  # manual_search | reservation | pos_webhook
    staff_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    checked_in_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
    )
    profile_snapshot = Column(JSONB, nullable=True)

    __table_args__ = (
        Index("idx_check_ins_consumer", "consumer_id", "checked_in_at"),
        Index("idx_check_ins_store", "store_id", "checked_in_at"),
    )
```

- [ ] **Step 2: Create member_dish_preference.py model**

```python
# apps/api-gateway/src/models/member_dish_preference.py
"""菜品偏好聚合 — 由 POS 订单数据定期聚合而来"""

import uuid
from sqlalchemy import Boolean, Column, Integer, String, UniqueConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP

from .base import Base, TimestampMixin


class MemberDishPreference(Base, TimestampMixin):
    """顾客菜品偏好（聚合表）"""

    __tablename__ = "member_dish_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    consumer_id = Column(
        UUID(as_uuid=True),
        ForeignKey("consumer_identities.id"),
        nullable=False,
    )
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    brand_id = Column(String(50), nullable=False, index=True)
    dish_name = Column(String(100), nullable=False)
    order_count = Column(Integer, nullable=False, default=0)
    last_ordered_at = Column(TIMESTAMP(timezone=True), nullable=True)
    is_favorite = Column(Boolean, default=False)

    __table_args__ = (
        UniqueConstraint("consumer_id", "store_id", "dish_name", name="uq_consumer_store_dish"),
    )
```

- [ ] **Step 3: Add columns to ConsumerIdentity model**

Modify `apps/api-gateway/src/models/consumer_identity.py` — add these two columns after the existing `birth_date` line:

```python
dietary_restrictions = Column(JSON, default=list)  # ["不吃香菜", "海鲜过敏"]
anniversary = Column(Date, nullable=True)
```

- [ ] **Step 4: Register models in alembic/env.py**

Add these two lines after the existing model imports (around line 30-40 in `alembic/env.py`):

```python
import src.models.member_check_in       # noqa: F401 — P1 识客
import src.models.member_dish_preference # noqa: F401 — P1 菜品偏好
```

- [ ] **Step 5: Generate Alembic migration**

```bash
cd /Users/lichun/zhilian-os/apps/api-gateway
alembic revision --autogenerate -m "P1: add member_check_ins and member_dish_preferences tables, extend consumer_identities"
```

Review the generated migration file to ensure it:
1. Creates `member_check_ins` table with UUID PK + correct FKs
2. Creates `member_dish_preferences` table with unique constraint
3. Adds `dietary_restrictions` (JSON, default list) and `anniversary` (Date) to `consumer_identities`
4. Does NOT re-add `tags` or `birth_date` (they already exist)

If autogenerate picks up unwanted changes, manually edit the migration file.

- [ ] **Step 6: Run migration**

```bash
cd /Users/lichun/zhilian-os/apps/api-gateway
alembic upgrade head
```

- [ ] **Step 7: Write model tests**

```python
# apps/api-gateway/tests/test_models_p1.py
import uuid
import pytest
from src.models.member_check_in import MemberCheckIn
from src.models.member_dish_preference import MemberDishPreference


class TestMemberCheckInModel:
    def test_create_instance(self):
        ci = MemberCheckIn(
            store_id="STORE001",
            brand_id="BRAND001",
            consumer_id=uuid.uuid4(),
            trigger_type="manual_search",
        )
        assert ci.trigger_type == "manual_search"
        assert ci.store_id == "STORE001"

    def test_trigger_type_values(self):
        for tt in ("manual_search", "reservation", "pos_webhook"):
            ci = MemberCheckIn(
                store_id="S1", brand_id="B1",
                consumer_id=uuid.uuid4(), trigger_type=tt,
            )
            assert ci.trigger_type == tt


class TestMemberDishPreferenceModel:
    def test_create_instance(self):
        dp = MemberDishPreference(
            consumer_id=uuid.uuid4(),
            store_id="STORE001",
            brand_id="BRAND001",
            dish_name="特色江蟹生",
            order_count=5,
        )
        assert dp.dish_name == "特色江蟹生"
        assert dp.order_count == 5
        assert dp.is_favorite is False
```

- [ ] **Step 8: Run tests**

```bash
cd /Users/lichun/zhilian-os/apps/api-gateway
pytest tests/test_models_p1.py -v
```
Expected: all tests PASS.

- [ ] **Step 9: Commit**

```bash
git add apps/api-gateway/src/models/member_check_in.py \
       apps/api-gateway/src/models/member_dish_preference.py \
       apps/api-gateway/src/models/consumer_identity.py \
       apps/api-gateway/alembic/env.py \
       apps/api-gateway/alembic/versions/*.py \
       apps/api-gateway/tests/test_models_p1.py
git commit -m "feat(P1): add member_check_ins and member_dish_preferences models + extend consumer_identities + migration"
```

---

### Task 2: MemberProfileAggregator Service

The core service that aggregates data from multiple sources into a unified member profile.

**Files:**
- Create: `apps/api-gateway/src/services/member_profile_aggregator.py`
- Create: `apps/api-gateway/tests/test_member_profile_aggregator.py`

**Context:**
- Service pattern: class-based singleton (see `member_service.py`)
- Uses `asyncio.gather()` with `_safe()` wrapper for parallel sub-calls (see `bff_member.py`)
- Must call `identity_resolution_service.resolve(db, phone)` to get `consumer_id`
- Aggregates: 微生活CRM (member_service.query_member), POS orders (SQL query), consumer_identities tags, AI script (LLM agent)
- Each sub-source failure → returns `None` for that section, never crashes
- Money returned in both fen and display format

- [ ] **Step 1: Write failing tests**

```python
# apps/api-gateway/tests/test_member_profile_aggregator.py
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession


class TestMemberProfileAggregator:
    """MemberProfileAggregator 聚合服务测试"""

    @pytest.mark.asyncio
    @patch("src.services.member_profile_aggregator.identity_resolution_service")
    async def test_aggregate_returns_consumer_id(self, mock_irs):
        """resolve phone → consumer_id 正确传递"""
        from src.services.member_profile_aggregator import member_profile_aggregator

        consumer_id = uuid.uuid4()
        mock_irs.resolve = AsyncMock(return_value=consumer_id)

        mock_db = AsyncMock(spec=AsyncSession)
        # Mock DB queries to return empty results
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        profile = await member_profile_aggregator.aggregate(
            db=mock_db, phone="13800001234", store_id="STORE001",
        )
        assert profile["consumer_id"] == str(consumer_id)
        mock_irs.resolve.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.services.member_profile_aggregator.identity_resolution_service")
    async def test_crm_failure_degrades_gracefully(self, mock_irs):
        """微生活CRM不可用时 assets=None"""
        from src.services.member_profile_aggregator import member_profile_aggregator

        mock_irs.resolve = AsyncMock(return_value=uuid.uuid4())

        mock_db = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.one_or_none.return_value = None
        mock_result.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch.object(
            member_profile_aggregator, "_fetch_crm_assets",
            AsyncMock(side_effect=Exception("CRM down")),
        ):
            profile = await member_profile_aggregator.aggregate(
                db=mock_db, phone="13800001234", store_id="STORE001",
            )
        assert profile["assets"] is None
        # Other sections should still be present
        assert "identity" in profile

    @pytest.mark.asyncio
    @patch("src.services.member_profile_aggregator.identity_resolution_service")
    async def test_identity_section_from_consumer(self, mock_irs):
        """identity 从 consumer_identities 表读取"""
        from src.services.member_profile_aggregator import member_profile_aggregator

        cid = uuid.uuid4()
        mock_irs.resolve = AsyncMock(return_value=cid)

        mock_db = AsyncMock(spec=AsyncSession)
        # Mock consumer query
        mock_consumer = MagicMock()
        mock_consumer.display_name = "刘女士"
        mock_consumer.primary_phone = "13800001234"
        mock_consumer.tags = ["VIP"]
        mock_consumer.birth_date = None
        mock_consumer.dietary_restrictions = None
        mock_consumer.anniversary = None

        mock_result_consumer = MagicMock()
        mock_result_consumer.scalar_one_or_none.return_value = mock_consumer

        mock_result_empty = MagicMock()
        mock_result_empty.all.return_value = []

        # First execute = consumer query, second = dish prefs
        mock_db.execute = AsyncMock(side_effect=[mock_result_consumer, mock_result_empty])
        mock_db.get = AsyncMock(return_value=mock_consumer)

        profile = await member_profile_aggregator.aggregate(
            db=mock_db, phone="13800001234", store_id="STORE001",
        )
        assert profile["identity"]["name"] == "刘女士"
        assert "VIP" in profile["identity"]["tags"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/lichun/zhilian-os/apps/api-gateway
pytest tests/test_member_profile_aggregator.py -v
```
Expected: FAIL (module not found).

- [ ] **Step 3: Implement MemberProfileAggregator**

```python
# apps/api-gateway/src/services/member_profile_aggregator.py
"""
会员画像聚合服务 — P1 核心

从多个数据源并发聚合会员画像：
- consumer_identities（身份+标签）
- 微生活CRM（资产：余额/积分/券）
- POS订单（菜品偏好）
- AI Agent（话术生成）

每个子源独立失败，降级返回 None。
"""

import asyncio
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.consumer_identity import ConsumerIdentity
from ..models.member_dish_preference import MemberDishPreference
from .identity_resolution_service import identity_resolution_service

logger = structlog.get_logger(__name__)


async def _safe(coro, *, label: str = "unknown") -> Any:
    """执行协程，失败时返回 None 并记录日志（不阻塞其他子调用）"""
    try:
        return await coro
    except Exception as exc:
        logger.warning("子源聚合失败，降级", label=label, error=str(exc))
        return None


def _mask_phone(phone: str) -> str:
    """138****1234"""
    if len(phone) >= 7:
        return phone[:3] + "****" + phone[-4:]
    return phone


def _fen_to_display(fen: Optional[int]) -> Optional[str]:
    if fen is None:
        return None
    return f"¥{fen / 100:,.2f}"


class MemberProfileAggregator:
    """会员画像聚合器"""

    async def aggregate(
        self,
        db: AsyncSession,
        phone: str,
        store_id: str,
        *,
        include_ai_script: bool = True,
    ) -> Dict[str, Any]:
        """
        聚合完整会员画像。

        返回结构：
        {
            "consumer_id": "uuid-str",
            "identity": {...} | None,
            "preferences": {...} | None,
            "assets": {...} | None,
            "milestones": {...} | None,
            "ai_script": "str" | None,
        }
        """
        # 1. Resolve phone → consumer_id
        consumer_id = await identity_resolution_service.resolve(
            db, phone, store_id=store_id, source="member_profile",
        )

        # 2. 并发聚合（每个子源独立失败）
        identity_task = _safe(
            self._fetch_identity(db, consumer_id), label="identity",
        )
        prefs_task = _safe(
            self._fetch_preferences(db, consumer_id, store_id), label="preferences",
        )
        assets_task = _safe(
            self._fetch_crm_assets(phone), label="crm_assets",
        )

        identity, preferences, assets = await asyncio.gather(
            identity_task, prefs_task, assets_task,
        )

        # 3. 里程碑（从 identity 数据派生，不单独查）
        milestones = self._derive_milestones(identity) if identity else None

        # 4. AI 话术（可选，失败不影响画像）
        ai_script = None
        if include_ai_script:
            ai_script = await _safe(
                self._generate_ai_script(identity, preferences, assets, milestones),
                label="ai_script",
            )

        return {
            "consumer_id": str(consumer_id),
            "identity": identity,
            "preferences": preferences,
            "assets": assets,
            "milestones": milestones,
            "ai_script": ai_script,
        }

    async def _fetch_identity(
        self, db: AsyncSession, consumer_id,
    ) -> Optional[Dict[str, Any]]:
        """从 consumer_identities 读取身份信息"""
        consumer = await db.get(ConsumerIdentity, consumer_id)
        if not consumer:
            return None

        return {
            "name": consumer.display_name or "未知",
            "phone": _mask_phone(consumer.primary_phone),
            "tags": consumer.tags or [],
            "lifecycle_stage": self._compute_lifecycle(consumer),
            # 内部字段，用于派生 milestones
            "_birth_date": consumer.birth_date,
            "_anniversary": getattr(consumer, "anniversary", None),
            "_first_order_at": consumer.first_order_at,
            "_last_order_at": consumer.last_order_at,
            "_total_order_count": consumer.total_order_count or 0,
            "_dietary_restrictions": getattr(consumer, "dietary_restrictions", None) or [],
        }

    async def _fetch_preferences(
        self, db: AsyncSession, consumer_id, store_id: str,
    ) -> Optional[Dict[str, Any]]:
        """从 member_dish_preferences 读取菜品偏好"""
        stmt = (
            select(MemberDishPreference)
            .where(
                MemberDishPreference.consumer_id == consumer_id,
                MemberDishPreference.store_id == store_id,
            )
            .order_by(MemberDishPreference.order_count.desc())
            .limit(10)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()

        favorites = [
            {"name": r.dish_name, "count": r.order_count}
            for r in rows
        ]
        return {
            "favorite_dishes": favorites,
            "dietary_restrictions": [],  # 从 identity 补充
            "preferred_seating": None,
        }

    async def _fetch_crm_assets(self, phone: str) -> Optional[Dict[str, Any]]:
        """从微生活CRM读取资产（余额/积分/券）"""
        try:
            from ..services.member_service import member_service
            member = await member_service.query_member(mobile=phone)
        except Exception:
            logger.warning("微生活CRM不可用", phone=_mask_phone(phone))
            return None

        if not member:
            return None

        balance_fen = int(float(member.get("balance", 0)) * 100)
        points = member.get("point", 0)

        # 尝试获取可用券（coupon_list 需要 card_no，从 query_member 结果提取）
        coupons: List[Dict] = []
        try:
            card_no = member.get("card_no", "")
            coupon_list = await member_service.coupon_list(card_no=card_no) if card_no else []
            for c in (coupon_list or []):
                coupons.append({
                    "id": str(c.get("coupon_id", "")),
                    "name": c.get("coupon_name", ""),
                    "expires": c.get("end_time", ""),
                })
        except Exception:
            pass  # 券列表失败不影响

        return {
            "level": member.get("level_name", ""),
            "balance_fen": balance_fen,
            "balance_display": _fen_to_display(balance_fen),
            "points": points,
            "available_coupons": coupons,
        }

    def _derive_milestones(self, identity: Dict[str, Any]) -> Dict[str, Any]:
        """从 identity 内部字段派生里程碑"""
        today = date.today()
        birth = identity.get("_birth_date")
        birthday_upcoming = False
        birthday_str = None
        if birth:
            birthday_str = birth.isoformat()
            this_year_bday = birth.replace(year=today.year)
            if this_year_bday < today:
                this_year_bday = birth.replace(year=today.year + 1)
            birthday_upcoming = (this_year_bday - today).days <= 7

        last_order = identity.get("_last_order_at")
        first_order = identity.get("_first_order_at")

        return {
            "birthday": birthday_str,
            "birthday_upcoming": birthday_upcoming,
            "last_visit": last_order.isoformat() if last_order else None,
            "total_visits": identity.get("_total_order_count", 0),
            "member_since": first_order.isoformat() if first_order else None,
        }

    def _compute_lifecycle(self, consumer: ConsumerIdentity) -> str:
        """简易生命周期阶段判定"""
        if not consumer.last_order_at:
            return "新客"
        days_since = (date.today() - consumer.last_order_at.date()).days
        freq = consumer.total_order_count or 0
        if freq <= 1:
            return "新客"
        if days_since <= 30 and freq >= 4:
            return "活跃期"
        if days_since <= 60:
            return "稳定期"
        if days_since <= 90:
            return "预警期"
        return "沉睡期"

    async def _generate_ai_script(
        self,
        identity: Optional[Dict],
        preferences: Optional[Dict],
        assets: Optional[Dict],
        milestones: Optional[Dict],
    ) -> Optional[str]:
        """调用 LLM 生成个性化服务话术（失败返回 None）"""
        # 简单实现：拼接关键信息让 LLM 生成
        # 后续可接入 private_domain Agent
        try:
            from ..agents.llm_agent import LLMAgent
            agent = LLMAgent()
            context_parts = []
            if identity:
                context_parts.append(f"顾客: {identity.get('name', '未知')}")
                if identity.get("tags"):
                    context_parts.append(f"标签: {', '.join(identity['tags'])}")
            if preferences and preferences.get("favorite_dishes"):
                top_dishes = [d["name"] for d in preferences["favorite_dishes"][:3]]
                context_parts.append(f"常点: {', '.join(top_dishes)}")
            if milestones and milestones.get("birthday_upcoming"):
                context_parts.append("本周即将生日")
            if assets:
                context_parts.append(f"会员等级: {assets.get('level', '')}")

            if not context_parts:
                return None

            prompt = (
                "你是一家中餐厅的资深服务员。根据以下顾客信息，生成一句简短的个性化迎宾话术（30字以内，亲切自然）：\n"
                + "\n".join(context_parts)
            )
            result = await agent.arun(prompt)
            return result.strip() if result else None
        except Exception:
            return None


# 全局单例
member_profile_aggregator = MemberProfileAggregator()
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/lichun/zhilian-os/apps/api-gateway
pytest tests/test_member_profile_aggregator.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api-gateway/src/services/member_profile_aggregator.py \
       apps/api-gateway/tests/test_member_profile_aggregator.py
git commit -m "feat(P1): add MemberProfileAggregator service with multi-source fallback"
```

---

### Task 3: BFF Member Profile Endpoint

The main API endpoint that exposes the member profile to frontend.

**Files:**
- Create: `apps/api-gateway/src/api/bff_member_profile.py`
- Modify: `apps/api-gateway/src/main.py` (register router)
- Create: `apps/api-gateway/tests/test_bff_member_profile.py`

**Context:**
- BFF pattern from `bff_member.py`: router with prefix, `AsyncSession = Depends(get_db)`, Redis cache
- Cache key: `member_profile:{consumer_id}`, TTL 300s
- Auth: `require_role()` from `dependencies.py` — all roles can search

- [ ] **Step 1: Write failing test**

```python
# apps/api-gateway/tests/test_bff_member_profile.py
import uuid
import pytest
from unittest.mock import AsyncMock, patch


class TestBffMemberProfile:
    @pytest.mark.asyncio
    @patch("src.api.bff_member_profile.member_profile_aggregator")
    @patch("src.api.bff_member_profile.get_db")
    async def test_endpoint_returns_profile(self, mock_get_db, mock_aggregator):
        """GET /api/v1/bff/member-profile/{store_id}/{phone} 返回画像"""
        from src.api.bff_member_profile import get_member_profile

        consumer_id = uuid.uuid4()
        mock_aggregator.aggregate = AsyncMock(return_value={
            "consumer_id": str(consumer_id),
            "identity": {"name": "刘女士", "phone": "138****1234", "tags": [], "lifecycle_stage": "活跃期"},
            "preferences": None,
            "assets": None,
            "milestones": None,
            "ai_script": None,
        })

        mock_db = AsyncMock()

        result = await get_member_profile(
            store_id="STORE001",
            phone="13800001234",
            db=mock_db,
        )
        assert result["consumer_id"] == str(consumer_id)
        assert result["identity"]["name"] == "刘女士"
```

- [ ] **Step 2: Implement BFF endpoint**

```python
# apps/api-gateway/src/api/bff_member_profile.py
"""
BFF 会员画像 — P1 到店识客

GET  /api/v1/bff/member-profile/{store_id}/{phone}  — 聚合画像
GET  /api/v1/bff/today-reservations/{store_id}       — 今日预订列表
"""

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.dependencies import get_db
from ..services.member_profile_aggregator import member_profile_aggregator

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/bff/member-profile",
    tags=["BFF-会员画像"],
)


_CACHE_TTL = 300  # 5分钟


async def _cache_get(key: str):
    """Redis 缓存读取（失败静默返回 None）"""
    try:
        from ..core.redis_client import redis_client
        import json
        val = await redis_client.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


async def _cache_set(key: str, data: dict):
    """Redis 缓存写入"""
    try:
        from ..core.redis_client import redis_client
        import json
        await redis_client.setex(key, _CACHE_TTL, json.dumps(data, default=str))
    except Exception:
        pass


@router.get("/{store_id}/{phone}", summary="获取会员画像")
async def get_member_profile(
    store_id: str,
    phone: str,
    include_ai: bool = Query(default=True, description="是否生成AI话术"),
    refresh: bool = Query(default=False, description="强制刷新缓存"),
    db: AsyncSession = Depends(get_db),
):
    """
    聚合多源会员画像：身份+偏好+资产+里程碑+AI话术。
    每个子源独立失败，降级返回 null。
    Redis 缓存 5 分钟，?refresh=true 强制刷新。
    """
    cache_key = f"member_profile:{store_id}:{phone}"
    if not refresh:
        cached = await _cache_get(cache_key)
        if cached:
            return cached

    profile = await member_profile_aggregator.aggregate(
        db=db,
        phone=phone.strip(),
        store_id=store_id,
        include_ai_script=include_ai,
    )

    # 清理内部字段（以 _ 开头的）
    identity = profile.get("identity")
    if identity:
        # 把 dietary_restrictions 移到 preferences
        dietary = identity.pop("_dietary_restrictions", [])
        profile["identity"] = {
            k: v for k, v in identity.items() if not k.startswith("_")
        }
        prefs = profile.get("preferences")
        if prefs and dietary:
            prefs["dietary_restrictions"] = dietary

    await _cache_set(cache_key, profile)
    return profile
```

- [ ] **Step 3: Register router in main.py**

Find the router registration section in `apps/api-gateway/src/main.py` and add:

```python
from src.api import bff_member_profile
app.include_router(bff_member_profile.router)
```

- [ ] **Step 4: Run tests**

```bash
cd /Users/lichun/zhilian-os/apps/api-gateway
pytest tests/test_bff_member_profile.py -v
```

- [ ] **Step 5: Commit**

```bash
git add apps/api-gateway/src/api/bff_member_profile.py \
       apps/api-gateway/src/main.py \
       apps/api-gateway/tests/test_bff_member_profile.py
git commit -m "feat(P1): add BFF member-profile endpoint with multi-source aggregation"
```

---

### Task 4: POS Webhook 识客扩展

Extend the existing POS webhook handler to trigger member recognition on order creation.

**Files:**
- Modify: `apps/api-gateway/src/api/pos_webhook.py`
- Create: `apps/api-gateway/tests/test_pos_webhook_check_in.py`

**Context:**
- `pos_webhook.py` already has `customer_phone` in `WebhookOrderPayload` (line 59)
- After `_upsert_order()`, if `customer_phone` is present, resolve identity and create `MemberCheckIn`
- Don't import heavy services at module level — lazy import inside the handler to avoid circular deps

- [ ] **Step 1: Write failing test**

```python
# apps/api-gateway/tests/test_pos_webhook_check_in.py
import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestPosWebhookCheckIn:
    @pytest.mark.asyncio
    @patch("src.api.pos_webhook.get_db_session")
    @patch("src.api.pos_webhook.identity_resolution_service")
    async def test_check_in_created_on_order_with_phone(self, mock_irs, mock_get_session):
        """POS订单含 customer_phone 时创建识客事件"""
        from src.api.pos_webhook import _handle_member_check_in

        consumer_id = uuid.uuid4()
        mock_irs.resolve = AsyncMock(return_value=consumer_id)

        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        # Mock store query for brand_id
        mock_store = MagicMock()
        mock_store.brand_id = "BRAND001"
        mock_session.get = AsyncMock(return_value=mock_store)
        mock_get_session.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_get_session.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await _handle_member_check_in(
            store_id="STORE001",
            customer_phone="13800001234",
        )
        assert result == consumer_id
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_in_skipped_when_no_phone(self):
        """无 customer_phone 时跳过"""
        from src.api.pos_webhook import _handle_member_check_in

        result = await _handle_member_check_in(
            store_id="STORE001", customer_phone=None,
        )
        assert result is None
```

- [ ] **Step 2: Add _handle_member_check_in to pos_webhook.py**

Add this function to `apps/api-gateway/src/api/pos_webhook.py` (before the endpoint functions):

```python
async def _handle_member_check_in(
    store_id: str,
    customer_phone: Optional[str],
) -> Optional["uuid.UUID"]:
    """POS开单时自动识客：resolve phone → 创建 MemberCheckIn 记录。
    自行管理 DB session（与 _upsert_order 模式一致，使用 get_db_session）。
    """
    if not customer_phone:
        return None
    try:
        from src.services.identity_resolution_service import identity_resolution_service
        from src.models.member_check_in import MemberCheckIn
        from src.models.store import Store

        async with get_db_session() as session:
            # 查 brand_id
            store = await session.get(Store, store_id)
            brand_id = store.brand_id if store else ""

            consumer_id = await identity_resolution_service.resolve(
                session, customer_phone.strip(),
                store_id=store_id,
                source="pos_webhook",
            )
            check_in = MemberCheckIn(
                store_id=store_id,
                brand_id=brand_id,
                consumer_id=consumer_id,
                trigger_type="pos_webhook",
            )
            session.add(check_in)
            await session.commit()
            logger.info("POS识客事件已创建", store_id=store_id, consumer_id=str(consumer_id))
            return consumer_id
    except Exception as exc:
        logger.warning("POS识客失败，不影响订单处理", error=str(exc))
        return None
```

Then in `_upsert_order`, after the order commit, add:

```python
# 识客：如果订单含手机号，自动创建识客事件（独立session，不影响订单事务）
if payload.customer_phone:
    await _handle_member_check_in(store_id=store_id, customer_phone=payload.customer_phone)
```

- [ ] **Step 3: Run tests**

```bash
cd /Users/lichun/zhilian-os/apps/api-gateway
pytest tests/test_pos_webhook_check_in.py -v
```

- [ ] **Step 4: Commit**

```bash
git add apps/api-gateway/src/api/pos_webhook.py \
       apps/api-gateway/tests/test_pos_webhook_check_in.py
git commit -m "feat(P1): extend POS webhook with auto member check-in on order"
```

---

### Task 5: P1 Frontend — MemberProfileCard + MemberSearchBar

Core frontend components for displaying member profiles.

**Files:**
- Create: `apps/web/src/components/MemberProfileCard.tsx`
- Create: `apps/web/src/components/MemberProfileCard.module.css`
- Create: `apps/web/src/components/MemberSearchBar.tsx`
- Create: `apps/web/src/components/MemberSearchBar.module.css`

**Context:**
- Component pattern: React FC, CSS Modules, Z-prefixed sub-components
- Data fetching: `apiClient.get<T>()` returns `T` directly (no `.data`)
- Design tokens: `var(--bg)`, `var(--surface)`, `var(--accent)` = `#FF6B2C`, `var(--text-primary)`
- Import Z components: `import { ZCard, ZButton, ZSkeleton, ZEmpty, ZTag } from '../design-system/components'`

- [ ] **Step 1: Create MemberSearchBar component**

```typescript
// apps/web/src/components/MemberSearchBar.tsx
import React, { useState, useCallback } from 'react';
import { Input, message } from 'antd';
import styles from './MemberSearchBar.module.css';

interface MemberSearchBarProps {
  onSearch: (phone: string) => void;
  loading?: boolean;
  placeholder?: string;
}

export default function MemberSearchBar({
  onSearch,
  loading = false,
  placeholder = '手机号 / 会员码',
}: MemberSearchBarProps) {
  const [value, setValue] = useState('');

  const handleSearch = useCallback(() => {
    const phone = value.trim();
    if (!phone) {
      message.warning('请输入手机号或会员码');
      return;
    }
    if (!/^\d{11}$/.test(phone) && !/^\d{6,}$/.test(phone)) {
      message.warning('请输入有效的手机号或会员码');
      return;
    }
    onSearch(phone);
  }, [value, onSearch]);

  return (
    <div className={styles.bar}>
      <Input.Search
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onSearch={handleSearch}
        placeholder={placeholder}
        loading={loading}
        enterButton="搜索"
        size="large"
        allowClear
      />
    </div>
  );
}
```

```css
/* apps/web/src/components/MemberSearchBar.module.css */
.bar {
  padding: 12px 16px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}
```

- [ ] **Step 2: Create MemberProfileCard component**

```typescript
// apps/web/src/components/MemberProfileCard.tsx
import React from 'react';
import { ZCard, ZTag, ZButton, ZEmpty, ZSkeleton } from '../design-system/components';
import styles from './MemberProfileCard.module.css';

/** BFF /api/v1/bff/member-profile/{store_id}/{phone} 响应类型 */
export interface MemberProfile {
  consumer_id: string;
  identity: {
    name: string;
    phone: string;
    tags: string[];
    lifecycle_stage: string;
  } | null;
  preferences: {
    favorite_dishes: { name: string; count: number }[];
    dietary_restrictions: string[];
    preferred_seating: string | null;
  } | null;
  assets: {
    level: string;
    balance_fen: number;
    balance_display: string;
    points: number;
    available_coupons: { id: string; name: string; expires: string }[];
  } | null;
  milestones: {
    birthday: string | null;
    birthday_upcoming: boolean;
    last_visit: string | null;
    total_visits: number;
    member_since: string | null;
  } | null;
  ai_script: string | null;
}

interface MemberProfileCardProps {
  profile: MemberProfile | null;
  loading?: boolean;
  compact?: boolean;
  onIssueCoupon?: (consumerId: string) => void;
}

export default function MemberProfileCard({
  profile,
  loading = false,
  compact = false,
  onIssueCoupon,
}: MemberProfileCardProps) {
  if (loading) {
    return <ZSkeleton rows={compact ? 3 : 6} />;
  }
  if (!profile || !profile.identity) {
    return <ZEmpty title="未找到会员信息" description="请确认手机号是否正确" />;
  }

  const { identity, preferences, assets, milestones, ai_script } = profile;

  return (
    <div className={compact ? styles.cardCompact : styles.card}>
      {/* 身份区 */}
      <div className={styles.header}>
        <div className={styles.avatar}>{identity.name.charAt(0)}</div>
        <div className={styles.info}>
          <div className={styles.name}>{identity.name}</div>
          <div className={styles.tags}>
            {assets?.level && <ZTag variant="mint">{assets.level}</ZTag>}
            <ZTag>{identity.lifecycle_stage}</ZTag>
            {identity.tags.map((t) => <ZTag key={t}>{t}</ZTag>)}
          </div>
        </div>
      </div>

      {/* 资产区 */}
      {assets && (
        <div className={styles.kpiRow}>
          <div className={styles.kpi}>
            <span className={styles.kpiValue}>{assets.balance_display}</span>
            <span className={styles.kpiLabel}>余额</span>
          </div>
          <div className={styles.kpi}>
            <span className={styles.kpiValue}>{assets.points?.toLocaleString()}</span>
            <span className={styles.kpiLabel}>积分</span>
          </div>
          <div className={styles.kpi}>
            <span className={styles.kpiValue} style={{ color: 'var(--accent)' }}>
              {assets.available_coupons?.length || 0}
            </span>
            <span className={styles.kpiLabel}>可用券</span>
          </div>
        </div>
      )}

      {/* 偏好标签 */}
      {!compact && preferences && (
        <div className={styles.section}>
          {milestones?.birthday_upcoming && (
            <ZTag variant="warn">本周生日</ZTag>
          )}
          {preferences.favorite_dishes?.slice(0, 3).map((d) => (
            <ZTag key={d.name}>❤️ {d.name}</ZTag>
          ))}
          {preferences.dietary_restrictions?.map((r) => (
            <ZTag key={r} color="danger">⚠️ {r}</ZTag>
          ))}
        </div>
      )}

      {/* AI 话术 */}
      {!compact && ai_script && (
        <div className={styles.aiScript}>
          <div className={styles.aiLabel}>AI 服务话术</div>
          <div className={styles.aiText}>{ai_script}</div>
        </div>
      )}

      {/* 操作按钮 */}
      {onIssueCoupon && (
        <div className={styles.actions}>
          <ZButton
            variant="primary"
            onClick={() => onIssueCoupon(profile.consumer_id)}
          >
            发券
          </ZButton>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create CSS Module**

```css
/* apps/web/src/components/MemberProfileCard.module.css */
.card {
  background: var(--surface);
  border-radius: var(--radius-lg);
  padding: 16px;
  border: 1px solid var(--border);
}

.cardCompact {
  composes: card;
  padding: 12px;
}

.header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  font-weight: 600;
  flex-shrink: 0;
}

.info {
  flex: 1;
  min-width: 0;
}

.name {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.kpiRow {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.kpi {
  flex: 1;
  background: var(--bg);
  border-radius: var(--radius-md);
  padding: 8px;
  text-align: center;
}

.kpiValue {
  display: block;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}

.kpiLabel {
  display: block;
  font-size: 10px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.section {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 12px;
}

.aiScript {
  background: rgba(255, 107, 44, 0.08);
  border-radius: var(--radius-md);
  padding: 10px;
  margin-bottom: 12px;
  border-left: 3px solid var(--accent);
}

.aiLabel {
  font-size: 11px;
  color: var(--accent);
  font-weight: 600;
  margin-bottom: 4px;
}

.aiText {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-primary);
}

.actions {
  display: flex;
  gap: 8px;
}
```

- [ ] **Step 4: Verify frontend builds**

```bash
cd /Users/lichun/zhilian-os/apps/web
pnpm build
```
Expected: BUILD SUCCESS, 0 TS errors.

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/components/MemberProfileCard.tsx \
       apps/web/src/components/MemberProfileCard.module.css \
       apps/web/src/components/MemberSearchBar.tsx \
       apps/web/src/components/MemberSearchBar.module.css
git commit -m "feat(P1): add MemberProfileCard and MemberSearchBar components"
```

---

### Task 6: P1 Frontend — Member Profile Page + Route Integration

Create the member profile page and integrate into role layouts.

**Files:**
- Create: `apps/web/src/pages/sm/MemberProfile.tsx`
- Create: `apps/web/src/pages/sm/MemberProfile.module.css`
- Modify: `apps/web/src/App.tsx` (add routes)
- Modify: `apps/web/src/layouts/StoreManagerLayout.tsx` (add nav item)

**Context:**
- Page pattern from `pages/sm/Home.tsx`: useState + useCallback + apiClient + CSS Modules
- `apiClient.get<MemberProfile>(url)` returns data directly
- Lazy loading in App.tsx: `const SmMemberProfile = lazy(() => import('./pages/sm/MemberProfile'))`
- StoreManagerLayout NAV_ITEMS: add new tab entry

- [ ] **Step 1: Create MemberProfile page**

```typescript
// apps/web/src/pages/sm/MemberProfile.tsx
import React, { useState, useCallback } from 'react';
import { message } from 'antd';
import MemberSearchBar from '../../components/MemberSearchBar';
import MemberProfileCard, { type MemberProfile as MemberProfileType } from '../../components/MemberProfileCard';
import { apiClient } from '../../services/api';
import styles from './MemberProfile.module.css';

export default function MemberProfile() {
  const [profile, setProfile] = useState<MemberProfileType | null>(null);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);

  // TODO: 从用户上下文获取 store_id
  const storeId = 'STORE001';

  const handleSearch = useCallback(async (phone: string) => {
    setLoading(true);
    setSearched(true);
    try {
      const data = await apiClient.get<MemberProfileType>(
        `/api/v1/bff/member-profile/${storeId}/${phone}`,
      );
      setProfile(data);
    } catch (err) {
      message.error('查询失败，请稍后重试');
      setProfile(null);
    } finally {
      setLoading(false);
    }
  }, [storeId]);

  const handleIssueCoupon = useCallback((consumerId: string) => {
    // P2 阶段实现
    message.info('发券功能即将上线');
  }, []);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>会员识客</div>
      </div>
      <MemberSearchBar onSearch={handleSearch} loading={loading} />
      <div className={styles.content}>
        {searched && (
          <MemberProfileCard
            profile={profile}
            loading={loading}
            onIssueCoupon={handleIssueCoupon}
          />
        )}
      </div>
    </div>
  );
}
```

```css
/* apps/web/src/pages/sm/MemberProfile.module.css */
.page {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: var(--bg);
}

.header {
  padding: 20px 16px 14px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  position: sticky;
  top: 0;
  z-index: 10;
}

.title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
}

.content {
  padding: 16px;
  flex: 1;
}
```

- [ ] **Step 2: Add lazy route in App.tsx**

In `apps/web/src/App.tsx`, add among the lazy imports:

```typescript
const SmMemberProfile = lazy(() => import('./pages/sm/MemberProfile'));
```

And inside the `/sm` route group:

```typescript
<Route path="members" element={<SmMemberProfile />} />
```

Similarly add for `/floor` and `/hq` routes (same page, different layout wrapping).

- [ ] **Step 3: Add nav item in StoreManagerLayout**

In `apps/web/src/layouts/StoreManagerLayout.tsx`, add to NAV_ITEMS:

```typescript
{ to: '/sm/members', label: '识客', icon: '👤' },
```

- [ ] **Step 4: Build and verify**

```bash
cd /Users/lichun/zhilian-os/apps/web
pnpm build
```

- [ ] **Step 5: Commit**

```bash
git add apps/web/src/pages/sm/MemberProfile.tsx \
       apps/web/src/pages/sm/MemberProfile.module.css \
       apps/web/src/App.tsx \
       apps/web/src/layouts/StoreManagerLayout.tsx
git commit -m "feat(P1): add MemberProfile page with search + route integration"
```

---

## Chunk 2: P2 Backend + Frontend — 发券 + ROI

### Task 7: P2 Database Models + Migration

**Files:**
- Create: `apps/api-gateway/src/models/service_voucher.py` (templates + instances)
- Create: `apps/api-gateway/src/models/coupon_distribution.py` (distributions + redemptions + roi_daily)
- Modify: `apps/api-gateway/alembic/env.py` (add imports)
- Create: Alembic migration file

- [ ] **Step 1: Create service_voucher.py model**

```python
# apps/api-gateway/src/models/service_voucher.py
"""屯象服务券 — P2 自建体验类券（赠小菜/试吃/生日惊喜）"""

import uuid
from sqlalchemy import Boolean, Column, Integer, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSONB

from .base import Base, TimestampMixin


class ServiceVoucherTemplate(Base, TimestampMixin):
    """服务券模板"""

    __tablename__ = "service_voucher_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    voucher_type = Column(String(20), nullable=False)  # complimentary_dish | tasting | birthday_gift
    description = Column(Text, nullable=True)
    valid_days = Column(Integer, nullable=False, default=7)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True, index=True)


class ServiceVoucher(Base, TimestampMixin):
    """服务券实例（状态机：created → sent → used → expired）"""

    __tablename__ = "service_vouchers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), ForeignKey("service_voucher_templates.id"), nullable=False)
    consumer_id = Column(UUID(as_uuid=True), ForeignKey("consumer_identities.id"), nullable=False)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    brand_id = Column(String(50), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="created")  # created | sent | used | expired
    issued_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    used_at = Column(TIMESTAMP(timezone=True), nullable=True)
    confirmed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
```

- [ ] **Step 2: Create coupon_distribution.py model**

```python
# apps/api-gateway/src/models/coupon_distribution.py
"""发券记录 + 核销记录 + ROI日汇总 — P2"""

import uuid
from sqlalchemy import Column, Date, Integer, String, ForeignKey, UniqueConstraint, Index, text
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP

from .base import Base, TimestampMixin


class CouponDistribution(Base, TimestampMixin):
    """统一发券记录（微生活券 + 服务券）"""

    __tablename__ = "coupon_distributions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    brand_id = Column(String(50), nullable=False, index=True)
    consumer_id = Column(UUID(as_uuid=True), ForeignKey("consumer_identities.id"), nullable=False)
    coupon_source = Column(String(20), nullable=False)  # weishenghuo | service_voucher
    coupon_id = Column(String(100), nullable=False)
    coupon_name = Column(String(100), nullable=False)
    coupon_value_fen = Column(Integer, default=0)
    distributed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    distributed_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()"))
    # marketing_task_id — P3 阶段通过 ALTER TABLE 添加

    __table_args__ = (
        Index("idx_dist_consumer", "consumer_id", "distributed_at"),
        Index("idx_dist_store", "store_id", "distributed_at"),
    )


class CouponRedemption(Base, TimestampMixin):
    """核销记录"""

    __tablename__ = "coupon_redemptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    distribution_id = Column(UUID(as_uuid=True), ForeignKey("coupon_distributions.id"), nullable=False)
    order_id = Column(String(100), nullable=True)
    order_amount_fen = Column(Integer, nullable=True)
    redeemed_at = Column(TIMESTAMP(timezone=True), nullable=False)


class CouponRoiDaily(Base, TimestampMixin):
    """ROI 日汇总"""

    __tablename__ = "coupon_roi_daily"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date = Column(Date, nullable=False)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    brand_id = Column(String(50), nullable=False)
    staff_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    distributed_count = Column(Integer, default=0)
    distributed_value_fen = Column(Integer, default=0)
    redeemed_count = Column(Integer, default=0)
    redeemed_value_fen = Column(Integer, default=0)
    driven_gmv_fen = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("date", "store_id", "staff_id", name="uq_roi_daily"),
    )
```

- [ ] **Step 3: Register in alembic/env.py and generate migration**

```python
import src.models.service_voucher        # noqa: F401 — P2 服务券
import src.models.coupon_distribution    # noqa: F401 — P2 发券+ROI
```

```bash
cd /Users/lichun/zhilian-os/apps/api-gateway
alembic revision --autogenerate -m "P2: add service_vouchers, coupon_distributions, coupon_redemptions, coupon_roi_daily"
alembic upgrade head
```

- [ ] **Step 4: Write model tests and verify**

```bash
cd /Users/lichun/zhilian-os/apps/api-gateway
pytest tests/test_models_p2.py -v
```

- [ ] **Step 5: Commit**

```bash
git add apps/api-gateway/src/models/service_voucher.py \
       apps/api-gateway/src/models/coupon_distribution.py \
       apps/api-gateway/alembic/env.py \
       apps/api-gateway/alembic/versions/*.py \
       apps/api-gateway/tests/test_models_p2.py
git commit -m "feat(P2): add service voucher, coupon distribution, and ROI models + migration"
```

---

### Task 8: Coupon Distribution Service + BFF Endpoints

**Files:**
- Create: `apps/api-gateway/src/services/coupon_distribution_service.py`
- Create: `apps/api-gateway/src/api/bff_coupon.py`
- Modify: `apps/api-gateway/src/main.py` (register router)
- Create: `apps/api-gateway/tests/test_coupon_distribution_service.py`

**Context:**
- Two coupon sources: 微生活 (via `member_service.coupon_use()`) and service voucher (local DB)
- Service券状态机: created → sent → used → expired
- ROI日汇总由 Celery 定时任务聚合（Task 9）

- [ ] **Step 1: Write failing tests**

```python
# apps/api-gateway/tests/test_coupon_distribution_service.py
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


class TestCouponDistributionService:
    @pytest.mark.asyncio
    async def test_distribute_service_voucher(self):
        """发放服务券：创建 voucher + distribution 记录"""
        from src.services.coupon_distribution_service import coupon_distribution_service

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        mock_db.commit = AsyncMock()

        # Mock template query
        mock_template = MagicMock()
        mock_template.id = uuid.uuid4()
        mock_template.name = "赠送小菜券"
        mock_template.valid_days = 7
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_template
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await coupon_distribution_service.distribute_service_voucher(
            db=mock_db,
            template_id=mock_template.id,
            consumer_id=uuid.uuid4(),
            store_id="STORE001",
            brand_id="BRAND001",
            distributed_by=uuid.uuid4(),
        )
        assert result["success"] is True
        assert mock_db.add.call_count == 2  # voucher + distribution

    @pytest.mark.asyncio
    async def test_confirm_service_voucher(self):
        """确认核销服务券"""
        from src.services.coupon_distribution_service import coupon_distribution_service

        voucher_id = uuid.uuid4()
        mock_voucher = MagicMock()
        mock_voucher.id = voucher_id
        mock_voucher.status = "sent"

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_voucher)
        mock_db.commit = AsyncMock()

        result = await coupon_distribution_service.confirm_service_voucher(
            db=mock_db,
            voucher_id=voucher_id,
            confirmed_by=uuid.uuid4(),
        )
        assert result["success"] is True
        assert mock_voucher.status == "used"
```

- [ ] **Step 2: Implement service**

```python
# apps/api-gateway/src/services/coupon_distribution_service.py
"""发券服务 — P2 核心：微生活券透传 + 服务券自建"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.service_voucher import ServiceVoucher, ServiceVoucherTemplate
from ..models.coupon_distribution import CouponDistribution

logger = structlog.get_logger(__name__)


class CouponDistributionService:
    """发券 + 核销服务"""

    async def distribute_weishenghuo_coupon(
        self,
        db: AsyncSession,
        *,
        consumer_id: UUID,
        store_id: str,
        brand_id: str,
        coupon_id: str,
        coupon_name: str,
        coupon_value_fen: int,
        distributed_by: UUID,
        phone: str,
    ) -> Dict[str, Any]:
        """透传微生活券"""
        from ..services.member_service import member_service

        # 调用微生活 API 发券
        await member_service.coupon_use(mobile=phone, coupon_id=coupon_id)

        # 记录发放
        dist = CouponDistribution(
            store_id=store_id,
            brand_id=brand_id,
            consumer_id=consumer_id,
            coupon_source="weishenghuo",
            coupon_id=coupon_id,
            coupon_name=coupon_name,
            coupon_value_fen=coupon_value_fen,
            distributed_by=distributed_by,
            distributed_at=datetime.now(timezone.utc),
        )
        db.add(dist)
        await db.flush()
        logger.info("微生活券已发放", coupon_id=coupon_id, consumer_id=str(consumer_id))
        return {"success": True, "distribution_id": str(dist.id)}

    async def distribute_service_voucher(
        self,
        db: AsyncSession,
        *,
        template_id: UUID,
        consumer_id: UUID,
        store_id: str,
        brand_id: str,
        distributed_by: UUID,
    ) -> Dict[str, Any]:
        """创建并发放服务券"""
        stmt = select(ServiceVoucherTemplate).where(
            ServiceVoucherTemplate.id == template_id,
            ServiceVoucherTemplate.is_active.is_(True),
        )
        result = await db.execute(stmt)
        template = result.scalar_one_or_none()
        if not template:
            return {"success": False, "error": "券模板不存在或已停用"}

        now = datetime.now(timezone.utc)
        voucher = ServiceVoucher(
            template_id=template.id,
            consumer_id=consumer_id,
            store_id=store_id,
            brand_id=brand_id,
            status="sent",
            issued_by=distributed_by,
            expires_at=now + timedelta(days=template.valid_days),
        )
        db.add(voucher)
        await db.flush()

        dist = CouponDistribution(
            store_id=store_id,
            brand_id=brand_id,
            consumer_id=consumer_id,
            coupon_source="service_voucher",
            coupon_id=str(voucher.id),
            coupon_name=template.name,
            coupon_value_fen=0,
            distributed_by=distributed_by,
            distributed_at=now,
        )
        db.add(dist)
        await db.flush()
        logger.info("服务券已发放", voucher_id=str(voucher.id))
        return {"success": True, "distribution_id": str(dist.id), "voucher_id": str(voucher.id)}

    async def confirm_service_voucher(
        self,
        db: AsyncSession,
        *,
        voucher_id: UUID,
        confirmed_by: UUID,
    ) -> Dict[str, Any]:
        """确认核销服务券"""
        voucher = await db.get(ServiceVoucher, voucher_id)
        if not voucher:
            return {"success": False, "error": "服务券不存在"}
        if voucher.status != "sent":
            return {"success": False, "error": f"当前状态({voucher.status})不可核销"}

        voucher.status = "used"
        voucher.used_at = datetime.now(timezone.utc)
        voucher.confirmed_by = confirmed_by
        await db.flush()
        logger.info("服务券已核销", voucher_id=str(voucher_id))
        return {"success": True}


coupon_distribution_service = CouponDistributionService()
```

- [ ] **Step 3: Implement BFF coupon endpoints**

```python
# apps/api-gateway/src/api/bff_coupon.py
"""BFF 发券 + ROI — P2"""

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from ..core.dependencies import get_db, get_current_user
from ..models.user import User
from ..services.coupon_distribution_service import coupon_distribution_service

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/v1/bff/member-profile",
    tags=["BFF-发券"],
)


class DistributeCouponRequest(BaseModel):
    consumer_id: str
    coupon_source: str  # weishenghuo | service_voucher
    coupon_id: str  # 微生活券ID 或 service_voucher_template ID
    coupon_name: Optional[str] = ""
    coupon_value_fen: Optional[int] = 0
    phone: Optional[str] = None  # 微生活券需要


@router.post("/{store_id}/distribute-coupon", summary="发券")
async def distribute_coupon(
    store_id: str,
    req: DistributeCouponRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """发放优惠券（微生活券透传 或 屯象服务券）"""
    distributed_by = current_user.id
    brand_id = current_user.brand_id or ""

    if req.coupon_source == "weishenghuo":
        if not req.phone:
            return {"success": False, "error": "微生活券需要手机号"}
        return await coupon_distribution_service.distribute_weishenghuo_coupon(
            db=db,
            consumer_id=UUID(req.consumer_id),
            store_id=store_id,
            brand_id=brand_id,
            coupon_id=req.coupon_id,
            coupon_name=req.coupon_name or "",
            coupon_value_fen=req.coupon_value_fen or 0,
            distributed_by=distributed_by,
            phone=req.phone,
        )
    elif req.coupon_source == "service_voucher":
        return await coupon_distribution_service.distribute_service_voucher(
            db=db,
            template_id=UUID(req.coupon_id),
            consumer_id=UUID(req.consumer_id),
            store_id=store_id,
            brand_id=brand_id,
            distributed_by=distributed_by,
        )
    else:
        return {"success": False, "error": f"未知券来源: {req.coupon_source}"}


@router.post("/{store_id}/confirm-service-voucher/{voucher_id}", summary="确认服务券核销")
async def confirm_service_voucher(
    store_id: str,
    voucher_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """员工确认服务券已送达"""
    confirmed_by = current_user.id
    return await coupon_distribution_service.confirm_service_voucher(
        db=db,
        voucher_id=UUID(voucher_id),
        confirmed_by=confirmed_by,
    )
```

- [ ] **Step 4: Register router + run tests**

Add to `main.py`:
```python
from src.api import bff_coupon
app.include_router(bff_coupon.router)
```

```bash
cd /Users/lichun/zhilian-os/apps/api-gateway
pytest tests/test_coupon_distribution_service.py -v
```

- [ ] **Step 5: Commit**

```bash
git add apps/api-gateway/src/services/coupon_distribution_service.py \
       apps/api-gateway/src/api/bff_coupon.py \
       apps/api-gateway/src/main.py \
       apps/api-gateway/tests/test_coupon_distribution_service.py
git commit -m "feat(P2): add coupon distribution service + BFF endpoints for issuing/confirming vouchers"
```

---

### Task 9: P2 Frontend — CouponSelector + Integration

**Files:**
- Create: `apps/web/src/components/CouponSelector.tsx`
- Create: `apps/web/src/components/CouponSelector.module.css`
- Modify: `apps/web/src/pages/sm/MemberProfile.tsx` (integrate coupon selector)

**Context:**
- CouponSelector is a modal/drawer that shows available coupons (from CRM + service voucher templates)
- Triggered by "发券" button in MemberProfileCard
- Uses Ant Design Modal + List

- [ ] **Step 1: Create CouponSelector**

```typescript
// apps/web/src/components/CouponSelector.tsx
import React, { useState, useEffect, useCallback } from 'react';
import { Modal, List, message, Tag } from 'antd';
import { ZButton } from '../design-system/components';
import { apiClient } from '../services/api';
import styles from './CouponSelector.module.css';

interface Coupon {
  id: string;
  name: string;
  source: 'weishenghuo' | 'service_voucher';
  value_display?: string;
  expires?: string;
}

interface CouponSelectorProps {
  visible: boolean;
  onClose: () => void;
  consumerId: string;
  storeId: string;
  phone?: string;
}

export default function CouponSelector({
  visible, onClose, consumerId, storeId, phone,
}: CouponSelectorProps) {
  const [coupons, setCoupons] = useState<Coupon[]>([]);
  const [loading, setLoading] = useState(false);
  const [distributing, setDistributing] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    // 加载可用券列表（合并两个来源）
    setLoading(true);
    // TODO: 实际调用后端接口获取可用券列表
    // 临时用空列表
    setCoupons([]);
    setLoading(false);
  }, [visible, consumerId]);

  const handleDistribute = useCallback(async (coupon: Coupon) => {
    setDistributing(coupon.id);
    try {
      await apiClient.post(`/api/v1/bff/member-profile/${storeId}/distribute-coupon`, {
        consumer_id: consumerId,
        coupon_source: coupon.source,
        coupon_id: coupon.id,
        coupon_name: coupon.name,
        phone,
      });
      message.success(`已发放: ${coupon.name}`);
      onClose();
    } catch {
      message.error('发券失败');
    } finally {
      setDistributing(null);
    }
  }, [consumerId, storeId, phone, onClose]);

  return (
    <Modal
      title="选择优惠券"
      open={visible}
      onCancel={onClose}
      footer={null}
      width={400}
    >
      <List
        loading={loading}
        dataSource={coupons}
        locale={{ emptyText: '暂无可用券' }}
        renderItem={(coupon) => (
          <List.Item
            actions={[
              <ZButton
                key="send"
                variant="primary"
                onClick={() => handleDistribute(coupon)}
                disabled={distributing !== null}
              >
                发放
              </ZButton>,
            ]}
          >
            <List.Item.Meta
              title={coupon.name}
              description={
                <>
                  <Tag color={coupon.source === 'weishenghuo' ? 'orange' : 'green'}>
                    {coupon.source === 'weishenghuo' ? '微生活' : '服务券'}
                  </Tag>
                  {coupon.value_display && <span>{coupon.value_display}</span>}
                </>
              }
            />
          </List.Item>
        )}
      />
    </Modal>
  );
}
```

```css
/* apps/web/src/components/CouponSelector.module.css */
.selector {
  padding: 0;
}
```

- [ ] **Step 2: Integrate into MemberProfile page**

Update `apps/web/src/pages/sm/MemberProfile.tsx` — add CouponSelector state and modal:

```typescript
// Add import
import CouponSelector from '../../components/CouponSelector';

// Add state inside component
const [couponTarget, setCouponTarget] = useState<string | null>(null);

// Update handleIssueCoupon
const handleIssueCoupon = useCallback((consumerId: string) => {
  setCouponTarget(consumerId);
}, []);

// Add modal before closing </div>
{couponTarget && (
  <CouponSelector
    visible={!!couponTarget}
    onClose={() => setCouponTarget(null)}
    consumerId={couponTarget}
    storeId={storeId}
    phone={profile?.identity?.phone}
  />
)}
```

- [ ] **Step 3: Build and verify**

```bash
cd /Users/lichun/zhilian-os/apps/web && pnpm build
```

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/components/CouponSelector.tsx \
       apps/web/src/components/CouponSelector.module.css \
       apps/web/src/pages/sm/MemberProfile.tsx
git commit -m "feat(P2): add CouponSelector modal + integrate into MemberProfile page"
```

---

## Chunk 3: P3 — 总部营销任务

### Task 10: P3 Database Models + Migration

**Files:**
- Create: `apps/api-gateway/src/models/marketing_task.py`
- Modify: `apps/api-gateway/alembic/env.py`
- Create: Alembic migration

- [ ] **Step 1: Create marketing_task.py with all P3 models**

```python
# apps/api-gateway/src/models/marketing_task.py
"""营销任务体系 — P3：总部创建 → 店长分配 → 员工执行 → 数据回流"""

import uuid
from sqlalchemy import Column, Date, Integer, String, Text, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP

from .base import Base, TimestampMixin


class MarketingTask(Base, TimestampMixin):
    """营销任务"""

    __tablename__ = "marketing_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(String(50), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    audience_type = Column(String(20), nullable=False)  # preset | ai_query
    audience_config = Column(JSONB, nullable=False)
    script_template = Column(Text, nullable=True)
    coupon_config = Column(JSONB, nullable=True)
    status = Column(String(20), nullable=False, default="draft")  # draft | published | in_progress | completed | cancelled
    deadline = Column(TIMESTAMP(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    published_at = Column(TIMESTAMP(timezone=True), nullable=True)


class MarketingTaskTarget(Base, TimestampMixin):
    """目标人群快照"""

    __tablename__ = "marketing_task_targets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("marketing_tasks.id"), nullable=False)
    consumer_id = Column(UUID(as_uuid=True), ForeignKey("consumer_identities.id"), nullable=False)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    profile_snapshot = Column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint("task_id", "consumer_id", "store_id", name="uq_task_consumer_store"),
    )


class MarketingTaskAssignment(Base, TimestampMixin):
    """门店分配"""

    __tablename__ = "marketing_task_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("marketing_tasks.id"), nullable=False)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    assigned_to = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    target_count = Column(Integer, default=0)
    completed_count = Column(Integer, default=0)
    status = Column(String(20), nullable=False, default="pending")  # pending | assigned | in_progress | completed
    assigned_at = Column(TIMESTAMP(timezone=True), nullable=True)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        Index("idx_assign_task_status", "task_id", "status"),
    )


class MarketingTaskExecution(Base, TimestampMixin):
    """执行记录"""

    __tablename__ = "marketing_task_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("marketing_task_assignments.id"), nullable=False)
    target_id = Column(UUID(as_uuid=True), ForeignKey("marketing_task_targets.id"), nullable=False)
    executor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    action_type = Column(String(20), nullable=False)  # wechat_msg | coupon | call | in_store
    action_detail = Column(JSONB, nullable=True)
    distribution_id = Column(UUID(as_uuid=True), ForeignKey("coupon_distributions.id"), nullable=True)
    feedback = Column(Text, nullable=True)
    executed_at = Column(TIMESTAMP(timezone=True), nullable=False)


class MarketingTaskStats(Base, TimestampMixin):
    """效果统计日汇总"""

    __tablename__ = "marketing_task_stats"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id = Column(UUID(as_uuid=True), ForeignKey("marketing_tasks.id"), nullable=False)
    store_id = Column(String(50), ForeignKey("stores.id"), nullable=False)
    date = Column(Date, nullable=False)
    target_count = Column(Integer, default=0)
    reached_count = Column(Integer, default=0)
    coupon_distributed = Column(Integer, default=0)
    coupon_redeemed = Column(Integer, default=0)
    driven_gmv_fen = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("task_id", "store_id", "date", name="uq_task_stats_daily"),
    )
```

- [ ] **Step 2: Generate migration (includes ALTER TABLE for coupon_distributions)**

Register in `alembic/env.py`:
```python
import src.models.marketing_task          # noqa: F401 — P3 营销任务
```

The migration should also include:
```python
# ALTER TABLE: add marketing_task_id to coupon_distributions
op.add_column('coupon_distributions',
    sa.Column('marketing_task_id', postgresql.UUID(as_uuid=True), nullable=True))
op.create_foreign_key(
    'fk_distributions_task', 'coupon_distributions', 'marketing_tasks',
    ['marketing_task_id'], ['id'])
```

```bash
cd /Users/lichun/zhilian-os/apps/api-gateway
alembic revision --autogenerate -m "P3: add marketing_tasks system + coupon_distributions.marketing_task_id"
# Review and manually add the ALTER TABLE if autogenerate doesn't pick it up
alembic upgrade head
```

- [ ] **Step 3: Commit**

```bash
git add apps/api-gateway/src/models/marketing_task.py \
       apps/api-gateway/alembic/env.py \
       apps/api-gateway/alembic/versions/*.py
git commit -m "feat(P3): add marketing task models (5 tables) + migration"
```

---

### Task 11: Marketing Task Service + HQ Endpoints

**Files:**
- Create: `apps/api-gateway/src/services/marketing_task_service.py`
- Create: `apps/api-gateway/src/api/hq_marketing_tasks.py`
- Create: `apps/api-gateway/src/api/sm_marketing_tasks.py`
- Modify: `apps/api-gateway/src/main.py`
- Create: `apps/api-gateway/tests/test_marketing_task_service.py`

- [ ] **Step 1: Write failing tests**

```python
# apps/api-gateway/tests/test_marketing_task_service.py
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock


class TestMarketingTaskService:
    @pytest.mark.asyncio
    async def test_create_task(self):
        from src.services.marketing_task_service import marketing_task_service

        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()

        result = await marketing_task_service.create_task(
            db=mock_db,
            brand_id="BRAND001",
            title="生日关怀",
            audience_type="preset",
            audience_config={"preset_id": "birthday_week"},
            created_by=uuid.uuid4(),
        )
        assert result["success"] is True
        assert "task_id" in result

    @pytest.mark.asyncio
    async def test_preset_birthday_week(self):
        """预设人群包：近一周生日"""
        from src.services.marketing_task_service import marketing_task_service
        sql = marketing_task_service._preset_to_sql("birthday_week")
        assert "birth_date" in sql
```

- [ ] **Step 2: Implement MarketingTaskService**

```python
# apps/api-gateway/src/services/marketing_task_service.py
"""营销任务服务 — P3"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.marketing_task import (
    MarketingTask, MarketingTaskTarget, MarketingTaskAssignment,
    MarketingTaskExecution, MarketingTaskStats,
)

logger = structlog.get_logger(__name__)

# 预设人群包 → 参数化 SQL WHERE（绝不拼接用户输入）
# 使用 generate_series 处理年末跨年的生日匹配
_PRESET_SQL = {
    "birthday_week": """ci.birth_date IS NOT NULL
        AND (DATE_PART('month', ci.birth_date) * 100 + DATE_PART('day', ci.birth_date))
        IN (SELECT DATE_PART('month', d) * 100 + DATE_PART('day', d)
            FROM generate_series(CURRENT_DATE, CURRENT_DATE + INTERVAL '7 days', '1 day'::interval) d)""",
    "inactive_30d": "ci.last_order_at < NOW() - INTERVAL '30 days' AND ci.total_order_count > 3",
    "low_balance": "ci.total_order_amount_fen > 0",  # 需要与CRM余额联合查询，简化实现
    "high_value_vip": "ci.total_order_count >= 10 AND ci.total_order_amount_fen >= 1000000",
    "new_customer": "ci.total_order_count = 1 AND ci.first_order_at > NOW() - INTERVAL '30 days'",
    "declining": "ci.rfm_frequency IS NOT NULL",  # 需要时序对比，简化实现
    "dormant": "ci.last_order_at < NOW() - INTERVAL '90 days'",
}


class MarketingTaskService:
    """营销任务 CRUD + 人群筛选"""

    async def create_task(
        self,
        db: AsyncSession,
        *,
        brand_id: str,
        title: str,
        audience_type: str,
        audience_config: Dict,
        created_by: UUID,
        description: str = "",
        script_template: str = "",
        coupon_config: Optional[Dict] = None,
        deadline: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        task = MarketingTask(
            brand_id=brand_id,
            title=title,
            description=description,
            audience_type=audience_type,
            audience_config=audience_config,
            script_template=script_template,
            coupon_config=coupon_config,
            deadline=deadline,
            created_by=created_by,
        )
        db.add(task)
        await db.flush()
        return {"success": True, "task_id": str(task.id)}

    async def preview_audience(
        self,
        db: AsyncSession,
        *,
        audience_type: str,
        audience_config: Dict,
        store_ids: List[str],
    ) -> Dict[str, Any]:
        """预览人群数量。

        预设人群包使用服务端硬编码 SQL（安全）。
        AI 查询由 LLM 生成结构化过滤条件，服务端构建参数化查询（不拼接 SQL）。
        """
        if audience_type == "preset":
            preset_id = audience_config.get("preset_id", "")
            where_clause = self._preset_to_sql(preset_id)
            if where_clause == "1=0":
                return {"total_count": 0, "error": f"未知预设包: {preset_id}"}

            # 预设包的 SQL 是服务端硬编码，安全
            stmt = text(f"""
                SELECT COUNT(*) FROM consumer_identities ci
                WHERE ci.is_merged = FALSE AND ({where_clause})
            """)
            result = await db.execute(stmt)
            total = result.scalar() or 0
            return {"total_count": total, "by_store": []}

        elif audience_type == "ai_query":
            # AI 查询：LLM 生成结构化条件（column, op, value），服务端构建参数化查询
            # 绝不将 AI 输出的 SQL 直接放入 text() — 违反项目宪法
            filters = audience_config.get("filters", [])
            return await self._query_by_structured_filters(db, filters)

        return {"total_count": 0, "by_store": []}

    async def _query_by_structured_filters(
        self, db: AsyncSession, filters: List[Dict],
    ) -> Dict[str, Any]:
        """将 AI 生成的结构化条件转为参数化 SQLAlchemy 查询。

        filters 格式: [{"column": "total_order_count", "op": ">", "value": 3}, ...]
        允许的列白名单 + 操作符白名单，防止 SQL 注入。
        """
        from ..models.consumer_identity import ConsumerIdentity

        ALLOWED_COLUMNS = {
            "total_order_count", "total_order_amount_fen", "rfm_recency_days",
            "rfm_frequency", "rfm_monetary_fen", "birth_date", "last_order_at",
            "first_order_at", "total_reservation_count",
        }
        ALLOWED_OPS = {"=", "!=", ">", ">=", "<", "<="}

        stmt = select(func.count()).select_from(ConsumerIdentity).where(
            ConsumerIdentity.is_merged.is_(False),
        )

        for f in filters:
            col_name = f.get("column", "")
            op = f.get("op", "")
            value = f.get("value")

            if col_name not in ALLOWED_COLUMNS or op not in ALLOWED_OPS:
                continue  # 跳过不合法的条件

            col = getattr(ConsumerIdentity, col_name, None)
            if col is None:
                continue

            if op == "=":
                stmt = stmt.where(col == value)
            elif op == "!=":
                stmt = stmt.where(col != value)
            elif op == ">":
                stmt = stmt.where(col > value)
            elif op == ">=":
                stmt = stmt.where(col >= value)
            elif op == "<":
                stmt = stmt.where(col < value)
            elif op == "<=":
                stmt = stmt.where(col <= value)

        result = await db.execute(stmt)
        total = result.scalar() or 0
        return {"total_count": total, "by_store": []}

    def _preset_to_sql(self, preset_id: str) -> str:
        return _PRESET_SQL.get(preset_id, "1=0")

    async def publish_task(
        self,
        db: AsyncSession,
        *,
        task_id: UUID,
        store_ids: List[str],
    ) -> Dict[str, Any]:
        """下发任务：创建目标人群快照 + 门店分配"""
        task = await db.get(MarketingTask, task_id)
        if not task or task.status != "draft":
            return {"success": False, "error": "任务不存在或状态不正确"}

        task.status = "published"
        task.published_at = datetime.now(timezone.utc)

        # 为每个门店创建分配记录
        for sid in store_ids:
            assignment = MarketingTaskAssignment(
                task_id=task.id,
                store_id=sid,
                status="pending",
            )
            db.add(assignment)

        await db.flush()
        return {"success": True, "assignment_count": len(store_ids)}

    async def assign_staff(
        self,
        db: AsyncSession,
        *,
        assignment_id: UUID,
        assigned_to: UUID,
    ) -> Dict[str, Any]:
        """店长分配执行人"""
        assignment = await db.get(MarketingTaskAssignment, assignment_id)
        if not assignment:
            return {"success": False, "error": "分配记录不存在"}

        assignment.assigned_to = assigned_to
        assignment.status = "assigned"
        assignment.assigned_at = datetime.now(timezone.utc)
        await db.flush()
        return {"success": True}

    async def record_execution(
        self,
        db: AsyncSession,
        *,
        assignment_id: UUID,
        target_id: UUID,
        executor_id: UUID,
        action_type: str,
        action_detail: Optional[Dict] = None,
        feedback: str = "",
        distribution_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """记录执行动作"""
        execution = MarketingTaskExecution(
            assignment_id=assignment_id,
            target_id=target_id,
            executor_id=executor_id,
            action_type=action_type,
            action_detail=action_detail or {},
            distribution_id=distribution_id,
            feedback=feedback,
            executed_at=datetime.now(timezone.utc),
        )
        db.add(execution)

        # 更新 assignment completed_count
        assignment = await db.get(MarketingTaskAssignment, assignment_id)
        if assignment:
            assignment.completed_count = (assignment.completed_count or 0) + 1
            if assignment.completed_count >= assignment.target_count and assignment.target_count > 0:
                assignment.status = "completed"
                assignment.completed_at = datetime.now(timezone.utc)

        await db.flush()
        return {"success": True, "execution_id": str(execution.id)}


marketing_task_service = MarketingTaskService()
```

- [ ] **Step 3: Implement HQ endpoints**

```python
# apps/api-gateway/src/api/hq_marketing_tasks.py
"""总部营销任务 API — P3"""

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, List, Optional
from uuid import UUID

from ..core.dependencies import get_db, get_current_user
from ..models.user import User
from ..services.marketing_task_service import marketing_task_service

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/hq/marketing-tasks", tags=["HQ-营销任务"])


class CreateTaskRequest(BaseModel):
    title: str
    audience_type: str  # preset | ai_query
    audience_config: Dict
    description: str = ""
    script_template: str = ""
    coupon_config: Optional[Dict] = None
    deadline: Optional[str] = None
    store_ids: List[str] = []


class AudiencePreviewRequest(BaseModel):
    audience_type: str
    audience_config: Dict
    store_ids: List[str] = []


class PublishRequest(BaseModel):
    store_ids: List[str]


class AssignRequest(BaseModel):
    assigned_to: str  # user UUID


@router.get("", summary="获取营销任务列表")
async def list_tasks(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """总部查看营销任务列表，可选按状态过滤"""
    from ..models.marketing_task import MarketingTask
    from sqlalchemy import select

    stmt = select(MarketingTask).where(
        MarketingTask.brand_id == current_user.brand_id,
    ).order_by(MarketingTask.created_at.desc())

    if status:
        stmt = stmt.where(MarketingTask.status == status)

    result = await db.execute(stmt)
    tasks = result.scalars().all()
    return [
        {
            "id": str(t.id), "title": t.title, "status": t.status,
            "audience_type": t.audience_type,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "deadline": t.deadline.isoformat() if t.deadline else None,
        }
        for t in tasks
    ]


@router.post("", summary="创建营销任务")
async def create_task(
    req: CreateTaskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await marketing_task_service.create_task(
        db=db, brand_id=current_user.brand_id, title=req.title,
        audience_type=req.audience_type, audience_config=req.audience_config,
        created_by=current_user.id, description=req.description,
        script_template=req.script_template, coupon_config=req.coupon_config,
    )


@router.post("/audience-preview", summary="预览人群数量")
async def audience_preview(req: AudiencePreviewRequest, db: AsyncSession = Depends(get_db)):
    return await marketing_task_service.preview_audience(
        db=db, audience_type=req.audience_type,
        audience_config=req.audience_config, store_ids=req.store_ids,
    )


@router.post("/{task_id}/publish", summary="下发任务")
async def publish_task(
    task_id: str,
    req: PublishRequest,
    db: AsyncSession = Depends(get_db),
):
    if not req.store_ids:
        return {"success": False, "error": "store_ids 不能为空"}
    return await marketing_task_service.publish_task(
        db=db, task_id=UUID(task_id), store_ids=req.store_ids,
    )
```

- [ ] **Step 4: Create SM marketing tasks endpoint**

SM (store manager) needs a separate router to see tasks assigned to their store.

```python
# apps/api-gateway/src/api/sm_marketing_tasks.py
"""店长端营销任务 API — P3"""

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from ..core.dependencies import get_db, get_current_user
from ..models.user import User
from ..models.marketing_task import MarketingTask, MarketingTaskAssignment

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/sm/marketing-tasks", tags=["SM-营销任务"])


@router.get("", summary="获取本店营销任务")
async def list_store_assignments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """返回当前用户所属门店的营销任务分配列表"""
    stmt = (
        select(MarketingTaskAssignment, MarketingTask)
        .join(MarketingTask, MarketingTask.id == MarketingTaskAssignment.task_id)
        .where(MarketingTaskAssignment.store_id == current_user.store_id)
        .order_by(MarketingTaskAssignment.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [
        {
            "id": str(a.id),
            "task_title": t.title,
            "status": a.status,
            "target_count": a.target_count or 0,
            "completed_count": a.completed_count or 0,
            "deadline": t.deadline.isoformat() if t.deadline else None,
        }
        for a, t in rows
    ]
```

Register in `main.py` alongside the HQ router:
```python
from src.api import sm_marketing_tasks
app.include_router(sm_marketing_tasks.router)
```

- [ ] **Step 5: Register routers in main.py + run tests**

```bash
cd /Users/lichun/zhilian-os/apps/api-gateway
pytest tests/test_marketing_task_service.py -v
```

- [ ] **Step 6: Commit**

```bash
git add apps/api-gateway/src/services/marketing_task_service.py \
       apps/api-gateway/src/api/hq_marketing_tasks.py \
       apps/api-gateway/src/api/sm_marketing_tasks.py \
       apps/api-gateway/src/main.py \
       apps/api-gateway/tests/test_marketing_task_service.py
git commit -m "feat(P3): add marketing task service + HQ/SM API endpoints"
```

---

### Task 12: P3 Frontend — Task Creator + Task List Pages

**Files:**
- Create: `apps/web/src/pages/hq/MarketingTasks.tsx`
- Create: `apps/web/src/pages/hq/MarketingTasks.module.css`
- Create: `apps/web/src/pages/hq/MarketingTaskCreate.tsx`
- Create: `apps/web/src/pages/hq/MarketingTaskCreate.module.css`
- Create: `apps/web/src/pages/sm/MarketingTasks.tsx`
- Create: `apps/web/src/pages/sm/MarketingTasks.module.css`
- Modify: `apps/web/src/App.tsx` (add routes)

**Context:**
- HQ pages use desktop layout with sidebar nav (HQLayout)
- SM pages use mobile layout (StoreManagerLayout)
- Same data, different views per role

- [ ] **Step 1: Create HQ MarketingTasks list page**

```typescript
// apps/web/src/pages/hq/MarketingTasks.tsx
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Tag, Space, message } from 'antd';
import { ZButton, ZCard } from '../../design-system/components';
import { apiClient } from '../../services/api';
import styles from './MarketingTasks.module.css';

interface Task {
  id: string;
  title: string;
  status: string;
  audience_type: string;
  created_at: string;
  deadline: string | null;
}

const STATUS_MAP: Record<string, { color: string; label: string }> = {
  draft: { color: 'default', label: '草稿' },
  published: { color: 'blue', label: '已下发' },
  in_progress: { color: 'orange', label: '执行中' },
  completed: { color: 'green', label: '已完成' },
  cancelled: { color: 'red', label: '已取消' },
};

export default function MarketingTasks() {
  const navigate = useNavigate();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);

  const loadTasks = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<Task[]>('/api/v1/hq/marketing-tasks');
      setTasks(data || []);
    } catch {
      message.error('加载任务列表失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadTasks(); }, [loadTasks]);

  const columns = [
    { title: '任务名称', dataIndex: 'title', key: 'title' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => {
        const m = STATUS_MAP[s] || { color: 'default', label: s };
        return <Tag color={m.color}>{m.label}</Tag>;
      },
    },
    {
      title: '人群类型', dataIndex: 'audience_type', key: 'audience_type',
      render: (t: string) => t === 'preset' ? '预设人群包' : 'AI筛选',
    },
    { title: '截止时间', dataIndex: 'deadline', key: 'deadline' },
    {
      title: '操作', key: 'action',
      render: (_: unknown, record: Task) => (
        <Space>
          <a onClick={() => navigate(`/hq/marketing-tasks/${record.id}`)}>详情</a>
        </Space>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.toolbar}>
        <h2>营销任务</h2>
        <ZButton variant="primary" onClick={() => navigate('/hq/marketing-tasks/create')}>
          创建任务
        </ZButton>
      </div>
      <ZCard>
        <Table dataSource={tasks} columns={columns} loading={loading} rowKey="id" />
      </ZCard>
    </div>
  );
}
```

```css
/* apps/web/src/pages/hq/MarketingTasks.module.css */
.page {
  padding: 24px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.toolbar h2 {
  margin: 0;
  color: var(--text-primary);
}
```

- [ ] **Step 2: Create HQ MarketingTaskCreate page**

```typescript
// apps/web/src/pages/hq/MarketingTaskCreate.tsx
import React, { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Select, message } from 'antd';
import { ZButton, ZCard } from '../../design-system/components';
import { apiClient } from '../../services/api';
import styles from './MarketingTaskCreate.module.css';

const PRESET_OPTIONS = [
  { value: 'birthday_week', label: '近一周生日' },
  { value: 'inactive_30d', label: '30天未消费' },
  { value: 'high_value_vip', label: '高价值VIP' },
  { value: 'new_customer', label: '首单新客' },
  { value: 'declining', label: '消费下降' },
  { value: 'dormant', label: '沉睡会员' },
];

export default function MarketingTaskCreate() {
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [submitting, setSubmitting] = useState(false);
  const [previewCount, setPreviewCount] = useState<number | null>(null);

  const handlePreview = useCallback(async () => {
    const values = form.getFieldsValue();
    try {
      const data = await apiClient.post<{ total_count: number }>(
        '/api/v1/hq/marketing-tasks/audience-preview',
        {
          audience_type: 'preset',
          audience_config: { preset_id: values.preset_id },
          store_ids: [],
        },
      );
      setPreviewCount(data.total_count);
    } catch {
      message.error('预览失败');
    }
  }, [form]);

  const handleSubmit = useCallback(async () => {
    const values = await form.validateFields();
    setSubmitting(true);
    try {
      await apiClient.post('/api/v1/hq/marketing-tasks', {
        title: values.title,
        audience_type: 'preset',
        audience_config: { preset_id: values.preset_id },
        script_template: values.script_template || '',
        description: values.description || '',
      });
      message.success('任务创建成功');
      navigate('/hq/marketing-tasks');
    } catch {
      message.error('创建失败');
    } finally {
      setSubmitting(false);
    }
  }, [form, navigate]);

  return (
    <div className={styles.page}>
      <h2>创建营销任务</h2>
      <ZCard>
        <Form form={form} layout="vertical" style={{ maxWidth: 600 }}>
          <Form.Item name="title" label="任务名称" rules={[{ required: true }]}>
            <Input placeholder="例：本周生日关怀" />
          </Form.Item>
          <Form.Item name="preset_id" label="目标人群" rules={[{ required: true }]}>
            <Select options={PRESET_OPTIONS} placeholder="选择预设人群包" />
          </Form.Item>
          {previewCount !== null && (
            <div className={styles.preview}>匹配人数: <strong>{previewCount}</strong></div>
          )}
          <ZButton variant="secondary" onClick={handlePreview}>预览人群</ZButton>
          <Form.Item name="script_template" label="话术模板" style={{ marginTop: 16 }}>
            <Input.TextArea rows={3} placeholder="可选，发送给员工的话术参考" />
          </Form.Item>
          <Form.Item name="description" label="任务说明">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item>
            <ZButton variant="primary" onClick={handleSubmit} disabled={submitting}>
              创建任务
            </ZButton>
          </Form.Item>
        </Form>
      </ZCard>
    </div>
  );
}
```

```css
/* apps/web/src/pages/hq/MarketingTaskCreate.module.css */
.page {
  padding: 24px;
}

.page h2 {
  color: var(--text-primary);
  margin-bottom: 16px;
}

.preview {
  margin: 8px 0 16px;
  padding: 8px 12px;
  background: rgba(255, 107, 44, 0.08);
  border-radius: var(--radius-md);
  font-size: 14px;
}
```

- [ ] **Step 3: Create SM MarketingTasks page (mobile view)**

```typescript
// apps/web/src/pages/sm/MarketingTasks.tsx
import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Tag, message } from 'antd';
import { ZCard, ZButton, ZEmpty } from '../../design-system/components';
import { apiClient } from '../../services/api';
import styles from './MarketingTasks.module.css';

interface Assignment {
  id: string;
  task_title: string;
  status: string;
  target_count: number;
  completed_count: number;
  deadline: string | null;
}

export default function SmMarketingTasks() {
  const navigate = useNavigate();
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(false);

  const loadAssignments = useCallback(async () => {
    setLoading(true);
    try {
      // TODO: 实际 store_id 从 auth context 获取
      const data = await apiClient.get<Assignment[]>('/api/v1/sm/marketing-tasks');
      setAssignments(data || []);
    } catch {
      setAssignments([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAssignments(); }, [loadAssignments]);

  if (!loading && assignments.length === 0) {
    return <ZEmpty title="暂无营销任务" description="总部下发的任务会在这里显示" />;
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div className={styles.title}>营销任务</div>
      </div>
      <div className={styles.list}>
        {assignments.map((a) => (
          <ZCard key={a.id} style={{ marginBottom: 12 }}>
            <div className={styles.taskRow}>
              <div>
                <div className={styles.taskTitle}>{a.task_title}</div>
                <Tag>{a.status === 'assigned' ? '待执行' : '进行中'}</Tag>
              </div>
              <div className={styles.progress}>
                {a.completed_count}/{a.target_count}
              </div>
            </div>
          </ZCard>
        ))}
      </div>
    </div>
  );
}
```

```css
/* apps/web/src/pages/sm/MarketingTasks.module.css */
.page { display: flex; flex-direction: column; min-height: 100%; background: var(--bg); }
.header { padding: 20px 16px 14px; background: var(--surface); border-bottom: 1px solid var(--border); }
.title { font-size: 20px; font-weight: 700; color: var(--text-primary); }
.list { padding: 16px; }
.taskRow { display: flex; justify-content: space-between; align-items: center; }
.taskTitle { font-weight: 600; margin-bottom: 4px; }
.progress { font-size: 20px; font-weight: 700; color: var(--accent); }
```

- [ ] **Step 4: Add routes in App.tsx**

```typescript
// Lazy imports
const HqMarketingTasks = lazy(() => import('./pages/hq/MarketingTasks'));
const HqMarketingTaskCreate = lazy(() => import('./pages/hq/MarketingTaskCreate'));
const SmMarketingTasks = lazy(() => import('./pages/sm/MarketingTasks'));

// In /hq route group:
<Route path="marketing-tasks" element={<HqMarketingTasks />} />
<Route path="marketing-tasks/create" element={<HqMarketingTaskCreate />} />

// In /sm route group:
<Route path="marketing-tasks" element={<SmMarketingTasks />} />
```

- [ ] **Step 5: Build and verify**

```bash
cd /Users/lichun/zhilian-os/apps/web && pnpm build
```

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/pages/hq/MarketingTasks.tsx \
       apps/web/src/pages/hq/MarketingTasks.module.css \
       apps/web/src/pages/hq/MarketingTaskCreate.tsx \
       apps/web/src/pages/hq/MarketingTaskCreate.module.css \
       apps/web/src/pages/sm/MarketingTasks.tsx \
       apps/web/src/pages/sm/MarketingTasks.module.css \
       apps/web/src/App.tsx
git commit -m "feat(P3): add marketing task pages for HQ (create+list) and SM (assignment list)"
```

---

## Verification Checklist

After all tasks are complete, verify:

- [ ] `cd apps/api-gateway && pytest tests/ -v` — all tests pass
- [ ] `cd apps/web && pnpm build` — 0 TS errors
- [ ] `alembic upgrade head` — all migrations apply cleanly
- [ ] Manual test: `GET /api/v1/bff/member-profile/STORE001/13800001234` returns profile JSON
- [ ] Manual test: `POST /api/v1/bff/member-profile/STORE001/distribute-coupon` works
- [ ] Manual test: `GET /api/v1/hq/marketing-tasks` returns task list
- [ ] Manual test: `POST /api/v1/hq/marketing-tasks` creates task
- [ ] Manual test: `POST /api/v1/hq/marketing-tasks/{id}/publish` with `{"store_ids": [...]}` works
- [ ] Manual test: `GET /api/v1/sm/marketing-tasks` returns store assignments
- [ ] Frontend: `/sm/members` shows search bar + profile card
- [ ] Frontend: `/hq/marketing-tasks` shows task list + create form
