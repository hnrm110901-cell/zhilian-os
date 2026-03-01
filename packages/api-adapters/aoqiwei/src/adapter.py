"""
奥琦玮供应链开放平台适配器
Base URL: https://openapi.acescm.cn  (HTTPS)
认证方式: AppKey + AppSecret + MD5签名（API方要求，非我方选择）
"""
import asyncio
import hashlib
import os
import re
import time
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx
import structlog

logger = structlog.get_logger()

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MAX_PAGE_SIZE = 500


def _validate_date(value: str, field: str) -> None:
    if not _DATE_RE.match(value):
        raise ValueError(f"{field} 格式错误，应为 YYYY-MM-DD，实际值: {value!r}")


class AoqiweiAdapter:
    """奥琦玮供应链开放平台适配器"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化适配器

        Args:
            config: 配置字典，包含:
                - base_url: API基础URL（应使用 HTTPS）
                - app_key: AppKey
                - app_secret: AppSecret
                - timeout: 超时时间（秒）
                - retry_times: 重试次数
        """
        self.base_url = config.get("base_url", os.getenv("AOQIWEI_BASE_URL", "https://openapi.acescm.cn"))
        self.app_key = config.get("app_key", os.getenv("AOQIWEI_APP_KEY", ""))
        self.app_secret = config.get("app_secret", os.getenv("AOQIWEI_APP_SECRET", ""))
        self.timeout = config.get("timeout", int(os.getenv("AOQIWEI_TIMEOUT", "30")))
        self.retry_times = config.get("retry_times", int(os.getenv("AOQIWEI_RETRY_TIMES", "3")))

        if self.base_url.startswith("http://"):
            logger.warning("奥琦玮 base_url 使用 HTTP 明文传输，建议改为 HTTPS", base_url=self.base_url)

        if not self.app_key or not self.app_secret:
            logger.warning("奥琦玮AppKey或AppSecret未配置，将使用降级模式")

        # 持久 HTTP client，避免每次请求重建 TCP 连接
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            follow_redirects=True,
        )

        logger.info("奥琦玮供应链适配器初始化", base_url=self.base_url)

    # ==================== 标准化数据总线接口 ====================

    def to_order(self, raw: Dict[str, Any], store_id: str, brand_id: str):
        """
        将奥琦玮原始订单字段映射到标准 OrderSchema

        奥琦玮 POS 订单字段参考：
          orderNo, shopCode, orderDate, orderStatus, totalAmount,
          discountAmount, items (list of goodCode, goodName, qty, price)
        """
        import sys
        import os as _os
        _repo_root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../../.."))
        if _repo_root not in sys.path:
            sys.path.insert(0, _repo_root)

        from apps.api_gateway.src.schemas.restaurant_standard_schema import (
            OrderSchema, OrderStatus, OrderType, OrderItemSchema, DishCategory
        )

        # 状态映射
        _STATUS_MAP = {
            "0": OrderStatus.PENDING,
            "1": OrderStatus.CONFIRMED,
            "2": OrderStatus.COMPLETED,
            "3": OrderStatus.CANCELLED,
        }
        raw_status = str(raw.get("orderStatus", "0"))
        order_status = _STATUS_MAP.get(raw_status, OrderStatus.PENDING)

        # 订单项映射
        items = []
        for idx, item in enumerate(raw.get("items", []), start=1):
            unit_price = Decimal(str(item.get("price", 0))) / 100  # 分 → 元
            qty = int(item.get("qty", item.get("quantity", 1)))
            items.append(OrderItemSchema(
                item_id=str(item.get("orderItemNo", f"{raw.get('orderNo', '')}_{idx}")),
                dish_id=str(item.get("goodCode", item.get("goodId", ""))),
                dish_name=str(item.get("goodName", "")),
                dish_category=DishCategory.MAIN_COURSE,
                quantity=qty,
                unit_price=unit_price,
                subtotal=unit_price * qty,
                special_requirements=item.get("remark"),
            ))

        total = Decimal(str(raw.get("totalAmount", raw.get("realAmount", 0)))) / 100
        discount = Decimal(str(raw.get("discountAmount", raw.get("specialOfferPrice", 0)))) / 100
        subtotal = total + discount

        order_date_raw = raw.get("orderDate", raw.get("orderTime", ""))
        try:
            created_at = datetime.fromisoformat(str(order_date_raw).replace("T", " "))
        except (ValueError, TypeError):
            created_at = datetime.utcnow()

        return OrderSchema(
            order_id=str(raw.get("orderId", raw.get("id", ""))),
            order_number=str(raw.get("orderNo", "")),
            order_type=OrderType.DINE_IN,
            order_status=order_status,
            store_id=store_id,
            brand_id=brand_id,
            table_number=raw.get("tableNo"),
            customer_id=raw.get("memberId"),
            items=items,
            subtotal=subtotal,
            discount=discount,
            service_charge=Decimal("0"),
            total=total,
            created_at=created_at,
            waiter_id=raw.get("waiterId"),
            notes=raw.get("remark"),
        )

    def to_staff_action(self, raw: Dict[str, Any], store_id: str, brand_id: str):
        """
        将奥琦玮原始操作数据映射为标准 StaffAction

        原始字段参考（POS 操作日志）：
          actionType, operatorId, amount, reason, approvedBy, actionTime
        """
        import sys
        import os as _os
        _repo_root = _os.path.abspath(_os.path.join(_os.path.dirname(__file__), "../../../../.."))
        if _repo_root not in sys.path:
            sys.path.insert(0, _repo_root)

        from apps.api_gateway.src.schemas.restaurant_standard_schema import StaffAction

        action_time_raw = raw.get("actionTime", raw.get("createdAt", ""))
        try:
            created_at = datetime.fromisoformat(str(action_time_raw).replace("T", " "))
        except (ValueError, TypeError):
            created_at = datetime.utcnow()

        amount_raw = raw.get("amount", raw.get("discountAmount"))
        amount = Decimal(str(amount_raw)) / 100 if amount_raw is not None else None

        return StaffAction(
            action_type=str(raw.get("actionType", "unknown")),
            brand_id=brand_id,
            store_id=store_id,
            operator_id=str(raw.get("operatorId", raw.get("staffId", ""))),
            amount=amount,
            reason=raw.get("reason"),
            approved_by=raw.get("approvedBy"),
            created_at=created_at,
        )

    async def aclose(self) -> None:

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.aclose()

    def _sign(self, params: Dict[str, Any]) -> str:
        """
        生成请求签名

        算法（API方要求）：
          1. 将所有参数按 key 字母序排列
          2. 拼接为 key=value&key=value...（跳过 None 和空字符串）
          3. 末尾追加 AppSecret
          4. 对整体做 MD5（小写 hex）

        注意：MD5 是 API 方要求的算法，非我方选择。
        警告：不要在此方法内打印 raw 字符串，否则会泄露 AppSecret。

        Args:
            params: 请求参数（不含 sign 字段，值必须为标量类型）

        Returns:
            签名字符串（32位小写MD5）
        """
        sorted_keys = sorted(params.keys())
        parts = []
        for k in sorted_keys:
            v = params[k]
            if v is None or v == "":
                continue
            # 只允许标量类型参与签名，复杂类型会导致签名错误
            if isinstance(v, (dict, list)):
                raise TypeError(f"签名参数 {k!r} 不能是 dict/list 类型，请先序列化为字符串")
            parts.append(f"{k}={v}")
        raw = "&".join(parts) + self.app_secret
        return hashlib.md5(raw.encode("utf-8")).hexdigest().lower()

    def _build_params(self, biz_params: Dict[str, Any]) -> Dict[str, Any]:
        """构建带公共参数和签名的完整请求体"""
        params: Dict[str, Any] = {
            "appKey": self.app_key,
            "timestamp": str(int(time.time() * 1000)),
        }
        params.update(biz_params)
        params["sign"] = self._sign(params)
        return params

    async def _request(
        self,
        endpoint: str,
        biz_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        发送 POST 请求，带指数退避重试

        Args:
            endpoint: API端点路径（如 /api/stock_v1/remain.html）
            biz_params: 业务参数（标量值）

        Returns:
            API响应 data 字段

        Raises:
            Exception: 请求失败或业务错误（不可重试的业务错误立即抛出）
        """
        params = self._build_params(biz_params or {})
        last_exc: Optional[Exception] = None

        for attempt in range(self.retry_times):
            if attempt > 0:
                # 指数退避：0.5s, 1s, 2s, ...
                await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

            try:
                response = await self._client.post(endpoint, json=params)
                response.raise_for_status()
                result = response.json()

                # 奥琦玮通用响应格式：{"code": 0, "msg": "success", "data": {...}}
                code = result.get("code", result.get("errcode", 0))
                if code != 0:
                    msg = result.get("msg", result.get("errmsg", "未知错误"))
                    # 业务错误不重试，直接抛出
                    raise Exception(f"奥琦玮API业务错误 [{code}]: {msg}")

                return result.get("data", result)

            except Exception as e:
                if "奥琦玮API业务错误" in str(e):
                    raise  # 业务错误不重试
                last_exc = e
                logger.warning(
                    "请求失败，准备重试",
                    endpoint=endpoint,
                    attempt=attempt + 1,
                    max_attempts=self.retry_times,
                    error=str(e),
                )

        raise Exception(f"请求失败，已重试 {self.retry_times} 次: {last_exc}")

    # ==================== POS订单接口 ====================

    async def pos_upload_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """POS订单上传"""
        logger.info("POS订单上传", order_no=order_data.get("orderNo"))
        try:
            return await self._request("/api/pos/order.html", order_data)
        except Exception as e:
            logger.warning("POS订单上传失败", error=str(e))
            return {"success": False, "message": str(e)}

    async def pos_check_order(self, shop_code: str, date: str) -> Dict[str, Any]:
        """POS订单校验"""
        _validate_date(date, "date")
        logger.info("POS订单校验", shop_code=shop_code, date=date)
        try:
            return await self._request("/api/pos/ordercheck.html", {"shopCode": shop_code, "date": date})
        except Exception as e:
            logger.warning("POS订单校验失败", error=str(e))
            return {"checked": False, "message": str(e)}

    async def pos_day_done(self, shop_code: str, date: str) -> Dict[str, Any]:
        """POS日结"""
        _validate_date(date, "date")
        logger.info("POS日结", shop_code=shop_code, date=date)
        try:
            return await self._request("/api/pos/daydone.html", {"shopCode": shop_code, "date": date})
        except Exception as e:
            logger.warning("POS日结失败", error=str(e))
            return {"success": False, "message": str(e)}

    # ==================== 库存接口 ====================

    async def query_stock(
        self,
        depot_code: Optional[str] = None,
        shop_code: Optional[str] = None,
        good_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """查询库存"""
        params: Dict[str, Any] = {}
        if depot_code:
            params["depotCode"] = depot_code
        if shop_code:
            params["shopCode"] = shop_code
        if good_code:
            params["goodCode"] = good_code

        logger.info("查询库存", params=params)
        try:
            result = await self._request("/api/stock_v1/remain.html", params)
            return result if isinstance(result, list) else result.get("list", [])
        except Exception as e:
            logger.warning("查询库存失败，返回空列表", error=str(e))
            return []

    async def query_stock_estimate(
        self,
        shop_code: str,
        start_date: str,
        end_date: str,
    ) -> Dict[str, Any]:
        """库存预估"""
        _validate_date(start_date, "start_date")
        _validate_date(end_date, "end_date")
        logger.info("库存预估", shop_code=shop_code)
        try:
            return await self._request(
                "/api/stock_v1/estimate.html",
                {"shopCode": shop_code, "startDate": start_date, "endDate": end_date},
            )
        except Exception as e:
            logger.warning("库存预估失败", error=str(e))
            return {}

    # ==================== 货品接口 ====================

    async def query_goods(
        self,
        good_code: Optional[str] = None,
        good_name: Optional[str] = None,
        page: int = 1,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """查询货品信息"""
        if page < 1:
            raise ValueError(f"page 必须 >= 1，实际值: {page}")
        if not (1 <= page_size <= _MAX_PAGE_SIZE):
            raise ValueError(f"page_size 必须在 1~{_MAX_PAGE_SIZE} 之间，实际值: {page_size}")

        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        if good_code:
            params["goodCode"] = good_code
        if good_name:
            params["goodName"] = good_name

        logger.info("查询货品", params=params)
        try:
            return await self._request("/api/basic/good.html", params)
        except Exception as e:
            logger.warning("查询货品失败", error=str(e))
            return {"list": [], "total": 0}

    async def query_suppliers(
        self,
        supplier_code: Optional[str] = None,
        page: int = 1,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """查询供应商信息"""
        if not (1 <= page_size <= _MAX_PAGE_SIZE):
            raise ValueError(f"page_size 必须在 1~{_MAX_PAGE_SIZE} 之间，实际值: {page_size}")

        params: Dict[str, Any] = {"page": page, "pageSize": page_size}
        if supplier_code:
            params["supplierCode"] = supplier_code

        logger.info("查询供应商", params=params)
        try:
            return await self._request("/api/basic/supplier.html", params)
        except Exception as e:
            logger.warning("查询供应商失败", error=str(e))
            return {"list": [], "total": 0}

    # ==================== 配送业务接口 ====================

    async def create_delivery_apply(self, apply_data: Dict[str, Any]) -> Dict[str, Any]:
        """创建配送申请单"""
        logger.info("创建配送申请", shop_code=apply_data.get("shopCode"))
        try:
            return await self._request("/api/delivery_v1/applygood.html", apply_data)
        except Exception as e:
            logger.warning("创建配送申请失败", error=str(e))
            return {"success": False, "message": str(e)}

    async def query_delivery_dispatch_out(
        self,
        start_date: str,
        end_date: str,
        shop_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """查询配送出库单"""
        _validate_date(start_date, "start_date")
        _validate_date(end_date, "end_date")
        params: Dict[str, Any] = {"startDate": start_date, "endDate": end_date}
        if shop_code:
            params["shopCode"] = shop_code

        logger.info("查询配送出库单", params=params)
        try:
            result = await self._request("/api/delivery_v1/dispatchout.html", params)
            return result if isinstance(result, list) else result.get("list", [])
        except Exception as e:
            logger.warning("查询配送出库单失败", error=str(e))
            return []

    async def confirm_delivery_in(self, dispatch_in_data: Dict[str, Any]) -> Dict[str, Any]:
        """配送入库确认（门店收货）"""
        logger.info("配送入库确认", order_no=dispatch_in_data.get("orderNo"))
        try:
            return await self._request("/api/delivery_v1/dispatchin.html", dispatch_in_data)
        except Exception as e:
            logger.warning("配送入库确认失败", error=str(e))
            return {"success": False, "message": str(e)}

    # ==================== 采购业务接口 ====================

    async def query_purchase_orders(
        self,
        start_date: str,
        end_date: str,
        depot_code: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """查询采购入库单"""
        _validate_date(start_date, "start_date")
        _validate_date(end_date, "end_date")
        if not (1 <= page_size <= _MAX_PAGE_SIZE):
            raise ValueError(f"page_size 必须在 1~{_MAX_PAGE_SIZE} 之间，实际值: {page_size}")

        params: Dict[str, Any] = {
            "startDate": start_date,
            "endDate": end_date,
            "page": page,
            "pageSize": page_size,
        }
        if depot_code:
            params["depotCode"] = depot_code

        logger.info("查询采购入库单", params=params)
        try:
            return await self._request("/api/purchase/pur_order.html", params)
        except Exception as e:
            logger.warning("查询采购入库单失败", error=str(e))
            return {"list": [], "total": 0}

    async def create_reserve_order(self, reserve_data: Dict[str, Any]) -> Dict[str, Any]:
        """创建采购订货单"""
        logger.info("创建采购订货单", depot_code=reserve_data.get("depotCode"))
        try:
            return await self._request("/api/purchase/reserve_order.html", reserve_data)
        except Exception as e:
            logger.warning("创建采购订货单失败", error=str(e))
            return {"success": False, "message": str(e)}

    # ==================== 数据报表接口 ====================

    async def query_inventory_report(
        self,
        start_date: str,
        end_date: str,
        shop_code: Optional[str] = None,
        good_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """查询进销存报表"""
        _validate_date(start_date, "start_date")
        _validate_date(end_date, "end_date")
        params: Dict[str, Any] = {"startDate": start_date, "endDate": end_date}
        if shop_code:
            params["shopCode"] = shop_code
        if good_code:
            params["goodCode"] = good_code

        logger.info("查询进销存报表", params=params)
        try:
            return await self._request("/api/report/invocingcost.html", params)
        except Exception as e:
            logger.warning("查询进销存报表失败", error=str(e))
            return {"list": [], "total": 0}

    async def query_good_diff_analysis(
        self,
        start_date: str,
        end_date: str,
        shop_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """货品差异分析"""
        _validate_date(start_date, "start_date")
        _validate_date(end_date, "end_date")
        params: Dict[str, Any] = {"startDate": start_date, "endDate": end_date}
        if shop_code:
            params["shopCode"] = shop_code

        logger.info("货品差异分析", params=params)
        try:
            return await self._request("/api/report/goodDiffAnalyse.html", params)
        except Exception as e:
            logger.warning("货品差异分析失败", error=str(e))
            return {"list": []}
