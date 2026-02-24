"""
Supply Chain Integration Service
供应链整合服务

Phase 5: 生态扩展期 (Ecosystem Expansion Period)
Integrates with suppliers for automated procurement
"""

import os
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession


class SupplierType(Enum):
    """Supplier type enum"""
    FOOD = "food"  # 食材供应商
    BEVERAGE = "beverage"  # 饮料供应商
    EQUIPMENT = "equipment"  # 设备供应商
    PACKAGING = "packaging"  # 包装供应商
    CLEANING = "cleaning"  # 清洁用品供应商


class QuoteStatus(Enum):
    """Quote status enum"""
    PENDING = "pending"
    RECEIVED = "received"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


@dataclass
class Supplier:
    """Supplier"""
    supplier_id: str
    name: str
    supplier_type: SupplierType
    contact: str
    rating: float  # 0-5
    delivery_time_days: int
    min_order_amount: float
    payment_terms: str  # e.g., "Net 30"
    api_endpoint: Optional[str]  # For automated integration
    created_at: datetime


@dataclass
class PurchaseQuote:
    """Purchase quote from supplier"""
    quote_id: str
    supplier_id: str
    material_id: str
    quantity: float
    unit_price: float
    total_price: float
    delivery_date: datetime
    valid_until: datetime
    status: QuoteStatus
    created_at: datetime


@dataclass
class PurchaseOrder:
    """Purchase order"""
    order_id: str
    supplier_id: str
    store_id: str
    items: List[Dict[str, Any]]
    total_amount: float
    delivery_date: datetime
    status: str  # pending, confirmed, shipped, delivered
    created_at: datetime


class SupplyChainIntegration:
    """
    Supply Chain Integration Service
    供应链整合服务

    Integrates with suppliers for:
    1. Automated quote requests
    2. Price comparison
    3. Purchase order management
    4. Supply chain finance

    Key features:
    - Multi-supplier integration
    - Automated quote comparison
    - Best price selection
    - Payment terms optimization
    - Supply chain financing
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        # Store suppliers
        self.suppliers: Dict[str, Supplier] = {}
        # Store quotes
        self.quotes: Dict[str, PurchaseQuote] = {}
        # Store purchase orders
        self.purchase_orders: Dict[str, PurchaseOrder] = {}
        # Initialize default suppliers
        self._initialize_default_suppliers()

    def _initialize_default_suppliers(self):
        """Initialize default suppliers"""
        # Food supplier
        supplier1 = Supplier(
            supplier_id="supplier_001",
            name="优质食材供应商",
            supplier_type=SupplierType.FOOD,
            contact="400-123-4567",
            rating=4.5,
            delivery_time_days=1,
            min_order_amount=float(os.getenv("SUPPLY_CHAIN_MIN_ORDER_AMOUNT_1", "500.0")),
            payment_terms="Net 30",
            api_endpoint="https://api.supplier001.com",
            created_at=datetime.utcnow()
        )
        self.suppliers[supplier1.supplier_id] = supplier1

        supplier2 = Supplier(
            supplier_id="supplier_002",
            name="快速配送食材",
            supplier_type=SupplierType.FOOD,
            contact="400-234-5678",
            rating=4.2,
            delivery_time_days=0,  # Same day
            min_order_amount=float(os.getenv("SUPPLY_CHAIN_MIN_ORDER_AMOUNT_2", "300.0")),
            payment_terms="Net 15",
            api_endpoint="https://api.supplier002.com",
            created_at=datetime.utcnow()
        )
        self.suppliers[supplier2.supplier_id] = supplier2

    def register_supplier(
        self,
        name: str,
        supplier_type: SupplierType,
        contact: str,
        delivery_time_days: int,
        min_order_amount: float,
        payment_terms: str,
        api_endpoint: Optional[str] = None
    ) -> Supplier:
        """
        Register new supplier
        注册新供应商

        Args:
            name: Supplier name
            supplier_type: Supplier type
            contact: Contact information
            delivery_time_days: Delivery time in days
            min_order_amount: Minimum order amount
            payment_terms: Payment terms
            api_endpoint: API endpoint for integration

        Returns:
            Registered supplier
        """
        supplier_id = f"supplier_{len(self.suppliers) + 1:03d}"

        supplier = Supplier(
            supplier_id=supplier_id,
            name=name,
            supplier_type=supplier_type,
            contact=contact,
            rating=0.0,
            delivery_time_days=delivery_time_days,
            min_order_amount=min_order_amount,
            payment_terms=payment_terms,
            api_endpoint=api_endpoint,
            created_at=datetime.utcnow()
        )

        self.suppliers[supplier_id] = supplier

        return supplier

    def request_quotes(
        self,
        material_id: str,
        quantity: float,
        required_date: datetime,
        supplier_ids: Optional[List[str]] = None
    ) -> List[PurchaseQuote]:
        """
        Request quotes from suppliers
        向供应商询价

        Args:
            material_id: Material identifier
            quantity: Required quantity
            required_date: Required delivery date
            supplier_ids: Specific suppliers (optional, defaults to all)

        Returns:
            List of quotes
        """
        if supplier_ids is None:
            # Request from all food suppliers
            supplier_ids = [
                s.supplier_id for s in self.suppliers.values()
                if s.supplier_type == SupplierType.FOOD
            ]

        quotes = []

        for supplier_id in supplier_ids:
            supplier = self.suppliers.get(supplier_id)
            if not supplier:
                continue

            # Simulate quote (in production, call supplier API)
            quote = self._simulate_quote(
                supplier_id,
                material_id,
                quantity,
                required_date
            )

            quotes.append(quote)
            self.quotes[quote.quote_id] = quote

        return quotes

    def _simulate_quote(
        self,
        supplier_id: str,
        material_id: str,
        quantity: float,
        required_date: datetime
    ) -> PurchaseQuote:
        """Generate quote based on supplier config"""
        quote_id = f"quote_{supplier_id}_{material_id}_{datetime.utcnow().timestamp()}"

        supplier = self.suppliers.get(supplier_id)
        base_price = float(os.getenv(
            f"SUPPLY_PRICE_{material_id.upper()}",
            os.getenv("SUPPLY_CHAIN_MOCK_BASE_PRICE", "10.0")
        ))
        if supplier:
            # Higher-rated suppliers carry a quality premium (rating 0-5 → factor 0.9-1.1)
            rating_factor = 0.9 + (supplier.rating / 5.0) * 0.2
            unit_price = base_price * rating_factor
        else:
            unit_price = base_price

        total_price = unit_price * quantity

        return PurchaseQuote(
            quote_id=quote_id,
            supplier_id=supplier_id,
            material_id=material_id,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
            delivery_date=required_date,
            valid_until=datetime.utcnow() + timedelta(days=int(os.getenv("SUPPLY_CHAIN_QUOTE_VALID_DAYS", "3"))),
            status=QuoteStatus.RECEIVED,
            created_at=datetime.utcnow()
        )

    def compare_quotes(
        self,
        quote_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Compare quotes
        比较报价

        Args:
            quote_ids: Quote identifiers

        Returns:
            Comparison results with best quote
        """
        quotes = [self.quotes[qid] for qid in quote_ids if qid in self.quotes]

        if not quotes:
            return {"error": "No quotes found"}

        # Sort by total price
        quotes.sort(key=lambda q: q.total_price)

        best_quote = quotes[0]
        supplier = self.suppliers[best_quote.supplier_id]

        comparisons = []
        for quote in quotes:
            sup = self.suppliers[quote.supplier_id]
            comparisons.append({
                "quote_id": quote.quote_id,
                "supplier_name": sup.name,
                "unit_price": quote.unit_price,
                "total_price": quote.total_price,
                "delivery_time_days": sup.delivery_time_days,
                "supplier_rating": sup.rating,
                "is_best": quote.quote_id == best_quote.quote_id
            })

        return {
            "best_quote": {
                "quote_id": best_quote.quote_id,
                "supplier_name": supplier.name,
                "total_price": best_quote.total_price,
                "savings": quotes[-1].total_price - best_quote.total_price if len(quotes) > 1 else 0
            },
            "comparisons": comparisons,
            "total_quotes": len(quotes)
        }

    def create_purchase_order(
        self,
        store_id: str,
        quote_id: str
    ) -> PurchaseOrder:
        """
        Create purchase order from quote
        从报价创建采购订单

        Args:
            store_id: Store identifier
            quote_id: Quote identifier

        Returns:
            Purchase order
        """
        quote = self.quotes.get(quote_id)
        if not quote:
            raise ValueError("Quote not found")

        if quote.status != QuoteStatus.RECEIVED:
            raise ValueError("Quote is not available")

        # Mark quote as accepted
        quote.status = QuoteStatus.ACCEPTED

        # Create purchase order
        order_id = f"po_{store_id}_{datetime.utcnow().timestamp()}"

        order = PurchaseOrder(
            order_id=order_id,
            supplier_id=quote.supplier_id,
            store_id=store_id,
            items=[{
                "material_id": quote.material_id,
                "quantity": quote.quantity,
                "unit_price": quote.unit_price,
                "total_price": quote.total_price
            }],
            total_amount=quote.total_price,
            delivery_date=quote.delivery_date,
            status="pending",
            created_at=datetime.utcnow()
        )

        self.purchase_orders[order_id] = order

        return order

    def get_supply_chain_finance_options(
        self,
        order_id: str
    ) -> Dict[str, Any]:
        """
        Get supply chain finance options
        获取供应链金融选项

        Provides financing options for purchase orders.

        Args:
            order_id: Purchase order identifier

        Returns:
            Finance options
        """
        order = self.purchase_orders.get(order_id)
        if not order:
            raise ValueError("Order not found")

        supplier = self.suppliers[order.supplier_id]

        # Calculate finance options
        options = []

        # Option 1: Early payment discount
        early_payment_discount = float(os.getenv("SUPPLY_CHAIN_EARLY_PAYMENT_DISCOUNT", "0.02"))  # early payment discount
        early_payment_amount = order.total_amount * (1 - early_payment_discount)
        options.append({
            "type": "early_payment_discount",
            "description": "提前付款享受2%折扣",
            "amount": early_payment_amount,
            "savings": order.total_amount - early_payment_amount,
            "payment_terms": "立即付款"
        })

        # Option 2: Standard payment terms
        options.append({
            "type": "standard_terms",
            "description": f"标准付款条款: {supplier.payment_terms}",
            "amount": order.total_amount,
            "savings": 0,
            "payment_terms": supplier.payment_terms
        })

        # Option 3: Extended payment terms (with interest)
        extended_interest = float(os.getenv("SUPPLY_CHAIN_EXTENDED_INTEREST", "0.05"))  # extended interest
        extended_amount = order.total_amount * (1 + extended_interest)
        options.append({
            "type": "extended_terms",
            "description": "延长付款期限至60天（需支付5%利息）",
            "amount": extended_amount,
            "savings": -extended_amount + order.total_amount,
            "payment_terms": "Net 60"
        })

        return {
            "order_id": order_id,
            "order_amount": order.total_amount,
            "finance_options": options,
            "recommended": "early_payment_discount"  # Recommend best option
        }

    def get_supplier_performance(
        self,
        supplier_id: str,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        Get supplier performance metrics
        获取供应商绩效指标

        Args:
            supplier_id: Supplier identifier
            start_date: Start date
            end_date: End date

        Returns:
            Performance metrics
        """
        supplier = self.suppliers.get(supplier_id)
        if not supplier:
            raise ValueError("Supplier not found")

        # Get orders for supplier in period
        orders = [
            o for o in self.purchase_orders.values()
            if o.supplier_id == supplier_id
            and start_date <= o.created_at <= end_date
        ]

        # Calculate metrics
        total_orders = len(orders)
        total_amount = sum(o.total_amount for o in orders)
        on_time_deliveries = len([o for o in orders if o.status == "delivered"])
        on_time_rate = on_time_deliveries / total_orders if total_orders > 0 else 0

        return {
            "supplier_id": supplier_id,
            "supplier_name": supplier.name,
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "metrics": {
                "total_orders": total_orders,
                "total_amount": total_amount,
                "on_time_delivery_rate": on_time_rate,
                "average_order_value": total_amount / total_orders if total_orders > 0 else 0,
                "supplier_rating": supplier.rating
            }
        }
