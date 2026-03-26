"""
酒水/烟草专项管理服务 测试

覆盖：
- 开瓶费计算（自带/非自带/各类别）
- 配餐推荐（海鲜/辣菜/预算限制/空菜单）
- 存酒管理（存/取/查/异常场景）
- 酒水销售报表（有数据/空数据/多类别）
- 烟草年龄验证（成年/未成年/边界/异常年份）
"""

import os
for _k, _v in {
    "APP_ENV": "test",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "CELERY_BROKER_URL": "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY": "test-secret-key",
    "JWT_SECRET": "test-jwt-secret",
}.items():
    os.environ.setdefault(_k, _v)

import pytest

from src.services.beverage_wine_service import (
    BeverageCategory,
    BeverageOrderItem,
    BeverageWineService,
    WineStorageRecord,
)


# ── 开瓶费计算 ───────────────────────────────────────────────────────────────────


class TestCalculateCorkageFee:
    """开瓶费计算测试"""

    def test_byob_white_wine(self):
        """自带白酒 → ¥200"""
        result = BeverageWineService.calculate_corkage_fee(BeverageCategory.WHITE_WINE, is_byob=True)
        assert result["corkage_fee_fen"] == 20000
        assert result["corkage_fee_yuan"] == "¥200.00"
        assert result["is_byob"] is True

    def test_byob_red_wine(self):
        """自带红酒 → ¥150"""
        result = BeverageWineService.calculate_corkage_fee(BeverageCategory.RED_WINE, is_byob=True)
        assert result["corkage_fee_fen"] == 15000

    def test_byob_beer(self):
        """自带啤酒 → ¥10"""
        result = BeverageWineService.calculate_corkage_fee(BeverageCategory.BEER, is_byob=True)
        assert result["corkage_fee_fen"] == 1000

    def test_not_byob_no_fee(self):
        """非自带 → 不收开瓶费"""
        result = BeverageWineService.calculate_corkage_fee(BeverageCategory.WHITE_WINE, is_byob=False)
        assert result["corkage_fee_fen"] == 0

    def test_soft_drink_no_fee(self):
        """软饮自带 → 不收费"""
        result = BeverageWineService.calculate_corkage_fee(BeverageCategory.SOFT_DRINK, is_byob=True)
        assert result["corkage_fee_fen"] == 0


# ── 配餐推荐 ─────────────────────────────────────────────────────────────────────


class TestRecommendWinePairing:
    """配餐酒水推荐测试"""

    def test_seafood_dishes(self):
        """海鲜菜品 → 推荐干白/啤酒等"""
        result = BeverageWineService.recommend_wine_pairing(["清蒸东星斑", "蒜蓉粉丝蒸虾"])
        recs = result["recommendations"]
        assert len(recs) > 0
        # 所有推荐都有 ¥ 价格
        for r in recs:
            assert r["price_yuan"].startswith("¥")
            assert "reason" in r

    def test_spicy_dishes(self):
        """辣菜 → 推荐啤酒/凉茶"""
        result = BeverageWineService.recommend_wine_pairing(["麻辣小龙虾", "水煮牛肉"])
        recs = result["recommendations"]
        assert len(recs) > 0
        categories = {r["category"] for r in recs}
        assert "beer" in categories or "soft_drink" in categories

    def test_budget_filter(self):
        """预算限制 → 过滤贵酒"""
        result = BeverageWineService.recommend_wine_pairing(
            ["清蒸鱼", "海鲜拼盘"],
            budget_fen=2000,  # ¥20 预算，大部分酒超预算
        )
        for r in result["recommendations"]:
            assert r["price_fen"] <= 2000

    def test_empty_dishes(self):
        """空菜单 → 空推荐"""
        result = BeverageWineService.recommend_wine_pairing([])
        assert result["recommendations"] == []

    def test_no_matching_keywords(self):
        """无匹配关键词 → 空推荐"""
        result = BeverageWineService.recommend_wine_pairing(["甜品拼盘", "冰淇淋"])
        assert result["recommendations"] == []


# ── 存酒管理 ─────────────────────────────────────────────────────────────────────


class TestManageWineStorage:
    """会员存酒管理测试"""

    def test_store_wine(self):
        """存酒成功"""
        result = BeverageWineService.manage_wine_storage(
            member_id="M001",
            action="store",
            wine_info={
                "record_id": "WS001",
                "wine_name": "茅台飞天53度",
                "category": "white_wine",
                "brand": "茅台",
                "vintage": "2020",
                "volume_ml": 500,
                "member_name": "张总",
            },
        )
        assert result["success"] is True
        assert result["action"] == "store"
        assert result["record"]["wine_name"] == "茅台飞天53度"
        assert len(result["updated_records"]) == 1

    def test_retrieve_wine(self):
        """取酒成功"""
        existing = [
            WineStorageRecord(
                record_id="WS001", member_id="M001", member_name="张总",
                wine_name="茅台飞天53度", category=BeverageCategory.WHITE_WINE,
                brand="茅台", volume_ml=500, remaining_ml=500,
                stored_date="2026-03-20", status="stored",
            ),
        ]
        result = BeverageWineService.manage_wine_storage(
            member_id="M001",
            action="retrieve",
            wine_info={"record_id": "WS001", "retrieve_ml": 200},
            storage_records=existing,
        )
        assert result["success"] is True
        assert result["record"]["remaining_ml"] == 300

    def test_retrieve_all_wine(self):
        """取完全部 → 状态变 retrieved"""
        existing = [
            WineStorageRecord(
                record_id="WS001", member_id="M001", member_name="张总",
                wine_name="红酒", category=BeverageCategory.RED_WINE,
                brand="拉菲", volume_ml=750, remaining_ml=750,
                stored_date="2026-03-20", status="stored",
            ),
        ]
        result = BeverageWineService.manage_wine_storage(
            member_id="M001",
            action="retrieve",
            wine_info={"record_id": "WS001", "retrieve_ml": 750},
            storage_records=existing,
        )
        assert result["success"] is True
        assert result["record"]["remaining_ml"] == 0
        assert result["record"]["status"] == "retrieved"

    def test_retrieve_exceeds_remaining(self):
        """取酒量超过剩余 → 失败"""
        existing = [
            WineStorageRecord(
                record_id="WS001", member_id="M001", member_name="张总",
                wine_name="红酒", category=BeverageCategory.RED_WINE,
                brand="拉菲", volume_ml=750, remaining_ml=200,
                stored_date="2026-03-20", status="stored",
            ),
        ]
        result = BeverageWineService.manage_wine_storage(
            member_id="M001",
            action="retrieve",
            wine_info={"record_id": "WS001", "retrieve_ml": 500},
            storage_records=existing,
        )
        assert result["success"] is False
        assert "超过剩余" in result["message"]

    def test_retrieve_not_found(self):
        """存酒记录不存在 → 失败"""
        result = BeverageWineService.manage_wine_storage(
            member_id="M001",
            action="retrieve",
            wine_info={"record_id": "WS999", "retrieve_ml": 100},
            storage_records=[],
        )
        assert result["success"] is False

    def test_query_member_wines(self):
        """查询会员存酒"""
        existing = [
            WineStorageRecord(
                record_id="WS001", member_id="M001", member_name="张总",
                wine_name="茅台", category=BeverageCategory.WHITE_WINE,
                brand="茅台", volume_ml=500, remaining_ml=300,
                stored_date="2026-03-20", status="stored",
            ),
            WineStorageRecord(
                record_id="WS002", member_id="M001", member_name="张总",
                wine_name="拉菲", category=BeverageCategory.RED_WINE,
                brand="拉菲", volume_ml=750, remaining_ml=750,
                stored_date="2026-03-22", status="stored",
            ),
            WineStorageRecord(
                record_id="WS003", member_id="M002", member_name="李总",
                wine_name="五粮液", category=BeverageCategory.WHITE_WINE,
                brand="五粮液", volume_ml=500, remaining_ml=500,
                stored_date="2026-03-21", status="stored",
            ),
        ]
        result = BeverageWineService.manage_wine_storage(
            member_id="M001",
            action="query",
            wine_info={},
            storage_records=existing,
        )
        assert result["success"] is True
        assert result["total_count"] == 2

    def test_invalid_action(self):
        """无效操作 → 失败"""
        result = BeverageWineService.manage_wine_storage(
            member_id="M001",
            action="delete",
            wine_info={},
        )
        assert result["success"] is False
        assert "不支持" in result["message"]


# ── 酒水销售报表 ─────────────────────────────────────────────────────────────────


class TestGetBeverageSalesReport:
    """酒水销售统计测试"""

    def test_empty_orders(self):
        """空订单 → 零值报表"""
        result = BeverageWineService.get_beverage_sales_report([])
        assert result["total_revenue_fen"] == 0
        assert result["total_revenue_yuan"] == "¥0.00"

    def test_multiple_orders(self):
        """多订单 → 正确汇总"""
        orders = [
            [
                BeverageOrderItem("茅台飞天", BeverageCategory.WHITE_WINE, 2, 158800, 317600),
                BeverageOrderItem("青岛纯生", BeverageCategory.BEER, 6, 1500, 9000),
            ],
            [
                BeverageOrderItem("茅台飞天", BeverageCategory.WHITE_WINE, 1, 158800, 158800),
                BeverageOrderItem("拉菲传奇", BeverageCategory.RED_WINE, 2, 28800, 57600),
            ],
        ]
        result = BeverageWineService.get_beverage_sales_report(orders)

        assert result["total_revenue_fen"] == 317600 + 9000 + 158800 + 57600
        assert result["total_quantity"] == 2 + 6 + 1 + 2
        assert len(result["by_category"]) == 3  # 白酒/啤酒/红酒
        # 按营收降序
        assert result["by_category"][0]["category"] == "white_wine"
        # Top items
        assert result["top_items"][0]["item_name"] == "茅台飞天"
        # ¥ 字段
        assert result["total_revenue_yuan"].startswith("¥")
        for c in result["by_category"]:
            assert "revenue_yuan" in c
            assert "revenue_ratio" in c


# ── 烟草年龄验证 ─────────────────────────────────────────────────────────────────


class TestCheckTobaccoAgeVerification:
    """烟草年龄验证测试"""

    def test_adult_allowed(self):
        """成年人 → 允许"""
        result = BeverageWineService.check_tobacco_age_verification(2000, current_year=2026)
        assert result["allowed"] is True
        assert result["age"] == 26

    def test_exactly_18(self):
        """刚满18 → 允许"""
        result = BeverageWineService.check_tobacco_age_verification(2008, current_year=2026)
        assert result["allowed"] is True
        assert result["age"] == 18

    def test_minor_forbidden(self):
        """未成年 → 禁止"""
        result = BeverageWineService.check_tobacco_age_verification(2010, current_year=2026)
        assert result["allowed"] is False
        assert result["age"] == 16
        assert "禁止" in result["message"]

    def test_future_birth_year_raises(self):
        """未来出生年份 → 异常"""
        with pytest.raises(ValueError, match="不能大于"):
            BeverageWineService.check_tobacco_age_verification(2030, current_year=2026)

    def test_too_old_birth_year_raises(self):
        """1900年前出生 → 异常"""
        with pytest.raises(ValueError, match="无效"):
            BeverageWineService.check_tobacco_age_verification(1899)
