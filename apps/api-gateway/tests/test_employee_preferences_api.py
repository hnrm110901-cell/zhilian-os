"""
EmployeePreference API 单元测试
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.api.employees import (
    EmployeePreferencePatchRequest,
    EmployeePreferenceUpsertRequest,
    delete_employee_preferences,
    get_employee_preferences,
    patch_employee_preferences,
    put_employee_preferences,
)


def _employee(employee_id="E001", store_id="S001", preferences=None):
    e = MagicMock()
    e.id = employee_id
    e.legacy_employee_id = employee_id
    e.store_id = store_id
    e.preferences = preferences if preferences is not None else {}
    return e


def _user():
    u = MagicMock()
    u.id = "manager-1"
    return u


class TestEmployeePreferenceApi:
    @pytest.mark.asyncio
    async def test_get_employee_preferences_success(self):
        session = AsyncMock()
        emp = _employee(preferences={"preferred_shifts": ["morning"]})
        with patch("src.api.employees.EmployeeRepository.get_by_id", new_callable=AsyncMock, return_value=emp):
            resp = await get_employee_preferences("E001", session=session, current_user=_user())
        assert resp.employee_id == "E001"
        assert resp.preferences["preferred_shifts"] == ["morning"]

    @pytest.mark.asyncio
    async def test_get_employee_preferences_not_found(self):
        session = AsyncMock()
        with patch("src.api.employees.EmployeeRepository.get_by_id", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc:
                await get_employee_preferences("E404", session=session, current_user=_user())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_put_employee_preferences_replace(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        emp = _employee(preferences={"old": 1})
        req = EmployeePreferenceUpsertRequest(preferences={"preferred_days_off": ["monday"]})
        with patch("src.api.employees.EmployeeRepository.get_by_id", new_callable=AsyncMock, return_value=emp):
            resp = await put_employee_preferences("E001", req=req, session=session, current_user=_user())
        assert resp.preferences == {"preferred_days_off": ["monday"]}
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_patch_employee_preferences_merge(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        emp = _employee(preferences={"preferred_shifts": ["morning"], "days_off": ["sunday"]})
        req = EmployeePreferencePatchRequest(preferences={"preferred_shifts": ["evening"]})
        with patch("src.api.employees.EmployeeRepository.get_by_id", new_callable=AsyncMock, return_value=emp):
            resp = await patch_employee_preferences("E001", req=req, session=session, current_user=_user())
        assert resp.preferences["preferred_shifts"] == ["evening"]
        assert resp.preferences["days_off"] == ["sunday"]

    @pytest.mark.asyncio
    async def test_patch_employee_preferences_not_found(self):
        session = AsyncMock()
        req = EmployeePreferencePatchRequest(preferences={"x": 1})
        with patch("src.api.employees.EmployeeRepository.get_by_id", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc:
                await patch_employee_preferences("E404", req=req, session=session, current_user=_user())
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_employee_preferences_clear_all(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        emp = _employee(preferences={"a": 1, "b": 2})
        with patch("src.api.employees.EmployeeRepository.get_by_id", new_callable=AsyncMock, return_value=emp):
            resp = await delete_employee_preferences("E001", key=None, session=session, current_user=_user())
        assert resp["ok"] is True
        assert resp["preferences"] == {}

    @pytest.mark.asyncio
    async def test_delete_employee_preferences_with_key(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        emp = _employee(preferences={"preferred_shifts": ["morning"], "days_off": ["sunday"]})
        with patch("src.api.employees.EmployeeRepository.get_by_id", new_callable=AsyncMock, return_value=emp):
            resp = await delete_employee_preferences("E001", key="preferred_shifts", session=session, current_user=_user())
        assert "preferred_shifts" not in resp["preferences"]
        assert "days_off" in resp["preferences"]

    @pytest.mark.asyncio
    async def test_delete_employee_preferences_not_found(self):
        session = AsyncMock()
        with patch("src.api.employees.EmployeeRepository.get_by_id", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc:
                await delete_employee_preferences("E404", key=None, session=session, current_user=_user())
        assert exc.value.status_code == 404

