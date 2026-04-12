"""
Tests for AquariumService — 活海鲜养殖管理服务

覆盖：
- 鱼缸 CRUD + 状态管理
- 水质指标记录 + 异常预警
- 活海鲜批次入缸登记
- 死亡记录（损耗¥金额计算 + 库存更新）
- 每日巡检
- 鱼缸仪表板 + 死亡率报告
- 健康度评分算法
- 水质阈值边界条件
"""

import os

# L002: 设置环境变量防止 pydantic_settings 校验失败
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import uuid
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.models.aquarium import (
    AquariumInspection,
    AquariumTank,
    AquariumWaterMetric,
    InspectionResult,
    LiveSeafoodBatch,
    MortalityReason,
    SeafoodMortalityLog,
    TankStatus,
    TankType,
)
from src.services.aquarium_service import AquariumService, WATER_THRESHOLDS


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def service():
    """创建 AquariumService 实例"""
    return AquariumService()


@pytest.fixture
def mock_db():
    """创建 mock AsyncSession"""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def mock_tank():
    """创建 mock 鱼缸"""
    tank = MagicMock(spec=AquariumTank)
    tank.id = uuid.uuid4()
    tank.store_id = "STORE_001"
    tank.name = "1号海水缸"
    tank.tank_type = TankType.SALTWATER.value
    tank.capacity_liters = 500.0
    tank.location = "大厅入口左侧"
    tank.status = TankStatus.ACTIVE.value
    tank.current_species = "波士顿龙虾,东星斑"
    tank.equipment_info = "蛋白分离器+冷水机"
    tank.notes = None
    tank.created_at = datetime(2026, 3, 1)
    tank.updated_at = datetime(2026, 3, 1)
    return tank


@pytest.fixture
def mock_batch():
    """创建 mock 活海鲜批次"""
    batch = MagicMock(spec=LiveSeafoodBatch)
    batch.id = uuid.uuid4()
    batch.tank_id = uuid.uuid4()
    batch.store_id = "STORE_001"
    batch.species = "波士顿龙虾"
    batch.category = "虾蟹类"
    batch.entry_date = datetime(2026, 3, 20)
    batch.initial_quantity = 50
    batch.initial_weight_g = 25000
    batch.unit = "只"
    batch.current_quantity = 48
    batch.current_weight_g = 24000
    batch.unit_cost_fen = 8000  # 80元/只
    batch.total_cost_fen = 400000  # 4000元
    batch.cost_unit = "只"
    batch.supplier_name = "海鲜一号供应商"
    batch.is_active = "true"
    batch.notes = None
    return batch


@pytest.fixture
def mock_water_metric():
    """创建 mock 水质指标（正常值）"""
    metric = MagicMock(spec=AquariumWaterMetric)
    metric.id = uuid.uuid4()
    metric.tank_id = uuid.uuid4()
    metric.temperature = 19.0
    metric.ph = 8.1
    metric.dissolved_oxygen = 6.5
    metric.salinity = 32.0
    metric.ammonia = 0.2
    metric.nitrite = 0.05
    metric.source = "manual"
    metric.recorded_by = "张厨师"
    metric.recorded_at = datetime(2026, 3, 25, 10, 0)
    metric.notes = None
    return metric


@pytest.fixture
def mock_water_metric_abnormal():
    """创建 mock 水质指标（异常值）"""
    metric = MagicMock(spec=AquariumWaterMetric)
    metric.id = uuid.uuid4()
    metric.tank_id = uuid.uuid4()
    metric.temperature = 25.0   # 超标：标准 16-22
    metric.ph = 7.5             # 超标：标准 7.8-8.4
    metric.dissolved_oxygen = 4.0  # 超标：标准 >5
    metric.salinity = 28.0      # 超标：标准 30-35
    metric.ammonia = 0.8        # 超标：标准 <0.5
    metric.nitrite = 0.15       # 超标：标准 <0.1
    metric.source = "iot"
    metric.recorded_by = None
    metric.recorded_at = datetime(2026, 3, 25, 14, 0)
    metric.notes = None
    return metric


@pytest.fixture
def mock_inspection():
    """创建 mock 巡检记录"""
    inspection = MagicMock(spec=AquariumInspection)
    inspection.id = uuid.uuid4()
    inspection.tank_id = uuid.uuid4()
    inspection.inspector = "李经理"
    inspection.inspection_date = date(2026, 3, 25)
    inspection.result = InspectionResult.NORMAL.value
    inspection.tank_cleanliness = 8
    inspection.fish_activity = 9
    inspection.equipment_status = 7
    inspection.abnormal_description = None
    inspection.action_taken = None
    inspection.image_urls = None
    inspection.notes = None
    return inspection


# ── 鱼缸管理测试 ─────────────────────────────────────────────────────────────


class TestCreateTank:
    """鱼缸创建测试"""

    @pytest.mark.asyncio
    async def test_create_tank_success(self, service, mock_db):
        """测试成功创建鱼缸"""
        result = await service.create_tank(
            mock_db,
            store_id="STORE_001",
            name="2号海水缸",
            tank_type="saltwater",
            capacity_liters=300.0,
            location="大厅右侧",
        )

        assert result["name"] == "2号海水缸"
        assert result["store_id"] == "STORE_001"
        assert result["capacity_liters"] == 300.0
        assert result["status"] == TankStatus.EMPTY.value
        assert result["tank_type"] == "saltwater"
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_tank_with_equipment_info(self, service, mock_db):
        """测试创建鱼缸时包含设备信息"""
        result = await service.create_tank(
            mock_db,
            store_id="STORE_001",
            name="VIP海水缸",
            capacity_liters=1000.0,
            equipment_info="德国进口蛋白分离器+双冷水机+UPS",
        )
        assert result["equipment_info"] == "德国进口蛋白分离器+双冷水机+UPS"


class TestGetTanks:
    """鱼缸列表查询测试"""

    @pytest.mark.asyncio
    async def test_get_tanks_returns_list(self, service, mock_db, mock_tank):
        """测试获取鱼缸列表"""
        # mock count query
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        # mock list query
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [mock_tank]

        mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

        result = await service.get_tanks(mock_db, store_id="STORE_001")
        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["name"] == "1号海水缸"

    @pytest.mark.asyncio
    async def test_get_tanks_empty(self, service, mock_db):
        """测试空鱼缸列表"""
        count_result = MagicMock()
        count_result.scalar.return_value = 0
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

        result = await service.get_tanks(mock_db, store_id="STORE_001")
        assert result["total"] == 0
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_get_tanks_with_status_filter(self, service, mock_db, mock_tank):
        """测试按状态过滤鱼缸"""
        count_result = MagicMock()
        count_result.scalar.return_value = 1
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [mock_tank]

        mock_db.execute = AsyncMock(side_effect=[count_result, list_result])

        result = await service.get_tanks(mock_db, store_id="STORE_001", status="active")
        assert result["total"] == 1


class TestUpdateTankStatus:
    """鱼缸状态更新测试"""

    @pytest.mark.asyncio
    async def test_update_tank_status_success(self, service, mock_db, mock_tank):
        """测试成功更新鱼缸状态"""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = mock_tank
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await service.update_tank_status(
            mock_db, tank_id=mock_tank.id, status="maintenance",
        )
        assert result is not None
        assert mock_tank.status == "maintenance"

    @pytest.mark.asyncio
    async def test_update_tank_status_not_found(self, service, mock_db):
        """测试更新不存在的鱼缸"""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await service.update_tank_status(
            mock_db, tank_id=uuid.uuid4(), status="maintenance",
        )
        assert result is None


# ── 水质指标测试 ─────────────────────────────────────────────────────────────


class TestRecordWaterMetrics:
    """水质指标记录测试"""

    @pytest.mark.asyncio
    async def test_record_normal_water_metrics(self, service, mock_db):
        """测试记录正常水质指标（无告警）"""
        result = await service.record_water_metrics(
            mock_db,
            tank_id=uuid.uuid4(),
            store_id="STORE_001",
            temperature=19.0,
            ph=8.1,
            dissolved_oxygen=6.5,
            salinity=32.0,
            ammonia=0.2,
            nitrite=0.05,
            source="manual",
            recorded_by="张厨师",
        )
        assert "metric" in result
        assert "alerts" in result
        assert len(result["alerts"]) == 0
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_abnormal_water_metrics(self, service, mock_db):
        """测试记录异常水质指标（产生告警）"""
        result = await service.record_water_metrics(
            mock_db,
            tank_id=uuid.uuid4(),
            store_id="STORE_001",
            temperature=25.0,  # 超标
            ph=7.5,            # 偏低
            dissolved_oxygen=4.0,  # 偏低
            source="iot",
        )
        alerts = result["alerts"]
        assert len(alerts) == 3
        # 验证告警包含水温、pH、溶氧
        alert_metrics = {a["metric"] for a in alerts}
        assert "temperature" in alert_metrics
        assert "ph" in alert_metrics
        assert "dissolved_oxygen" in alert_metrics

    @pytest.mark.asyncio
    async def test_record_iot_source(self, service, mock_db):
        """测试 IoT 来源的水质记录"""
        result = await service.record_water_metrics(
            mock_db,
            tank_id=uuid.uuid4(),
            store_id="STORE_001",
            temperature=20.0,
            source="iot",
        )
        assert result["metric"]["source"] == "iot"


class TestCheckMetricAlerts:
    """水质告警检查测试"""

    def test_all_normal(self, service, mock_water_metric):
        """测试所有指标正常时无告警"""
        alerts = service._check_metric_alerts(mock_water_metric)
        assert len(alerts) == 0

    def test_all_abnormal(self, service, mock_water_metric_abnormal):
        """测试所有指标异常时产生6个告警"""
        alerts = service._check_metric_alerts(mock_water_metric_abnormal)
        assert len(alerts) == 6

    def test_temperature_high_warning(self, service):
        """测试水温偏高告警（warning 级别：22-26.4°C）"""
        metric = MagicMock(spec=AquariumWaterMetric)
        metric.temperature = 23.0  # 超标但 <20% 偏差
        metric.ph = None
        metric.dissolved_oxygen = None
        metric.salinity = None
        metric.ammonia = None
        metric.nitrite = None

        alerts = service._check_metric_alerts(metric)
        assert len(alerts) == 1
        assert alerts[0]["metric"] == "temperature"
        assert alerts[0]["level"] == "warning"

    def test_temperature_high_critical(self, service):
        """测试水温严重偏高告警（critical 级别：>26.4°C）"""
        metric = MagicMock(spec=AquariumWaterMetric)
        metric.temperature = 28.0  # 超过20%偏差 → critical
        metric.ph = None
        metric.dissolved_oxygen = None
        metric.salinity = None
        metric.ammonia = None
        metric.nitrite = None

        alerts = service._check_metric_alerts(metric)
        assert len(alerts) == 1
        assert alerts[0]["level"] == "critical"

    def test_partial_metrics(self, service):
        """测试部分指标为 None 时不产生告警"""
        metric = MagicMock(spec=AquariumWaterMetric)
        metric.temperature = 19.0  # 正常
        metric.ph = None  # 未记录
        metric.dissolved_oxygen = None
        metric.salinity = None
        metric.ammonia = None
        metric.nitrite = None

        alerts = service._check_metric_alerts(metric)
        assert len(alerts) == 0

    def test_ammonia_exceeds_threshold(self, service):
        """测试氨氮超标告警"""
        metric = MagicMock(spec=AquariumWaterMetric)
        metric.temperature = None
        metric.ph = None
        metric.dissolved_oxygen = None
        metric.salinity = None
        metric.ammonia = 0.7  # 超标：>0.5
        metric.nitrite = None

        alerts = service._check_metric_alerts(metric)
        assert len(alerts) == 1
        assert alerts[0]["metric"] == "ammonia"
        assert "氨氮偏高" in alerts[0]["message"]


# ── 活海鲜批次测试 ───────────────────────────────────────────────────────────


class TestAddSeafoodBatch:
    """活海鲜入缸登记测试"""

    @pytest.mark.asyncio
    async def test_add_batch_success(self, service, mock_db, mock_tank):
        """测试成功入缸登记"""
        # mock get tank
        tank_result = MagicMock()
        tank_result.scalar_one_or_none.return_value = mock_tank
        mock_db.execute = AsyncMock(return_value=tank_result)

        result = await service.add_seafood_batch(
            mock_db,
            tank_id=mock_tank.id,
            store_id="STORE_001",
            species="波士顿龙虾",
            category="虾蟹类",
            initial_quantity=50,
            initial_weight_g=25000,
            unit_cost_fen=8000,  # 80元/只
            supplier_name="海鲜一号",
        )

        assert result["species"] == "波士顿龙虾"
        assert result["initial_quantity"] == 50
        assert result["current_quantity"] == 50
        assert result["total_cost_fen"] == 400000  # 50 × 8000 = 400000分 = 4000元
        assert result["total_cost_yuan"] == "¥4000.00"

    @pytest.mark.asyncio
    async def test_add_batch_updates_tank_species(self, service, mock_db, mock_tank):
        """测试入缸时更新鱼缸当前品种"""
        mock_tank.current_species = "东星斑"
        tank_result = MagicMock()
        tank_result.scalar_one_or_none.return_value = mock_tank
        mock_db.execute = AsyncMock(return_value=tank_result)

        await service.add_seafood_batch(
            mock_db,
            tank_id=mock_tank.id,
            store_id="STORE_001",
            species="波士顿龙虾",
            initial_quantity=10,
            unit_cost_fen=8000,
        )
        # 验证品种列表被更新
        species_set = set(mock_tank.current_species.split(","))
        assert "波士顿龙虾" in species_set
        assert "东星斑" in species_set


# ── 死亡记录测试 ─────────────────────────────────────────────────────────────


class TestRecordMortality:
    """死亡记录测试"""

    @pytest.mark.asyncio
    async def test_record_mortality_success(self, service, mock_db, mock_batch):
        """测试成功记录死亡"""
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = mock_batch
        mock_db.execute = AsyncMock(return_value=batch_result)

        result = await service.record_mortality(
            mock_db,
            batch_id=mock_batch.id,
            store_id="STORE_001",
            dead_quantity=3,
            reason="water_quality",
            disposal="discard",
            recorded_by="张厨师",
        )

        # 损耗金额 = 3 × 8000分 = 24000分 = 240元
        assert result["loss_amount_fen"] == 24000
        assert result["loss_amount_yuan"] == "¥240.00"
        # 验证批次存活量更新：48 - 3 = 45
        assert mock_batch.current_quantity == 45

    @pytest.mark.asyncio
    async def test_record_mortality_exceeds_quantity(self, service, mock_db, mock_batch):
        """测试死亡数量超过存活数量时报错"""
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = mock_batch
        mock_db.execute = AsyncMock(return_value=batch_result)

        with pytest.raises(ValueError, match="不能超过当前存活数量"):
            await service.record_mortality(
                mock_db,
                batch_id=mock_batch.id,
                store_id="STORE_001",
                dead_quantity=100,  # 超过当前 48
            )

    @pytest.mark.asyncio
    async def test_record_mortality_batch_not_found(self, service, mock_db):
        """测试批次不存在时报错"""
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=batch_result)

        with pytest.raises(ValueError, match="批次不存在"):
            await service.record_mortality(
                mock_db,
                batch_id=uuid.uuid4(),
                store_id="STORE_001",
                dead_quantity=1,
            )

    @pytest.mark.asyncio
    async def test_record_mortality_all_dead_deactivates_batch(self, service, mock_db, mock_batch):
        """测试全部死亡时批次标记为非活跃"""
        mock_batch.current_quantity = 5
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = mock_batch
        mock_db.execute = AsyncMock(return_value=batch_result)

        await service.record_mortality(
            mock_db,
            batch_id=mock_batch.id,
            store_id="STORE_001",
            dead_quantity=5,  # 全部死亡
        )

        assert mock_batch.current_quantity == 0
        assert mock_batch.is_active == "false"


# ── 巡检测试 ─────────────────────────────────────────────────────────────────


class TestDailyInspection:
    """每日巡检测试"""

    @pytest.mark.asyncio
    async def test_daily_inspection_normal(self, service, mock_db):
        """测试正常巡检记录"""
        result = await service.daily_inspection(
            mock_db,
            tank_id=uuid.uuid4(),
            store_id="STORE_001",
            inspector="李经理",
            result="normal",
            tank_cleanliness=8,
            fish_activity=9,
            equipment_status=7,
        )
        assert result["inspector"] == "李经理"
        assert result["result"] == "normal"
        assert result["tank_cleanliness"] == 8
        mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_daily_inspection_with_abnormal(self, service, mock_db):
        """测试异常巡检记录"""
        result = await service.daily_inspection(
            mock_db,
            tank_id=uuid.uuid4(),
            store_id="STORE_001",
            inspector="李经理",
            result="warning",
            abnormal_description="水面有泡沫，疑似过滤系统故障",
            action_taken="已通知维修人员",
        )
        assert result["result"] == "warning"


# ── 健康度评分测试 ───────────────────────────────────────────────────────────


class TestHealthScore:
    """健康度评分算法测试"""

    def test_perfect_health_score(self, service, mock_water_metric, mock_inspection):
        """测试满分健康度（所有指标正常）"""
        score = service._calculate_health_score(
            latest_metric=mock_water_metric,
            latest_inspection=mock_inspection,
            total_dead_7d=0,
            total_quantity=50,
            total_initial=50,
        )
        # 水质60 + 死亡率20 + 巡检(8+9+7)/3*2=16 = 96
        assert score == 96.0

    def test_health_score_with_critical_water(self, service, mock_water_metric_abnormal, mock_inspection):
        """测试水质严重异常时健康度下降"""
        score = service._calculate_health_score(
            latest_metric=mock_water_metric_abnormal,
            latest_inspection=mock_inspection,
            total_dead_7d=0,
            total_quantity=50,
            total_initial=50,
        )
        # 6 个告警，水质分数大幅下降
        assert score < 60.0

    def test_health_score_high_mortality(self, service, mock_water_metric, mock_inspection):
        """测试高死亡率时健康度下降"""
        score = service._calculate_health_score(
            latest_metric=mock_water_metric,
            latest_inspection=mock_inspection,
            total_dead_7d=10,  # 20% 死亡率
            total_quantity=40,
            total_initial=50,
        )
        # 死亡率 >10% → 死亡评分 = 0
        assert score < 80.0

    def test_health_score_no_data(self, service):
        """测试无任何数据时的健康度（满分，因为无告警）"""
        score = service._calculate_health_score(
            latest_metric=None,
            latest_inspection=None,
            total_dead_7d=0,
            total_quantity=0,
            total_initial=0,
        )
        assert score == 100.0

    def test_health_score_critical_inspection(self, service, mock_water_metric, mock_inspection):
        """测试巡检严重异常时扣分"""
        mock_inspection.result = InspectionResult.CRITICAL.value
        score = service._calculate_health_score(
            latest_metric=mock_water_metric,
            latest_inspection=mock_inspection,
            total_dead_7d=0,
            total_quantity=50,
            total_initial=50,
        )
        # 巡检分从 16 扣 10 变为 6
        assert score == 86.0


# ── 仪表板测试 ───────────────────────────────────────────────────────────────


class TestTankDashboard:
    """鱼缸仪表板测试"""

    @pytest.mark.asyncio
    async def test_dashboard_tank_not_found(self, service, mock_db):
        """测试鱼缸不存在时返回错误"""
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await service.get_tank_dashboard(mock_db, tank_id=uuid.uuid4())
        assert "error" in result


# ── 死亡率报告测试 ────────────────────────────────────────────────────────────


class TestMortalityReport:
    """死亡率报告测试"""

    @pytest.mark.asyncio
    async def test_empty_mortality_report(self, service, mock_db):
        """测试无死亡记录时的报告"""
        result_mock = MagicMock()
        result_mock.all.return_value = []
        mock_db.execute = AsyncMock(return_value=result_mock)

        result = await service.get_mortality_report(
            mock_db, store_id="STORE_001",
        )
        assert result["total_dead"] == 0
        assert result["total_loss_fen"] == 0
        assert result["total_loss_yuan"] == "¥0.00"
        assert result["by_species"] == []
        assert result["by_reason"] == []


# ── 序列化测试 ───────────────────────────────────────────────────────────────


class TestSerialization:
    """序列化辅助方法测试"""

    def test_tank_to_dict(self, service, mock_tank):
        """测试鱼缸序列化"""
        result = service._tank_to_dict(mock_tank)
        assert result["name"] == "1号海水缸"
        assert result["store_id"] == "STORE_001"
        assert result["status"] == TankStatus.ACTIVE.value

    def test_batch_to_dict_includes_yuan(self, service, mock_batch):
        """测试批次序列化包含¥金额"""
        result = service._batch_to_dict(mock_batch)
        assert "total_cost_yuan" in result
        assert result["total_cost_yuan"] == "¥4000.00"
        assert result["total_cost_fen"] == 400000

    def test_mortality_to_dict_includes_yuan(self, service):
        """测试死亡记录序列化包含¥金额"""
        log = MagicMock(spec=SeafoodMortalityLog)
        log.id = uuid.uuid4()
        log.batch_id = uuid.uuid4()
        log.tank_id = uuid.uuid4()
        log.dead_quantity = 3
        log.dead_weight_g = 1500
        log.reason = "water_quality"
        log.disposal = "discard"
        log.loss_amount_fen = 24000  # 240元
        log.recorded_by = "张厨师"
        log.recorded_at = datetime(2026, 3, 25)
        log.notes = None

        result = service._mortality_to_dict(log)
        assert result["loss_amount_yuan"] == "¥240.00"
        assert result["loss_amount_fen"] == 24000

    def test_inspection_to_dict(self, service, mock_inspection):
        """测试巡检序列化"""
        result = service._inspection_to_dict(mock_inspection)
        assert result["inspector"] == "李经理"
        assert result["result"] == InspectionResult.NORMAL.value

    def test_metric_to_dict(self, service, mock_water_metric):
        """测试水质指标序列化"""
        result = service._metric_to_dict(mock_water_metric)
        assert result["temperature"] == 19.0
        assert result["ph"] == 8.1
        assert result["source"] == "manual"


# ── 边界条件测试 ─────────────────────────────────────────────────────────────


class TestEdgeCases:
    """边界条件测试"""

    def test_is_critical_deviation_below(self, service):
        """测试低于阈值时的严重偏差判断"""
        # 温度 12°C，阈值 16°C → 偏差 25% → critical
        assert AquariumService._is_critical_deviation("temperature", 12.0, 16.0, "below") is True
        # 温度 15°C，阈值 16°C → 偏差 6.25% → warning
        assert AquariumService._is_critical_deviation("temperature", 15.0, 16.0, "below") is False

    def test_is_critical_deviation_above(self, service):
        """测试高于阈值时的严重偏差判断"""
        # 温度 28°C，阈值 22°C → 偏差 27% → critical
        assert AquariumService._is_critical_deviation("temperature", 28.0, 22.0, "above") is True
        # 温度 23°C，阈值 22°C → 偏差 4.5% → warning
        assert AquariumService._is_critical_deviation("temperature", 23.0, 22.0, "above") is False

    def test_water_thresholds_completeness(self):
        """测试水质阈值配置完整性"""
        expected_metrics = {"temperature", "ph", "dissolved_oxygen", "salinity", "ammonia", "nitrite"}
        assert set(WATER_THRESHOLDS.keys()) == expected_metrics
        for key, val in WATER_THRESHOLDS.items():
            assert "label" in val
            assert "unit" in val
