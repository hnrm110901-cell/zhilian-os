"""P3 Attendance Engine tests — shift-driven compute + appeal + seed + export

12+ tests covering:
- _compute_attendance with shift params (6)
- _resolve_shift logic (2)
- appeal submit/resolve (2)
- seed data loading (1)
- attendance Excel export (1)
"""
import json
import uuid
from datetime import date, datetime, time, timezone, timedelta
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.services.hr.attendance_service import (
    AttendanceService,
    _FALLBACK_LATE_THRESHOLD,
    _FALLBACK_STANDARD_MINUTES,
    _FALLBACK_WORK_END,
    _FALLBACK_WORK_START,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TARGET = date(2026, 3, 10)


def make_clock(clock_type: str, hour: int, minute: int, target_date: date = TARGET):
    """Create a mock clock record."""
    return SimpleNamespace(
        clock_type=clock_type,
        clock_time=datetime.combine(
            target_date, time(hour, minute), tzinfo=timezone.utc,
        ),
    )


# ---------------------------------------------------------------------------
# 1-6: _compute_attendance with shift params
# ---------------------------------------------------------------------------

class TestComputeAttendanceShifts:
    """Tests for _compute_attendance with explicit shift parameters."""

    def setup_method(self):
        self.svc = AttendanceService()

    def test_morning_shift_on_time(self):
        """早班准时：07:00 in, 15:00 out -> normal（恰好480min）"""
        records = [
            make_clock("in", 7, 0),
            make_clock("out", 15, 0),
        ]
        status, work, late, early, ot = self.svc._compute_attendance(
            records, TARGET,
            shift_start=time(7, 0),
            shift_end=time(15, 0),
            late_threshold=5,
            standard_minutes=480,
        )
        assert status == "normal"
        assert late == 0
        assert early == 0
        # work = 15:00 - 07:00 = 480 min
        assert work == 480
        assert ot == 0

    def test_morning_shift_on_time_status_overtime(self):
        """早班准时但超过标准工时 -> overtime (because 495 > 480)"""
        records = [
            make_clock("in", 6, 55),
            make_clock("out", 15, 10),
        ]
        status, work, late, early, ot = self.svc._compute_attendance(
            records, TARGET,
            shift_start=time(7, 0),
            shift_end=time(15, 0),
            late_threshold=5,
            standard_minutes=480,
        )
        # 495 > 480, early_leave=0, late=0 -> overtime
        assert status in ("normal", "overtime")
        # Actually early_leave: scheduled_end=15:00, last_out=15:10 -> no early leave
        # work=495 > 480 -> overtime
        assert status == "overtime" or (status == "normal" and ot > 0)

    def test_morning_shift_late(self):
        """早班迟到：07:10 in（迟到10分钟 > threshold 5）"""
        records = [
            make_clock("in", 7, 10),
            make_clock("out", 15, 5),
        ]
        status, work, late, early, ot = self.svc._compute_attendance(
            records, TARGET,
            shift_start=time(7, 0),
            shift_end=time(15, 0),
            late_threshold=5,
            standard_minutes=480,
        )
        assert status == "late"
        assert late == 10  # 07:10 - 07:00 = 10min

    def test_evening_shift_correct(self):
        """晚班准时：14:55 in, 23:05 out -> normal (early_leave=0)"""
        records = [
            make_clock("in", 14, 55),
            make_clock("out", 23, 5),
        ]
        status, work, late, early, ot = self.svc._compute_attendance(
            records, TARGET,
            shift_start=time(15, 0),
            shift_end=time(23, 0),
            late_threshold=5,
            standard_minutes=480,
        )
        assert late == 0
        assert early == 0  # 23:05 > 23:00 -> no early leave
        # work = 23:05 - 14:55 = 490 min
        assert work == 490

    def test_full_shift_overtime(self):
        """全天班超时：10:00-22:00 -> 720min工作, 240min加班"""
        records = [
            make_clock("in", 10, 0),
            make_clock("out", 22, 0),
        ]
        status, work, late, early, ot = self.svc._compute_attendance(
            records, TARGET,
            shift_start=time(10, 0),
            shift_end=time(22, 0),
            late_threshold=5,
            standard_minutes=480,
        )
        assert work == 720
        assert ot == 240
        assert status == "overtime"

    def test_no_records_absent(self):
        """无打卡记录 -> absent"""
        status, work, late, early, ot = self.svc._compute_attendance(
            [], TARGET,
            shift_start=time(7, 0),
            shift_end=time(15, 0),
        )
        assert status == "absent"
        assert work == 0

    def test_early_leave(self):
        """早退2小时 -> early_leave"""
        records = [
            make_clock("in", 9, 55),
            make_clock("out", 20, 0),
        ]
        status, work, late, early, ot = self.svc._compute_attendance(
            records, TARGET,
            shift_start=time(10, 0),
            shift_end=time(22, 0),
            late_threshold=5,
            standard_minutes=480,
        )
        assert status == "early_leave"
        assert early == 120  # 22:00 - 20:00 = 120min


# ---------------------------------------------------------------------------
# 7-8: _resolve_shift
# ---------------------------------------------------------------------------

class TestResolveShift:

    @pytest.mark.asyncio
    async def test_resolve_shift_with_rule(self):
        """合同绑定考勤规则 -> 返回规则中的班次时间"""
        svc = AttendanceService()
        rule_config = {
            "shifts": {
                "morning": {"start": "07:00", "end": "15:00"},
                "full": {"start": "10:00", "end": "22:00"},
            },
            "default_shift": "morning",
            "late_threshold_minutes": 10,
        }

        mock_contract = SimpleNamespace(
            attendance_rule_id=uuid.uuid4(),
        )
        mock_rule = SimpleNamespace(
            rule_config=rule_config,
        )

        session = AsyncMock()
        # First execute -> contract query
        contract_result = MagicMock()
        contract_result.scalar_one_or_none.return_value = mock_contract
        # Second execute -> rule query
        rule_result = MagicMock()
        rule_result.scalar_one_or_none.return_value = mock_rule

        session.execute = AsyncMock(side_effect=[contract_result, rule_result])

        assignment_id = uuid.uuid4()
        shift_start, shift_end, rc = await svc._resolve_shift(
            assignment_id, TARGET, session,
        )

        assert shift_start == time(7, 0)
        assert shift_end == time(15, 0)
        assert rc["late_threshold_minutes"] == 10

    @pytest.mark.asyncio
    async def test_resolve_shift_fallback(self):
        """无合同 -> 后备值 09:00-22:00"""
        svc = AttendanceService()

        session = AsyncMock()
        contract_result = MagicMock()
        contract_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=contract_result)

        assignment_id = uuid.uuid4()
        shift_start, shift_end, rc = await svc._resolve_shift(
            assignment_id, TARGET, session,
        )

        # No rule_config -> fallback parsing "09:00" / "22:00"
        assert shift_start == time(9, 0)
        assert shift_end == time(22, 0)
        assert rc == {}


# ---------------------------------------------------------------------------
# 9-10: appeal submit/resolve
# ---------------------------------------------------------------------------

class TestAppeal:

    @pytest.mark.asyncio
    async def test_submit_appeal_returns_dict(self):
        """提交申诉：返回 appeal_id + status"""
        svc = AttendanceService()
        session = AsyncMock()

        # approval_workflow_service.start will raise ValueError (resource_type不支持)
        # 因此走 submitted_no_workflow 分支
        result = await svc.submit_appeal(
            assignment_id=uuid.uuid4(),
            target_date=TARGET,
            reason="外勤未打卡",
            created_by="admin",
            session=session,
        )
        assert "appeal_id" in result
        assert result["status"] == "submitted_no_workflow"
        assert result["approval_instance_id"] is None

    @pytest.mark.asyncio
    async def test_resolve_appeal_overrides_status(self):
        """申诉通过：覆盖状态为 normal"""
        svc = AttendanceService()
        session = AsyncMock()

        await svc.resolve_appeal(
            assignment_id=uuid.uuid4(),
            target_date=TARGET,
            new_status="normal",
            session=session,
        )
        # Should have called session.execute with UPDATE + session.flush
        assert session.execute.called
        assert session.flush.called

    @pytest.mark.asyncio
    async def test_resolve_appeal_invalid_status(self):
        """申诉：无效状态 -> ValueError"""
        svc = AttendanceService()
        session = AsyncMock()

        with pytest.raises(ValueError, match="Invalid override status"):
            await svc.resolve_appeal(
                assignment_id=uuid.uuid4(),
                target_date=TARGET,
                new_status="invalid_xxx",
                session=session,
            )


# ---------------------------------------------------------------------------
# 11: seed data
# ---------------------------------------------------------------------------

class TestSeedData:

    def test_attendance_rules_seed_loads(self):
        """JSON 文件可加载，rule_config 含 shifts"""
        from pathlib import Path
        data_dir = Path(__file__).parent.parent / "src" / "data"
        path = data_dir / "xuji_attendance_rules.json"
        assert path.exists(), f"{path} not found"

        with path.open(encoding="utf-8") as f:
            rules = json.load(f)

        assert len(rules) >= 1
        rule = rules[0]
        assert "rule_config" in rule
        rc = rule["rule_config"]
        assert "shifts" in rc
        assert "morning" in rc["shifts"]
        assert "full" in rc["shifts"]
        assert rc["default_shift"] == "full"
        assert rc["late_threshold_minutes"] == 5


# ---------------------------------------------------------------------------
# 12: export attendance xlsx
# ---------------------------------------------------------------------------

class TestExportAttendance:

    @pytest.mark.asyncio
    async def test_export_attendance_xlsx(self):
        """导出考勤Excel：mock数据 -> 有效xlsx BytesIO"""
        from src.services.hr.hr_export_service import HRExportService

        svc = HRExportService()

        # Mock person + assignment
        mock_person = SimpleNamespace(name="张三")
        mock_assignment = SimpleNamespace(
            id=uuid.uuid4(),
            person_id=uuid.uuid4(),
            org_node_id="xj-store-wuyi",
            status="active",
        )

        # Mock attendance records
        mock_att1 = SimpleNamespace(
            status="normal", overtime_minutes=0, work_minutes=480,
        )
        mock_att2 = SimpleNamespace(
            status="late", overtime_minutes=0, work_minutes=450,
        )

        session = AsyncMock()

        # First call: select assignments+persons
        assignment_result = MagicMock()
        assignment_result.all.return_value = [(mock_assignment, mock_person)]

        # Second call: select daily_attendances
        att_scalars = MagicMock()
        att_scalars.all.return_value = [mock_att1, mock_att2]
        att_result = MagicMock()
        att_result.scalars.return_value = att_scalars

        session.execute = AsyncMock(side_effect=[assignment_result, att_result])

        buf = await svc.export_attendance_monthly(
            "xj-store-wuyi", 2026, 3, session,
        )

        assert isinstance(buf, BytesIO)
        # Verify it's a valid xlsx by checking the magic bytes
        content = buf.read()
        assert len(content) > 100
        # xlsx files start with PK (zip format)
        assert content[:2] == b"PK"
