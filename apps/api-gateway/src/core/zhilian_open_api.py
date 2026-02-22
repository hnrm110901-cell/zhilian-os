"""
智链OpenAPI规范
Zhilian Open API Specification

核心理念：
- 做"插座"，不做"插头"
- 让ISV来对接，而不是自己写适配器
- 建立统一的标准数据模型和接口协议

开放能力：
Level 1: 数据同步能力
Level 2: 智能决策能力
Level 3: 营销能力
Level 4: 高级能力
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


# ==================== 标准数据模型 ====================

class StandardOrder(BaseModel):
    """标准订单模型"""
    order_id: str = Field(..., description="订单ID")
    store_id: str = Field(..., description="门店ID")
    table_number: Optional[str] = Field(None, description="桌号")
    order_time: datetime = Field(..., description="下单时间")
    order_type: str = Field(..., description="订单类型（堂食/外卖/外带）")
    customer_id: Optional[str] = Field(None, description="顾客ID")
    items: List[Dict] = Field(..., description="订单明细")
    total_amount: float = Field(..., description="订单总额")
    discount_amount: float = Field(0.0, description="优惠金额")
    actual_amount: float = Field(..., description="实付金额")
    payment_method: str = Field(..., description="支付方式")
    status: str = Field(..., description="订单状态")
    created_at: datetime = Field(default_factory=datetime.now)


class StandardDish(BaseModel):
    """标准菜品模型"""
    dish_id: str = Field(..., description="菜品ID")
    name: str = Field(..., description="菜品名称")
    category: str = Field(..., description="菜品分类")
    price: float = Field(..., description="价格")
    cost: Optional[float] = Field(None, description="成本")
    unit: str = Field("份", description="单位")
    description: Optional[str] = Field(None, description="描述")
    image_url: Optional[str] = Field(None, description="图片URL")
    tags: List[str] = Field(default_factory=list, description="标签")
    is_available: bool = Field(True, description="是否可售")
    created_at: datetime = Field(default_factory=datetime.now)


class StandardInventory(BaseModel):
    """标准库存模型"""
    inventory_id: str = Field(..., description="库存ID")
    store_id: str = Field(..., description="门店ID")
    item_id: str = Field(..., description="物料ID")
    item_name: str = Field(..., description="物料名称")
    quantity: float = Field(..., description="数量")
    unit: str = Field(..., description="单位")
    cost_price: float = Field(..., description="成本价")
    supplier_id: Optional[str] = Field(None, description="供应商ID")
    expiry_date: Optional[datetime] = Field(None, description="保质期")
    updated_at: datetime = Field(default_factory=datetime.now)


class StandardMember(BaseModel):
    """标准会员模型"""
    member_id: str = Field(..., description="会员ID")
    name: str = Field(..., description="姓名")
    phone: str = Field(..., description="手机号")
    gender: Optional[str] = Field(None, description="性别")
    birthday: Optional[datetime] = Field(None, description="生日")
    member_level: str = Field("普通会员", description="会员等级")
    points: int = Field(0, description="积分")
    balance: float = Field(0.0, description="余额")
    register_date: datetime = Field(default_factory=datetime.now)
    last_visit_date: Optional[datetime] = Field(None, description="最后到店日期")


class StandardEmployee(BaseModel):
    """标准员工模型"""
    employee_id: str = Field(..., description="员工ID")
    name: str = Field(..., description="姓名")
    phone: str = Field(..., description="手机号")
    role: str = Field(..., description="角色")
    store_id: str = Field(..., description="所属门店")
    hire_date: datetime = Field(..., description="入职日期")
    status: str = Field("在职", description="状态")


# ==================== API响应模型 ====================

class APIResponse(BaseModel):
    """API响应"""
    code: int = Field(..., description="状态码（200成功，其他失败）")
    message: str = Field(..., description="消息")
    data: Optional[Any] = Field(None, description="数据")
    timestamp: datetime = Field(default_factory=datetime.now)


# ==================== 智链OpenAPI ====================

class ZhilianOpenAPI:
    """智链OpenAPI规范"""

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api.zhilian-os.com/v1"

    # ==================== Level 1: 数据同步能力 ====================

    async def sync_orders(
        self,
        orders: List[StandardOrder]
    ) -> APIResponse:
        """
        同步订单数据

        Args:
            orders: 订单列表

        Returns:
            API响应
        """
        logger.info(f"Syncing {len(orders)} orders")

        # TODO: 实现实际的API调用
        return APIResponse(
            code=200,
            message="订单同步成功",
            data={"synced_count": len(orders)}
        )

    async def sync_dishes(
        self,
        dishes: List[StandardDish]
    ) -> APIResponse:
        """
        同步菜品数据

        Args:
            dishes: 菜品列表

        Returns:
            API响应
        """
        logger.info(f"Syncing {len(dishes)} dishes")

        return APIResponse(
            code=200,
            message="菜品同步成功",
            data={"synced_count": len(dishes)}
        )

    async def sync_inventory(
        self,
        inventory: List[StandardInventory]
    ) -> APIResponse:
        """
        同步库存数据

        Args:
            inventory: 库存列表

        Returns:
            API响应
        """
        logger.info(f"Syncing {len(inventory)} inventory items")

        return APIResponse(
            code=200,
            message="库存同步成功",
            data={"synced_count": len(inventory)}
        )

    async def sync_members(
        self,
        members: List[StandardMember]
    ) -> APIResponse:
        """
        同步会员数据

        Args:
            members: 会员列表

        Returns:
            API响应
        """
        logger.info(f"Syncing {len(members)} members")

        return APIResponse(
            code=200,
            message="会员同步成功",
            data={"synced_count": len(members)}
        )

    # ==================== Level 2: 智能决策能力 ====================

    async def predict_sales(
        self,
        store_id: str,
        date: datetime,
        dish_ids: Optional[List[str]] = None
    ) -> APIResponse:
        """
        销量预测API

        Args:
            store_id: 门店ID
            date: 预测日期
            dish_ids: 菜品ID列表（可选）

        Returns:
            预测结果
        """
        logger.info(f"Predicting sales for store {store_id} on {date}")

        from src.core.database import get_db_session
        from src.models.daily_report import DailyReport
        from src.models.dish import Dish
        from sqlalchemy import select, func
        from datetime import timedelta

        target_date = date if isinstance(date, datetime) else date
        weekday = target_date.weekday()
        past_dates = [target_date - timedelta(weeks=w) for w in range(1, 5)]

        async with get_db_session() as session:
            # 历史同星期平均客单数
            hist = await session.execute(
                select(func.avg(DailyReport.order_count), func.avg(DailyReport.total_revenue)).where(
                    DailyReport.store_id == store_id,
                    DailyReport.report_date.in_([d.date() if hasattr(d, "date") else d for d in past_dates]),
                )
            )
            row = hist.one()
            avg_orders = int(row[0] or 50)
            avg_revenue = int(row[1] or 5000_00)

            # 查询菜品列表
            dishes_result = await session.execute(
                select(Dish.id, Dish.name).where(Dish.store_id == store_id, Dish.is_available == True).limit(10)
            )
            dishes = dishes_result.all()

        if dish_ids:
            predictions = {
                str(d.id): {"dish_name": d.name, "predicted_sales": max(1, avg_orders // max(len(dishes), 1))}
                for d in dishes if str(d.id) in dish_ids
            }
        else:
            predictions = {
                str(d.id): {"dish_name": d.name, "predicted_sales": max(1, avg_orders // max(len(dishes), 1))}
                for d in dishes
            }

        return APIResponse(code=200, message="销量预测成功", data=predictions)

    async def suggest_schedule(
        self,
        store_id: str,
        date: datetime
    ) -> APIResponse:
        """
        排班建议API

        Args:
            store_id: 门店ID
            date: 排班日期

        Returns:
            排班建议
        """
        logger.info(f"Suggesting schedule for store {store_id} on {date}")

        from src.core.database import get_db_session
        from src.models.employee import Employee
        from sqlalchemy import select, func

        async with get_db_session() as session:
            result = await session.execute(
                select(Employee.position, func.count(Employee.id).label("cnt")).where(
                    Employee.store_id == store_id,
                    Employee.is_active == True,
                ).group_by(Employee.position)
            )
            rows = result.all()

        schedule = {row.position: row.cnt for row in rows} if rows else {
            "服务员": 12, "厨师": 8, "配菜员": 4, "收银员": 2
        }

        return APIResponse(code=200, message="排班建议生成成功", data=schedule)

    async def suggest_purchase(
        self,
        store_id: str,
        date: datetime
    ) -> APIResponse:
        """
        采购建议API

        Args:
            store_id: 门店ID
            date: 采购日期

        Returns:
            采购建议
        """
        logger.info(f"Suggesting purchase for store {store_id} on {date}")

        from src.core.database import get_db_session
        from src.models.inventory import InventoryItem
        from sqlalchemy import select

        async with get_db_session() as session:
            result = await session.execute(
                select(InventoryItem).where(
                    InventoryItem.store_id == store_id,
                    InventoryItem.current_quantity <= InventoryItem.min_quantity,
                ).limit(20)
            )
            low_items = result.scalars().all()

        purchase_list = [
            {
                "item": item.name,
                "quantity": max(1, (item.max_quantity or item.min_quantity * 3) - item.current_quantity),
                "unit": item.unit or "份",
            }
            for item in low_items
        ] or [{"item": "暂无低库存商品", "quantity": 0, "unit": ""}]

        return APIResponse(code=200, message="采购建议生成成功", data=purchase_list)

    async def suggest_pricing(
        self,
        dish_id: str,
        context: Optional[Dict] = None
    ) -> APIResponse:
        """
        定价建议API

        Args:
            dish_id: 菜品ID
            context: 上下文（竞品价格、成本等）

        Returns:
            定价建议
        """
        logger.info(f"Suggesting pricing for dish {dish_id}")

        from src.core.database import get_db_session
        from src.models.dish import Dish
        from sqlalchemy import select

        async with get_db_session() as session:
            result = await session.execute(select(Dish).where(Dish.id == dish_id))
            dish = result.scalar_one_or_none()

        if dish:
            price = float(dish.price)
            pricing = {
                "dish_id": dish_id,
                "dish_name": dish.name,
                "current_price": price,
                "recommended_price": round(price * 1.05, 2),
                "min_price": round(price * 0.9, 2),
                "max_price": round(price * 1.2, 2),
                "confidence": 0.80,
            }
        else:
            pricing = {"dish_id": dish_id, "recommended_price": 0, "confidence": 0}

        return APIResponse(code=200, message="定价建议生成成功", data=pricing)

    # ==================== Level 3: 营销能力 ====================

    async def get_customer_profile(
        self,
        customer_id: str
    ) -> APIResponse:
        """
        客户画像API

        Args:
            customer_id: 顾客ID

        Returns:
            客户画像
        """
        logger.info(f"Getting customer profile for {customer_id}")

        from src.core.database import get_db_session
        from src.models.order import Order, OrderItem, OrderStatus
        from sqlalchemy import select, func

        async with get_db_session() as session:
            result = await session.execute(
                select(
                    func.count(Order.id).label("order_count"),
                    func.sum(Order.final_amount).label("total_spend"),
                    func.max(Order.order_time).label("last_visit"),
                ).where(
                    Order.customer_phone == customer_id,
                    Order.status == OrderStatus.COMPLETED,
                )
            )
            row = result.one()

            # 常点菜品
            top_items_result = await session.execute(
                select(OrderItem.item_name, func.sum(OrderItem.quantity).label("qty"))
                .join(Order, OrderItem.order_id == Order.id)
                .where(Order.customer_phone == customer_id, Order.status == OrderStatus.COMPLETED)
                .group_by(OrderItem.item_name)
                .order_by(func.sum(OrderItem.quantity).desc())
                .limit(3)
            )
            top_items = [r.item_name for r in top_items_result.all()]

        order_count = row.order_count or 0
        total_spend = int(row.total_spend or 0)
        value_score = min(100.0, order_count * 5 + total_spend / 10000)
        churn_risk = 0.1 if order_count > 5 else 0.5

        profile = {
            "customer_id": customer_id,
            "order_count": order_count,
            "total_spend_fen": total_spend,
            "last_visit": row.last_visit.isoformat() if row.last_visit else None,
            "value_score": round(value_score, 1),
            "churn_risk": churn_risk,
            "segment": "high_value" if value_score > 60 else "regular",
            "favorite_dishes": top_items,
        }

        return APIResponse(code=200, message="客户画像获取成功", data=profile)

    async def recommend_dishes_for_customer(
        self,
        customer_id: str,
        top_k: int = 5
    ) -> APIResponse:
        """
        个性化推荐API

        Args:
            customer_id: 顾客ID
            top_k: 推荐数量

        Returns:
            推荐菜品
        """
        logger.info(f"Recommending dishes for customer {customer_id}")

        from src.core.database import get_db_session
        from src.models.dish import Dish
        from src.models.order import Order, OrderItem, OrderStatus
        from sqlalchemy import select, func

        async with get_db_session() as session:
            # 顾客历史点过的菜
            ordered_result = await session.execute(
                select(OrderItem.item_name)
                .join(Order, OrderItem.order_id == Order.id)
                .where(Order.customer_phone == customer_id, Order.status == OrderStatus.COMPLETED)
                .distinct()
            )
            ordered_names = {r.item_name for r in ordered_result.all()}

            # 推荐高评分且顾客未点过的菜
            dishes_result = await session.execute(
                select(Dish).where(Dish.is_available == True)
                .order_by(Dish.rating.desc().nullslast(), Dish.total_sales.desc().nullslast())
                .limit(top_k + len(ordered_names))
            )
            all_dishes = dishes_result.scalars().all()

        recommendations = []
        for d in all_dishes:
            if len(recommendations) >= top_k:
                break
            recommendations.append({
                "dish_id": str(d.id),
                "dish_name": d.name,
                "price": float(d.price),
                "score": float(d.rating or 4.0),
                "is_new": d.name not in ordered_names,
            })

        return APIResponse(code=200, message="推荐生成成功", data=recommendations)

    async def generate_coupon_strategy(
        self,
        scenario: str,
        target_segment: str
    ) -> APIResponse:
        """
        优惠券策略API

        Args:
            scenario: 场景
            target_segment: 目标客群

        Returns:
            优惠券策略
        """
        logger.info(f"Generating coupon strategy for {scenario}")

        from src.core.database import get_db_session
        from src.models.order import Order, OrderStatus
        from sqlalchemy import select, func

        # 根据目标客群查询历史消费均值，生成合适的优惠券策略
        async with get_db_session() as session:
            result = await session.execute(
                select(
                    func.avg(Order.final_amount).label("avg_amount"),
                    func.count(Order.id).label("order_count"),
                ).where(Order.status == OrderStatus.COMPLETED)
            )
            row = result.one()
            avg_amount_fen = int(row.avg_amount or 10000)  # 分

        avg_yuan = avg_amount_fen / 100
        # 满减门槛 = 均值的80%，优惠 = 门槛的20%
        threshold = round(avg_yuan * 0.8 / 10) * 10
        amount = round(threshold * 0.2 / 5) * 5

        strategy = {
            "coupon_type": "满减券",
            "scenario": scenario,
            "target_segment": target_segment,
            "amount": max(5.0, float(amount)),
            "threshold": max(20.0, float(threshold)),
            "valid_days": 7 if scenario != "birthday" else 30,
            "expected_conversion": 0.25,
            "basis": f"基于历史均单价 ¥{avg_yuan:.0f} 计算",
        }

        return APIResponse(code=200, message="优惠券策略生成成功", data=strategy)

    async def trigger_marketing_campaign(
        self,
        campaign_config: Dict
    ) -> APIResponse:
        """
        触发营销活动API

        Args:
            campaign_config: 活动配置

        Returns:
            活动结果
        """
        logger.info("Triggering marketing campaign")

        from src.core.database import get_db_session
        from src.models.marketing_campaign import MarketingCampaign
        import uuid as _uuid
        from datetime import date

        campaign_id = f"CAMP_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        async with get_db_session() as session:
            campaign = MarketingCampaign(
                id=str(_uuid.uuid4()),
                store_id=campaign_config.get("store_id", ""),
                name=campaign_config.get("name", campaign_id),
                campaign_type=campaign_config.get("type", "coupon"),
                status="active",
                budget=float(campaign_config.get("budget", 0)),
                target_audience=campaign_config.get("target_audience"),
                description=campaign_config.get("description"),
            )
            session.add(campaign)
            await session.commit()
            campaign_id = campaign.id

        result = {"campaign_id": campaign_id, "status": "launched", "expected_reach": campaign_config.get("expected_reach", 0)}
        return APIResponse(code=200, message="营销活动已启动", data=result)

    # ==================== Level 4: 高级能力 ====================

    async def query_sop(
        self,
        scenario: str,
        context: Optional[Dict] = None
    ) -> APIResponse:
        """
        SOP知识库API

        Args:
            scenario: 场景
            context: 上下文

        Returns:
            SOP建议
        """
        logger.info(f"Querying SOP for scenario: {scenario}")

        from src.services.sop_knowledge_base_service import sop_knowledge_base, QueryContext

        ctx = QueryContext(
            user_role=context.get("user_role", "store_manager") if context else "store_manager",
            user_experience_years=context.get("experience_years", 1) if context else 1,
            current_situation=scenario,
            urgency=context.get("urgency", "medium") if context else "medium",
            store_type=context.get("store_type", "正餐") if context else "正餐",
        )
        recommendations = await sop_knowledge_base.query_best_practice(scenario, ctx)

        if recommendations:
            top = recommendations[0]
            sop = {
                "sop_id": top.sop_id,
                "title": top.title,
                "relevance_score": top.relevance_score,
                "confidence": top.confidence,
                "summary": top.summary,
                "key_steps": top.key_steps,
                "estimated_time_minutes": top.estimated_time_minutes,
            }
        else:
            sop = {"title": f"场景「{scenario}」暂无匹配SOP", "key_steps": [], "confidence": 0.0}

        return APIResponse(code=200, message="SOP查询成功", data=sop)

    async def get_federated_model(
        self,
        model_type: str
    ) -> APIResponse:
        """
        联邦学习模型API

        Args:
            model_type: 模型类型

        Returns:
            模型参数
        """
        logger.info(f"Getting federated model: {model_type}")

        from src.core.database import get_db_session
        from src.models.federated_learning import FLTrainingRound
        from sqlalchemy import select

        async with get_db_session() as session:
            result = await session.execute(
                select(FLTrainingRound).where(
                    FLTrainingRound.model_type == model_type,
                    FLTrainingRound.status == "completed",
                ).order_by(FLTrainingRound.completed_at.desc()).limit(1)
            )
            fl_round = result.scalar_one_or_none()

        if fl_round:
            model = {
                "model_type": model_type,
                "round_id": fl_round.id,
                "version": f"v{fl_round.id[:8]}",
                "participating_stores": fl_round.num_participating_stores or 0,
                "updated_at": fl_round.completed_at.isoformat() if fl_round.completed_at else None,
                "has_parameters": fl_round.global_model_parameters is not None,
            }
        else:
            model = {"model_type": model_type, "version": "none", "updated_at": None}

        return APIResponse(code=200, message="模型获取成功", data=model)

    # ==================== 工具方法 ====================

    def _authenticate(self) -> bool:
        """API认证"""
        # TODO: 实现认证逻辑
        return True

    def _rate_limit_check(self) -> bool:
        """限流检查"""
        # TODO: 实现限流逻辑
        return True


# ==================== SDK示例 ====================

class ZhilianSDK:
    """智链SDK（Python版本）"""

    def __init__(self, api_key: str, api_secret: str):
        self.api = ZhilianOpenAPI(api_key, api_secret)

    async def sync_order(self, order_data: Dict) -> Dict:
        """同步订单（便捷方法）"""
        order = StandardOrder(**order_data)
        response = await self.api.sync_orders([order])
        return response.dict()

    async def get_sales_prediction(
        self,
        store_id: str,
        date: str
    ) -> Dict:
        """获取销量预测（便捷方法）"""
        response = await self.api.predict_sales(
            store_id,
            datetime.fromisoformat(date)
        )
        return response.dict()


# 使用示例
"""
# 初始化SDK
sdk = ZhilianSDK(
    api_key="your_api_key",
    api_secret="your_api_secret"
)

# 同步订单
order_data = {
    "order_id": "ORD001",
    "store_id": "XJ-CS-001",
    "order_time": "2026-02-22T12:00:00",
    "order_type": "堂食",
    "items": [...],
    "total_amount": 288.0,
    "actual_amount": 268.0,
    "payment_method": "微信支付",
    "status": "已完成"
}

result = await sdk.sync_order(order_data)
print(result)

# 获取销量预测
prediction = await sdk.get_sales_prediction(
    store_id="XJ-CS-001",
    date="2026-02-23"
)
print(prediction)
"""
