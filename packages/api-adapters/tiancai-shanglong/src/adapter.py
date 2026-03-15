"""
天财商龙（吾享）餐饮开放 API 适配器

Base URL:   https://cysms.wuuxiang.com
文档来源:   http://doc.wuuxiang.com/showdoc/web/#/46
鉴权方式:   OAuth2 Token 换取（二步流程）
  Step 1: POST /api/auth/accesstoken  →  获取 access_token（expires_in 秒）
  Step 2: 后续请求 Header 带 access_token + accessid + granttype:client

核心接口:
  账单明细(分页): POST /api/datatransfer/getserialdata
  授权令牌获取:   POST /api/auth/accesstoken

环境变量（优先级低于 config 字典）:
  TIANCAI_BASE_URL   默认 https://cysms.wuuxiang.com
  TIANCAI_APPID      Terminal ID
  TIANCAI_ACCESSID   Terminal authorization ID
  TIANCAI_CENTER_ID  集团 centerId
  TIANCAI_SHOP_ID    门店 shopId
"""
import asyncio
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger()

_AUTH_PATH = "/api/auth/accesstoken"
_SERIAL_PATH = "/api/datatransfer/getserialdata"
_MAX_PAGE_SIZE = 500


class TiancaiShanglongAdapter:
    """
    天财商龙餐饮开放 API 适配器。

    Config 参数:
        base_url   : API 根地址（默认 https://cysms.wuuxiang.com）
        appid      : Terminal ID（用于获取 token）
        accessid   : Terminal authorization ID（用于获取 token + 请求 Header）
        center_id  : 集团 ID（接口参数 centerId）
        shop_id    : 门店 ID（接口参数 shopId）
        timeout    : HTTP 超时秒数（默认 30）
        retry_times: 重试次数（默认 3）
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        self.base_url = config.get(
            "base_url", os.getenv("TIANCAI_BASE_URL", "https://cysms.wuuxiang.com")
        ).rstrip("/")
        self.appid = config.get("appid", os.getenv("TIANCAI_APPID", ""))
        self.accessid = config.get("accessid", os.getenv("TIANCAI_ACCESSID", ""))
        self.center_id = config.get("center_id", os.getenv("TIANCAI_CENTER_ID", ""))
        self.shop_id = config.get("shop_id", os.getenv("TIANCAI_SHOP_ID", ""))
        self.timeout = config.get("timeout", int(os.getenv("TIANCAI_TIMEOUT", "30")))
        self.retry_times = config.get(
            "retry_times", int(os.getenv("TIANCAI_RETRY_TIMES", "3"))
        )

        if not self.appid or not self.accessid:
            logger.warning("天财商龙 appid/accessid 未配置，将使用降级模式")

        # Token 缓存（延迟初始化）
        self._access_token: str = ""
        self._token_expires_at: float = 0.0  # unix timestamp

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            follow_redirects=True,
        )
        logger.info("天财商龙适配器初始化", base_url=self.base_url, shop_id=self.shop_id)

    # ── Token 管理 ────────────────────────────────────────────────────────────

    async def _fetch_token(self) -> None:
        """
        POST /api/auth/accesstoken 获取新 token 并缓存。

        官方注意事项：
          - token 有效期由 expires_in（秒）决定，提前 60s 主动刷新
          - 重新获取会使旧 token 失效，高并发场景应避免并发获取
        """
        resp = await self._client.post(
            _AUTH_PATH,
            json={
                "appid": self.appid,
                "accessid": self.accessid,
                "response_type": "token",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if str(data.get("code", "-1")) != "0":
            raise Exception(f"天财商龙获取token失败: {data.get('msg', '未知错误')}")

        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 1200))
        self._token_expires_at = time.time() + expires_in - 60  # 提前60s刷新
        logger.info("天财商龙 token 已刷新", expires_in=expires_in)

    async def _ensure_token(self) -> str:
        """返回有效 token，必要时自动刷新。"""
        if not self._access_token or time.time() >= self._token_expires_at:
            await self._fetch_token()
        return self._access_token

    def _api_headers(self, token: str) -> Dict[str, str]:
        """构建 API 请求通用 Header。"""
        return {
            "Content-Type": "application/json",
            "access_token": token,
            "accessid": self.accessid,
            "granttype": "client",
        }

    # ── 核心请求方法 ─────────────────────────────────────────────────────────

    async def _request(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        POST 请求（含指数退避重试）。
        天财商龙响应格式: {"code": "0", "msg": "success", "data": {...}}
        """
        last_exc: Optional[Exception] = None

        for attempt in range(self.retry_times):
            if attempt > 0:
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

            try:
                token = await self._ensure_token()
                resp = await self._client.post(
                    path,
                    json=params or {},
                    headers=self._api_headers(token),
                )
                resp.raise_for_status()
                result = resp.json()

                if str(result.get("code", "-1")) != "0":
                    msg = result.get("msg", "未知错误")
                    raise Exception(f"天财商龙业务错误: {msg}")

                return result.get("data", result)

            except Exception as e:
                if "天财商龙业务错误" in str(e):
                    raise
                last_exc = e
                logger.warning(
                    "天财商龙请求失败，准备重试",
                    path=path,
                    attempt=attempt + 1,
                    error=str(e),
                )

        raise Exception(f"天财商龙请求失败，已重试 {self.retry_times} 次: {last_exc}")

    # ── 账单明细接口 ─────────────────────────────────────────────────────────

    async def get_serial_data(
        self,
        page_no: int = 1,
        page_size: int = 100,
        settle_date: Optional[str] = None,
        begin_date: Optional[str] = None,
        end_date: Optional[str] = None,
        date_type: Optional[int] = None,
        is_need_member: int = 1,
        order_type: Optional[str] = None,
        need_pkg_detail: int = 0,
    ) -> Dict[str, Any]:
        """
        账单明细查询（分页）。
        settle_date 与 begin_date/end_date 二选一。

        Args:
            page_no:         页码（从1开始）
            page_size:       每页条数（最大 500）
            settle_date:     营业日期 yyyy-MM-dd（按营业日查询）
            begin_date:      开始时间 yyyy-MM-dd HH:mm:ss（按时间范围）
            end_date:        结束时间 yyyy-MM-dd HH:mm:ss
            date_type:       时间过滤类型 1-5
            is_need_member:  是否返回会员信息 1=是（默认）
            order_type:      订单类型过滤 0-7
            need_pkg_detail: 是否返回套餐明细 0=否（默认）

        Returns:
            {"billList": [...], "pageInfo": {...}}
        """
        if not settle_date and not (begin_date and end_date):
            raise ValueError("settle_date 或 begin_date/end_date 必须填写一个")
        if not (1 <= page_size <= _MAX_PAGE_SIZE):
            raise ValueError(f"page_size 必须在 1~{_MAX_PAGE_SIZE}，实际: {page_size}")

        body: Dict[str, Any] = {
            "centerId": self.center_id,
            "shopId": self.shop_id,
            "pageNo": page_no,
            "pageSize": page_size,
            "isNeedMember": is_need_member,
            "needPkgDetail": need_pkg_detail,
        }
        if settle_date:
            body["settleDate"] = settle_date
        if begin_date:
            body["beginDate"] = begin_date
        if end_date:
            body["endDate"] = end_date
        if date_type is not None:
            body["dateType"] = date_type
        if order_type is not None:
            body["orderType"] = order_type

        logger.info("查询账单明细", settle_date=settle_date, page_no=page_no)
        return await self._request(_SERIAL_PATH, body)

    async def fetch_orders_by_date(
        self,
        date_str: str,
        page: int = 1,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """
        按营业日期分页拉取账单（统一分页格式，供 pull_daily_orders 使用）。

        Returns:
            {"items": [...raw bill dicts], "page": int, "page_size": int,
             "total": int, "has_more": bool}
        """
        raw = await self.get_serial_data(
            page_no=page,
            page_size=page_size,
            settle_date=date_str,
            is_need_member=1,
        )
        bill_list = raw.get("billList", [])
        page_info = raw.get("pageInfo", {})
        total = int(page_info.get("total", len(bill_list)))

        return {
            "items": bill_list,
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_more": page * page_size < total,
        }

    # ── 高层全量拉取（自动分页） ──────────────────────────────────────────────

    async def pull_daily_orders(
        self,
        date_str: str,
        brand_id: str,
        max_pages: int = 50,
    ) -> List[Any]:
        """
        拉取指定营业日的全量账单，自动翻页，返回 OrderSchema 列表。

        Args:
            date_str:  营业日期 YYYY-MM-DD
            brand_id:  品牌 ID（传入 to_order()）
            max_pages: 最大页数防护（默认 50 × 100 = 5000 条）
        """
        all_orders = []
        page = 1

        while page <= max_pages:
            result = await self.fetch_orders_by_date(date_str, page=page)
            for raw in result["items"]:
                try:
                    all_orders.append(self.to_order(raw, self.shop_id, brand_id))
                except Exception as exc:
                    logger.warning(
                        "tiancai_order_map_failed",
                        bs_id=raw.get("bs_id"),
                        error=str(exc),
                    )
            if not result["has_more"]:
                break
            page += 1

        logger.info(
            "tiancai_pull_daily_done",
            date=date_str,
            total=len(all_orders),
            pages=page,
        )
        return all_orders

    # ── 标准数据总线：字段映射 ────────────────────────────────────────────────

    def to_order(self, raw: Dict[str, Any], store_id: str, brand_id: str):
        """
        将天财商龙 getserialdata billList 单条记录映射到标准 OrderSchema。

        关键字段对应（来源：官方文档 #/46 page_id=460）：
          bs_id          → order_id
          bs_code        → order_number
          settle_time    → created_at（结账时间）
          open_time      → 开台时间
          point_code     → table_number（桌位编号）
          last_total     → total（实收，分）
          disc_total     → discount（折扣，分）
          orig_total     → subtotal（折前合计，分）
          state          → order_status (0=未结, 1=已结, 其他=特殊)
          member_card_no → customer_id
          waiter_code    → waiter_id
          item[]         → items（品项明细）
        """
        import sys
        import os as _os
        _src_dir = _os.path.dirname(__file__)
        _repo_root = _os.path.abspath(_os.path.join(_src_dir, "../../../.."))
        _gateway_src = _os.path.join(_repo_root, "apps", "api-gateway", "src")
        if _gateway_src not in sys.path:
            sys.path.insert(0, _gateway_src)

        from schemas.restaurant_standard_schema import (
            OrderSchema, OrderStatus, OrderType, OrderItemSchema, DishCategory,
        )

        # state: 0=未结 1=已结 其他=特殊（押金/存酒等）
        state = int(raw.get("state", 0))
        if state == 1:
            order_status = OrderStatus.COMPLETED
        elif state == 0:
            order_status = OrderStatus.PENDING
        else:
            order_status = OrderStatus.COMPLETED  # 特殊态按已完成处理

        # 品项明细映射
        items = []
        for idx, item in enumerate(raw.get("item", []), start=1):
            # orig_price / last_price 均以分为单位
            unit_price_fen = int(item.get("last_price", item.get("orig_price", 0)))
            unit_price = Decimal(unit_price_fen) / 100
            qty = Decimal(str(item.get("last_qty", item.get("orig_qty", 1))))
            subtotal = Decimal(str(item.get("last_total", 0))) / 100

            items.append(OrderItemSchema(
                item_id=str(item.get("item_id", f"{raw.get('bs_id', '')}_{idx}")),
                dish_id=str(item.get("item_code", item.get("item_id", ""))),
                dish_name=str(item.get("item_name", item.get("temp_item_name", ""))),
                dish_category=DishCategory.MAIN_COURSE,
                quantity=int(qty),
                unit_price=unit_price,
                subtotal=subtotal,
                special_requirements=None,
            ))

        total = Decimal(str(raw.get("last_total", 0))) / 100
        discount = Decimal(str(raw.get("disc_total", 0))) / 100
        subtotal = Decimal(str(raw.get("orig_total", 0))) / 100

        # 时间解析：优先 settle_time，退化到 open_time
        time_raw = raw.get("settle_time") or raw.get("open_time", "")
        try:
            created_at = datetime.fromisoformat(str(time_raw).replace("T", " "))
        except (ValueError, TypeError):
            created_at = datetime.now(timezone.utc).replace(tzinfo=None)

        return OrderSchema(
            order_id=str(raw.get("bs_id", "")),
            order_number=str(raw.get("bs_code", raw.get("bs_id", ""))),
            order_type=OrderType.DINE_IN,
            order_status=order_status,
            store_id=store_id,
            brand_id=brand_id,
            table_number=raw.get("point_code") or raw.get("point_name"),
            customer_id=raw.get("member_card_no") or raw.get("member_id"),
            items=items,
            subtotal=subtotal,
            discount=discount,
            service_charge=Decimal(str(raw.get("service_fee_income_money", 0))) / 100,
            total=total,
            created_at=created_at,
            waiter_id=raw.get("waiter_code") or raw.get("waiter_name"),
            notes=None,
        )

    def to_staff_action(self, raw: Dict[str, Any], store_id: str, brand_id: str):
        """
        将天财商龙操作记录映射为标准 StaffAction（付款修正、折扣操作等）。
        对应接口：付款修正记录 [page_id=27276]
        """
        import sys
        import os as _os
        _src_dir = _os.path.dirname(__file__)
        _repo_root = _os.path.abspath(_os.path.join(_src_dir, "../../../.."))
        _gateway_src = _os.path.join(_repo_root, "apps", "api-gateway", "src")
        if _gateway_src not in sys.path:
            sys.path.insert(0, _gateway_src)

        from schemas.restaurant_standard_schema import StaffAction

        time_raw = raw.get("action_time", raw.get("settle_time", raw.get("create_time", "")))
        try:
            created_at = datetime.fromisoformat(str(time_raw).replace("T", " "))
        except (ValueError, TypeError):
            created_at = datetime.now(timezone.utc).replace(tzinfo=None)

        amount_raw = raw.get("amount", raw.get("pay_money", raw.get("last_total")))
        amount = Decimal(str(amount_raw)) / 100 if amount_raw is not None else None

        return StaffAction(
            action_type=str(raw.get("action_type", raw.get("type", "unknown"))),
            brand_id=brand_id,
            store_id=store_id,
            operator_id=str(raw.get("operator_id", raw.get("waiter_code", ""))),
            amount=amount,
            reason=raw.get("reason"),
            approved_by=raw.get("approved_by"),
            created_at=created_at,
        )

    # ── 生命周期 ─────────────────────────────────────────────────────────────

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()
