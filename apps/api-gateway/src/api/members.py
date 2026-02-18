"""
Member API
奥琦韦会员系统API端点
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import date
import structlog

from ..services.member_service import member_service
from ..core.auth import get_current_user, require_permissions
from ..models.user import User

logger = structlog.get_logger()

router = APIRouter()


# ==================== Request/Response Models ====================


class MemberInfo(BaseModel):
    """会员信息"""

    cardNo: str
    mobile: str
    name: str
    sex: int
    birthday: Optional[str] = None
    level: int
    points: int
    balance: int  # 单位：分
    regTime: Optional[str] = None
    regStore: Optional[str] = None


class AddMemberRequest(BaseModel):
    """新增会员请求"""

    mobile: str = Field(..., description="手机号")
    name: str = Field(..., description="姓名")
    sex: int = Field(1, description="性别 (1-男, 2-女)")
    birthday: Optional[str] = Field(None, description="生日 (YYYY-MM-DD)")
    card_type: int = Field(1, description="卡类型 (1-电子卡, 2-实体卡)")
    store_id: Optional[str] = Field(None, description="注册门店ID")


class UpdateMemberRequest(BaseModel):
    """修改会员请求"""

    name: Optional[str] = Field(None, description="姓名")
    sex: Optional[int] = Field(None, description="性别")
    birthday: Optional[str] = Field(None, description="生日")
    avatar: Optional[str] = Field(None, description="头像URL")


class TradePreviewRequest(BaseModel):
    """交易预览请求"""

    card_no: str = Field(..., description="会员卡号")
    store_id: str = Field(..., description="门店ID")
    cashier: str = Field(..., description="收银员")
    amount: int = Field(..., description="消费总金额（分）")
    dish_list: Optional[List[dict]] = Field(None, description="菜品列表")


class TradeSubmitRequest(BaseModel):
    """交易提交请求"""

    card_no: str = Field(..., description="会员卡号")
    store_id: str = Field(..., description="门店ID")
    cashier: str = Field(..., description="收银员")
    amount: int = Field(..., description="实付金额（分）")
    pay_type: int = Field(..., description="支付方式代码")
    trade_no: str = Field(..., description="第三方流水号")
    discount_plan: Optional[dict] = Field(None, description="抵扣方案")


class RechargeRequest(BaseModel):
    """储值请求"""

    card_no: str = Field(..., description="会员卡号")
    store_id: str = Field(..., description="充值门店")
    cashier: str = Field(..., description="收银员")
    amount: int = Field(..., description="充值金额（分）")
    pay_type: int = Field(..., description="支付方式")
    trade_no: str = Field(..., description="第三方流水号")


class CouponUseRequest(BaseModel):
    """券码核销请求"""

    code: str = Field(..., description="券码")
    store_id: str = Field(..., description="门店ID")
    cashier: str = Field(..., description="收银员")
    amount: int = Field(..., description="消费金额（分）")


class ConnectionTestResponse(BaseModel):
    """连接测试响应"""

    success: bool
    message: Optional[str] = None
    error: Optional[str] = None
    member_card: Optional[str] = None


# ==================== API Endpoints ====================


@router.get("/query", response_model=MemberInfo, summary="查询会员信息")
async def query_member(
    card_no: Optional[str] = Query(None, description="会员卡号"),
    mobile: Optional[str] = Query(None, description="手机号"),
    openid: Optional[str] = Query(None, description="微信openid"),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["member:read"])),
):
    """
    查询会员信息

    至少需要提供一个查询条件：card_no, mobile, openid

    需要权限: member:read
    """
    try:
        member = await member_service.query_member(
            card_no=card_no, mobile=mobile, openid=openid
        )
        return member
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("查询会员信息失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"查询会员信息失败: {str(e)}")


@router.post("/add", summary="新增会员")
async def add_member(
    request: AddMemberRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["member:write"])),
):
    """
    新增会员

    需要权限: member:write
    """
    try:
        member = await member_service.add_member(
            mobile=request.mobile,
            name=request.name,
            sex=request.sex,
            birthday=request.birthday,
            card_type=request.card_type,
            store_id=request.store_id,
        )
        return member
    except Exception as e:
        logger.error("新增会员失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"新增会员失败: {str(e)}")


@router.put("/{card_no}", summary="修改会员信息")
async def update_member(
    card_no: str,
    request: UpdateMemberRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["member:write"])),
):
    """
    修改会员信息

    需要权限: member:write
    """
    try:
        update_data = request.dict(exclude_none=True)
        result = await member_service.update_member(card_no, update_data)
        return result
    except Exception as e:
        logger.error("修改会员信息失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"修改会员信息失败: {str(e)}")


@router.post("/trade/preview", summary="交易预览")
async def trade_preview(
    request: TradePreviewRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["member:trade"])),
):
    """
    交易预览（计算优惠）

    需要权限: member:trade
    """
    try:
        preview = await member_service.trade_preview(
            card_no=request.card_no,
            store_id=request.store_id,
            cashier=request.cashier,
            amount=request.amount,
            dish_list=request.dish_list,
        )
        return preview
    except Exception as e:
        logger.error("交易预览失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"交易预览失败: {str(e)}")


@router.post("/trade/submit", summary="交易提交")
async def trade_submit(
    request: TradeSubmitRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["member:trade"])),
):
    """
    交易提交

    需要权限: member:trade
    """
    try:
        trade = await member_service.trade_submit(
            card_no=request.card_no,
            store_id=request.store_id,
            cashier=request.cashier,
            amount=request.amount,
            pay_type=request.pay_type,
            trade_no=request.trade_no,
            discount_plan=request.discount_plan,
        )
        return trade
    except Exception as e:
        logger.error("交易提交失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"交易提交失败: {str(e)}")


@router.get("/trade/query", summary="查询交易记录")
async def trade_query(
    trade_id: Optional[str] = Query(None, description="交易ID"),
    trade_no: Optional[str] = Query(None, description="第三方流水号"),
    card_no: Optional[str] = Query(None, description="会员卡号"),
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["member:read"])),
):
    """
    查询交易记录

    需要权限: member:read
    """
    try:
        trades = await member_service.trade_query(
            trade_id=trade_id,
            trade_no=trade_no,
            card_no=card_no,
            start_date=start_date,
            end_date=end_date,
        )
        return trades
    except Exception as e:
        logger.error("查询交易记录失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"查询交易记录失败: {str(e)}")


@router.post("/trade/cancel/{trade_id}", summary="交易撤销")
async def trade_cancel(
    trade_id: str,
    reason: str = Query("", description="撤销原因"),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["member:trade"])),
):
    """
    交易撤销

    需要权限: member:trade
    """
    try:
        result = await member_service.trade_cancel(trade_id, reason)
        return result
    except Exception as e:
        logger.error("交易撤销失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"交易撤销失败: {str(e)}")


@router.post("/recharge/submit", summary="储值提交")
async def recharge_submit(
    request: RechargeRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["member:recharge"])),
):
    """
    储值提交

    需要权限: member:recharge
    """
    try:
        recharge = await member_service.recharge_submit(
            card_no=request.card_no,
            store_id=request.store_id,
            cashier=request.cashier,
            amount=request.amount,
            pay_type=request.pay_type,
            trade_no=request.trade_no,
        )
        return recharge
    except Exception as e:
        logger.error("储值提交失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"储值提交失败: {str(e)}")


@router.get("/recharge/query", summary="查询储值记录")
async def recharge_query(
    card_no: str = Query(..., description="会员卡号"),
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["member:read"])),
):
    """
    查询储值记录

    需要权限: member:read
    """
    try:
        balance = await member_service.recharge_query(card_no, start_date, end_date)
        return balance
    except Exception as e:
        logger.error("查询储值记录失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"查询储值记录失败: {str(e)}")


@router.get("/coupon/list", summary="查询可用优惠券")
async def coupon_list(
    card_no: str = Query(..., description="会员卡号"),
    store_id: Optional[str] = Query(None, description="门店ID"),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["member:read"])),
):
    """
    查询可用优惠券

    需要权限: member:read
    """
    try:
        coupons = await member_service.coupon_list(card_no, store_id)
        return coupons
    except Exception as e:
        logger.error("查询优惠券失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"查询优惠券失败: {str(e)}")


@router.post("/coupon/use", summary="券码核销")
async def coupon_use(
    request: CouponUseRequest,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["member:coupon"])),
):
    """
    券码核销

    需要权限: member:coupon
    """
    try:
        result = await member_service.coupon_use(
            code=request.code,
            store_id=request.store_id,
            cashier=request.cashier,
            amount=request.amount,
        )
        return result
    except Exception as e:
        logger.error("券码核销失败", error=str(e))
        raise HTTPException(status_code=500, detail=f"券码核销失败: {str(e)}")


@router.get(
    "/test-connection",
    response_model=ConnectionTestResponse,
    summary="测试会员系统连接",
)
async def test_connection(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permissions(["system:config"])),
):
    """
    测试会员系统连接

    需要权限: system:config
    """
    try:
        result = await member_service.test_connection()
        return result
    except Exception as e:
        logger.error("测试连接失败", error=str(e))
        return ConnectionTestResponse(success=False, error=str(e))
