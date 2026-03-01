import sys
from pathlib import Path

import pytest

# Add agent src so `from agent import ...` works
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
# base_agent lives in apps/api-gateway/src/core
sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent.parent.parent.parent
        / "apps" / "api-gateway" / "src" / "core"),
)

# ---------------------------------------------------------------------------
# Sample customer RFM data injected via monkeypatch (L005: no real DB in tests)
# ---------------------------------------------------------------------------

SAMPLE_CUSTOMERS = [
    # S1 高价值: recency ≤ 30, freq ≥ 2, monetary ≥ 10000
    {"customer_id": "C001", "recency_days": 2,   "frequency": 5, "monetary": 25000, "last_visit": "2025-01-10", "avg_order_time": 12},
    {"customer_id": "C002", "recency_days": 5,   "frequency": 3, "monetary": 18000, "last_visit": "2025-01-07", "avg_order_time": 19},
    {"customer_id": "C003", "recency_days": 10,  "frequency": 2, "monetary": 12000, "last_visit": "2025-01-02", "avg_order_time": 12},
    # S2 潜力: recency ≤ 30, but low freq/monetary
    {"customer_id": "C004", "recency_days": 20,  "frequency": 1, "monetary": 6000,  "last_visit": "2024-12-23", "avg_order_time": 12},
    {"customer_id": "C005", "recency_days": 25,  "frequency": 1, "monetary": 5000,  "last_visit": "2024-12-18", "avg_order_time": 12},
    # S3 沉睡: 31-60 days
    {"customer_id": "C006", "recency_days": 35,  "frequency": 0, "monetary": 0,     "last_visit": "2024-12-08", "avg_order_time": 12},
    {"customer_id": "C007", "recency_days": 45,  "frequency": 0, "monetary": 0,     "last_visit": "2024-11-28", "avg_order_time": 12},
    {"customer_id": "C008", "recency_days": 60,  "frequency": 0, "monetary": 0,     "last_visit": "2024-11-13", "avg_order_time": 12},
    # S4 流失预警: 61-90 days
    {"customer_id": "C009", "recency_days": 80,  "frequency": 0, "monetary": 0,     "last_visit": "2024-10-24", "avg_order_time": 12},
    # S5 流失: > 90 days
    {"customer_id": "C010", "recency_days": 100, "frequency": 0, "monetary": 0,     "last_visit": "2024-10-04", "avg_order_time": 12},
]
# C004-C010 have recency_days >= 14 (PD_CHURN_THRESHOLD_DAYS default) → CHURN_RISK signals


@pytest.fixture(autouse=True)
def patch_customers_db(monkeypatch):
    """
    Replace _fetch_customers_from_db with sample data for every test.
    Allows tests to run without a real PostgreSQL connection (L005 rule).
    """
    from agent import PrivateDomainAgent

    async def _fake_fetch(self, days):
        return SAMPLE_CUSTOMERS

    monkeypatch.setattr(PrivateDomainAgent, "_fetch_customers_from_db", _fake_fetch)
