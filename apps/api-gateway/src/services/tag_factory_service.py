"""
可配置标签工厂服务 — Phase 3

标签规则存储在数据库（tag_rules 表），运营人员通过 API 配置规则，引擎动态执行。
支持 AND / OR 条件组合、优先级覆盖、批量评估与规则预览。
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog
from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# --------------------------------------------------------------------------- #
# 支持的条件字段白名单（防注入：只允许这些字段名进入动态判断逻辑）
# --------------------------------------------------------------------------- #
SUPPORTED_CONDITIONS: Dict[str, Dict[str, Any]] = {
    "brand_order_count":      {"type": "int",      "ops": ["gt", "gte", "lt", "lte", "eq"]},
    "brand_order_amount_fen": {"type": "int",      "ops": ["gt", "gte", "lt", "lte"]},
    "brand_last_order_at":    {"type": "days_ago", "ops": ["within", "not_within"]},
    "lifecycle_state":        {"type": "enum",     "ops": ["in", "not_in"]},
    "brand_rfm_level":        {"type": "enum",     "ops": ["in", "not_in"]},
    "registration_channel":   {"type": "enum",     "ops": ["in", "not_in"]},
    "brand_level":            {"type": "enum",     "ops": ["in", "not_in"]},
    "brand_points":           {"type": "int",      "ops": ["gt", "gte", "lt", "lte"]},
    "cross_brand_count":      {"type": "int",      "ops": ["gt", "gte"]},
}

# 合法 logic 值
VALID_LOGIC = {"AND", "OR"}


# --------------------------------------------------------------------------- #
# 条件校验
# --------------------------------------------------------------------------- #

class ConditionValidationError(ValueError):
    """条件 JSON 结构非法"""


def _validate_condition(cond: dict) -> None:
    """
    校验单条条件字典结构，拒绝非法字段/操作符。
    合法结构：{"field": str, "op": str, "value": any}
    """
    if not isinstance(cond, dict):
        raise ConditionValidationError("条件必须是字典")

    field = cond.get("field")
    op = cond.get("op")
    value = cond.get("value")

    if field not in SUPPORTED_CONDITIONS:
        raise ConditionValidationError(
            f"不支持的条件字段: {field!r}，合法字段: {list(SUPPORTED_CONDITIONS)}"
        )

    spec = SUPPORTED_CONDITIONS[field]
    if op not in spec["ops"]:
        raise ConditionValidationError(
            f"字段 {field!r} 不支持操作符 {op!r}，合法操作符: {spec['ops']}"
        )

    if value is None:
        raise ConditionValidationError(f"条件字段 {field!r} 的 value 不能为 None")


def validate_conditions(conditions: List[dict]) -> None:
    """批量校验条件列表"""
    if not isinstance(conditions, list):
        raise ConditionValidationError("conditions 必须是列表")
    for i, cond in enumerate(conditions):
        try:
            _validate_condition(cond)
        except ConditionValidationError as exc:
            raise ConditionValidationError(f"第 {i} 条规则非法: {exc}") from exc


# --------------------------------------------------------------------------- #
# 单条件评估（对 BrandConsumerProfile 字典）
# --------------------------------------------------------------------------- #

def _eval_condition(cond: dict, profile: dict) -> bool:
    """
    对单个会员的档案数据执行一条条件判断。
    profile 是 BrandConsumerProfile 的字段字典（字段名与模型属性对齐）。
    """
    field = cond["field"]
    op = cond["op"]
    value = cond["value"]

    raw = profile.get(field)

    # cross_brand_count 不在 brand_consumer_profiles，从 profile 中取计算值
    if raw is None:
        return False

    spec = SUPPORTED_CONDITIONS[field]
    field_type = spec["type"]

    if field_type == "int":
        try:
            raw_int = int(raw)
            val_int = int(value)
        except (TypeError, ValueError):
            return False
        if op == "gt":
            return raw_int > val_int
        if op == "gte":
            return raw_int >= val_int
        if op == "lt":
            return raw_int < val_int
        if op == "lte":
            return raw_int <= val_int
        if op == "eq":
            return raw_int == val_int

    elif field_type == "days_ago":
        # raw 为 datetime 或 None
        if not isinstance(raw, datetime):
            try:
                raw = datetime.fromisoformat(str(raw))
            except (ValueError, TypeError):
                return False
        now = datetime.now(tz=timezone.utc)
        if raw.tzinfo is None:
            raw = raw.replace(tzinfo=timezone.utc)
        days_diff = (now - raw).days
        try:
            threshold = int(value)
        except (TypeError, ValueError):
            return False
        if op == "within":
            return days_diff <= threshold
        if op == "not_within":
            return days_diff > threshold

    elif field_type == "enum":
        raw_str = str(raw)
        if not isinstance(value, list):
            value = [value]
        value_strs = [str(v) for v in value]
        if op == "in":
            return raw_str in value_strs
        if op == "not_in":
            return raw_str not in value_strs

    return False


def _eval_rule(conditions: List[dict], logic: str, profile: dict) -> bool:
    """对 profile 执行整条规则（AND / OR）"""
    if not conditions:
        return False
    if logic == "AND":
        return all(_eval_condition(c, profile) for c in conditions)
    # OR
    return any(_eval_condition(c, profile) for c in conditions)


# --------------------------------------------------------------------------- #
# TagFactoryService
# --------------------------------------------------------------------------- #

class TagFactoryService:
    """
    可配置标签工厂服务。
    - 规则从 tag_rules 表动态加载（含集团通用规则 brand_id='*'）
    - 评估结果写入 consumer_tag_snapshots
    - 所有金额字段同时返回 _fen 和 _yuan
    """

    # ------------------------------------------------------------------ #
    # 规则管理
    # ------------------------------------------------------------------ #

    async def create_rule(
        self,
        rule_data: dict,
        brand_id: str,
        group_id: str,
        created_by: Optional[str] = None,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """
        创建标签规则，返回 rule_id。
        session 参数预留给单元测试注入；生产路径从 get_db_session 获取。
        """
        conditions = rule_data.get("conditions", [])
        logic = rule_data.get("logic", "AND").upper()

        # 校验
        validate_conditions(conditions)
        if logic not in VALID_LOGIC:
            raise ConditionValidationError(f"logic 必须是 AND 或 OR，当前: {logic!r}")

        rule_id = str(uuid.uuid4())
        now = datetime.utcnow()

        async def _do_insert(s: AsyncSession) -> str:
            await s.execute(
                text("""
                    INSERT INTO tag_rules
                        (id, brand_id, group_id, tag_name, tag_code,
                         conditions, logic, priority, is_active, created_by,
                         created_at, updated_at)
                    VALUES
                        (:id, :brand_id, :group_id, :tag_name, :tag_code,
                         CAST(:conditions AS jsonb), :logic, :priority,
                         :is_active, :created_by, :created_at, :updated_at)
                """),
                {
                    "id": rule_id,
                    "brand_id": brand_id,
                    "group_id": group_id,
                    "tag_name": rule_data["tag_name"],
                    "tag_code": rule_data["tag_code"],
                    "conditions": __import__("json").dumps(conditions, ensure_ascii=False),
                    "logic": logic,
                    "priority": rule_data.get("priority", 100),
                    "is_active": rule_data.get("is_active", True),
                    "created_by": created_by,
                    "created_at": now,
                    "updated_at": now,
                },
            )
            return rule_id

        if session is not None:
            return await _do_insert(session)

        from ..core.database import get_db_session
        async with get_db_session() as s:
            result = await _do_insert(s)
            await s.commit()
            return result

    async def update_rule(
        self,
        rule_id: str,
        updates: dict,
        session: Optional[AsyncSession] = None,
    ) -> bool:
        """
        更新规则（停用 / 修改条件等）。
        支持的字段：tag_name, tag_code, conditions, logic, priority, is_active。
        返回 True 表示找到并更新。
        """
        allowed_fields = {"tag_name", "tag_code", "conditions", "logic", "priority", "is_active"}
        set_clauses = []
        params: dict = {"rule_id": rule_id, "updated_at": datetime.utcnow()}

        for key, val in updates.items():
            if key not in allowed_fields:
                continue
            if key == "conditions":
                validate_conditions(val)
                set_clauses.append("conditions = CAST(:conditions AS jsonb)")
                params["conditions"] = __import__("json").dumps(val, ensure_ascii=False)
            elif key == "logic":
                val_upper = str(val).upper()
                if val_upper not in VALID_LOGIC:
                    raise ConditionValidationError(f"logic 必须是 AND 或 OR，当前: {val!r}")
                set_clauses.append("logic = :logic")
                params["logic"] = val_upper
            else:
                set_clauses.append(f"{key} = :{key}")
                params[key] = val

        if not set_clauses:
            return False

        set_clauses.append("updated_at = :updated_at")
        sql = text(
            f"UPDATE tag_rules SET {', '.join(set_clauses)} WHERE id = :rule_id"
        )

        async def _do_update(s: AsyncSession) -> bool:
            result = await s.execute(sql, params)
            return result.rowcount > 0

        if session is not None:
            return await _do_update(session)

        from ..core.database import get_db_session
        async with get_db_session() as s:
            ok = await _do_update(s)
            await s.commit()
            return ok

    async def list_rules(
        self,
        brand_id: str,
        group_id: str,
        include_group_rules: bool = True,
        session: Optional[AsyncSession] = None,
    ) -> List[dict]:
        """列出品牌的所有规则（含集团通用规则 brand_id='*'）"""

        async def _fetch(s: AsyncSession) -> List[dict]:
            if include_group_rules:
                sql = text("""
                    SELECT id, brand_id, group_id, tag_name, tag_code,
                           conditions, logic, priority, is_active, created_by,
                           created_at, updated_at
                    FROM tag_rules
                    WHERE (brand_id = :brand_id OR brand_id = '*' OR group_id = :group_id)
                      AND is_active = TRUE
                    ORDER BY priority DESC, created_at
                """)
                params = {"brand_id": brand_id, "group_id": group_id}
            else:
                sql = text("""
                    SELECT id, brand_id, group_id, tag_name, tag_code,
                           conditions, logic, priority, is_active, created_by,
                           created_at, updated_at
                    FROM tag_rules
                    WHERE brand_id = :brand_id AND is_active = TRUE
                    ORDER BY priority DESC, created_at
                """)
                params = {"brand_id": brand_id}

            rows = await s.execute(sql, params)
            return [dict(row._mapping) for row in rows]

        if session is not None:
            return await _fetch(session)

        from ..core.database import get_db_session
        async with get_db_session() as s:
            return await _fetch(s)

    # ------------------------------------------------------------------ #
    # 标签评估
    # ------------------------------------------------------------------ #

    async def _load_active_rules(
        self, brand_id: str, group_id: str, s: AsyncSession
    ) -> List[dict]:
        """加载激活规则（含集团通用），按 priority 降序"""
        sql = text("""
            SELECT id, tag_code, tag_name, conditions, logic, priority
            FROM tag_rules
            WHERE (brand_id = :brand_id OR brand_id = '*' OR group_id = :group_id)
              AND is_active = TRUE
            ORDER BY priority DESC
        """)
        rows = await s.execute(sql, {"brand_id": brand_id, "group_id": group_id})
        return [dict(r._mapping) for r in rows]

    async def _load_profile(
        self,
        consumer_id: str,
        brand_id: str,
        s: AsyncSession,
    ) -> Optional[dict]:
        """
        从 brand_consumer_profiles 加载会员品牌档案，
        并补充 cross_brand_count（跨品牌消费次数）。
        """
        sql = text("""
            SELECT
                bcp.consumer_id,
                bcp.brand_id,
                bcp.group_id,
                bcp.brand_order_count,
                bcp.brand_order_amount_fen,
                bcp.brand_last_order_at,
                bcp.lifecycle_state,
                bcp.registration_channel,
                bcp.brand_level,
                bcp.brand_points,
                COUNT(DISTINCT bcp2.brand_id) AS cross_brand_count
            FROM brand_consumer_profiles bcp
            LEFT JOIN brand_consumer_profiles bcp2
                ON bcp2.consumer_id = bcp.consumer_id
                AND bcp2.brand_order_count > 0
            WHERE bcp.consumer_id = CAST(:consumer_id AS uuid)
              AND bcp.brand_id = :brand_id
            GROUP BY
                bcp.consumer_id, bcp.brand_id, bcp.group_id,
                bcp.brand_order_count, bcp.brand_order_amount_fen,
                bcp.brand_last_order_at, bcp.lifecycle_state,
                bcp.registration_channel, bcp.brand_level, bcp.brand_points
        """)
        row = await s.execute(sql, {"consumer_id": consumer_id, "brand_id": brand_id})
        result = row.first()
        if result is None:
            return None
        return dict(result._mapping)

    async def evaluate_tags_for_consumer(
        self,
        consumer_id: str,
        brand_id: str,
        group_id: str,
        session: AsyncSession,
    ) -> List[str]:
        """
        对单个会员执行所有激活的标签规则，返回命中的 tag_code 列表。
        逻辑：
        1. 加载该 brand_id 的所有激活规则（按priority降序）
        2. 读取会员的 BrandConsumerProfile
        3. 对每条规则执行条件判断
        4. 返回命中的 tag_code 列表
        """
        rules = await self._load_active_rules(brand_id, group_id, session)
        if not rules:
            return []

        profile = await self._load_profile(consumer_id, brand_id, session)
        if not profile:
            return []

        hit_tags: List[str] = []
        for rule in rules:
            conditions = rule.get("conditions") or []
            logic = rule.get("logic", "AND")
            if isinstance(conditions, str):
                import json as _json
                conditions = _json.loads(conditions)
            try:
                if _eval_rule(conditions, logic, profile):
                    hit_tags.append(rule["tag_code"])
            except Exception as exc:
                logger.warning(
                    "标签规则评估异常",
                    rule_id=rule.get("id"),
                    tag_code=rule.get("tag_code"),
                    error=str(exc),
                )
        return hit_tags

    async def batch_evaluate_tags(
        self,
        brand_id: str,
        group_id: str,
        consumer_ids: List[str],
        session: AsyncSession,
    ) -> Dict[str, List[str]]:
        """
        批量评估会员标签。
        返回 {consumer_id: [tag_codes]} 映射。
        一次性加载规则，对每个消费者复用。
        """
        rules = await self._load_active_rules(brand_id, group_id, session)
        result: Dict[str, List[str]] = {}

        if not rules:
            return {cid: [] for cid in consumer_ids}

        for consumer_id in consumer_ids:
            profile = await self._load_profile(consumer_id, brand_id, session)
            if not profile:
                result[consumer_id] = []
                continue

            hit_tags: List[str] = []
            for rule in rules:
                conditions = rule.get("conditions") or []
                logic = rule.get("logic", "AND")
                if isinstance(conditions, str):
                    import json as _json
                    conditions = _json.loads(conditions)
                try:
                    if _eval_rule(conditions, logic, profile):
                        hit_tags.append(rule["tag_code"])
                except Exception as exc:
                    logger.warning(
                        "批量评估规则异常",
                        rule_id=rule.get("id"),
                        consumer_id=consumer_id,
                        error=str(exc),
                    )
            result[consumer_id] = hit_tags

        return result

    async def persist_tag_snapshot(
        self,
        consumer_id: str,
        brand_id: str,
        group_id: str,
        tag_codes: List[str],
        session: AsyncSession,
    ) -> None:
        """将评估结果写入 consumer_tag_snapshots（UPSERT）"""
        import json as _json
        await session.execute(
            text("""
                INSERT INTO consumer_tag_snapshots
                    (id, consumer_id, brand_id, group_id, tag_codes, last_evaluated_at)
                VALUES
                    (gen_random_uuid(),
                     CAST(:consumer_id AS uuid),
                     :brand_id,
                     :group_id,
                     CAST(:tag_codes AS text[]),
                     NOW())
                ON CONFLICT (consumer_id, brand_id)
                DO UPDATE SET
                    tag_codes = EXCLUDED.tag_codes,
                    last_evaluated_at = NOW()
            """),
            {
                "consumer_id": consumer_id,
                "brand_id": brand_id,
                "group_id": group_id,
                "tag_codes": "{" + ",".join(tag_codes) + "}",
            },
        )

    async def get_consumer_tags(
        self,
        consumer_id: str,
        brand_id: str,
        session: AsyncSession,
    ) -> Dict[str, Any]:
        """
        查询会员当前快照标签。
        返回 tag_codes 列表 + last_evaluated_at。
        """
        sql = text("""
            SELECT tag_codes, last_evaluated_at
            FROM consumer_tag_snapshots
            WHERE consumer_id = CAST(:consumer_id AS uuid)
              AND brand_id = :brand_id
        """)
        row = await session.execute(sql, {"consumer_id": consumer_id, "brand_id": brand_id})
        result = row.first()
        if result is None:
            return {"tag_codes": [], "last_evaluated_at": None}
        return {
            "tag_codes": list(result.tag_codes or []),
            "last_evaluated_at": result.last_evaluated_at.isoformat()
            if result.last_evaluated_at
            else None,
        }

    # ------------------------------------------------------------------ #
    # 规则预览
    # ------------------------------------------------------------------ #

    async def preview_rule(
        self,
        conditions: List[dict],
        logic: str,
        brand_id: str,
        group_id: str,
        limit: int = 100,
        session: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        """
        预览：规则将命中多少会员（不实际打标签）。
        为了效率，只扫描 brand_consumer_profiles 中最多 10000 条记录。
        返回命中人数 + 命中率（估算）。
        """
        # 安全校验
        validate_conditions(conditions)
        logic = logic.upper()
        if logic not in VALID_LOGIC:
            raise ConditionValidationError(f"logic 必须是 AND 或 OR")

        async def _do_preview(s: AsyncSession) -> Dict[str, Any]:
            # 拉取最多 10000 条档案做估算
            sql = text("""
                SELECT
                    bcp.consumer_id::text,
                    bcp.brand_order_count,
                    bcp.brand_order_amount_fen,
                    bcp.brand_last_order_at,
                    bcp.lifecycle_state,
                    bcp.registration_channel,
                    bcp.brand_level,
                    bcp.brand_points,
                    COUNT(DISTINCT bcp2.brand_id) AS cross_brand_count
                FROM brand_consumer_profiles bcp
                LEFT JOIN brand_consumer_profiles bcp2
                    ON bcp2.consumer_id = bcp.consumer_id
                    AND bcp2.brand_order_count > 0
                WHERE bcp.brand_id = :brand_id
                  AND bcp.is_active = TRUE
                GROUP BY
                    bcp.consumer_id, bcp.brand_order_count,
                    bcp.brand_order_amount_fen, bcp.brand_last_order_at,
                    bcp.lifecycle_state, bcp.registration_channel,
                    bcp.brand_level, bcp.brand_points
                LIMIT 10000
            """)
            rows = await s.execute(sql, {"brand_id": brand_id})
            profiles = [dict(r._mapping) for r in rows]

            total = len(profiles)
            hit = 0
            sample_ids: List[str] = []

            for p in profiles:
                if _eval_rule(conditions, logic, p):
                    hit += 1
                    if len(sample_ids) < limit:
                        sample_ids.append(str(p["consumer_id"]))

            hit_rate = round(hit / total * 100, 2) if total > 0 else 0.0

            return {
                "scanned_count": total,
                "hit_count": hit,
                "hit_rate_pct": hit_rate,
                "sample_consumer_ids": sample_ids,
                "note": "估算基于最多 10000 条档案" if total == 10000 else None,
            }

        if session is not None:
            return await _do_preview(session)

        from ..core.database import get_db_session
        async with get_db_session() as s:
            return await _do_preview(s)


# 全局单例
tag_factory_service = TagFactoryService()
