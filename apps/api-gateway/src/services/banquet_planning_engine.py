"""
BanquetPlanningEngine — 宴会熔断规划引擎

职责：
  - 宴会熔断：当确认宴会人数 ≥ BANQUET_CIRCUIT_THRESHOLD 时，
    从散客概率预测轨道"熔断"，切入确定性规划路径
  - 生成宴会专属采购加成（在常规采购清单之上叠加）
  - 生成宴会专属排班加成（坐席/厨师/协调员）
  - 生成 BEO 单（Banquet Event Order）—— 各部门协调文档
  - 检测资源冲突（场地容量超限、时间重叠）

BEO 单结构（参考 宴荟佳 / 宴专家 PPT）：
  - 活动基本信息（宴会 ID、客户、日期、时间、人数、场地）
  - 菜单快照（当前版本号、变更记录）
  - 采购清单（食材 + 用量 + 采购状态）
  - 排班方案（岗位 + 班次 + 姓名）
  - 财务摘要（预算 + 已收定金 + 待收尾款）
  - 变更日志（version_number、field、old/new value、operator、time）

宴会熔断阈值：
  BANQUET_CIRCUIT_THRESHOLD=20（默认；可通过环境变量覆盖）
  > 20 人宴会 → 切入确定性路径，触发 BEO 生成 + 资源检查
  ≤ 20 人宴会 → 仍走散客预测轨道（小宴会 / 私人聚餐）

食材安全系数：
  BANQUET_SAFETY_FACTOR=1.1（默认 +10% 余量）

与其他服务的集成：
  - DailyHubService._get_banquet_variables(): 调用 check_circuit_breaker()
  - FastPlanningService.generate_procurement(): 接受 banquet_addon 参数叠加
  - WorkflowEngine procurement 阶段：可写入 BEO 采购清单到 DecisionVersion
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

import structlog

logger = structlog.get_logger()

# ── 可调参数 ──────────────────────────────────────────────────────────────────
BANQUET_CIRCUIT_THRESHOLD: int   = int(os.getenv("BANQUET_CIRCUIT_THRESHOLD", "20"))
BANQUET_SAFETY_FACTOR:     float = float(os.getenv("BANQUET_SAFETY_FACTOR", "1.1"))

# ── 宴会食材基准（克/人/类别） ────────────────────────────────────────────────
# 依据：宴会标准套餐物料参考；各门店可通过 menu_package 覆盖
_BANQUET_INGREDIENTS: List[Dict[str, Any]] = [
    {"category": "premium_meat",  "label": "优质肉类",  "grams_per_head": 250, "unit": "g", "urgency": "high"},
    {"category": "seafood",       "label": "海鲜",      "grams_per_head": 200, "unit": "g", "urgency": "high"},
    {"category": "poultry",       "label": "禽类",      "grams_per_head": 150, "unit": "g", "urgency": "medium"},
    {"category": "vegetables",    "label": "蔬菜",      "grams_per_head": 300, "unit": "g", "urgency": "medium"},
    {"category": "rice_staples",  "label": "主食/米面", "grams_per_head": 200, "unit": "g", "urgency": "low"},
    {"category": "condiments",    "label": "调味料",    "grams_per_head":  50, "unit": "g", "urgency": "low"},
    {"category": "beverages",     "label": "饮品",      "grams_per_head": 500, "unit": "ml","urgency": "medium"},
    {"category": "desserts",      "label": "甜品/点心", "grams_per_head": 100, "unit": "g", "urgency": "low"},
]

# ── 宴会排班基准 ───────────────────────────────────────────────────────────────
_BANQUET_STAFFING_RULES: Dict[str, Any] = {
    "coordinator_fixed":    1,      # 每场固定 1 名宴会协调员
    "waiter_per_n_guests":  10,     # 每 10 位客人 1 名服务员
    "chef_per_n_guests":    25,     # 每 25 位客人 1 名厨师
    "senior_chef_threshold": 30,    # ≥ 30 人启动 1 名主厨（升级 senior）
    "cashier_fixed":        1,      # 固定 1 名收银（大型宴会 ≥ 80 人加 1）
    "shift_before_event_h": 2,      # 宴会开始前 2 小时进场
    "shift_after_event_h":  1,      # 宴会结束后 1 小时撤场
}


class BanquetCircuitBreaker:
    """宴会熔断结果（传递给 DailyHubService）。"""

    __slots__ = (
        "triggered", "reservation_id", "party_size",
        "procurement_addon", "staffing_addon", "beo",
    )

    def __init__(
        self,
        triggered:        bool,
        reservation_id:   Optional[str]       = None,
        party_size:       int                 = 0,
        procurement_addon: Optional[List[Dict]] = None,
        staffing_addon:   Optional[Dict]      = None,
        beo:              Optional[Dict]      = None,
    ):
        self.triggered         = triggered
        self.reservation_id    = reservation_id
        self.party_size        = party_size
        self.procurement_addon = procurement_addon or []
        self.staffing_addon    = staffing_addon or {}
        self.beo               = beo


class BanquetPlanningEngine:
    """
    宴会规划引擎（无状态，可直接实例化使用）。

    Usage:
        engine = BanquetPlanningEngine()

        # 检查是否触发熔断
        result = engine.check_circuit_breaker(banquet_dict)

        # 生成采购加成
        procurement = engine.generate_procurement_addon(banquet, menu_package=None)

        # 生成排班加成
        staffing = engine.generate_staffing_addon(banquet)

        # 生成 BEO 单
        beo = engine.generate_beo(banquet, store_id="S001", plan_date=date.today())

        # 检测资源冲突
        conflicts = engine.check_resource_conflicts(banquets_list, max_capacity=200)
    """

    # ── 熔断判定 ───────────────────────────────────────────────────────────────

    def check_circuit_breaker(
        self,
        banquet:      Dict[str, Any],
        store_id:     str  = "",
        plan_date:    Optional[date] = None,
        menu_package: Optional[Dict[str, Any]] = None,
    ) -> BanquetCircuitBreaker:
        """
        判断单场宴会是否触发熔断，并生成完整的熔断上下文。

        触发条件：party_size ≥ BANQUET_CIRCUIT_THRESHOLD（默认 20）

        Args:
            banquet:      宴会预约数据 dict（含 party_size、reservation_id 等）
            store_id:     门店 ID（用于 BEO 生成）
            plan_date:    规划日期（用于 BEO 生成）
            menu_package: 可选菜单套餐配置（覆盖默认食材基准）

        Returns:
            BanquetCircuitBreaker（triggered=False 时其余字段为空）
        """
        party_size = int(banquet.get("party_size") or 0)
        rid        = banquet.get("reservation_id", "")

        if party_size < BANQUET_CIRCUIT_THRESHOLD:
            logger.debug(
                "宴会未触发熔断",
                reservation_id=rid,
                party_size=party_size,
                threshold=BANQUET_CIRCUIT_THRESHOLD,
            )
            return BanquetCircuitBreaker(triggered=False)

        logger.info(
            "宴会熔断已触发",
            reservation_id=rid,
            party_size=party_size,
            threshold=BANQUET_CIRCUIT_THRESHOLD,
        )

        procurement_addon = self.generate_procurement_addon(banquet, menu_package)
        staffing_addon    = self.generate_staffing_addon(banquet)
        beo               = self.generate_beo(banquet, store_id=store_id, plan_date=plan_date)

        return BanquetCircuitBreaker(
            triggered=True,
            reservation_id=rid,
            party_size=party_size,
            procurement_addon=procurement_addon,
            staffing_addon=staffing_addon,
            beo=beo,
        )

    # ── 采购加成 ───────────────────────────────────────────────────────────────

    def generate_procurement_addon(
        self,
        banquet:      Dict[str, Any],
        menu_package: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        基于宴会规模生成采购加成清单。

        公式：qty = party_size × grams_per_head × SAFETY_FACTOR / 1000 (kg)

        Args:
            banquet:      宴会预约（含 party_size）
            menu_package: 可选套餐覆盖，支持自定义 grams_per_head：
                          {"premium_meat": {"grams_per_head": 300}, ...}

        Returns:
            采购加成条目列表（item_name, recommended_quantity, unit, alert_level, source）
        """
        party_size = int(banquet.get("party_size") or 0)
        if party_size <= 0:
            return []

        addon:  List[Dict[str, Any]] = []
        pkg_overrides = menu_package or {}

        for ingredient in _BANQUET_INGREDIENTS:
            cat  = ingredient["category"]
            gpeh = pkg_overrides.get(cat, {}).get("grams_per_head", ingredient["grams_per_head"])
            unit = ingredient["unit"]

            raw_qty = party_size * gpeh * BANQUET_SAFETY_FACTOR

            # 换算到合适单位（液体用 L，固体用 kg）
            if unit in ("g", "ml"):
                display_qty  = round(raw_qty / 1000, 2)
                display_unit = "L" if unit == "ml" else "kg"
            else:
                display_qty  = round(raw_qty, 2)
                display_unit = unit

            addon.append({
                "item_name":            f"{ingredient['label']}（宴会加成）",
                "category":             cat,
                "current_stock":        None,            # 由 InventoryService 补充
                "recommended_quantity": display_qty,
                "unit":                 display_unit,
                "alert_level":          ingredient["urgency"],
                "supplier_name":        None,            # 由 SupplierService 补充
                "source":               "banquet_circuit_breaker",
                "party_size_basis":     party_size,
            })

        total_addon_cost = self._estimate_addon_cost(addon)

        logger.debug(
            "宴会采购加成生成",
            reservation_id=banquet.get("reservation_id"),
            party_size=party_size,
            addon_items=len(addon),
            estimated_cost=total_addon_cost,
        )
        return addon

    # ── 排班加成 ───────────────────────────────────────────────────────────────

    def generate_staffing_addon(
        self,
        banquet: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        基于宴会规模生成排班加成方案。

        Args:
            banquet: 宴会预约（含 party_size、reservation_time）

        Returns:
            {
                "roles": [{role, count, shift_start, shift_end, notes}],
                "total_addon_staff": int,
                "shift_notes": str,
            }
        """
        party_size = int(banquet.get("party_size") or 0)
        rules      = _BANQUET_STAFFING_RULES

        # 计算各岗位人数
        coordinator_count = rules["coordinator_fixed"]
        waiter_count      = max(1, party_size // rules["waiter_per_n_guests"])
        chef_count        = max(1, party_size // rules["chef_per_n_guests"])
        cashier_count     = rules["cashier_fixed"] + (1 if party_size >= 80 else 0)

        # 高级主厨（≥ 30 人升级）
        senior_chef_count = 0
        if party_size >= rules["senior_chef_threshold"]:
            senior_chef_count = 1
            chef_count        = max(0, chef_count - 1)  # 主厨替代一名普通厨师

        # 班次时间（基于宴会开始时间）
        raw_time = banquet.get("reservation_time")
        event_start, event_end, shift_start, shift_end = self._calc_shifts(raw_time)

        roles = []

        if coordinator_count:
            roles.append({
                "role":        "宴会协调员",
                "count":       coordinator_count,
                "shift_start": shift_start,
                "shift_end":   shift_end,
                "notes":       "全程跟场，对接客户",
            })

        roles.append({
            "role":        "服务员",
            "count":       waiter_count,
            "shift_start": shift_start,
            "shift_end":   shift_end,
            "notes":       f"每 {rules['waiter_per_n_guests']} 位客人配 1 人",
        })

        if senior_chef_count:
            roles.append({
                "role":        "主厨",
                "count":       senior_chef_count,
                "shift_start": shift_start,
                "shift_end":   shift_end,
                "notes":       "负责宴会主菜制作",
            })

        if chef_count > 0:
            roles.append({
                "role":        "厨师",
                "count":       chef_count,
                "shift_start": shift_start,
                "shift_end":   shift_end,
                "notes":       "协助备菜/配菜",
            })

        if cashier_count:
            roles.append({
                "role":        "收银",
                "count":       cashier_count,
                "shift_start": shift_start,
                "shift_end":   shift_end,
                "notes":       "结账 / 发票",
            })

        total_addon_staff = sum(r["count"] for r in roles)

        return {
            "roles":             roles,
            "total_addon_staff": total_addon_staff,
            "event_start":       event_start,
            "event_end":         event_end,
            "shift_start":       shift_start,
            "shift_end":         shift_end,
            "shift_notes":       (
                f"宴会 {event_start}~{event_end}，"
                f"员工 {shift_start} 进场 / {shift_end} 撤场"
            ),
            "source": "banquet_circuit_breaker",
        }

    # ── BEO 单生成 ────────────────────────────────────────────────────────────

    def generate_beo(
        self,
        banquet:      Dict[str, Any],
        store_id:     str  = "",
        plan_date:    Optional[date] = None,
        version:      int  = 1,
        operator:     str  = "system",
    ) -> Dict[str, Any]:
        """
        生成 BEO（Banquet Event Order）—— 宴会执行协调单。

        BEO 是各部门（厨房/前厅/采购）共享的事实来源，
        记录宴会详情、菜单版本、资源分配和变更历史。

        Args:
            banquet:   宴会预约数据
            store_id:  门店 ID
            plan_date: 规划日期
            version:   BEO 版本号（首次生成 = 1，更新时递增）
            operator:  操作人 ID（system / 店长ID）

        Returns:
            完整 BEO dict（可序列化为 JSON 存入 DecisionVersion.content）
        """
        now        = datetime.now().isoformat()
        plan_date  = plan_date or date.today() + timedelta(days=1)
        party_size = int(banquet.get("party_size") or 0)

        procurement_addon = self.generate_procurement_addon(banquet)
        staffing_addon    = self.generate_staffing_addon(banquet)

        estimated_budget = float(banquet.get("estimated_budget") or 0)
        deposit          = float(banquet.get("deposit", 0))

        beo = {
            # ── 元数据
            "beo_id":         f"BEO-{store_id}-{plan_date.isoformat()}-{banquet.get('reservation_id', 'UNKNOWN')}",
            "version":        version,
            "generated_at":   now,
            "generated_by":   operator,
            "store_id":       store_id,

            # ── 活动信息
            "event": {
                "reservation_id":   banquet.get("reservation_id"),
                "customer_name":    banquet.get("customer_name"),
                "customer_phone":   banquet.get("customer_phone"),
                "event_date":       plan_date.isoformat(),
                "event_type":       banquet.get("event_type", "宴会"),
                "reservation_time": banquet.get("reservation_time"),
                "party_size":       party_size,
                "venue":            banquet.get("venue"),
                "special_requests": banquet.get("special_requests", ""),
            },

            # ── 菜单快照
            "menu": {
                "package_name":      banquet.get("menu_package_name", "标准宴会套餐"),
                "snapshot_version":  banquet.get("menu_version", 1),
                "items":             banquet.get("menu_items", []),
                "last_changed_at":   banquet.get("menu_last_changed_at"),
                "change_log":        banquet.get("menu_change_log", []),
            },

            # ── 采购清单（来自熔断引擎）
            "procurement": {
                "items":            procurement_addon,
                "total_items":      len(procurement_addon),
                "procurement_note": f"宴会专属加成（{party_size} 人 × 安全系数 {BANQUET_SAFETY_FACTOR}）",
                "status":           "pending",           # pending / ordered / received
            },

            # ── 排班方案（来自熔断引擎）
            "staffing": {
                "roles":             staffing_addon.get("roles", []),
                "total_addon_staff": staffing_addon.get("total_addon_staff", 0),
                "shift_start":       staffing_addon.get("shift_start"),
                "shift_end":         staffing_addon.get("shift_end"),
                "shift_notes":       staffing_addon.get("shift_notes", ""),
                "status":            "draft",            # draft / confirmed / executed
            },

            # ── 财务摘要
            "finance": {
                "estimated_budget":  estimated_budget,
                "deposit_received":  deposit,
                "balance_due":       round(max(0, estimated_budget - deposit), 2),
                "payment_status":    "deposit_paid" if deposit > 0 else "unpaid",
                "currency":          "CNY",
            },

            # ── 变更日志（首次生成写入一条）
            "change_log": [
                {
                    "version":    version,
                    "changed_at": now,
                    "operator":   operator,
                    "changes":    [
                        {
                            "field":     "beo_created",
                            "old_value": None,
                            "new_value": f"v{version} 自动生成",
                        }
                    ],
                }
            ],

            # ── 熔断元信息
            "circuit_breaker": {
                "triggered":    True,
                "threshold":    BANQUET_CIRCUIT_THRESHOLD,
                "party_size":   party_size,
                "safety_factor": BANQUET_SAFETY_FACTOR,
            },
        }

        logger.info(
            "BEO 单已生成",
            beo_id=beo["beo_id"],
            party_size=party_size,
            procurement_items=len(procurement_addon),
            addon_staff=staffing_addon.get("total_addon_staff"),
        )
        return beo

    # ── 资源冲突检测 ──────────────────────────────────────────────────────────

    def check_resource_conflicts(
        self,
        banquets:     List[Dict[str, Any]],
        max_capacity: int = 200,
    ) -> Dict[str, Any]:
        """
        检测当日宴会的资源冲突：
          1. 场地容量超限：所有宴会同时客人总数 > max_capacity
          2. 场地时间重叠：同一场地在重叠时间段有多场宴会

        Args:
            banquets:     当日宴会预约列表（已触发熔断的）
            max_capacity: 场地最大接待人数（默认 200）

        Returns:
            {
                "has_conflict": bool,
                "conflicts": [{type, description, affected_reservations}]
            }
        """
        conflicts: List[Dict[str, Any]] = []

        if not banquets:
            return {"has_conflict": False, "conflicts": []}

        # 1. 容量检测
        total_party_size = sum(int(b.get("party_size") or 0) for b in banquets)
        if total_party_size > max_capacity:
            conflicts.append({
                "type":                   "capacity_exceeded",
                "description":            (
                    f"当日宴会合计 {total_party_size} 人，"
                    f"超过场地容量上限 {max_capacity} 人"
                ),
                "total_party_size":       total_party_size,
                "max_capacity":           max_capacity,
                "affected_reservations":  [b.get("reservation_id") for b in banquets],
            })

        # 2. 时间重叠检测（同一场地）
        venue_timeline: Dict[str, List[Tuple[str, str, str]]] = {}
        for b in banquets:
            venue = b.get("venue") or "default"
            raw_t = b.get("reservation_time")
            if not raw_t:
                continue
            s, e = self._parse_event_window(raw_t)
            venue_timeline.setdefault(venue, []).append((s, e, b.get("reservation_id", "")))

        for venue, slots in venue_timeline.items():
            slots.sort(key=lambda x: x[0])
            for i in range(len(slots) - 1):
                s1, e1, rid1 = slots[i]
                s2, e2, rid2 = slots[i + 1]
                if s2 < e1:  # 时间重叠
                    conflicts.append({
                        "type":        "time_overlap",
                        "description": (
                            f"场地「{venue}」时间冲突：预约 {rid1}（{s1}~{e1}）"
                            f" 与 {rid2}（{s2}~{e2}）重叠"
                        ),
                        "venue":       venue,
                        "affected_reservations": [rid1, rid2],
                    })

        return {
            "has_conflict": len(conflicts) > 0,
            "conflicts":    conflicts,
        }

    # ── Private helpers ───────────────────────────────────────────────────────

    def _calc_shifts(
        self,
        reservation_time: Optional[str],
    ) -> Tuple[str, str, str, str]:
        """
        计算班次时间：进场 = 宴会开始前 2h；撤场 = 宴会结束后 1h。

        Returns:
            (event_start, event_end, shift_start, shift_end)  各为 "HH:MM" 字符串
        """
        rules = _BANQUET_STAFFING_RULES

        if reservation_time:
            try:
                # 支持 "18:00"、"18:00:00"、"2024-01-01 18:00"
                raw = reservation_time.strip()
                if "T" in raw or " " in raw:
                    raw = raw.split("T")[-1].split(" ")[-1]
                parts = raw.split(":")
                h = int(parts[0])
                m = int(parts[1]) if len(parts) > 1 else 0
                event_start_t = time(h, m)
            except (ValueError, IndexError):
                event_start_t = time(18, 0)  # 默认晚宴 18:00
        else:
            event_start_t = time(18, 0)

        # 宴会时长估算：2.5 小时
        event_start_dt = datetime.combine(date.today(), event_start_t)
        event_end_dt   = event_start_dt + timedelta(hours=2, minutes=30)

        shift_start_dt = event_start_dt - timedelta(hours=rules["shift_before_event_h"])
        shift_end_dt   = event_end_dt   + timedelta(hours=rules["shift_after_event_h"])

        fmt = "%H:%M"
        return (
            event_start_dt.strftime(fmt),
            event_end_dt.strftime(fmt),
            shift_start_dt.strftime(fmt),
            shift_end_dt.strftime(fmt),
        )

    def _parse_event_window(
        self,
        reservation_time: str,
    ) -> Tuple[str, str]:
        """
        从预约时间推算宴会窗口（start, end）—— 用于时间重叠检测。

        Returns:
            ("HH:MM", "HH:MM")
        """
        _, _, shift_start, shift_end = self._calc_shifts(reservation_time)
        return shift_start, shift_end

    @staticmethod
    def _estimate_addon_cost(addon: List[Dict[str, Any]]) -> float:
        """
        粗略估算采购加成成本（用于日志 / BEO 财务摘要）。

        使用简单的单位价格映射；实际价格应由 SupplierService 提供。
        """
        # 单位价格（元/kg 或 元/L）— 仅用于粗略估算
        _UNIT_PRICE: Dict[str, float] = {
            "premium_meat":  80.0,
            "seafood":       120.0,
            "poultry":       35.0,
            "vegetables":    8.0,
            "rice_staples":  5.0,
            "condiments":    20.0,
            "beverages":     15.0,
            "desserts":      30.0,
        }
        total = 0.0
        for item in addon:
            cat   = item.get("category", "")
            qty   = float(item.get("recommended_quantity") or 0)
            price = _UNIT_PRICE.get(cat, 20.0)
            total += qty * price
        return round(total, 2)

    # ── BEO 持久化 ────────────────────────────────────────────────────────────

    async def save_beo(
        self,
        beo:          Dict[str, Any],
        banquet:      Dict[str, Any],
        db:           Any,
        operator:     str = "system",
    ) -> Optional[Any]:
        """
        将 BEO 单写入数据库（versioned）。

        如果该 reservation_id 已存在 BEO 记录，将旧记录的 is_latest 置为 False，
        然后创建新版本（version + 1）。

        Args:
            beo:      BanquetPlanningEngine.generate_beo() 的输出 dict
            banquet:  原始宴会预约数据（用于提取冗余字段）
            db:       AsyncSession
            operator: 操作人

        Returns:
            新创建的 BanquetEventOrder ORM 对象，或 None（失败时非致命）
        """
        try:
            from sqlalchemy import select, update
            from src.models.banquet_event_order import BanquetEventOrder, BEOStatus

            reservation_id = banquet.get("reservation_id", "")
            store_id       = beo.get("store_id", "")
            event_date_raw = beo.get("event", {}).get("event_date")

            # 解析 event_date
            from datetime import date as _date
            if isinstance(event_date_raw, str):
                try:
                    event_date_val = _date.fromisoformat(event_date_raw)
                except ValueError:
                    event_date_val = _date.today()
            elif isinstance(event_date_raw, _date):
                event_date_val = event_date_raw
            else:
                event_date_val = _date.today()

            # 查找当前最新版本号
            stmt = (
                select(BanquetEventOrder.version)
                .where(
                    BanquetEventOrder.store_id       == store_id,
                    BanquetEventOrder.reservation_id == reservation_id,
                    BanquetEventOrder.is_latest      == True,  # noqa: E712
                )
                .order_by(BanquetEventOrder.version.desc())
                .limit(1)
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
            new_version = (row + 1) if row else 1

            # 将旧版本 is_latest → False
            if row:
                await db.execute(
                    update(BanquetEventOrder)
                    .where(
                        BanquetEventOrder.store_id       == store_id,
                        BanquetEventOrder.reservation_id == reservation_id,
                        BanquetEventOrder.is_latest      == True,  # noqa: E712
                    )
                    .values(is_latest=False)
                )

            # 预算从元 → 分（避免浮点精度问题）
            budget_cents = int(
                float(banquet.get("estimated_budget") or 0) * 100
            )

            new_beo = BanquetEventOrder(
                store_id=store_id,
                reservation_id=reservation_id,
                event_date=event_date_val,
                version=new_version,
                is_latest=True,
                status=BEOStatus.DRAFT.value,
                content=beo,
                party_size=int(banquet.get("party_size") or 0),
                estimated_budget=budget_cents,
                circuit_triggered=beo.get("circuit_breaker", {}).get("triggered", False),
                generated_by=operator,
                change_summary=f"v{new_version} 自动生成（熔断引擎）",
            )
            db.add(new_beo)
            await db.flush()  # 获取 id，但不 commit（由调用方控制事务）

            logger.info(
                "BEO 已写入数据库",
                beo_id=str(new_beo.id),
                reservation_id=reservation_id,
                version=new_version,
                store_id=store_id,
            )
            return new_beo

        except Exception as e:
            logger.warning("BEO 持久化失败（非致命）", error=str(e))
            return None


# ── 全局单例 ──────────────────────────────────────────────────────────────────
banquet_planning_engine = BanquetPlanningEngine()
