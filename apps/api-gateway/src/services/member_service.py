"""
Member Service
奥琦韦会员系统服务层
"""
from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog
import sys
import os

# 添加packages路径到sys.path
packages_path = os.path.join(os.path.dirname(__file__), "../../../../packages")
sys.path.insert(0, os.path.abspath(packages_path))

try:
    from api_adapters.aoqiwei.src.adapter import AoqiweiAdapter
    AOQIWEI_AVAILABLE = True
except ImportError:
    logger = structlog.get_logger()
    logger.warning("AoqiweiAdapter not available, member features will be limited")
    AoqiweiAdapter = None
    AOQIWEI_AVAILABLE = False

from ..core.config import settings

logger = structlog.get_logger()


class MemberService:
    """会员服务"""

    def __init__(self):
        self._adapter: Optional[Any] = None

    def _get_adapter(self) -> Any:
        """获取或创建会员适配器实例"""
        if not AOQIWEI_AVAILABLE:
            raise RuntimeError("AoqiweiAdapter is not available")
        if self._adapter is None:
            config = {
                "base_url": settings.AOQIWEI_BASE_URL,
                "api_key": settings.AOQIWEI_API_KEY,
                "timeout": settings.AOQIWEI_TIMEOUT,
                "retry_times": settings.AOQIWEI_RETRY_TIMES,
            }
            self._adapter = AoqiweiAdapter(config)
            logger.info("会员适配器初始化成功")
        return self._adapter

    async def query_member(
        self,
        card_no: Optional[str] = None,
        mobile: Optional[str] = None,
        openid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        查询会员信息

        Args:
            card_no: 会员卡号
            mobile: 手机号
            openid: 微信openid

        Returns:
            会员信息
        """
        adapter = self._get_adapter()
        member = await adapter.query_member(card_no=card_no, mobile=mobile, openid=openid)
        logger.info("查询会员信息", card_no=card_no, mobile=mobile)
        return member

    async def add_member(
        self,
        mobile: str,
        name: str,
        sex: int = 1,
        birthday: Optional[str] = None,
        card_type: int = 1,
        store_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        新增会员

        Args:
            mobile: 手机号
            name: 姓名
            sex: 性别 (1-男, 2-女)
            birthday: 生日 (YYYY-MM-DD)
            card_type: 卡类型 (1-电子卡, 2-实体卡)
            store_id: 注册门店ID

        Returns:
            新增会员信息
        """
        adapter = self._get_adapter()
        member = await adapter.add_member(
            mobile=mobile,
            name=name,
            sex=sex,
            birthday=birthday,
            card_type=card_type,
            store_id=store_id,
        )
        logger.info("新增会员", mobile=mobile, name=name)
        return member

    async def update_member(
        self, card_no: str, update_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        修改会员信息

        Args:
            card_no: 会员卡号
            update_data: 更新数据

        Returns:
            更新结果
        """
        adapter = self._get_adapter()
        result = await adapter.update_member(card_no, update_data)
        logger.info("修改会员信息", card_no=card_no)
        return result

    async def trade_preview(
        self,
        card_no: str,
        store_id: str,
        cashier: str,
        amount: int,
        dish_list: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        交易预览

        Args:
            card_no: 会员卡号
            store_id: 门店ID
            cashier: 收银员
            amount: 消费总金额（分）
            dish_list: 菜品列表

        Returns:
            预览结果
        """
        adapter = self._get_adapter()
        preview = await adapter.trade_preview(
            card_no=card_no,
            store_id=store_id,
            cashier=cashier,
            amount=amount,
            dish_list=dish_list,
        )
        logger.info("交易预览", card_no=card_no, amount=amount)
        return preview

    async def trade_submit(
        self,
        card_no: str,
        store_id: str,
        cashier: str,
        amount: int,
        pay_type: int,
        trade_no: str,
        discount_plan: Optional[Dict[str, int]] = None,
    ) -> Dict[str, Any]:
        """
        交易提交

        Args:
            card_no: 会员卡号
            store_id: 门店ID
            cashier: 收银员
            amount: 实付金额（分）
            pay_type: 支付方式代码
            trade_no: 第三方流水号
            discount_plan: 抵扣方案

        Returns:
            交易结果
        """
        adapter = self._get_adapter()
        trade = await adapter.trade_submit(
            card_no=card_no,
            store_id=store_id,
            cashier=cashier,
            amount=amount,
            pay_type=pay_type,
            trade_no=trade_no,
            discount_plan=discount_plan,
        )
        logger.info("交易提交", card_no=card_no, amount=amount, trade_no=trade_no)
        return trade

    async def trade_query(
        self,
        trade_id: Optional[str] = None,
        trade_no: Optional[str] = None,
        card_no: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        查询交易记录

        Args:
            trade_id: 交易ID
            trade_no: 第三方流水号
            card_no: 会员卡号
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            交易记录列表
        """
        adapter = self._get_adapter()
        trades = await adapter.trade_query(
            trade_id=trade_id,
            trade_no=trade_no,
            card_no=card_no,
            start_date=start_date,
            end_date=end_date,
        )
        logger.info("查询交易记录", card_no=card_no)
        return trades

    async def trade_cancel(self, trade_id: str, reason: str = "") -> Dict[str, Any]:
        """
        交易撤销

        Args:
            trade_id: 交易ID
            reason: 撤销原因

        Returns:
            撤销结果
        """
        adapter = self._get_adapter()
        result = await adapter.trade_cancel(trade_id, reason)
        logger.info("交易撤销", trade_id=trade_id, reason=reason)
        return result

    async def recharge_submit(
        self,
        card_no: str,
        store_id: str,
        cashier: str,
        amount: int,
        pay_type: int,
        trade_no: str,
    ) -> Dict[str, Any]:
        """
        储值提交

        Args:
            card_no: 会员卡号
            store_id: 充值门店
            cashier: 收银员
            amount: 充值金额（分）
            pay_type: 支付方式
            trade_no: 第三方流水号

        Returns:
            充值结果
        """
        adapter = self._get_adapter()
        recharge = await adapter.recharge_submit(
            card_no=card_no,
            store_id=store_id,
            cashier=cashier,
            amount=amount,
            pay_type=pay_type,
            trade_no=trade_no,
        )
        logger.info("储值提交", card_no=card_no, amount=amount)
        return recharge

    async def recharge_query(
        self,
        card_no: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        查询储值记录

        Args:
            card_no: 会员卡号
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            储值记录
        """
        adapter = self._get_adapter()
        balance = await adapter.recharge_query(card_no, start_date, end_date)
        logger.info("查询储值记录", card_no=card_no)
        return balance

    async def coupon_list(
        self, card_no: str, store_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        查询可用优惠券

        Args:
            card_no: 会员卡号
            store_id: 门店ID

        Returns:
            优惠券列表
        """
        adapter = self._get_adapter()
        coupons = await adapter.coupon_list(card_no, store_id)
        logger.info("查询优惠券", card_no=card_no, count=len(coupons))
        return coupons

    async def coupon_use(
        self, code: str, store_id: str, cashier: str, amount: int
    ) -> Dict[str, Any]:
        """
        券码核销

        Args:
            code: 券码
            store_id: 门店ID
            cashier: 收银员
            amount: 消费金额（分）

        Returns:
            核销结果
        """
        adapter = self._get_adapter()
        result = await adapter.coupon_use(code, store_id, cashier, amount)
        logger.info("券码核销", code=code, amount=amount)
        return result

    async def test_connection(self) -> Dict[str, Any]:
        """
        测试会员系统连接

        Returns:
            测试结果
        """
        try:
            adapter = self._get_adapter()
            # 尝试查询会员信息来测试连接
            member = await adapter.query_member(card_no="TEST001")
            return {
                "success": True,
                "message": "连接成功",
                "member_card": member.get("cardNo"),
            }
        except Exception as e:
            logger.error("会员系统连接测试失败", error=str(e))
            return {
                "success": False,
                "error": str(e),
            }

    async def close(self):
        """关闭服务，释放资源"""
        if self._adapter:
            await self._adapter.close()
            self._adapter = None
            logger.info("会员服务关闭")


# 创建全局服务实例
member_service = MemberService()
