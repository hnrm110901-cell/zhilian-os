"""
packages/api-adapters/base/tests/conftest.py

Shared path setup for all base-adapter tests.
Adds both the package's own src/ and the gateway's src/ to sys.path
so tests can do `from registry import ...` without manual path surgery.
"""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
_pkg_src = os.path.abspath(os.path.join(_here, "../src"))
_repo_root = os.path.abspath(os.path.join(_here, "../../../.."))
_gateway_src = os.path.join(_repo_root, "apps", "api-gateway", "src")

for _p in (_pkg_src, _gateway_src):
    if _p not in sys.path:
        sys.path.insert(0, _p)
