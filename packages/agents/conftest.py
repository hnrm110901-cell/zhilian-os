"""
Shared conftest for all agent packages.

Centralizes sys.path setup so individual agent test conftests don't need to repeat it.
This file is auto-discovered by pytest when running from packages/agents/ or any subdirectory.

Adds to sys.path:
1. Each agent's root dir (so `from src.agent import ...` works)
2. api-gateway/src/core (for base_agent imports)
"""
import sys
from pathlib import Path

_agents_root = Path(__file__).resolve().parent
_project_root = _agents_root.parent.parent

# Add api-gateway core path (for base_agent, config, etc.)
_core_path = str(_project_root / "apps" / "api-gateway" / "src" / "core")
if _core_path not in sys.path:
    sys.path.insert(0, _core_path)

# Auto-add each agent's root dir based on the test being collected
# This is handled by the pytest_collect_modifyitems hook below


def pytest_collection_modifyitems(session, config, items):
    """Dynamically add each agent's root to sys.path based on collected test items."""
    added = set()
    for item in items:
        # Find the agent root: packages/agents/{agent_name}/
        fspath = Path(item.fspath)
        for parent in fspath.parents:
            if parent.parent == _agents_root and str(parent) not in added:
                added.add(str(parent))
                if str(parent) not in sys.path:
                    sys.path.insert(0, str(parent))
                break
