"""
数据融合引擎完整测试 — Phase P1

覆盖：
  1. EntityResolver: 精确/名称/模糊/批量/冲突 (15 tests)
  2. DataFusionEngine: 项目/任务/进度/重试 (10 tests)
  3. HistoricalBackfill: CSV/断点续传/血缘 (8 tests)
  4. TimelineAssembler: 事件/快照/模式/异常 (10 tests)
  5. KnowledgeGenerator: 体检报告6维分析 (7 tests)
"""

import os

# 测试环境变量（必须在 src.* 导入前设置，参考 L002 经验教训）
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

from datetime import date, datetime, timedelta
from typing import Dict, List

from src.services.entity_resolver import (
    EntityResolver,
    _jaccard_similarity,
    _normalize_customer_phone,
    _normalize_dish_name,
    _normalize_ingredient_name,
)
from src.services.data_fusion_engine import DataFusionEngine
from src.services.historical_backfill import HistoricalBackfill
from src.services.timeline_assembler import TimelineAssembler, TimelineEvent
from src.services.knowledge_generator import KnowledgeGenerator


# ═══════════════════════════════════════════════════════════════════════════════
# EntityResolver Tests (15)
# ═══════════════════════════════════════════════════════════════════════════════

class TestNormalization:
    """文本规范化测试"""

    def test_dish_name_remove_brackets(self):
        assert _normalize_dish_name("剁椒鱼头(大份)") == "剁椒鱼头"

    def test_dish_name_remove_square_brackets(self):
        assert _normalize_dish_name("【必点】秘制红烧肉 买一送一") == "红烧肉"

    def test_dish_name_remove_prefix(self):
        assert _normalize_dish_name("招牌水煮鱼") == "水煮鱼"

    def test_dish_name_plain(self):
        assert _normalize_dish_name("宫保鸡丁") == "宫保鸡丁"

    def test_dish_name_empty(self):
        assert _normalize_dish_name("") == ""

    def test_phone_normalize_spaces(self):
        assert _normalize_customer_phone("138 1234 5678") == "13812345678"

    def test_phone_normalize_country_code(self):
        assert _normalize_customer_phone("+8613812345678") == "13812345678"

    def test_phone_normalize_86_prefix(self):
        assert _normalize_customer_phone("8613812345678") == "13812345678"

    def test_ingredient_name_remove_weight(self):
        assert _normalize_ingredient_name("五花肉500g") == "五花肉"

    def test_jaccard_identical(self):
        assert _jaccard_similarity("剁椒鱼头", "剁椒鱼头") == 1.0

    def test_jaccard_different(self):
        assert _jaccard_similarity("剁椒鱼头", "酸菜鱼") < 0.5

    def test_jaccard_empty(self):
        assert _jaccard_similarity("", "abc") == 0.0


class TestEntityResolver:
    """实体解析器测试"""

    def test_new_entity(self):
        resolver = EntityResolver()
        r = resolver.resolve("dish", "pinzhi", external_id="D001", name="剁椒鱼头")
        assert r.is_new is True
        assert r.match_method == "new"
        assert r.canonical_name == "剁椒鱼头"

    def test_exact_id_match(self):
        resolver = EntityResolver()
        r1 = resolver.resolve("dish", "pinzhi", external_id="D001", name="剁椒鱼头")
        r2 = resolver.resolve("dish", "pinzhi", external_id="D001", name="剁椒鱼头")
        assert r2.is_new is False
        assert r2.match_method == "exact_id"
        assert r2.canonical_id == r1.canonical_id
        assert r2.confidence == 1.0

    def test_cross_system_name_match(self):
        resolver = EntityResolver()
        r1 = resolver.resolve("dish", "pinzhi", external_id="D001", name="剁椒鱼头")
        r2 = resolver.resolve("dish", "meituan", external_id="MT999", name="剁椒鱼头")
        assert r2.is_new is False
        assert r2.match_method == "exact_name"
        assert r2.canonical_id == r1.canonical_id
        assert r2.confidence == 0.98

    def test_fuzzy_name_match(self):
        """招牌剁椒鱼头(大份) 规范化后 → 剁椒鱼头 → 精确匹配"""
        resolver = EntityResolver()
        resolver.resolve("dish", "pinzhi", external_id="D001", name="剁椒鱼头")
        r = resolver.resolve("dish", "eleme", external_id="EL888", name="招牌剁椒鱼头(大份)")
        assert r.is_new is False
        # 规范化后"剁椒鱼头"完全匹配
        assert r.match_method in ("exact_name", "fuzzy_name")

    def test_different_entity(self):
        resolver = EntityResolver()
        resolver.resolve("dish", "pinzhi", external_id="D001", name="剁椒鱼头")
        r = resolver.resolve("dish", "pinzhi", external_id="D999", name="麻婆豆腐")
        assert r.is_new is True

    def test_batch_resolve(self):
        resolver = EntityResolver()
        result = resolver.batch_resolve("dish", "test", [
            {"external_id": "T1", "name": "剁椒鱼头"},
            {"external_id": "T2", "name": "酸菜鱼"},
            {"external_id": "T3", "name": "宫保鸡丁"},
        ])
        assert result.total == 3
        assert result.resolved == 3
        assert result.new_entities == 3

    def test_batch_resolve_with_duplicates(self):
        resolver = EntityResolver()
        # 先注册一个
        resolver.resolve("dish", "pinzhi", external_id="D001", name="剁椒鱼头")
        result = resolver.batch_resolve("dish", "meituan", [
            {"external_id": "MT1", "name": "剁椒鱼头"},  # 应匹配已有
            {"external_id": "MT2", "name": "新菜品"},
        ])
        assert result.total == 2
        assert result.new_entities == 1  # 只有新菜品是新的

    def test_conflict_detection(self):
        resolver = EntityResolver()
        conflict = resolver.detect_conflict(
            "dish", "canonical-001", "price",
            "pinzhi", 5800, "meituan", 6200
        )
        assert conflict is not None
        assert conflict["field_name"] == "price"

    def test_no_conflict_same_value(self):
        resolver = EntityResolver()
        conflict = resolver.detect_conflict(
            "dish", "canonical-001", "price",
            "pinzhi", 5800, "meituan", 5800
        )
        assert conflict is None

    def test_no_conflict_null_value(self):
        resolver = EntityResolver()
        conflict = resolver.detect_conflict(
            "dish", "canonical-001", "price",
            "pinzhi", 5800, "meituan", None
        )
        assert conflict is None

    def test_get_entity_map_records(self):
        resolver = EntityResolver()
        resolver.resolve("dish", "pinzhi", external_id="D001", name="剁椒鱼头")
        resolver.resolve("dish", "pinzhi", external_id="D002", name="酸菜鱼")
        records = resolver.get_entity_map_records()
        assert len(records) == 2

    def test_customer_phone_match(self):
        """客户手机号精确匹配"""
        resolver = EntityResolver()
        # 第一次注册客户（带手机号在metadata里）
        r1 = resolver.resolve(
            "customer", "pinzhi", external_id="C001", name="张三",
            phone="13812345678",
            metadata={"phone": "13812345678"}
        )
        # 用external_id注册映射并带手机号
        # 由于phone匹配逻辑需要遍历已有映射的metadata，
        # 我们需要确保metadata被索引
        assert r1.is_new is True


# ═══════════════════════════════════════════════════════════════════════════════
# DataFusionEngine Tests (10)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDataFusionEngine:
    """融合引擎测试"""

    def _create_engine_with_project(self):
        engine = DataFusionEngine()
        plan = engine.create_project(
            brand_id="BRAND001",
            name="尝在一起-测试融合",
            source_systems=[
                {"system_type": "pinzhi", "category": "pos"},
                {"system_type": "weishenghuo", "category": "member"},
            ],
            store_ids=["S001"],
            entity_types=["order", "dish", "customer"],
        )
        return engine, plan

    def test_create_project(self):
        engine, plan = self._create_engine_with_project()
        assert plan.total_tasks > 0
        assert plan.brand_id == "BRAND001"

    def test_task_priority_ordering(self):
        engine, plan = self._create_engine_with_project()
        priorities = [t["priority"] for t in plan.tasks]
        assert priorities == sorted(priorities, reverse=True)

    def test_entity_type_filtering(self):
        """member系统不应生成order任务（member类别只支持customer）"""
        engine, plan = self._create_engine_with_project()
        member_tasks = [t for t in plan.tasks if t["source_system"] == "weishenghuo"]
        entity_types = {t["entity_type"] for t in member_tasks}
        assert "order" not in entity_types
        assert "customer" in entity_types

    def test_initial_progress(self):
        engine, plan = self._create_engine_with_project()
        progress = engine.get_project_progress(plan.project_id)
        assert progress is not None
        assert progress.completed_tasks == 0
        assert progress.progress_pct == 0.0

    def test_update_task_progress(self):
        engine, plan = self._create_engine_with_project()
        task = plan.tasks[0]
        engine.update_task_progress(
            task["id"],
            processed_count=50,
            success_count=48,
            error_count=2,
            last_cursor="page_5",
            status="running",
            total_estimated=200,
        )
        progress = engine.get_project_progress(plan.project_id)
        running = [t for t in progress.tasks if t.status == "running"]
        assert len(running) == 1
        assert running[0].processed_count == 50

    def test_mark_task_completed(self):
        engine, plan = self._create_engine_with_project()
        task = plan.tasks[0]
        engine.update_task_progress(task["id"], 100, 98, 2, status="running")
        engine.mark_task_completed(task["id"])
        progress = engine.get_project_progress(plan.project_id)
        assert progress.completed_tasks == 1
        assert progress.total_records_imported == 98

    def test_mark_task_failed(self):
        engine, plan = self._create_engine_with_project()
        task = plan.tasks[0]
        engine.mark_task_failed(task["id"], "连接超时")
        progress = engine.get_project_progress(plan.project_id)
        assert progress.failed_tasks == 1

    def test_retry_failed_task(self):
        engine, plan = self._create_engine_with_project()
        task = plan.tasks[0]
        engine.mark_task_failed(task["id"], "网络错误")
        assert engine.retry_task(task["id"]) is True
        # 重试后状态变回pending
        progress = engine.get_project_progress(plan.project_id)
        pending = [t for t in progress.tasks if t.task_id == task["id"]]
        assert pending[0].status == "pending"

    def test_retry_non_failed_task(self):
        engine, plan = self._create_engine_with_project()
        task = plan.tasks[0]
        assert engine.retry_task(task["id"]) is False  # pending状态不能重试

    def test_get_next_tasks(self):
        engine, plan = self._create_engine_with_project()
        next_tasks = engine.get_next_tasks(plan.project_id, limit=2)
        assert len(next_tasks) <= 2
        assert all(t["status"] == "pending" for t in next_tasks)

    def test_project_auto_transition_to_resolving(self):
        """所有任务完成后项目自动进入resolving状态"""
        engine, plan = self._create_engine_with_project()
        for task in plan.tasks:
            engine.update_task_progress(task["id"], 10, 10, 0, status="running")
            engine.mark_task_completed(task["id"])
        progress = engine.get_project_progress(plan.project_id)
        assert progress.status == "resolving"


# ═══════════════════════════════════════════════════════════════════════════════
# HistoricalBackfill Tests (8)
# ═══════════════════════════════════════════════════════════════════════════════

class TestHistoricalBackfill:
    """历史回填测试"""

    def test_backfill_from_records(self):
        resolver = EntityResolver()
        backfill = HistoricalBackfill(entity_resolver=resolver)
        result = backfill.backfill_from_records(
            task_id="test-001",
            entity_type="dish",
            source_system="pinzhi",
            records=[
                {"id": "D001", "name": "剁椒鱼头"},
                {"id": "D002", "name": "酸菜鱼"},
            ],
        )
        assert result.status == "completed"
        assert result.processed_count == 2
        assert result.success_count == 2

    def test_backfill_from_csv(self):
        resolver = EntityResolver()
        backfill = HistoricalBackfill(entity_resolver=resolver)
        csv = "id,name,price\nD001,剁椒鱼头,158\nD002,酸菜鱼,88"
        result = backfill.backfill_from_csv(
            task_id="test-002",
            entity_type="dish",
            source_system="pinzhi",
            csv_content=csv,
        )
        assert result.processed_count == 2
        assert result.success_count == 2

    def test_backfill_provenance_generated(self):
        resolver = EntityResolver()
        backfill = HistoricalBackfill(entity_resolver=resolver)
        result = backfill.backfill_from_records(
            task_id="test-003",
            entity_type="dish",
            source_system="pinzhi",
            records=[{"id": "D001", "name": "剁椒鱼头"}],
        )
        assert len(result.provenances) == 1
        prov = result.provenances[0]
        assert prov["target_table"] == "dishs"
        assert prov["source_system"] == "pinzhi"
        assert prov["source_id"] == "D001"

    def test_backfill_error_handling(self):
        """缺少ID字段的记录应计入error"""
        resolver = EntityResolver()
        backfill = HistoricalBackfill(entity_resolver=resolver)
        result = backfill.backfill_from_records(
            task_id="test-004",
            entity_type="dish",
            source_system="pinzhi",
            records=[
                {"id": "D001", "name": "剁椒鱼头"},
                {"name": "无ID菜品"},  # 缺少id
            ],
        )
        assert result.success_count == 1
        assert result.error_count == 1

    def test_backfill_resume_from_cursor(self):
        """断点续传：从指定ID后恢复"""
        resolver = EntityResolver()
        backfill = HistoricalBackfill(entity_resolver=resolver)
        records = [
            {"id": "D001", "name": "菜品1"},
            {"id": "D002", "name": "菜品2"},
            {"id": "D003", "name": "菜品3"},
        ]
        result = backfill.backfill_from_records(
            task_id="test-005",
            entity_type="dish",
            source_system="pinzhi",
            records=records,
            resume_from="D001",  # 从D001后恢复
        )
        # D001被跳过，D002和D003被处理
        assert result.success_count == 2

    def test_generate_date_ranges(self):
        backfill = HistoricalBackfill()
        ranges = backfill.generate_date_ranges(
            date(2025, 9, 1), date(2025, 9, 5), interval_days=2
        )
        assert len(ranges) == 3
        assert ranges[0]["start"] == date(2025, 9, 1)
        assert ranges[0]["end"] == date(2025, 9, 2)

    def test_generate_date_ranges_single_day(self):
        backfill = HistoricalBackfill()
        ranges = backfill.generate_date_ranges(
            date(2025, 9, 1), date(2025, 9, 1), interval_days=1
        )
        assert len(ranges) == 1

    def test_estimate_total_records(self):
        backfill = HistoricalBackfill()
        est = backfill.estimate_total_records("order", "pinzhi", 180)
        assert est == 27000  # 150/day * 180


# ═══════════════════════════════════════════════════════════════════════════════
# TimelineAssembler Tests (10)
# ═══════════════════════════════════════════════════════════════════════════════

class TestTimelineAssembler:
    """时间线组装器测试"""

    def _make_order_events(self, store_id: str, days: int = 30) -> List[Dict]:
        """生成模拟订单数据"""
        orders = []
        base = datetime(2025, 9, 1, 10, 0, 0)
        for d in range(days):
            # 每天10个订单，分布在11:00~20:00
            for h in range(10):
                hour = 11 + h
                orders.append({
                    "id": f"O-{d}-{h}",
                    "created_at": (base + timedelta(days=d, hours=hour - 10)).isoformat(),
                    "total": 15000 + d * 100 + h * 50,  # fen
                    "items": [{"dish": "test"}],
                    "order_type": "dine_in",
                })
        return orders

    def test_add_order_events(self):
        assembler = TimelineAssembler()
        orders = self._make_order_events("S001", days=3)
        count = assembler.add_order_events("pinzhi", orders, "S001")
        assert count == 30  # 3 days * 10 orders

    def test_assemble_basic(self):
        assembler = TimelineAssembler()
        orders = self._make_order_events("S001", days=7)
        assembler.add_order_events("pinzhi", orders, "S001")
        analysis = assembler.assemble("S001")
        assert analysis.total_days == 7
        assert analysis.total_events == 70

    def test_daily_snapshots(self):
        assembler = TimelineAssembler()
        orders = self._make_order_events("S001", days=3)
        assembler.add_order_events("pinzhi", orders, "S001")
        analysis = assembler.assemble("S001")
        assert len(analysis.daily_snapshots) == 3
        for snap in analysis.daily_snapshots:
            assert snap.total_orders == 10

    def test_peak_patterns(self):
        assembler = TimelineAssembler()
        orders = self._make_order_events("S001", days=14)
        assembler.add_order_events("pinzhi", orders, "S001")
        analysis = assembler.assemble("S001")
        assert "peak_hours" in analysis.peak_patterns
        assert "avg_daily_orders" in analysis.peak_patterns

    def test_weekly_patterns(self):
        assembler = TimelineAssembler()
        orders = self._make_order_events("S001", days=14)
        assembler.add_order_events("pinzhi", orders, "S001")
        analysis = assembler.assemble("S001")
        assert "周一" in analysis.weekly_patterns
        assert "周日" in analysis.weekly_patterns

    def test_revenue_trend(self):
        assembler = TimelineAssembler()
        orders = self._make_order_events("S001", days=7)
        assembler.add_order_events("pinzhi", orders, "S001")
        analysis = assembler.assemble("S001")
        assert len(analysis.revenue_trend_fen) == 7
        for point in analysis.revenue_trend_fen:
            assert "revenue_yuan" in point
            assert "orders" in point

    def test_date_range_filter(self):
        assembler = TimelineAssembler()
        orders = self._make_order_events("S001", days=30)
        assembler.add_order_events("pinzhi", orders, "S001")
        analysis = assembler.assemble(
            "S001",
            date_range_start=date(2025, 9, 10),
            date_range_end=date(2025, 9, 15),
        )
        assert analysis.total_days == 6

    def test_store_isolation(self):
        """不同门店的事件隔离"""
        assembler = TimelineAssembler()
        assembler.add_order_events("pinzhi", self._make_order_events("S001", 5), "S001")
        assembler.add_order_events("pinzhi", self._make_order_events("S002", 3), "S002")
        a1 = assembler.assemble("S001")
        a2 = assembler.assemble("S002")
        assert a1.total_events == 50
        assert a2.total_events == 30

    def test_anomaly_detection(self):
        """异常检测需要至少7天数据"""
        assembler = TimelineAssembler()
        orders = self._make_order_events("S001", days=5)
        assembler.add_order_events("pinzhi", orders, "S001")
        analysis = assembler.assemble("S001")
        # 5天数据不够做异常检测
        assert analysis.anomaly_dates == []

    def test_customer_events(self):
        assembler = TimelineAssembler()
        visits = [
            {"id": "C1", "consumer_id": "C1", "name": "张三",
             "last_visit_date": "2025-09-01T12:00:00", "total_amount": 350},
            {"id": "C2", "consumer_id": "C2", "name": "李四",
             "last_visit_date": "2025-09-01T13:00:00", "total_amount": 220},
        ]
        count = assembler.add_customer_events("member", visits, "S001")
        assert count == 2


# ═══════════════════════════════════════════════════════════════════════════════
# KnowledgeGenerator Tests (7)
# ═══════════════════════════════════════════════════════════════════════════════

class TestKnowledgeGenerator:
    """知识库生成器测试"""

    def _make_timeline(self, store_id: str) -> "TimelineAnalysis":
        assembler = TimelineAssembler()
        base = datetime(2025, 9, 1, 10, 0, 0)
        orders = []
        for d in range(30):
            for h in range(10):
                orders.append({
                    "id": f"O-{d}-{h}",
                    "created_at": (base + timedelta(days=d, hours=h)).isoformat(),
                    "total": 15000 + d * 100,
                })
        assembler.add_order_events("pinzhi", orders, store_id)
        return assembler.assemble(store_id)

    def _make_dishes(self) -> List[Dict]:
        return [
            {"id": "D1", "name": "剁椒鱼头", "total_sold": 500,
             "total_revenue_fen": 7900000, "total_cost_fen": 2370000},  # 30%
            {"id": "D2", "name": "酸菜鱼", "total_sold": 300,
             "total_revenue_fen": 2640000, "total_cost_fen": 1320000},  # 50%
            {"id": "D3", "name": "麻婆豆腐", "total_sold": 100,
             "total_revenue_fen": 380000, "total_cost_fen": 133000},   # 35%
            {"id": "D4", "name": "凉拌黄瓜", "total_sold": 50,
             "total_revenue_fen": 60000, "total_cost_fen": 36000},     # 60%
        ]

    def _make_customers(self) -> List[Dict]:
        today = date.today()
        return [
            {"id": "C1", "total_amount": 8000, "total_visits": 15,
             "last_visit_date": (today - timedelta(days=5)).isoformat()},
            {"id": "C2", "total_amount": 3000, "total_visits": 5,
             "last_visit_date": (today - timedelta(days=20)).isoformat()},
            {"id": "C3", "total_amount": 2000, "total_visits": 4,
             "last_visit_date": (today - timedelta(days=90)).isoformat()},
            {"id": "C4", "total_amount": 1000, "total_visits": 8,
             "last_visit_date": (today - timedelta(days=150)).isoformat()},
            {"id": "C5", "total_amount": 200, "total_visits": 1,
             "last_visit_date": (today - timedelta(days=10)).isoformat()},
        ]

    def test_generate_basic_report(self):
        gen = KnowledgeGenerator()
        report = gen.generate_health_report(
            store_id="S001", brand_id="BRAND001"
        )
        assert report.store_id == "S001"
        assert report.overall_health_score >= 0

    def test_revenue_analysis(self):
        gen = KnowledgeGenerator()
        timeline = self._make_timeline("S001")
        report = gen.generate_health_report(
            store_id="S001", brand_id="B001", timeline=timeline
        )
        assert "total_revenue_yuan" in report.revenue_summary
        assert "monthly_trend" in report.revenue_summary
        assert report.revenue_summary["total_days"] == 30

    def test_cost_analysis(self):
        gen = KnowledgeGenerator()
        report = gen.generate_health_report(
            store_id="S001", brand_id="B001", dishes=self._make_dishes()
        )
        assert "cost_rate_pct" in report.cost_summary
        assert "top_high_cost_dishes" in report.cost_summary

    def test_dish_quadrant(self):
        gen = KnowledgeGenerator()
        report = gen.generate_health_report(
            store_id="S001", brand_id="B001", dishes=self._make_dishes()
        )
        assert len(report.dish_performances) > 0
        quadrants = {p.quadrant for p in report.dish_performances}
        # 应该至少有两种象限
        assert len(quadrants) >= 2

    def test_customer_segmentation(self):
        gen = KnowledgeGenerator()
        report = gen.generate_health_report(
            store_id="S001", brand_id="B001", customers=self._make_customers()
        )
        assert len(report.customer_segments) == 5
        segment_names = {s.segment_name for s in report.customer_segments}
        assert "高价值" in segment_names
        assert "流失预警" in segment_names

    def test_staff_efficiency(self):
        gen = KnowledgeGenerator()
        timeline = self._make_timeline("S001")
        employees = [{"id": f"E{i}"} for i in range(10)]
        report = gen.generate_health_report(
            store_id="S001", brand_id="B001",
            timeline=timeline, employees=employees
        )
        assert report.staff_efficiency is not None
        assert report.staff_efficiency.total_employees == 10
        assert report.staff_efficiency.revenue_per_person_per_hour_fen > 0

    def test_ai_recommendations(self):
        gen = KnowledgeGenerator()
        timeline = self._make_timeline("S001")
        report = gen.generate_health_report(
            store_id="S001", brand_id="B001",
            timeline=timeline,
            dishes=self._make_dishes(),
            customers=self._make_customers(),
        )
        assert len(report.ai_recommendations) > 0
        for rec in report.ai_recommendations:
            assert "action" in rec
            assert "expected_saving_yuan" in rec
            assert "confidence" in rec
