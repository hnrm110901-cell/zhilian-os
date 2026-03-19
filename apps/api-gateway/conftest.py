"""Root conftest for apps/api-gateway.

Registers local alembic/versions/ as a discoverable Python package so that
migration test files can do:
    from alembic.versions.zXX_... import upgrade, downgrade

without conflicting with the installed `alembic` library.
"""
import importlib.util
import sys
import types
from pathlib import Path

_VERSIONS_DIR = Path(__file__).parent / "alembic" / "versions"


def _register_alembic_versions() -> None:
    """Inject alembic.versions into sys.modules pointing at the local directory."""
    if "alembic.versions" not in sys.modules:
        m = types.ModuleType("alembic.versions")
        m.__path__ = [str(_VERSIONS_DIR)]  # type: ignore[attr-defined]
        m.__package__ = "alembic.versions"
        sys.modules["alembic.versions"] = m


_register_alembic_versions()
