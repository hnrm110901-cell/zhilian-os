"""
酒水/烟草专项管理服务（Beverage & Wine Service）

核心功能：
- 酒水分类管理（白酒/红酒/啤酒/洋酒/软饮/茶/烟草）
- 开瓶费计算（自带酒水）
- 配餐酒水推荐
- 会员存酒管理（存/取/查）
- 酒水销售统计报表
- 烟草年龄验证

金额单位：分（fen），API 返回时 /100 转元
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Any, Dict, List, Optional


# ── 枚举定义 ────────────────────────────────────────────────────────────────────


class BeverageCategory(str, Enum):
    """酒水/烟草类别"""
    WHITE_WINE = "white_wine"       # 白酒
    RED_WINE = "red_wine"           # 红酒/葡萄酒
    BEER = "beer"                   # 啤酒
    SPIRITS = "spirits"             # 洋酒（威士忌/白兰地等）
    SOFT_DRINK = "soft_drink"       # 软饮/果汁
    TEA = "tea"                     # 茶饮
    TOBACCO = "tobacco"             # 烟草


# ── 数据模型 ────────────────────────────────────────────────────────────────────


@dataclass
class WineStorageRecord:
    """会员存酒记录"""
    record_id: str
    member_id: str
    member_name: str
    wine_name: str
    category: BeverageCategory
    brand: str
    vintage: Optional[str] = None   # 年份（红酒/白酒）
    volume_ml: int = 750            # 容量毫升
    remaining_ml: int = 750         # 剩余容量
    stored_date: str = ""           # 存入日期（YYYY-MM-DD）
    expiry_date: Optional[str] = None  # 存酒到期日（过期店方有权处理）
    status: str = "stored"          # stored / retrieved / expired
    notes: str = ""


@dataclass
class BeverageOrderItem:
    """酒水订单明细"""
    item_name: str
    category: BeverageCategory
    quantity: int
    unit_price_fen: int
    total_fen: int


# ── 开瓶费配置 ──────────────────────────────────────────────────────────────────

# 自带酒水开瓶费标准（分）
CORKAGE_FEE_TABLE: Dict[BeverageCategory, int] = {
    BeverageCategory.WHITE_WINE: 20000,     # ¥200/瓶
    BeverageCategory.RED_WINE: 15000,       # ¥150/瓶
    BeverageCategory.BEER: 1000,            # ¥10/瓶
    BeverageCategory.SPIRITS: 30000,        # ¥300/瓶
    BeverageCategory.SOFT_DRINK: 0,         # 不收
    BeverageCategory.TEA: 0,                # 不收
    BeverageCategory.TOBACCO: 0,            # 不适用
}

# ── 配餐推荐知识库 ──────────────────────────────────────────────────────────────

# 菜品关键词 → 推荐酒水类别及具体推荐
PAIRING_RULES: List[Dict[str, Any]] = [
    {
        "keywords": ["海鲜", "鱼", "虾", "蟹", "贝", "刺身", "蒸"],
        "recommendations": [
            {"name": "长城干白葡萄酒", "category": BeverageCategory.RED_WINE, "price_fen": 12800, "reason": "干白配海鲜，清爽不腻"},
            {"name": "青岛纯生", "category": BeverageCategory.BEER, "price_fen": 1500, "reason": "冰啤配海鲜，经典搭配"},
            {"name": "獭祭纯米大吟酿", "category": BeverageCategory.SPIRITS, "price_fen": 38800, "reason": "日本清酒配刺身，极致体验"},
        ],
    },
    {
        "keywords": ["牛肉", "羊肉", "烤", "红烧", "炖"],
        "recommendations": [
            {"name": "张裕解百纳干红", "category": BeverageCategory.RED_WINE, "price_fen": 16800, "reason": "浓郁干红配红肉，层次丰富"},
            {"name": "泸州老窖特曲", "category": BeverageCategory.WHITE_WINE, "price_fen": 28800, "reason": "浓香型白酒配肉菜，香气浑厚"},
        ],
    },
    {
        "keywords": ["辣", "麻辣", "火锅", "小龙虾", "水煮"],
        "recommendations": [
            {"name": "雪花纯生", "category": BeverageCategory.BEER, "price_fen": 800, "reason": "冰啤解辣，清爽畅快"},
            {"name": "王老吉凉茶", "category": BeverageCategory.SOFT_DRINK, "price_fen": 600, "reason": "凉茶降火，健康之选"},
            {"name": "酸梅汤", "category": BeverageCategory.SOFT_DRINK, "price_fen": 500, "reason": "酸甜解腻，开胃佐餐"},
        ],
    },
    {
        "keywords": ["清蒸", "炒菜", "素菜", "汤"],
        "recommendations": [
            {"name": "西湖龙井", "category": BeverageCategory.TEA, "price_fen": 3800, "reason": "清茶配清淡菜肴，相得益彰"},
            {"name": "长城干白", "category": BeverageCategory.RED_WINE, "price_fen": 12800, "reason": "轻盈白葡萄酒配素菜"},
        ],
    },
    {
        "keywords": ["宴会", "宴席", "生日", "聚餐", "庆祝"],
        "recommendations": [
            {"name": "茅台飞天53度", "category": BeverageCategory.WHITE_WINE, "price_fen": 158800, "reason": "国宴级白酒，宴请首选"},
            {"name": "拉菲传奇波尔多", "category": BeverageCategory.RED_WINE, "price_fen": 28800, "reason": "法国名庄，宴会有面子"},
            {"name": "轩尼诗VSOP", "category": BeverageCategory.SPIRITS, "price_fen": 48800, "reason": "经典白兰地，品位之选"},
        ],
    },
]


# ── 服务类 ──────────────────────────────────────────────────────────────────────


class BeverageWineService:
    """酒水/烟草专项管理服务"""

    @staticmethod
    def calculate_corkage_fee(
        wine_category: BeverageCategory,
        is_byob: bool,
    ) -> Dict[str, Any]:
        """
        计算开瓶费

        Args:
            wine_category: 酒水类别
            is_byob: 是否自带酒水（Bring Your Own Bottle）

        Returns:
            {
                "corkage_fee_fen": int,
                "corkage_fee_yuan": str,
                "is_byob": bool,
                "category": str,
            }
        """
        fee_fen = 0
        if is_byob:
            fee_fen = CORKAGE_FEE_TABLE.get(wine_category, 0)

        return {
            "corkage_fee_fen": fee_fen,
            "corkage_fee_yuan": f"¥{fee_fen / 100:.2f}",
            "is_byob": is_byob,
            "category": wine_category.value,
        }

    @staticmethod
    def recommend_wine_pairing(
        dish_names: List[str],
        budget_fen: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        配餐酒水推荐

        Args:
            dish_names: 菜品名称列表
            budget_fen: 预算上限（分），None 表示不限

        Returns:
            {
                "recommendations": [...],
                "budget_fen": int | None,
                "budget_yuan": str | None,
            }
        """
        if not dish_names:
            return {
                "recommendations": [],
                "budget_fen": budget_fen,
                "budget_yuan": f"¥{budget_fen / 100:.2f}" if budget_fen is not None else None,
            }

        # 收集匹配的推荐
        seen_names: set = set()
        matched: List[Dict[str, Any]] = []

        combined_text = " ".join(dish_names)

        for rule in PAIRING_RULES:
            for keyword in rule["keywords"]:
                if keyword in combined_text:
                    for rec in rule["recommendations"]:
                        if rec["name"] not in seen_names:
                            # 预算过滤
                            if budget_fen is not None and rec["price_fen"] > budget_fen:
                                continue
                            seen_names.add(rec["name"])
                            matched.append({
                                "name": rec["name"],
                                "category": rec["category"].value,
                                "price_fen": rec["price_fen"],
                                "price_yuan": f"¥{rec['price_fen'] / 100:.2f}",
                                "reason": rec["reason"],
                            })
                    break  # 一条规则匹配一个关键词就够了

        # 按价格升序排列
        matched.sort(key=lambda x: x["price_fen"])

        return {
            "recommendations": matched,
            "budget_fen": budget_fen,
            "budget_yuan": f"¥{budget_fen / 100:.2f}" if budget_fen is not None else None,
        }

    @staticmethod
    def manage_wine_storage(
        member_id: str,
        action: str,
        wine_info: Dict[str, Any],
        storage_records: Optional[List[WineStorageRecord]] = None,
    ) -> Dict[str, Any]:
        """
        会员存/取酒操作

        Args:
            member_id: 会员ID
            action: "store" 存酒 / "retrieve" 取酒 / "query" 查询
            wine_info: 酒水信息
                - store: {record_id, wine_name, category, brand, vintage?, volume_ml?, notes?}
                - retrieve: {record_id, retrieve_ml}
                - query: {} （无需额外参数）
            storage_records: 现有存酒记录列表（纯函数，外部传入）

        Returns:
            操作结果字典
        """
        records = list(storage_records or [])

        if action == "store":
            # 存酒
            new_record = WineStorageRecord(
                record_id=wine_info.get("record_id", ""),
                member_id=member_id,
                member_name=wine_info.get("member_name", ""),
                wine_name=wine_info.get("wine_name", ""),
                category=BeverageCategory(wine_info.get("category", "red_wine")),
                brand=wine_info.get("brand", ""),
                vintage=wine_info.get("vintage"),
                volume_ml=wine_info.get("volume_ml", 750),
                remaining_ml=wine_info.get("volume_ml", 750),
                stored_date=wine_info.get("stored_date", datetime.now().strftime("%Y-%m-%d")),
                expiry_date=wine_info.get("expiry_date"),
                status="stored",
                notes=wine_info.get("notes", ""),
            )
            records.append(new_record)
            return {
                "success": True,
                "action": "store",
                "record": {
                    "record_id": new_record.record_id,
                    "wine_name": new_record.wine_name,
                    "volume_ml": new_record.volume_ml,
                    "stored_date": new_record.stored_date,
                },
                "updated_records": records,
                "message": f"已为会员 {member_id} 存入 {new_record.wine_name}",
            }

        elif action == "retrieve":
            # 取酒
            record_id = wine_info.get("record_id", "")
            retrieve_ml = wine_info.get("retrieve_ml", 0)

            target = None
            for r in records:
                if r.record_id == record_id and r.member_id == member_id:
                    target = r
                    break

            if target is None:
                return {
                    "success": False,
                    "action": "retrieve",
                    "message": f"未找到会员 {member_id} 的存酒记录 {record_id}",
                    "updated_records": records,
                }

            if target.status != "stored":
                return {
                    "success": False,
                    "action": "retrieve",
                    "message": f"该存酒记录状态为 {target.status}，无法取酒",
                    "updated_records": records,
                }

            if retrieve_ml <= 0:
                return {
                    "success": False,
                    "action": "retrieve",
                    "message": "取酒量必须大于 0",
                    "updated_records": records,
                }

            if retrieve_ml > target.remaining_ml:
                return {
                    "success": False,
                    "action": "retrieve",
                    "message": f"取酒量 {retrieve_ml}ml 超过剩余 {target.remaining_ml}ml",
                    "updated_records": records,
                }

            target.remaining_ml -= retrieve_ml
            if target.remaining_ml == 0:
                target.status = "retrieved"

            return {
                "success": True,
                "action": "retrieve",
                "record": {
                    "record_id": target.record_id,
                    "wine_name": target.wine_name,
                    "retrieved_ml": retrieve_ml,
                    "remaining_ml": target.remaining_ml,
                    "status": target.status,
                },
                "updated_records": records,
                "message": f"已取出 {target.wine_name} {retrieve_ml}ml，剩余 {target.remaining_ml}ml",
            }

        elif action == "query":
            # 查询存酒
            member_records = [r for r in records if r.member_id == member_id and r.status == "stored"]
            return {
                "success": True,
                "action": "query",
                "records": [
                    {
                        "record_id": r.record_id,
                        "wine_name": r.wine_name,
                        "brand": r.brand,
                        "category": r.category.value,
                        "volume_ml": r.volume_ml,
                        "remaining_ml": r.remaining_ml,
                        "stored_date": r.stored_date,
                        "expiry_date": r.expiry_date,
                    }
                    for r in member_records
                ],
                "total_count": len(member_records),
                "message": f"会员 {member_id} 当前有 {len(member_records)} 条存酒记录",
            }

        else:
            return {
                "success": False,
                "action": action,
                "message": f"不支持的操作: {action}，仅支持 store/retrieve/query",
                "updated_records": records,
            }

    @staticmethod
    def get_beverage_sales_report(
        orders: List[List[BeverageOrderItem]],
    ) -> Dict[str, Any]:
        """
        酒水销售统计（按类别）

        Args:
            orders: 订单酒水明细列表（每个订单包含多个酒水项）

        Returns:
            {
                "total_revenue_fen": int,
                "total_revenue_yuan": str,
                "total_quantity": int,
                "by_category": [...],
                "top_items": [...],
            }
        """
        if not orders:
            return {
                "total_revenue_fen": 0,
                "total_revenue_yuan": "¥0.00",
                "total_quantity": 0,
                "by_category": [],
                "top_items": [],
            }

        # 按类别统计
        category_stats: Dict[str, Dict[str, Any]] = {}
        item_stats: Dict[str, Dict[str, Any]] = {}

        total_revenue = 0
        total_quantity = 0

        for order_items in orders:
            for item in order_items:
                total_revenue += item.total_fen
                total_quantity += item.quantity

                cat = item.category.value
                if cat not in category_stats:
                    category_stats[cat] = {
                        "category": cat,
                        "quantity": 0,
                        "revenue_fen": 0,
                    }
                category_stats[cat]["quantity"] += item.quantity
                category_stats[cat]["revenue_fen"] += item.total_fen

                if item.item_name not in item_stats:
                    item_stats[item.item_name] = {
                        "item_name": item.item_name,
                        "category": cat,
                        "quantity": 0,
                        "revenue_fen": 0,
                    }
                item_stats[item.item_name]["quantity"] += item.quantity
                item_stats[item.item_name]["revenue_fen"] += item.total_fen

        # 按营收排序的类别列表
        by_category = sorted(
            category_stats.values(),
            key=lambda x: x["revenue_fen"],
            reverse=True,
        )
        for c in by_category:
            c["revenue_yuan"] = f"¥{c['revenue_fen'] / 100:.2f}"
            if total_revenue > 0:
                c["revenue_ratio"] = round(c["revenue_fen"] / total_revenue, 4)
            else:
                c["revenue_ratio"] = 0

        # 按销量排序的 Top 单品
        top_items = sorted(
            item_stats.values(),
            key=lambda x: x["revenue_fen"],
            reverse=True,
        )[:10]
        for t in top_items:
            t["revenue_yuan"] = f"¥{t['revenue_fen'] / 100:.2f}"

        return {
            "total_revenue_fen": total_revenue,
            "total_revenue_yuan": f"¥{total_revenue / 100:.2f}",
            "total_quantity": total_quantity,
            "by_category": by_category,
            "top_items": top_items,
        }

    @staticmethod
    def check_tobacco_age_verification(
        customer_birth_year: int,
        current_year: int = 2026,
    ) -> Dict[str, Any]:
        """
        烟草年龄验证（中国法定购烟年龄 18 岁）

        Args:
            customer_birth_year: 顾客出生年份
            current_year: 当前年份（默认 2026）

        Returns:
            {
                "allowed": bool,
                "age": int,
                "min_age": int,
                "message": str,
            }
        """
        if customer_birth_year > current_year:
            raise ValueError(f"出生年份 {customer_birth_year} 不能大于当前年份 {current_year}")
        if customer_birth_year < 1900:
            raise ValueError(f"出生年份 {customer_birth_year} 无效")

        age = current_year - customer_birth_year
        min_age = 18
        allowed = age >= min_age

        if allowed:
            message = f"验证通过：顾客年龄 {age} 岁，符合购烟条件"
        else:
            message = f"验证未通过：顾客年龄 {age} 岁，未满 {min_age} 岁，禁止销售烟草"

        return {
            "allowed": allowed,
            "age": age,
            "min_age": min_age,
            "message": message,
        }
