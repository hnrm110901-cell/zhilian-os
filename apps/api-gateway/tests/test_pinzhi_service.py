from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.pinzhi_service import PinzhiService


def _mock_response(status_code=200, payload=None, elapsed_ms=25):
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = b"{}"
    resp.json.return_value = payload or {}
    resp.elapsed = SimpleNamespace(total_seconds=lambda: elapsed_ms / 1000)
    return resp


@pytest.mark.asyncio
async def test_health_check_not_configured():
    svc = PinzhiService()
    svc.token = ""
    svc.base_url = ""
    result = await svc.health_check()
    assert result["status"] == "not_configured"
    assert result["reachable"] is False


@pytest.mark.asyncio
async def test_health_check_do_probe_success():
    svc = PinzhiService()
    svc.token = "token-x"
    svc.base_url = "https://pinzhi.example.com"
    svc.timeout = 3

    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(payload={"success": 0, "data": []})

    with patch("src.services.pinzhi_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__.return_value = mock_client
        result = await svc.health_check()

    assert result["status"] == "healthy"
    assert result["reachable"] is True
    assert result["probe_endpoint"] == "/pinzhi/reportcategory.do"


@pytest.mark.asyncio
async def test_health_check_auth_failed():
    svc = PinzhiService()
    svc.token = "bad-token"
    svc.base_url = "https://pinzhi.example.com"
    svc.timeout = 3

    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(payload={"success": 1, "msg": "token invalid"})

    with patch("src.services.pinzhi_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__.return_value = mock_client
        result = await svc.health_check()

    assert result["status"] == "auth_failed"
    assert result["reachable"] is False


@pytest.mark.asyncio
async def test_health_check_timeout():
    svc = PinzhiService()
    svc.token = "token-x"
    svc.base_url = "https://pinzhi.example.com"
    svc.timeout = 1

    mock_client = AsyncMock()
    mock_client.get.side_effect = __import__("httpx").TimeoutException("timeout")

    with patch("src.services.pinzhi_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__.return_value = mock_client
        result = await svc.health_check()

    assert result["status"] == "timeout"
    assert result["reachable"] is False
