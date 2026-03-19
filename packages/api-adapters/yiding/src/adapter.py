"""
易订适配器 - YiDing Adapter

基于真实易订开放API（https://open.zhidianfan.com/yidingopen/）
实现预订数据读取、会员查询、订单列表等功能
"""

import structlog
from typing import Any, Dict, List, Optional

from .client import YiDingClient, YiDingAPIError
from .mapper import YiDingMapper
from .cache import YiDingCache
from .types import (
    YiDingConfig,
    UnifiedReservation,
    UnifiedCustomer,
    ReservationStats,
    CreateReservationDTO,
)

logger = structlog.get_logger()


class YiDingAdapter:
    """
    易订适配器

    对接易订预订系统真实API，提供:
    - 预订订单查询（轮询/列表/V2列表）
    - 预订订单确认/更新
    - 会员信息查询
    - 会员列表查询
    - 桌位预订状态检查
    - 数据同步（桌位/菜品/账单/客史）
    """

    def __init__(self, config: YiDingConfig):
        self.config = config
        self.client = YiDingClient(config)
        self.mapper = YiDingMapper()
        self.cache = YiDingCache(
            ttl=config.get("cache_ttl", 300)
        )
        self.hotel_id = config.get("hotel_id")
        self.logger = logger.bind(adapter="yiding")

    async def close(self):
        """关闭适配器"""
        await self.client.close()

    def get_system_name(self) -> str:
        return "yiding"

    async def health_check(self) -> bool:
        """通过获取token验证连通性"""
        try:
            return await self.client.ping()
        except Exception as e:
            self.logger.error("health_check_failed", error=str(e))
            return False

    @property
    def business_name(self) -> Optional[str]:
        """获取认证后的商户名称"""
        return self.client._business_name

    # ============================================
    # 2.1 获取线上预订订单（轮询）
    # ============================================

    async def get_pending_orders(self) -> List[UnifiedReservation]:
        """
        获取待处理的线上预订订单

        GET /resv/orders?access_token=xxx

        返回后需调用 confirm_orders() 确认已收到
        """
        response = await self.client.get("resv/orders")
        data_list = response.get("data", [])
        request_id = response.get("requestId")

        reservations = self.mapper.to_unified_reservations(
            data_list, store_id=self.hotel_id
        )

        self.logger.info(
            "pending_orders_fetched",
            count=len(reservations),
            request_id=request_id
        )

        return reservations

    # ============================================
    # 2.2 确认线上预订订单
    # ============================================

    async def confirm_orders(
        self,
        orders: List[Dict[str, Any]],
        request_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        确认已收到订单

        PUT /resv/orders
        确认后下次轮询不再返回这些订单

        Args:
            orders: [{"resv_order": "xxx", "status": 1, "order_type": 1}]
            request_id: 2.1接口返回的requestId
        """
        body: Dict[str, Any] = {"orders": orders}
        if request_id:
            body["requestId"] = request_id

        return await self.client.put("resv/orders", json=body)

    # ============================================
    # 2.3 检查桌位当前预订状态
    # ============================================

    async def check_table_status(
        self,
        table_code: str,
        meal_type_code: str,
        resv_date: str,
    ) -> bool:
        """
        检查桌位是否已被预订

        GET /resv/resvable?table_code=xxx&meal_type_code=xxx&resv_date=xxx

        Returns:
            True=已被预订, False=未被预订
        """
        response = await self.client.get(
            "resv/resvable",
            params={
                "table_code": table_code,
                "meal_type_code": meal_type_code,
                "resv_date": resv_date,
            }
        )
        data = response.get("data", {})
        return int(data.get("status", 0)) == 1

    # ============================================
    # 2.4 线下预订订单更新
    # ============================================

    async def update_order(
        self,
        data: CreateReservationDTO,
    ) -> Dict[str, Any]:
        """
        新建/更新线下预订

        PUT /resv/hh_orders

        注意：新建时不传resv_order，由易订返回订单号
        """
        return await self.client.put("resv/hh_orders", json=dict(data))

    # ============================================
    # 4.1 获取会员信息
    # ============================================

    async def get_member_info(
        self,
        vip_phone: str,
        hotel_id: Optional[str] = None,
    ) -> Optional[UnifiedCustomer]:
        """
        根据手机号查询会员信息

        GET /resv/user_info?vip_phone=xxx&hotel_id=xxx

        Returns:
            会员信息，不存在返回None
        """
        params: Dict[str, str] = {"vip_phone": vip_phone}
        if hotel_id or self.hotel_id:
            params["hotel_id"] = hotel_id or self.hotel_id

        try:
            response = await self.client.get("resv/user_info", params=params)
            data = response.get("data")
            if not data:
                return None
            return self.mapper.to_unified_customer(data)
        except YiDingAPIError as e:
            if e.error_code == 1:
                return None
            raise

    # ============================================
    # 5.1 获取会员列表
    # ============================================

    async def get_member_list(
        self,
        start_date: str,
        end_date: str,
        hotel_id: Optional[str] = None,
    ) -> List[UnifiedCustomer]:
        """
        获取时间范围内的会员列表

        GET /resv/user/list?start_date=xxx&end_date=xxx&hotel_id=xxx

        Args:
            start_date: 格式 yyyy-mm-dd 或 yyyy-mm-dd hh:mm:ss
            end_date: 格式 yyyy-mm-dd 或 yyyy-mm-dd hh:mm:ss
        """
        params: Dict[str, str] = {
            "start_date": start_date,
            "end_date": end_date,
        }
        if hotel_id or self.hotel_id:
            params["hotel_id"] = hotel_id or self.hotel_id

        response = await self.client.get("resv/user/list", params=params)
        data_list = response.get("data", [])

        customers = self.mapper.to_unified_customers(data_list)

        self.logger.info(
            "member_list_fetched",
            count=len(customers),
            start_date=start_date,
            end_date=end_date,
        )

        return customers

    # ============================================
    # 5.2 订单列表
    # ============================================

    async def get_order_list(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        hotel_id: Optional[str] = None,
    ) -> List[UnifiedReservation]:
        """
        获取预订订单列表

        GET /resv/orders/list?start_date=xxx&end_date=xxx&hotel_id=xxx

        不传日期则默认查当天
        """
        params: Dict[str, str] = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if hotel_id or self.hotel_id:
            params["hotel_id"] = hotel_id or self.hotel_id

        response = await self.client.get("resv/orders/list", params=params)
        data_list = response.get("data", [])

        reservations = self.mapper.to_unified_reservations(
            data_list, store_id=self.hotel_id
        )

        self.logger.info(
            "order_list_fetched",
            count=len(reservations),
            start_date=start_date,
            end_date=end_date,
        )

        return reservations

    # ============================================
    # 5.3 订单列表V2（更多字段）
    # ============================================

    async def get_order_list_v2(
        self,
        start_date: str,
        end_date: str,
    ) -> List[UnifiedReservation]:
        """
        获取预订订单列表V2

        GET /resv/orders/list/V2?start_date=xxx&end_date=xxx

        V2特点：
        - start_date/end_date必传，跨度不超过1个月
        - 返回更多字段：sourceName, resvOrderTypeName, billNo, inTableTime
        """
        response = await self.client.get(
            "resv/orders/list/V2",
            params={
                "start_date": start_date,
                "end_date": end_date,
            }
        )
        data_list = response.get("data", [])

        reservations = self.mapper.to_unified_reservations(
            data_list, store_id=self.hotel_id
        )

        self.logger.info(
            "order_list_v2_fetched",
            count=len(reservations),
            start_date=start_date,
            end_date=end_date,
        )

        return reservations

    # ============================================
    # 统计分析
    # ============================================

    async def get_reservation_stats(
        self,
        start_date: str,
        end_date: str,
        hotel_id: Optional[str] = None,
    ) -> ReservationStats:
        """
        获取预订统计（基于订单列表V2计算）

        先拉取订单列表，再汇总计算统计指标
        """
        reservations = await self.get_order_list_v2(start_date, end_date)

        return self.mapper.compute_reservation_stats(
            reservations,
            store_id=hotel_id or self.hotel_id or "",
            start_date=start_date,
            end_date=end_date,
        )

    # ============================================
    # 数据同步（推送方向：POS → 易订）
    # ============================================

    async def sync_tables(
        self,
        areas: List[Dict[str, Any]],
        tables: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        桌位同步 POST /sync/tables

        Args:
            areas: [{"area_code": "1", "area_name": "大厅", "sort_id": 1}]
            tables: [{"area_code": "1", "table_code": "3", "table_name": "101",
                      "max_people_num": "10", "status": "1", "sort_id": 1}]
        """
        return await self.client.post(
            "sync/tables",
            json={"areas": areas, "tables": tables}
        )

    async def sync_dishes(
        self,
        dls: List[Dict[str, Any]],
        xls: List[Dict[str, Any]],
        cms: List[Dict[str, Any]],
        remarks: Optional[List[str]] = None,
        making_method: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """
        菜品同步 POST /sync/dishes

        Args:
            dls: 大类列表 [{"dlbh": "1", "dlmc": "热菜", "status": "1"}]
            xls: 小类列表 [{"dlbh": "1", "xlbh": "001", "xlmc": "海鲜"}]
            cms: 菜品列表 [{"xlbh": "001", "cmbh": "001", "cmmc": "剁椒鱼头",
                           "cmje": 100, "dwmc": "份", "pycode": "djyt"}]
            remarks: 备注列表 ["重辣", "少辣"]
            making_method: 做法列表 [{"cmbh": "001", "method_name": "清蒸"}]
        """
        body: Dict[str, Any] = {"dls": dls, "xls": xls, "cms": cms}
        if remarks:
            body["remarks"] = remarks
        if making_method:
            body["making_method"] = making_method

        return await self.client.post("sync/dishes", json=body)

    async def sync_bills(
        self,
        bills: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        账单数据同步 POST /sync/bills

        Args:
            bills: 账单列表，每个包含:
                area_code, table_code, bbbc(班次), zdbh(账单编号),
                sjje(实结金额), phone, bbrq(结账日期),
                mx: [{zdbh, cmbh, cmsl, cmmc, sjje, wdbz}]
        """
        return await self.client.post("sync/bills", json={"bills": bills})

    async def sync_vips(
        self,
        vips: List[Dict[str, Any]],
        classes: Optional[List[Dict[str, str]]] = None,
        hotel_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        客史数据同步 POST /sync/vips

        Args:
            vips: 客户列表 [{"vip_name": "张三", "vip_phone": "158xxx",
                            "vip_company": "xxx", "vip_sex": "男"}]
            classes: 客户类型 [{"vip_class_name": "活跃用户", "remark": "..."}]
            hotel_id: 门店ID（多店时使用）
        """
        body: Dict[str, Any] = {"vips": vips}
        if classes:
            body["classes"] = classes
        if hotel_id or self.hotel_id:
            body["hotel_id"] = hotel_id or self.hotel_id

        return await self.client.post("sync/vips", json=body)
