"""
POS 适配器注册表（registry.py）单元测试

覆盖：
- 已注册的有效 pos_type → 适配器实例化成功
- 未知的 pos_type → ValueError（含已注册列表提示）
- 注册表中值为 None 的 pos_type → AdapterNotImplementedError
- 模块路径无效 → ImportError（含清晰错误信息）
- list_registered_pos_types / list_implemented_pos_types 辅助函数
"""
import os
import sys
import types
import pytest

_here = os.path.dirname(os.path.abspath(__file__))
_pkg_src = os.path.abspath(os.path.join(_here, "../src"))
_repo_root = os.path.abspath(os.path.join(_here, "../../../.."))
_gateway_src = os.path.join(_repo_root, "apps", "api-gateway", "src")

for _p in (_pkg_src, _gateway_src):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from registry import (
    get_transformer,
    list_registered_pos_types,
    list_implemented_pos_types,
    AdapterNotImplementedError,
    POS_REGISTRY,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeAdapter:
    """最简适配器 stub，满足 get_transformer 实例化要求"""
    def __init__(self, config: dict):
        self.config = config


def _inject_fake_adapter(monkeypatch, pos_type: str, module_path: str, class_name: str):
    """在 sys.modules 中注入 _FakeAdapter，让 importlib 找到它"""
    fake_module = types.ModuleType(module_path)
    setattr(fake_module, class_name, _FakeAdapter)
    monkeypatch.setitem(sys.modules, module_path, fake_module)
    monkeypatch.setitem(POS_REGISTRY, pos_type, f"{module_path}.{class_name}")


# ---------------------------------------------------------------------------
# 1. 未知 pos_type → ValueError
# ---------------------------------------------------------------------------

class TestUnknownPosType:
    def test_raises_value_error(self):
        with pytest.raises(ValueError, match="未知的 POS 系统类型"):
            get_transformer("nonexistent_pos", store_id="S1", brand_id="B1")

    def test_error_lists_registered_types(self):
        with pytest.raises(ValueError) as exc_info:
            get_transformer("ghost_pos", store_id="S1", brand_id="B1")
        msg = str(exc_info.value)
        # 错误信息应包含至少一个已知 POS 类型
        assert any(k in msg for k in POS_REGISTRY)


# ---------------------------------------------------------------------------
# 2. 注册表中值为 None → AdapterNotImplementedError
# ---------------------------------------------------------------------------

class TestNotImplementedAdapter:
    def test_raises_adapter_not_implemented(self, monkeypatch):
        monkeypatch.setitem(POS_REGISTRY, "stub_pos", None)
        with pytest.raises(AdapterNotImplementedError):
            get_transformer("stub_pos", store_id="S1", brand_id="B1")

    def test_error_carries_pos_type(self, monkeypatch):
        monkeypatch.setitem(POS_REGISTRY, "stub_pos2", None)
        with pytest.raises(AdapterNotImplementedError) as exc_info:
            get_transformer("stub_pos2", store_id="S1", brand_id="B1")
        assert exc_info.value.pos_type == "stub_pos2"

    def test_is_subclass_of_not_implemented_error(self, monkeypatch):
        monkeypatch.setitem(POS_REGISTRY, "stub_pos3", None)
        with pytest.raises(NotImplementedError):
            get_transformer("stub_pos3", store_id="S1", brand_id="B1")


# ---------------------------------------------------------------------------
# 3. 有效的 pos_type（使用注入的 fake adapter）→ 实例化成功
# ---------------------------------------------------------------------------

class TestSuccessfulInstantiation:
    def test_returns_adapter_instance(self, monkeypatch):
        _inject_fake_adapter(monkeypatch, "fake_pos", "fake_module", "FakeAdapter")
        adapter = get_transformer("fake_pos", store_id="STORE1", brand_id="BRAND1")
        assert isinstance(adapter, _FakeAdapter)

    def test_store_id_injected_into_config(self, monkeypatch):
        _inject_fake_adapter(monkeypatch, "fake_pos2", "fake_module2", "FakeAdapter2")
        adapter = get_transformer("fake_pos2", store_id="STORE_X", brand_id="BRAND_X")
        assert adapter.config["store_id"] == "STORE_X"

    def test_brand_id_injected_into_config(self, monkeypatch):
        _inject_fake_adapter(monkeypatch, "fake_pos3", "fake_module3", "FakeAdapter3")
        adapter = get_transformer("fake_pos3", store_id="STORE_Y", brand_id="BRAND_Y")
        assert adapter.config["brand_id"] == "BRAND_Y"

    def test_extra_config_passed_through(self, monkeypatch):
        _inject_fake_adapter(monkeypatch, "fake_pos4", "fake_module4", "FakeAdapter4")
        adapter = get_transformer(
            "fake_pos4", store_id="S", brand_id="B", config={"token": "abc"}
        )
        assert adapter.config["token"] == "abc"

    def test_module_hyphen_replaced_with_underscore(self, monkeypatch):
        """注册路径中的 '-' 应被替换为 '_' 以满足 Python 模块命名规范"""
        fake_module_name = "packages.api_adapters.hyphen_test.src.adapter"
        fake_module = types.ModuleType(fake_module_name)
        setattr(fake_module, "HyphenAdapter", _FakeAdapter)
        monkeypatch.setitem(sys.modules, fake_module_name, fake_module)
        # 注册路径含 '-'
        monkeypatch.setitem(
            POS_REGISTRY,
            "hyphen_pos",
            "packages.api-adapters.hyphen-test.src.adapter.HyphenAdapter",
        )
        adapter = get_transformer("hyphen_pos", store_id="S", brand_id="B")
        assert isinstance(adapter, _FakeAdapter)


# ---------------------------------------------------------------------------
# 4. 无效模块路径 → ImportError
# ---------------------------------------------------------------------------

class TestInvalidModulePath:
    def test_raises_import_error(self, monkeypatch):
        monkeypatch.setitem(
            POS_REGISTRY,
            "bad_pos",
            "totally.nonexistent.module.BadAdapter",
        )
        with pytest.raises(ImportError, match="无法加载 POS 适配器"):
            get_transformer("bad_pos", store_id="S", brand_id="B")

    def test_error_contains_pos_type(self, monkeypatch):
        monkeypatch.setitem(
            POS_REGISTRY,
            "bad_pos2",
            "totally.nonexistent.module2.BadAdapter2",
        )
        with pytest.raises(ImportError) as exc_info:
            get_transformer("bad_pos2", store_id="S", brand_id="B")
        assert "bad_pos2" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 5. 辅助函数
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_list_registered_includes_all_keys(self):
        registered = list_registered_pos_types()
        for key in POS_REGISTRY:
            assert key in registered

    def test_list_implemented_excludes_none(self, monkeypatch):
        monkeypatch.setitem(POS_REGISTRY, "unimplemented_pos", None)
        implemented = list_implemented_pos_types()
        assert "unimplemented_pos" not in implemented

    def test_list_implemented_subset_of_registered(self):
        assert set(list_implemented_pos_types()) <= set(list_registered_pos_types())
