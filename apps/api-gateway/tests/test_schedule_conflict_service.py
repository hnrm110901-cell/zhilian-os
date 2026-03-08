from __future__ import annotations

from datetime import time

from src.services.schedule_conflict_service import detect_schedule_conflicts


class TestScheduleConflictService:
    def test_no_conflict_for_different_employees(self):
        shifts = [
            {"employee_id": "E1", "start_time": time(8, 0), "end_time": time(14, 0), "shift_type": "morning"},
            {"employee_id": "E2", "start_time": time(12, 0), "end_time": time(18, 0), "shift_type": "lunch"},
        ]
        assert detect_schedule_conflicts(shifts) == []

    def test_overlap_conflict_same_employee(self):
        shifts = [
            {"employee_id": "E1", "start_time": time(8, 0), "end_time": time(14, 0), "shift_type": "morning"},
            {"employee_id": "E1", "start_time": time(13, 0), "end_time": time(18, 0), "shift_type": "lunch"},
        ]
        conflicts = detect_schedule_conflicts(shifts)
        assert len(conflicts) == 1
        assert conflicts[0]["employee_id"] == "E1"

    def test_no_conflict_touching_boundary(self):
        shifts = [
            {"employee_id": "E1", "start_time": time(8, 0), "end_time": time(14, 0), "shift_type": "morning"},
            {"employee_id": "E1", "start_time": time(14, 0), "end_time": time(20, 0), "shift_type": "afternoon"},
        ]
        assert detect_schedule_conflicts(shifts) == []

    def test_overnight_overlap_conflict(self):
        shifts = [
            {"employee_id": "E1", "start_time": time(20, 0), "end_time": time(2, 0), "shift_type": "evening"},
            {"employee_id": "E1", "start_time": time(22, 0), "end_time": time(1, 0), "shift_type": "night"},
        ]
        conflicts = detect_schedule_conflicts(shifts)
        assert len(conflicts) == 1
