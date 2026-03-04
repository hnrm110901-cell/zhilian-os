"""
Tests for small utility modules:
  - src/core/root_cause_config.py
  - src/core/exceptions.py
  - src/core/money.py
  - src/services/base_service.py
"""
import pytest
import sys
from unittest.mock import MagicMock, patch
from decimal import Decimal


# ---------------------------------------------------------------------------
# root_cause_config.py
# ---------------------------------------------------------------------------

class TestRootCauseConfig:
    def test_root_cause_to_training_has_inventory_variance(self):
        from src.core.root_cause_config import ROOT_CAUSE_TO_TRAINING
        entry = ROOT_CAUSE_TO_TRAINING["inventory_variance"]
        assert entry["skill_gap"] == "inventory_management"
        assert entry["urgency"] == "high"
        assert "inv_count_accuracy" in entry["course_ids"]

    def test_root_cause_to_training_has_bom_deviation(self):
        from src.core.root_cause_config import ROOT_CAUSE_TO_TRAINING
        entry = ROOT_CAUSE_TO_TRAINING["bom_deviation"]
        assert entry["urgency_days"] == 3

    def test_root_cause_to_training_has_staff_error(self):
        from src.core.root_cause_config import ROOT_CAUSE_TO_TRAINING
        entry = ROOT_CAUSE_TO_TRAINING["staff_error"]
        assert entry["urgency"] == "medium"

    def test_root_cause_to_training_has_food_quality(self):
        from src.core.root_cause_config import ROOT_CAUSE_TO_TRAINING
        entry = ROOT_CAUSE_TO_TRAINING["food_quality"]
        assert entry["urgency"] == "high"
        assert entry["urgency_days"] == 2

    def test_urgency_to_priority_mapping(self):
        from src.core.root_cause_config import URGENCY_TO_PRIORITY
        assert URGENCY_TO_PRIORITY["high"] == "P1"
        assert URGENCY_TO_PRIORITY["medium"] == "P2"
        assert URGENCY_TO_PRIORITY["low"] == "P3"

    def test_all_known_root_causes_present(self):
        from src.core.root_cause_config import ROOT_CAUSE_TO_TRAINING
        for key in ["inventory_variance", "bom_deviation", "time_window_staff",
                    "supplier_batch", "staff_error", "process_deviation",
                    "food_quality", "equipment_fault", "supply_chain"]:
            assert key in ROOT_CAUSE_TO_TRAINING, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# exceptions.py
# ---------------------------------------------------------------------------

class TestExceptions:
    def test_not_found_error_is_exception(self):
        from src.core.exceptions import NotFoundError
        with pytest.raises(NotFoundError, match="item 42 not found"):
            raise NotFoundError("item 42 not found")

    def test_validation_error_is_exception(self):
        from src.core.exceptions import ValidationError
        with pytest.raises(ValidationError):
            raise ValidationError("invalid input")

    def test_authentication_error_is_exception(self):
        from src.core.exceptions import AuthenticationError
        with pytest.raises(AuthenticationError):
            raise AuthenticationError("invalid token")

    def test_authorization_error_is_exception(self):
        from src.core.exceptions import AuthorizationError
        with pytest.raises(AuthorizationError):
            raise AuthorizationError("access denied")

    def test_all_are_subclass_of_exception(self):
        from src.core.exceptions import (
            NotFoundError, ValidationError,
            AuthenticationError, AuthorizationError,
        )
        for cls in [NotFoundError, ValidationError, AuthenticationError, AuthorizationError]:
            assert issubclass(cls, Exception)


# ---------------------------------------------------------------------------
# money.py
# ---------------------------------------------------------------------------

class TestMoneyUtils:
    def test_D_from_int(self):
        from src.core.money import D
        assert D(100) == Decimal("100")

    def test_D_from_float(self):
        from src.core.money import D
        # avoids Decimal(0.1) floating point pitfall
        assert D(0.1) == Decimal("0.1")

    def test_D_from_str(self):
        from src.core.money import D
        assert D("99.99") == Decimal("99.99")

    def test_D_from_decimal_passthrough(self):
        from src.core.money import D
        d = Decimal("55.5")
        assert D(d) is d

    def test_yuan_to_fen_basic(self):
        from src.core.money import yuan_to_fen
        assert yuan_to_fen(10) == 1000

    def test_yuan_to_fen_rounds_half_up(self):
        from src.core.money import yuan_to_fen
        # 10.005 * 100 = 1000.5 → rounds to 1001
        assert yuan_to_fen("10.005") == 1001

    def test_yuan_to_fen_float(self):
        from src.core.money import yuan_to_fen
        assert yuan_to_fen(38.5) == 3850

    def test_fen_to_yuan_basic(self):
        from src.core.money import fen_to_yuan
        assert fen_to_yuan(1050) == Decimal("10.50")

    def test_fen_to_yuan_zero(self):
        from src.core.money import fen_to_yuan
        assert fen_to_yuan(0) == Decimal("0.00")

    def test_mul_rate_basic(self):
        from src.core.money import mul_rate
        result = mul_rate(1000, "0.20")
        assert result == Decimal("200.00")

    def test_mul_rate_rounds(self):
        from src.core.money import mul_rate
        # 1050 * 0.1 = 105.0
        result = mul_rate(1050, "0.10")
        assert result == Decimal("105.00")

    def test_mul_rate_float_rate(self):
        from src.core.money import mul_rate
        result = mul_rate(500, 0.15)
        assert result == Decimal("75.00")


# ---------------------------------------------------------------------------
# base_service.py — import with env vars set so Settings() succeeds
# ---------------------------------------------------------------------------

_ENV_VARS = {
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "CELERY_BROKER_URL": "redis://localhost:6379/0",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/0",
    "SECRET_KEY": "test-secret-key-32chars-padding!!",
    "JWT_SECRET": "test-jwt-secret-32chars-padding!!",
}


class TestBaseService:
    @classmethod
    def _get_base_service_class(cls):
        """Import BaseService, setting env vars if needed to satisfy Settings()."""
        if "src.services.base_service" in sys.modules:
            return sys.modules["src.services.base_service"].BaseService
        with patch.dict("os.environ", _ENV_VARS):
            from src.services.base_service import BaseService
            return BaseService

    def test_init_with_store_id(self):
        BaseService = self._get_base_service_class()
        svc = BaseService(store_id="STORE001")
        assert svc.get_store_id() == "STORE001"
        assert svc.require_store_id() == "STORE001"

    def test_init_without_store_id_uses_tenant_context(self):
        BaseService = self._get_base_service_class()
        from src.core.tenant_context import TenantContext
        TenantContext.set_current_tenant("CTX_STORE")
        try:
            svc = BaseService()
            assert svc.get_store_id() == "CTX_STORE"
        finally:
            TenantContext.clear_current_tenant()

    def test_require_store_id_raises_when_missing(self):
        BaseService = self._get_base_service_class()
        svc = BaseService()  # no store_id, no tenant context
        with pytest.raises(RuntimeError, match="requires a valid store_id"):
            svc.require_store_id()

    @pytest.mark.asyncio
    async def test_get_session_returns_context_manager(self):
        BaseService = self._get_base_service_class()
        svc = BaseService(store_id="STORE001")
        mock_cm = MagicMock()
        with patch("src.services.base_service.get_db_session", return_value=mock_cm) as mock_db:
            result = await svc.get_session()
            assert result is mock_cm
            mock_db.assert_called_once_with(enable_tenant_isolation=True)
