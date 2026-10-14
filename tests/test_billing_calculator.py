import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import date
from src.services.billing_service import (
    UsageAlertManager,
    UsageCalculator,
    BillingCalculator,
    InvoiceGenerator,
    PlanDefinitionService,
    PlanLimits,
    UsageSummary,
    ResourceUsage,
    Subscription,
)
from src.schemas.tenant_schemas import TenantPlanEnum


@pytest.fixture
def mock_db():
    db = Mock()
    db.client = Mock()
    return db


@pytest.fixture
def billing_calculator(mock_db):
    return BillingCalculator(db=mock_db)


@pytest.fixture
def invoice_generator(mock_db):
    return InvoiceGenerator(db=mock_db)


@pytest.fixture
def usage_alert_manager(mock_db):
    return UsageAlertManager(db=mock_db)


@pytest.fixture
def sample_subscription_growth():
    return Subscription(
        id="sub-123",
        tenant_id="tenant-123",
        plan_key=TenantPlanEnum.GROWTH.value,
        status="active",
        current_period_start=date(2026, 1, 1),
        current_period_end=date(2026, 1, 31),
        trial_end=None,
        billing_email="test@example.com",
        billing_cycle="monthly",
        allow_overages=True,
    )


@pytest.fixture
def sample_subscription_starter():
    return Subscription(
        id="sub-456",
        tenant_id="tenant-456",
        plan_key=TenantPlanEnum.STARTER.value,
        status="active",
        current_period_start=date(2026, 1, 1),
        current_period_end=date(2026, 1, 31),
        trial_end=None,
        billing_email="test@example.com",
        billing_cycle="monthly",
        allow_overages=False,
    )


class TestPlanDefinitionService:

    def test_get_plan_limits_starter(self):
        limits = PlanDefinitionService._get_default_limits(TenantPlanEnum.STARTER.value)
        assert limits.messages_limit == 1000
        assert limits.products_limit == 100
        assert limits.users_limit == 2

    def test_get_plan_limits_growth(self):
        starter = PlanDefinitionService._get_default_limits(
            TenantPlanEnum.STARTER.value
        )
        growth = PlanDefinitionService._get_default_limits(TenantPlanEnum.GROWTH.value)
        assert growth.messages_limit > starter.messages_limit
        assert growth.products_limit > starter.products_limit

    def test_get_plan_limits_scale(self):
        limits = PlanDefinitionService._get_default_limits(TenantPlanEnum.SCALE.value)
        assert limits.messages_limit == -1
        assert limits.storage_limit_mb == -1
        assert limits.api_calls_limit == -1

    def test_normalize_legacy_plans(self):
        assert (
            PlanDefinitionService._normalize_plan_key("free")
            == TenantPlanEnum.STARTER.value
        )
        assert (
            PlanDefinitionService._normalize_plan_key("pro")
            == TenantPlanEnum.GROWTH.value
        )

    @pytest.mark.skip(reason="get_all_plans() calls Supabase real")
    def test_get_all_plans_returns_three(self):
        pass

    def test_growth_has_whatsapp_full(self):
        limits = PlanDefinitionService._get_default_limits(TenantPlanEnum.GROWTH.value)
        assert "whatsapp_full" in limits.features

    def test_growth_has_api_access(self):
        limits = PlanDefinitionService._get_default_limits(TenantPlanEnum.GROWTH.value)
        assert "api_access" in limits.features


class TestInvoiceGenerator:

    def test_generate_invoice_number_format(self, invoice_generator, mock_db):
        mock_table = Mock()
        mock_db.client.table.return_value = mock_table
        mock_table.select.return_value.like.return_value.execute.return_value = Mock(
            data=[]
        )
        invoice_num = invoice_generator._generate_invoice_number(
            "tenant-123", date(2026, 3, 24)
        )
        assert invoice_num.startswith("INV-2026-")

    def test_generate_invoice_number_increments(self, invoice_generator, mock_db):
        mock_table = Mock()
        mock_db.client.table.return_value = mock_table
        mock_table.select.return_value.like.return_value.execute.return_value = Mock(
            data=[{"invoice_number": "INV-2026-TEST-0001"}]
        )
        invoice_num = invoice_generator._generate_invoice_number(
            "tenant-123", date(2026, 3, 24)
        )
        assert "0002" in invoice_num


class TestUsageAlertManager:

    def test_alert_thresholds(self, usage_alert_manager):
        assert usage_alert_manager.THRESHOLD_WARNING == 80
        assert usage_alert_manager.THRESHOLD_CRITICAL == 100

    def test_check_and_send_alerts_below_threshold(self, usage_alert_manager):
        mock_summary = UsageSummary(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            messages=ResourceUsage(current=10, limit=100, percent=10, remaining=90),
            storage=ResourceUsage(current=10, limit=100, percent=10, remaining=90),
            api_calls=ResourceUsage(current=10, limit=100, percent=10, remaining=90),
            products=ResourceUsage(current=10, limit=100, percent=10, remaining=90),
        )
        with patch.object(
            UsageCalculator, "get_current_usage_summary", return_value=mock_summary
        ):
            usage_alert_manager.check_and_send_alerts("tenant-123")

    def test_check_and_send_alerts_warning_threshold(
        self, usage_alert_manager, mock_db
    ):
        mock_summary = UsageSummary(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            messages=ResourceUsage(current=80, limit=100, percent=80, remaining=20),
            storage=ResourceUsage(current=50, limit=100, percent=50, remaining=50),
            api_calls=ResourceUsage(current=50, limit=100, percent=50, remaining=50),
            products=ResourceUsage(current=50, limit=100, percent=50, remaining=50),
        )
        mock_table = Mock()
        mock_db.client.table.return_value = mock_table
        mock_table.select.return_value.eq.return_value.eq.return_value.eq.return_value.gte.return_value.execute.return_value = Mock(
            data=[]
        )
        with patch.object(
            UsageCalculator, "get_current_usage_summary", return_value=mock_summary
        ):
            usage_alert_manager.check_and_send_alerts("tenant-123")
            mock_table.insert.assert_called()


class TestUsageDataClasses:

    def test_resource_usage_within_limit(self):
        usage = ResourceUsage(current=50, limit=100, percent=50, remaining=50)
        assert usage.current == 50

    def test_resource_usage_exceeds_limit(self):
        usage = ResourceUsage(current=150, limit=100, percent=150, remaining=0)
        assert usage.current == 150

    def test_usage_summary_creation(self):
        summary = UsageSummary(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            messages=ResourceUsage(current=50, limit=100, percent=50, remaining=50),
            storage=ResourceUsage(current=50, limit=100, percent=50, remaining=50),
            api_calls=ResourceUsage(current=50, limit=100, percent=50, remaining=50),
            products=ResourceUsage(current=50, limit=100, percent=50, remaining=50),
        )
        assert summary.messages.current == 50
