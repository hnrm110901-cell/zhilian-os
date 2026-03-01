"""
品智收银系统API适配器
提供门店管理、菜品管理、订单查询、营业数据等功能
"""
import os
from decimal import Decimal
from datetime import datetime
from typing import Dict, Any, Optional, List
import structlog
import asyncio
import httpx
from .signature import generate_sign

logger = structlog.get_logger()


class PinzhiAdapter:
    """品智收银系统适配器"""

    def __init__(self, config: Dict[str, Any]):
        """
        初始化适配器

        Args:
            config: 配置字典，包含:
                - base_url: API基础URL
                - token: API Token
                - timeout: 超时时间（秒）
                - retry_times: 重试次数
        """
        self.config = config
        self.base_url = config.get("base_url")
        self.token = config.get("token")
        self.timeout = config.get("timeout", 30)
        self.retry_times = config.get("retry_times", 3)

        if not self.base_url:
            raise ValueError("base_url不能为空")
        if not self.token:
            raise ValueError("token不能为空")

        # 初始化HTTP客户端
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            follow_redirects=True,
        )

        logger.info("品智适配器初始化", base_url=self.base_url)

    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        发送HTTP请求

        Args:
            method: HTTP方法 (GET/POST)
            endpoint: API端点
            params: URL参数
            data: 请求体数据

        Returns:
            API响应数据

        Raises:
            Exception: 请求失败
        """
        for attempt in range(self.retry_times):
            try:
                if method.upper() == "GET":
                    response = await self.client.get(endpoint, params=params)
                elif method.upper() == "POST":
                    response = await self.client.post(endpoint, json=data)
                else:
                    raise ValueError(f"不支持的HTTP方法: {method}")

                response.raise_for_status()
                result = response.json()
                self.handle_error(result)
                return result

            except httpx.HTTPStatusError as e:
                logger.error(
                    "HTTP请求失败",
                    endpoint=endpoint,
                    status_code=e.response.status_code,
                    attempt=attempt + 1,
                )
                if attempt == self.retry_times - 1:
                    raise Exception(f"HTTP请求失败: {e.response.status_code}")
                await asyncio.sleep(0.5 * (2 ** attempt))

            except Exception as e:
                logger.error(
                    "请求异常",
                    endpoint=endpoint,
                    error=str(e),
                    attempt=attempt + 1,
                )
                if attempt == self.retry_times - 1:
                    raise
                await asyncio.sleep(0.5 * (2 ** attempt))

        raise Exception("请求失败，已达到最大重试次数")

    def _add_sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        为请求参数添加签名

        Args:
            params: 请求参数

        Returns:
            添加签名后的参数
        """
        sign = generate_sign(self.token, params)
        params["sign"] = sign
        return params

    def handle_error(self, response: Dict[str, Any]) -> None:
        """
        处理业务错误

        Args:
            response: API响应数据

        Raises:
            Exception: 业务错误
        """
        # 品智系统使用success字段，0表示成功
        success = response.get("success")
        if success is not None and success != 0:
            msg = response.get("msg", "未知错误")
            raise Exception(f"品智API错误 [{success}]: {msg}")

        # 有些接口使用errcode字段
        errcode = response.get("errcode")
        if errcode is not None and errcode != 0:
            errmsg = response.get("errmsg", "未知错误")
            raise Exception(f"品智API错误 [{errcode}]: {errmsg}")

    # ==================== 基础数据接口 ====================

    async def get_store_info(self, ognid: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        查询门店信息

        Args:
            ognid: 门店omsID，不传则返回所有门店

        Returns:
            门店信息列表
        """
        params = {}
        if ognid:
            params["ognid"] = ognid

        params = self._add_sign(params)
        logger.info("查询门店信息", ognid=ognid)

        response = await self._request("GET", "/pinzhi/storeInfo.do", params=params)
        return response.get("res", [])

    async def get_dish_categories(self) -> List[Dict[str, Any]]:
        """
        查询菜品类别

        Returns:
            菜品类别列表
        """
        params = self._add_sign({})
        logger.info("查询菜品类别")

        response = await self._request("GET", "/pinzhi/reportcategory.do", params=params)
        return response.get("data", [])

    async def get_dishes(self, updatetime: int = 0) -> List[Dict[str, Any]]:
        """
        查询菜品信息

        Args:
            updatetime: 同步时间戳，传0拉取所有，传日期拉取该日期后修改的菜品

        Returns:
            菜品信息列表
        """
        params = {"updatetime": updatetime}
        params = self._add_sign(params)
        logger.info("查询菜品信息", updatetime=updatetime)

        try:
            response = await self._request("POST", "/pinzhi/querydishes.do", data=params)
            return response.get("data", [])
        except Exception as e:
            logger.warning("查询菜品失败", error=str(e))
            return []

    async def get_practice(self) -> List[Dict[str, Any]]:
        """
        查询做法和配料信息

        Returns:
            做法和配料列表
        """
        params = self._add_sign({})
        logger.info("查询做法配料")

        try:
            response = await self._request("POST", "/pinzhi/queryPractice.do", data=params)
            return response.get("data", [])
        except Exception as e:
            logger.warning("查询做法配料失败", error=str(e))
            return []

    async def get_tables(self) -> List[Dict[str, Any]]:
        """
        查询收银桌台信息

        Returns:
            桌台信息列表
        """
        params = self._add_sign({})
        logger.info("查询桌台信息")

        try:
            response = await self._request("GET", "/pinzhi/queryTable.do", params=params)
            return response.get("res", [])
        except Exception as e:
            logger.warning("查询桌台失败", error=str(e))
            return []

    async def get_employees(self) -> List[Dict[str, Any]]:
        """
        查询门店用户（员工）信息

        Returns:
            员工信息列表
        """
        params = self._add_sign({})
        logger.info("查询员工信息")

        try:
            response = await self._request("GET", "/pinzhi/employe.do", params=params)
            return response.get("data", [])
        except Exception as e:
            logger.warning("查询员工失败", error=str(e))
            return []

    # ==================== 业务数据接口 ====================

    async def query_orders(
        self,
        ognid: Optional[str] = None,
        begin_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page_index: int = 1,
        page_size: int = int(os.getenv("PINZHI_PAGE_SIZE", "20")),
    ) -> List[Dict[str, Any]]:
        """
        按日期查询订单数据（V2）

        Args:
            ognid: 门店omsID
            begin_date: 开始日期（yyyy-MM-dd）
            end_date: 结束日期（yyyy-MM-dd）
            page_index: 页码
            page_size: 每页数量

        Returns:
            订单列表
        """
        params = {"pageIndex": page_index, "pageSize": page_size}

        if ognid:
            params["ognid"] = ognid
        if begin_date:
            params["beginDate"] = begin_date
        if end_date:
            params["endDate"] = end_date

        params = self._add_sign(params)
        logger.info(
            "查询订单",
            ognid=ognid,
            begin_date=begin_date,
            end_date=end_date,
            page=page_index,
        )

        response = await self._request("GET", "/pinzhi/queryOrderListV2.do", params=params)
        return response.get("res", [])

    async def query_order_summary(
        self, ognid: str, business_date: str
    ) -> Dict[str, Any]:
        """
        按门店查询收入数据

        Args:
            ognid: 门店omsID
            business_date: 营业日（yyyy-MM-dd）

        Returns:
            收入汇总数据
        """
        params = {"ognid": ognid, "businessDate": business_date}
        params = self._add_sign(params)
        logger.info("查询收入数据", ognid=ognid, business_date=business_date)

        try:
            response = await self._request("GET", "/pinzhi/queryOrderSummary.do", params=params)
            return response.get("res", {})
        except Exception as e:
            logger.warning("查询收入数据失败", error=str(e))
            return {}

    async def query_store_summary_list(
        self, business_date: str
    ) -> List[Dict[str, Any]]:
        """
        查询所有门店营业额及菜类销售数据

        Args:
            business_date: 营业日（yyyy-MM-dd）

        Returns:
            门店营业数据列表
        """
        params = {"businessDate": business_date}
        params = self._add_sign(params)
        logger.info("查询门店营业数据", business_date=business_date)

        try:
            response = await self._request("GET", "/pinzhi/queryStoreSummaryList.do", params=params)
            return response.get("data", [])
        except Exception as e:
            logger.warning("查询门店营业数据失败", error=str(e))
            return []

    async def query_cooking_detail(self, business_date: str) -> List[Dict[str, Any]]:
        """
        查询门店出品过程明细数据

        Args:
            business_date: 营业日（yyyy-MM-dd）

        Returns:
            出品过程明细列表
        """
        params = {"businessDate": business_date}
        params = self._add_sign(params)
        logger.info("查询出品明细", business_date=business_date)

        try:
            response = await self._request("GET", "/pinzhi/queryCookingDetail.do", params=params)
            return response.get("data", [])
        except Exception as e:
            logger.warning("查询出品明细失败", error=str(e))
            return []

    async def get_payment_customer(
        self,
        begin_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        查询挂账客户管理

        Args:
            begin_date: 查询开始时间
            end_date: 查询结束时间

        Returns:
            挂账客户列表
        """
        params = {}
        if begin_date:
            params["beginDate"] = begin_date
        if end_date:
            params["endDate"] = end_date

        params = self._add_sign(params)
        logger.info("查询挂账客户", begin_date=begin_date, end_date=end_date)

        try:
            response = await self._request("GET", "/pinzhi/paymentCustomer.do", params=params)
            return response.get("data", [])
        except Exception as e:
            logger.warning("查询挂账客户失败", error=str(e))
            return []

    async def query_ogn_daily_biz_data(
        self,
        business_date: str,
        ognid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        查询门店每日经营数据（报表核心）

        Args:
            business_date: 营业日（yyyy-MM-dd）
            ognid: 门店omsID，不传则全部门店

        Returns:
            含 sum（consumeAmount_餐段_类型、dishList）及 list 明细
        """
        params = {"businessDate": business_date}
        if ognid:
            params["ognid"] = ognid
        params = self._add_sign(params)
        logger.info("查询门店每日经营数据", business_date=business_date, ognid=ognid)

        try:
            response = await self._request(
                "GET", "/pinzhi/queryOgnDailyBizData.do", params=params
            )
            return response.get("res", response.get("data", {}))
        except Exception as e:
            logger.warning("查询门店每日经营数据失败", error=str(e))
            return {}

    async def get_organizations(self) -> List[Dict[str, Any]]:
        """
        查询组织/机构列表

        Returns:
            组织/机构列表
        """
        params = self._add_sign({})
        logger.info("查询组织/机构")

        try:
            response = await self._request("GET", "/pinzhi/organizations.do", params=params)
            return response.get("data", response.get("res", []))
        except Exception as e:
            logger.warning("查询组织/机构失败", error=str(e))
            return []

    async def get_pay_types(self) -> List[Dict[str, Any]]:
        """
        查询支付方式（优先 payType.do，失败则尝试 payment.do）

        Returns:
            支付方式列表
        """
        params = self._add_sign({})
        logger.info("查询支付方式")

        for path in ["/pinzhi/payType.do", "/pinzhi/payment.do"]:
            try:
                response = await self._request("GET", path, params=params)
                return response.get("data", response.get("res", []))
            except Exception as e:
                logger.warning("查询支付方式失败", path=path, error=str(e))
        return []

    async def download_bill_data(
        self, ognid: str, pay_date: str, pay_type: int
    ) -> str:
        """
        下载微信支付宝订单数据

        Args:
            ognid: 门店omsID
            pay_date: 日期（yyyy-MM-dd）
            pay_type: 支付类型（1-微信，2-支付宝）

        Returns:
            对账单数据
        """
        params = {"ognid": ognid, "payDate": pay_date, "payType": pay_type}
        params = self._add_sign(params)
        logger.info(
            "下载对账单", ognid=ognid, pay_date=pay_date, pay_type=pay_type
        )

        try:
            response = await self._request("GET", "/pinzhi/downloadBillData.do", params=params)
            return response.get("data", "")
        except Exception as e:
            logger.warning("下载对账单失败", error=str(e))
            return ""

    async def run_all_checks(
        self,
        business_date: Optional[str] = None,
        ognid: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        一次性检测所有对接接口是否成功（不降级，真实请求结果）。

        Args:
            business_date: 营业日 yyyy-MM-dd，不传则用昨天
            ognid: 门店 omsID，部分接口需要

        Returns:
            [{"name": "接口名", "endpoint": "xxx.do", "ok": True/False, "message": "", "required": True/False}, ...]
        """
        from datetime import datetime, timedelta

        if not business_date:
            business_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # 定义所有检测项：name, method, endpoint, params_builder, required(核心=True)
        checks = [
            ("门店信息", "GET", "/pinzhi/storeInfo.do", lambda: {"ognid": ognid} if ognid else {}, True),
            ("门店每日经营数据(报表)", "GET", "/pinzhi/queryOgnDailyBizData.do", lambda: {"businessDate": business_date, **({"ognid": ognid} if ognid else {})}, True),
            ("按门店收入数据", "GET", "/pinzhi/queryOrderSummary.do", lambda: {"ognid": ognid or "", "businessDate": business_date}, True),  # 无 ognid 时可能报错，仍尝试
            ("订单列表V2", "GET", "/pinzhi/queryOrderListV2.do", lambda: {"beginDate": business_date, "endDate": business_date, "pageIndex": 1, "pageSize": 5}, True),
            ("菜品类别", "GET", "/pinzhi/reportcategory.do", lambda: {}, True),
            ("支付方式", "GET", "/pinzhi/payType.do", lambda: {}, True),
            ("支付方式(payment)", "GET", "/pinzhi/payment.do", lambda: {}, False),  # 部分环境用 payment.do
            ("组织/机构", "GET", "/pinzhi/organizations.do", lambda: {}, False),
            ("所有门店营业额", "GET", "/pinzhi/queryStoreSummaryList.do", lambda: {"businessDate": business_date}, False),
            ("出品过程明细", "GET", "/pinzhi/queryCookingDetail.do", lambda: {"businessDate": business_date}, False),
            ("挂账客户", "GET", "/pinzhi/paymentCustomer.do", lambda: {}, False),
            ("桌台信息", "GET", "/pinzhi/queryTable.do", lambda: {}, False),
            ("门店用户(employe)", "GET", "/pinzhi/employe.do", lambda: {}, False),
        ]

        core_names = {
            "门店信息",
            "门店每日经营数据(报表)",
            "按门店收入数据",
            "订单列表V2",
            "菜品类别",
            "支付方式",
        }
        results = []
        for name, method, endpoint, params_builder, _ in checks:
            required = name in core_names
            params = {k: v for k, v in params_builder().items() if v is not None and v != ""}
            try:
                p = self._add_sign(params)
                if method == "GET":
                    r = await self._request(method, endpoint, params=p)
                else:
                    r = await self._request(method, endpoint, data=p)
                # 解析条数
                count = ""
                if isinstance(r, dict):
                    for key in ("res", "data"):
                        val = r.get(key)
                        if isinstance(val, list):
                            count = f"共{len(val)}条"
                            break
                        if isinstance(val, dict) and "list" in val:
                            count = f"list共{len(val.get('list', []))}条"
                            break
                results.append({
                    "name": name,
                    "endpoint": endpoint.split("/")[-1],
                    "ok": True,
                    "message": count or "成功",
                    "required": required,
                })
            except Exception as e:
                results.append({
                    "name": name,
                    "endpoint": endpoint.split("/")[-1],
                    "ok": False,
                    "message": str(e)[:80],
                    "required": required,
                })
        return results

    async def close(self):
        """关闭适配器，释放资源"""
        logger.info("关闭品智适配器")
        await self.client.aclose()

    # ==================== 标准化数据总线接口 ====================

    def to_order(self, raw: Dict[str, Any], store_id: str, brand_id: str):
        """
        将品智原始订单字段映射到标准 OrderSchema

        品智订单字段参考（queryOrderListV2.do）：
          billId, billNo, orderSource, tableNo, openTime, payTime,
          dishPriceTotal, specialOfferPrice, realPrice, billStatus,
          openOrderUser, cashiers, paymentList
        """
        import sys
        import os as _os
        _src_dir = _os.path.dirname(__file__)
        _repo_root = _os.path.abspath(_os.path.join(_src_dir, "../../../.."))
        _gateway_src = _os.path.join(_repo_root, "apps", "api-gateway", "src")
        if _gateway_src not in sys.path:
            sys.path.insert(0, _gateway_src)

        from schemas.restaurant_standard_schema import (
            OrderSchema, OrderStatus, OrderType, OrderItemSchema, DishCategory
        )

        # 品智 billStatus: 1=已结账, 0=未结账, 2=已退单
        _STATUS_MAP = {
            1: OrderStatus.COMPLETED,
            0: OrderStatus.PENDING,
            2: OrderStatus.CANCELLED,
        }
        bill_status = raw.get("billStatus", 0)
        order_status = _STATUS_MAP.get(bill_status, OrderStatus.PENDING)

        # 品智金额单位：分（整数）
        dish_total = Decimal(str(raw.get("dishPriceTotal", 0))) / 100
        special_offer = Decimal(str(raw.get("specialOfferPrice", 0))) / 100
        real_price = Decimal(str(raw.get("realPrice", 0))) / 100
        tea_price = Decimal(str(raw.get("teaPrice", 0))) / 100

        # 解析时间
        open_time_raw = raw.get("openTime", "")
        try:
            created_at = datetime.fromisoformat(str(open_time_raw).replace("T", " "))
        except (ValueError, TypeError):
            created_at = datetime.utcnow()

        pay_time_raw = raw.get("payTime")
        completed_at = None
        if pay_time_raw:
            try:
                completed_at = datetime.fromisoformat(str(pay_time_raw).replace("T", " "))
            except (ValueError, TypeError):
                pass

        # 品智的 dishList 不总是随订单返回，构建占位 items
        items = []
        for idx, dish in enumerate(raw.get("dishList", []), start=1):
            unit_price = Decimal(str(dish.get("dishPrice", dish.get("price", 0)))) / 100
            qty = int(dish.get("dishNum", dish.get("quantity", 1)))
            items.append(OrderItemSchema(
                item_id=str(dish.get("dishId", f"{raw.get('billId', '')}_{idx}")),
                dish_id=str(dish.get("dishId", "")),
                dish_name=str(dish.get("dishName", "")),
                dish_category=DishCategory.MAIN_COURSE,
                quantity=qty,
                unit_price=unit_price,
                subtotal=unit_price * qty,
            ))

        order_source = raw.get("orderSource", 1)
        order_type = OrderType.DINE_IN if order_source == 1 else OrderType.DELIVERY

        return OrderSchema(
            order_id=str(raw.get("billId", "")),
            order_number=str(raw.get("billNo", "")),
            order_type=order_type,
            order_status=order_status,
            store_id=store_id,
            brand_id=brand_id,
            table_number=raw.get("tableNo"),
            customer_id=raw.get("vipCard"),
            items=items,
            subtotal=dish_total,
            discount=special_offer,
            service_charge=tea_price,
            total=real_price,
            created_at=created_at,
            completed_at=completed_at,
            waiter_id=raw.get("openOrderUser"),
            cashier_id=raw.get("cashiers"),
            notes=raw.get("remark"),
        )

    def to_staff_action(self, raw: Dict[str, Any], store_id: str, brand_id: str):
        """
        将品智原始操作数据映射为标准 StaffAction

        原始字段参考（品智操作日志）：
          actionType, staffId, amount, reason, approvedBy, createdAt
        """
        import sys
        import os as _os
        _src_dir = _os.path.dirname(__file__)
        _repo_root = _os.path.abspath(_os.path.join(_src_dir, "../../../.."))
        _gateway_src = _os.path.join(_repo_root, "apps", "api-gateway", "src")
        if _gateway_src not in sys.path:
            sys.path.insert(0, _gateway_src)

        from schemas.restaurant_standard_schema import StaffAction

        action_time_raw = raw.get("createdAt", raw.get("actionTime", ""))
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
            operator_id=str(raw.get("staffId", raw.get("operatorId", ""))),
            amount=amount,
            reason=raw.get("reason"),
            approved_by=raw.get("approvedBy"),
            created_at=created_at,
        )
