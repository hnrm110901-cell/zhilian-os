import sys
from pathlib import Path

import pytest

# Add agent root dir so `from src.agent import ...` works (src is a package)
agent_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(agent_root))
# Add base_agent (lives in apps/api-gateway/src/core)
sys.path.insert(0, str(agent_root.parent.parent.parent / "apps" / "api-gateway" / "src" / "core"))

# ---------------------------------------------------------------------------
# Sample reservation data injected via monkeypatch (L005: no real DB in tests)
# ---------------------------------------------------------------------------

_SAMPLE_RESERVATIONS = {
    "RES001": {
        "reservation_id": "RES001",
        "customer_id": "CUST001",
        "customer_name": "张三",
        "customer_phone": "13800138000",
        "store_id": "STORE001",
        "reservation_type": "regular",
        "reservation_date": "2099-12-31",   # far future → cancellation always valid
        "reservation_time": "18:00",
        "party_size": 4,
        "table_type": "medium",
        "table_number": "M001",
        "special_requests": None,
        "status": "pending",
        "deposit_amount": 10000,
        "estimated_amount": 32000,
        "created_at": "2026-02-28T10:00:00",
        "updated_at": "2026-02-28T10:00:00",
        "confirmed_at": None,
        "seated_at": None,
        "completed_at": None,
    },
    "RES002": {
        "reservation_id": "RES002",
        "customer_id": "CUST002",
        "customer_name": "李四",
        "customer_phone": "13900139000",
        "store_id": "STORE001",
        "reservation_type": "regular",
        "reservation_date": "2099-12-31",
        "reservation_time": "19:00",
        "party_size": 2,
        "table_type": "small",
        "table_number": "S001",
        "special_requests": None,
        "status": "pending",
        "deposit_amount": 5000,
        "estimated_amount": 15000,
        "created_at": "2026-02-28T11:00:00",
        "updated_at": "2026-02-28T11:00:00",
        "confirmed_at": None,
        "seated_at": None,
        "completed_at": None,
    },
}


@pytest.fixture(autouse=True)
def patch_reservation_db(monkeypatch):
    """
    Replace _get_reservation with sample data for every test.
    Allows tests to run without a real PostgreSQL connection (L005 rule).
    """
    from src.agent import ReservationAgent
    import copy

    async def _fake_get_reservation(self, reservation_id: str):
        if reservation_id not in _SAMPLE_RESERVATIONS:
            raise ValueError(f"预定不存在: {reservation_id}")
        # Return a fresh copy so test mutations don't affect other tests
        return copy.deepcopy(_SAMPLE_RESERVATIONS[reservation_id])

    monkeypatch.setattr(ReservationAgent, "_get_reservation", _fake_get_reservation)
