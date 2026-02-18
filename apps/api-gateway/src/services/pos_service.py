"""
POS Service
品智收银系统服务层
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog
import sys
import os

# 添加packages路径到sys.path
packages_path = os.path.join(os.path.dirname(__file__), "../../../../packages")
sys.path.insert(0, os.path.abspath(packages_path))

from api_adapters.pinzhi.src.adapter import PinzhiAdapter
from ..core.config import settings

logger = structlog.get_logger()


class POSService:
    """POS服务"""

    def __init__(self):
        self._adapter: Optional[PinzhiAdapter] = None

    def _get_adapter(self) -> PinzhiAdapter:
        """获取或创建POS适配器实例"""
        if self._adapter is None:
            config = {
                "base_url": settings.PINZHI_BASE_URL,
                "token": settings.PINZHI_TOKEN,
                "timeout": settings.PINZHI_TIMEOUT,
                "retry_times": settings.PINZHI_RETRY_TIMES,
            }
            self._adapter = PinzhiAdapter(config)
            logger.info("POS适配器初始化成功")
        return self._adapter

    async def get_stores(self, ognid: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取门店信息

        Args:
            ognid: 门店ID，不传则返回所有门店

        Returns:
            门店信息列表
        """
        adapter = self._get_adapter()
        stores = await adapter.get_store_info(ognid)
        logger.info("获取门店信息", count=len(stores))
        return stores

    async def get_dish_categories(self) -> List[Dict[str, Any]]:
        """
        获取菜品类别

        Returns:
            菜品类别列表
        """
        adapter = self._get_adapter()
        categories = await adapter.get_dish_categories()
        logger.info("获取菜品类别", count=len(categories))
        return categories

    async def get_dishes(self, updatetime: int = 0) -> List[Dict[str, Any]]:
        """
        获取菜品信息

        Args:
            updatetime: 同步时间戳，传0拉取所有

        Returns:
            菜品信息列表
        """
        adapter = self._get_adapter()
        dishes = await adapter.get_dishes(updatetime)
        logger.info("获取菜品信息", count=len(dishes))
        return dishes

    async def get_tables(self) -> List[Dict[str, Any]]:
        """
        获取桌台信息

        Returns:
            桌台信息列表
        """
        adapter = self._get_adapter()
        tables = await adapter.get_tables()
        logger.info("获取桌台信息", count=len(tables))
        return tables

    async def get_employees(self) -> List[Dict[str, Any]]:
        """
        获取员工信息

        Returns:
            员工信息列表
        """
        adapter = self._get_adapter()
        employees = await adapter.get_employees()
        logger.info("获取员工信息", count=len(employees))
        return employees

    async def query_orders(
        self,
        ognid: Optional[str] = None,
        begin_date: Optional[str] = None,
        end_date: Optional[str] = None,
        page_index: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        查询订单

        Args:
            ognid: 门店ID
            begin_date: 开始日期（yyyy-MM-dd）
            end_date: 结束日期（yyyy-MM-dd）
            page_index: 页码
            page_size: 每页数量

        Returns:
            订单列表和分页信息
        """
        adapter = self._get_adapter()
        orders = await adapter.query_orders(
            ognid=ognid,
            begin_date=begin_date,
            end_date=end_date,
            page_index=page_index,
            page_size=page_size,
        )
        logger.info(
            "查询订单",
            count=len(orders),
            page=page_index,
            ognid=ognid,
        )
        return {
            "orders": orders,
            "page": page_index,
            "page_size": page_size,
            "total": len(orders),
        }

    async def query_order_summary(
        self, ognid: str, business_date: str
    ) -> Dict[str, Any]:
        """
        查询门店收入汇总

        Args:
            ognid: 门店ID
            business_date: 营业日（yyyy-MM-dd）

        Returns:
            收入汇总数据
        """
        adapter = self._get_adapter()
        summary = await adapter.query_order_summary(ognid, business_date)
        logger.info("查询收入汇总", ognid=ognid, business_date=business_date)
        return summary

    async def get_pay_types(self) -> List[Dict[str, Any]]:
        """
        获取支付方式

        Returns:
            支付方式列表
        """
        adapter = self._get_adapter()
        pay_types = await adapter.get_pay_types()
        logger.info("获取支付方式", count=len(pay_types))
        return pay_types

    async def test_connection(self) -> Dict[str, Any]:
        """
        测试POS系统连接

        Returns:
            测试结果
        """
        try:
            adapter = self._get_adapter()
            # 尝试获取门店信息来测试连接
            stores = await adapter.get_store_info()
            return {
                "success": True,
                "message": "连接成功",
                "stores_count": len(stores),
            }
        except Exception as e:
            logger.error("POS连接测试失败", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def close(self):
        """关闭服务，释放资源"""
        if self._adapter:
            await self._adapter.close()
            self._adapter = None
            logger.info("POS服务关闭")


# 创建全局服务实例
pos_service = POSService()
