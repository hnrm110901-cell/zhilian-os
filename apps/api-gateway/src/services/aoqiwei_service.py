"""
奥琦玮供应链服务层
封装供应链开放平台的核心业务操作
"""
from typing import Any, Dict, List, Optional

import structlog

from ..core.config import settings

logger = structlog.get_logger()


class AoqiweiService:
    """奥琦玮供应链服务"""

    def __init__(self):
        self.app_key = settings.AOQIWEI_APP_KEY
        self.app_secret = settings.AOQIWEI_APP_SECRET
        self.base_url = settings.AOQIWEI_BASE_URL
        self.timeout = settings.AOQIWEI_TIMEOUT
        self.retry_times = settings.AOQIWEI_RETRY_TIMES
        self._adapter = None

    def is_configured(self) -> bool:
        """检查是否已配置"""
        return bool(self.app_key and self.app_secret)

    def _get_adapter(self):
        """懒加载适配器"""
        if self._adapter is None:
            from packages.api_adapters.aoqiwei.src.adapter import AoqiweiAdapter
            self._adapter = AoqiweiAdapter({
                "base_url": self.base_url,
                "app_key": self.app_key,
                "app_secret": self.app_secret,
                "timeout": self.timeout,
                "retry_times": self.retry_times,
            })
        return self._adapter

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        if not self.is_configured():
            return {
                "status": "not_configured",
                "message": "奥琦玮未配置，请设置 AOQIWEI_APP_KEY 和 AOQIWEI_APP_SECRET",
                "configured": False,
                "reachable": False,
            }

        try:
            # 用查询货品接口做连通性测试
            adapter = self._get_adapter()
            result = await adapter.query_goods(page=1, page_size=1)
            return {
                "status": "healthy",
                "message": "奥琦玮供应链连接正常",
                "configured": True,
                "reachable": True,
            }
        except Exception as e:
            logger.error("奥琦玮健康检查失败", error=str(e))
            return {
                "status": "error",
                "message": f"奥琦玮连接失败: {str(e)}",
                "configured": True,
                "reachable": False,
            }

    # ==================== POS订单 ====================

    async def upload_pos_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """上传POS订单到供应链系统"""
        if not self.is_configured():
            raise Exception("奥琦玮未配置")
        return await self._get_adapter().pos_upload_order(order_data)

    async def check_pos_orders(self, shop_code: str, date: str) -> Dict[str, Any]:
        """校验指定门店指定日期的POS订单"""
        if not self.is_configured():
            raise Exception("奥琦玮未配置")
        return await self._get_adapter().pos_check_order(shop_code, date)

    async def pos_day_done(self, shop_code: str, date: str) -> Dict[str, Any]:
        """执行POS日结"""
        if not self.is_configured():
            raise Exception("奥琦玮未配置")
        return await self._get_adapter().pos_day_done(shop_code, date)

    # ==================== 库存管理 ====================

    async def get_stock(
        self,
        depot_code: Optional[str] = None,
        shop_code: Optional[str] = None,
        good_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """查询库存"""
        if not self.is_configured():
            logger.warning("奥琦玮未配置，返回空库存")
            return []
        return await self._get_adapter().query_stock(depot_code, shop_code, good_code)

    async def get_stock_estimate(self, shop_code: str, start_date: str, end_date: str) -> Dict[str, Any]:
        """获取库存预估"""
        if not self.is_configured():
            return {}
        return await self._get_adapter().query_stock_estimate(shop_code, start_date, end_date)

    # ==================== 货品管理 ====================

    async def get_goods(
        self,
        good_code: Optional[str] = None,
        good_name: Optional[str] = None,
        page: int = 1,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """查询货品信息"""
        if not self.is_configured():
            return {"list": [], "total": 0}
        return await self._get_adapter().query_goods(good_code, good_name, page, page_size)

    async def get_suppliers(
        self,
        supplier_code: Optional[str] = None,
        page: int = 1,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """查询供应商信息"""
        if not self.is_configured():
            return {"list": [], "total": 0}
        return await self._get_adapter().query_suppliers(supplier_code, page, page_size)

    # ==================== 配送业务 ====================

    async def create_delivery_apply(self, apply_data: Dict[str, Any]) -> Dict[str, Any]:
        """创建配送申请单"""
        if not self.is_configured():
            raise Exception("奥琦玮未配置")
        return await self._get_adapter().create_delivery_apply(apply_data)

    async def get_dispatch_out_orders(
        self,
        start_date: str,
        end_date: str,
        shop_code: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """查询配送出库单"""
        if not self.is_configured():
            return []
        return await self._get_adapter().query_delivery_dispatch_out(start_date, end_date, shop_code)

    async def confirm_delivery_receipt(self, dispatch_in_data: Dict[str, Any]) -> Dict[str, Any]:
        """确认配送收货（生成配送入库单）"""
        if not self.is_configured():
            raise Exception("奥琦玮未配置")
        return await self._get_adapter().confirm_delivery_in(dispatch_in_data)

    # ==================== 采购业务 ====================

    async def get_purchase_orders(
        self,
        start_date: str,
        end_date: str,
        depot_code: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """查询采购入库单"""
        if not self.is_configured():
            return {"list": [], "total": 0}
        return await self._get_adapter().query_purchase_orders(start_date, end_date, depot_code, page, page_size)

    async def create_reserve_order(self, reserve_data: Dict[str, Any]) -> Dict[str, Any]:
        """创建采购订货单"""
        if not self.is_configured():
            raise Exception("奥琦玮未配置")
        return await self._get_adapter().create_reserve_order(reserve_data)

    # ==================== 数据报表 ====================

    async def get_inventory_report(
        self,
        start_date: str,
        end_date: str,
        shop_code: Optional[str] = None,
        good_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """查询进销存报表"""
        if not self.is_configured():
            return {"list": [], "total": 0}
        return await self._get_adapter().query_inventory_report(start_date, end_date, shop_code, good_code)

    async def get_good_diff_analysis(
        self,
        start_date: str,
        end_date: str,
        shop_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """货品差异分析"""
        if not self.is_configured():
            return {"list": []}
        return await self._get_adapter().query_good_diff_analysis(start_date, end_date, shop_code)


# 全局实例
aoqiwei_service = AoqiweiService()
