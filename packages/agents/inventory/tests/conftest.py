import sys
from pathlib import Path
from datetime import datetime, timedelta

import pytest

# Add agent root dir so `from src.agent import ...` works (src is a package)
agent_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(agent_root))
# Add base_agent (lives in apps/api-gateway/src/core)
sys.path.insert(0, str(agent_root.parent.parent.parent / "apps" / "api-gateway" / "src" / "core"))

# ---------------------------------------------------------------------------
# Sample inventory data injected via monkeypatch (L005: no real DB in tests)
# ---------------------------------------------------------------------------

def _make_sample_inventory():
    """5 items covering all status/expiration scenarios used by tests."""
    return [
        {
            "item_id": "INV001",
            "item_name": "鲜牛肉",
            "category": "meat",
            "unit": "kg",
            "current_stock": 22.0,   # above min(20) but below safe(50) → LOW
            "safe_stock": 50.0,
            "min_stock": 20.0,
            "max_stock": 150.0,
            "unit_cost": 8000,
            "supplier_id": None,
            "lead_time_days": 2,
            "expiration_date": None,
            "location": "",
        },
        {
            "item_id": "INV002",
            "item_name": "青菜",
            "category": "vegetable",
            "unit": "kg",
            "current_stock": 0.0,    # OUT_OF_STOCK
            "safe_stock": 20.0,
            "min_stock": 10.0,
            "max_stock": 60.0,
            "unit_cost": 500,
            "supplier_id": None,
            "lead_time_days": 1,
            "expiration_date": None,
            "location": "",
        },
        {
            "item_id": "INV003",
            "item_name": "酱油",
            "category": "condiment",
            "unit": "瓶",
            "current_stock": 100.0,  # SUFFICIENT
            "safe_stock": 30.0,
            "min_stock": 10.0,
            "max_stock": 200.0,
            "unit_cost": 1500,
            "supplier_id": None,
            "lead_time_days": 3,
            "expiration_date": None,
            "location": "",
        },
        {
            "item_id": "INV004",
            "item_name": "大米",
            "category": "grain",
            "unit": "kg",
            "current_stock": 80.0,   # SUFFICIENT
            "safe_stock": 40.0,
            "min_stock": 20.0,
            "max_stock": 200.0,
            "unit_cost": 600,
            "supplier_id": None,
            "lead_time_days": 2,
            "expiration_date": None,
            "location": "",
        },
        {
            "item_id": "INV005",
            "item_name": "鲜牛奶",
            "category": "dairy",
            "unit": "L",
            "current_stock": 5.0,    # CRITICAL (below min_stock=10)
            "safe_stock": 20.0,
            "min_stock": 10.0,
            "max_stock": 50.0,
            "unit_cost": 1200,
            "supplier_id": None,
            "lead_time_days": 1,
            # expires in 1 day → triggers URGENT expiration alert
            "expiration_date": (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d"),
            "location": "",
        },
    ]


@pytest.fixture(autouse=True)
def patch_inventory_db(monkeypatch):
    """
    Replace _fetch_inventory_from_db with sample data for every test.
    Allows tests to run without a real PostgreSQL connection (L005 rule).
    """
    from src.agent import InventoryAgent

    sample = _make_sample_inventory()

    def _fake_fetch(self, category=None):
        if category is None:
            return sample
        return [item for item in sample if item["category"] == category]

    monkeypatch.setattr(InventoryAgent, "_fetch_inventory_from_db", _fake_fetch)
