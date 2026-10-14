import pytest
from unittest.mock import Mock, patch
from datetime import date
from src.services.billing_service import (
    QuotaChecker,
    QuotaExceededError,
    PlanDefinitionService,
    PlanLimits,
    Subscription,
    QuotaCheckResult,
)
from src.schemas.tenant_schemas import TenantPlanEnum


@pytest.fixture
def mock_db():
    db = Mock()
    db.client = Mock()
    return db


@pytest.fixture
def quota_checker(mock_db):
    return QuotaChecker(db=mock_db)


@pytest.fixture
def subscription_starter():
    return Subscription(
        id="sub-123",
        tenant_id="tenant-123",
        plan_key=TenantPlanEnum.STARTER.value,
        status="active",
        current_period_start=date(2026, 1, 1),
        current_period_end=date(2026, 1, 31),
        trial_end=None,
        billing_email=None,
        billing_cycle="monthly",
        allow_overages=False,
    )


@pytest.fixture
def subscription_growth():
    return Subscription(
        id="sub-456",
        tenant_id="tenant-456",
        plan_key=TenantPlanEnum.GROWTH.value,
        status="active",
        current_period_start=date(2026, 1, 1),
        current_period_end=date(2026, 1, 31),
        trial_end=None,
        billing_email=None,
        billing_cycle="monthly",
        allow_overages=True,
    )


@pytest.fixture
def subscription_scale():
    return Subscription(
        id="sub-789",
        tenant_id="tenant-789",
        plan_key=TenantPlanEnum.SCALE.value,
        status="active",
        current_period_start=date(2026, 1, 1),
        current_period_end=date(2026, 1, 31),
        trial_end=None,
        billing_email=None,
        billing_cycle="monthly",
        allow_overages=False,
    )


class TestPlanDefinitionService:

    def test_get_plan_limits_starter(self):
        limits = PlanDefinitionService._get_default_limits(TenantPlanEnum.STARTER.value)
        assert limits.messages_limit > 0
        assert limits.products_limit > 0
        assert limits.users_limit > 0

    def test_get_plan_limits_growth(self):
        starter = PlanDefinitionService._get_default_limits(
            TenantPlanEnum.STARTER.value
        )
        growth = PlanDefinitionService._get_default_limits(TenantPlanEnum.GROWTH.value)
        assert growth.messages_limit > starter.messages_limit
        assert growth.products_limit > starter.products_limit

    def test_get_plan_limits_scale_unlimited(self):
        limits = PlanDefinitionService._get_default_limits(TenantPlanEnum.SCALE.value)
        assert limits.messages_limit == -1
        assert limits.storage_limit_mb == -1
        assert limits.api_calls_limit == -1

    @pytest.mark.skip(reason="get_all_plans() calls Supabase real")
    def test_get_all_plans_count(self):
        """Hay al menos 3 planes (puede haber más según la implementación)"""
        plans = PlanDefinitionService.get_all_plans()
        assert len(plans) >= 3

    @pytest.mark.skip(reason="get_all_plans() calls Supabase real")
    def test_get_all_plans_keys(self):
        """Los planes incluyen starter, growth y scale"""
        plans = PlanDefinitionService.get_all_plans()
        keys = [p["key"] for p in plans]
        assert TenantPlanEnum.STARTER.value in keys
        assert TenantPlanEnum.GROWTH.value in keys
        assert TenantPlanEnum.SCALE.value in keys

    def test_growth_has_whatsapp_full(self):
        limits = PlanDefinitionService._get_default_limits(TenantPlanEnum.GROWTH.value)
        assert "whatsapp_full" in limits.features

    def test_growth_has_api_access(self):
        limits = PlanDefinitionService._get_default_limits(TenantPlanEnum.GROWTH.value)
        assert "api_access" in limits.features


class TestQuotaChecker:

    def test_check_quota_no_subscription(self, quota_checker):
        with patch.object(quota_checker, "_get_subscription", return_value=None):
            result = quota_checker.check_quota("tenant-123", "messages")
            assert result.allowed is True
            assert result.current_usage == 0

    def test_check_quota_within_limit_starter(
        self, quota_checker, subscription_starter
    ):
        with patch.object(
            quota_checker, "_get_subscription", return_value=subscription_starter
        ):
            with patch.object(quota_checker, "_get_current_usage", return_value=50):
                result = quota_checker.check_quota("tenant-123", "messages")
                assert result.allowed is True
                assert result.current_usage == 50

    def test_check_quota_exceeds_limit_no_overage(
        self, quota_checker, subscription_starter
    ):
        with patch.object(
            quota_checker, "_get_subscription", return_value=subscription_starter
        ):
            with patch.object(quota_checker, "_get_current_usage", return_value=1500):
                result = quota_checker.check_quota("tenant-123", "messages")
                assert result.allowed is False

    def test_check_quota_exceeds_limit_with_overage(
        self, quota_checker, subscription_growth
    ):
        with patch.object(
            quota_checker, "_get_subscription", return_value=subscription_growth
        ):
            with patch.object(quota_checker, "_get_current_usage", return_value=6000):
                result = quota_checker.check_quota("tenant-456", "messages")
                assert result.allowed is True
                assert result.overage_allowed is True

    def test_check_quota_scale_unlimited(self, quota_checker, subscription_scale):
        with patch.object(
            quota_checker, "_get_subscription", return_value=subscription_scale
        ):
            with patch.object(quota_checker, "_get_current_usage", return_value=999999):
                result = quota_checker.check_quota("tenant-789", "messages")
                assert result.allowed is True
                assert result.limit == -1
                assert result.remaining == -1

    def test_check_all_quotas_returns_all_resources(
        self, quota_checker, subscription_starter
    ):
        with patch.object(
            quota_checker, "_get_subscription", return_value=subscription_starter
        ):
            with patch.object(quota_checker, "_get_current_usage", return_value=10):
                results = quota_checker.check_all_quotas("tenant-123")
                assert "messages" in results
                assert "storage" in results
                assert "api_calls" in results
                assert "products" in results

    def test_require_quota_raises_when_exceeded(
        self, quota_checker, subscription_starter
    ):
        with patch.object(
            quota_checker, "_get_subscription", return_value=subscription_starter
        ):
            with patch.object(quota_checker, "_get_current_usage", return_value=1500):
                with pytest.raises(QuotaExceededError):
                    quota_checker.require_quota("tenant-123", "messages", quantity=1)

    def test_require_quota_passes_within_limit(
        self, quota_checker, subscription_starter
    ):
        with patch.object(
            quota_checker, "_get_subscription", return_value=subscription_starter
        ):
            with patch.object(quota_checker, "_get_current_usage", return_value=10):
                quota_checker.require_quota("tenant-123", "messages", quantity=1)


class TestQuotaExceededError:

    def test_raise_error(self):
        with pytest.raises(QuotaExceededError):
            raise QuotaExceededError("Cuota excedida")

    def test_error_message(self):
        error = QuotaExceededError("Test error message")
        assert str(error) == "Test error message"
