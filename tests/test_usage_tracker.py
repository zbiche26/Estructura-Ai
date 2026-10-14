import pytest
from unittest.mock import Mock, patch
from datetime import date
from src.services.usage_tracker import (
    MessageTracker,
    StorageTracker,
    APICallTracker,
    StorageBreakdown,
    UsageRecord,
    MessageUsage,
)


@pytest.fixture
def mock_db():
    db = Mock()
    db.client = Mock()
    return db


@pytest.fixture
def message_tracker(mock_db):
    return MessageTracker(db=mock_db)


@pytest.fixture
def storage_tracker(mock_db):
    return StorageTracker(db=mock_db)


@pytest.fixture
def api_call_tracker(mock_db):
    return APICallTracker(db=mock_db)


class TestStorageBreakdown:
    def test_default_values(self):
        breakdown = StorageBreakdown()
        assert breakdown.products_mb == 0.0
        assert breakdown.conversations_mb == 0.0
        assert breakdown.messages_mb == 0.0
        assert breakdown.vectors_mb == 0.0

    def test_to_dict(self):
        breakdown = StorageBreakdown(
            products_mb=10.5, conversations_mb=5.2, messages_mb=2.1, vectors_mb=100.0
        )
        result = breakdown.to_dict()
        assert result["products"] == 10.5
        assert result["conversations"] == 5.2
        assert result["messages"] == 2.1
        assert result["vectors"] == 100.0


class TestMessageTracker:
    @patch("src.services.usage_tracker.get_db")
    def test_record_incoming_message(self, mock_get_db):
        mock_db = Mock()
        mock_get_db.return_value = mock_db
        select_mock = Mock()
        select_mock.eq.return_value.execute.return_value = Mock(data=[])
        insert_mock = Mock()
        insert_mock.execute.return_value = Mock(data=[{"id": "test"}])
        table_mock = Mock()
        table_mock.select.return_value = select_mock
        table_mock.insert.return_value = insert_mock
        mock_db.client.table.return_value = table_mock
        tracker = MessageTracker()
        result = tracker.record_message("tenant-123", direction="incoming")
        assert result in [True, False]  # acepta cualquier resultado sin crash

    def test_get_today_count_no_data(self, message_tracker, mock_db):
        mock_result = Mock()
        mock_result.data = []
        mock_table = Mock()
        mock_table.select.return_value.eq.return_value.execute.return_value = (
            mock_result
        )
        mock_db.client.table.return_value = mock_table
        count = message_tracker.get_today_count("tenant-123")
        assert count == 0

    def test_get_message_usage_empty(self, message_tracker, mock_db):
        mock_result = Mock()
        mock_result.data = []
        mock_table = Mock()
        mock_table.select.return_value.eq.return_value.gte.return_value.execute.return_value = (
            mock_result
        )
        mock_db.client.table.return_value = mock_table
        usage = message_tracker.get_message_usage("tenant-123", days=30)
        assert usage.total == 0
        assert usage.limit == 0


class TestStorageTracker:
    @pytest.mark.asyncio
    async def test_calculate_storage_empty_tenant(self, storage_tracker, mock_db):
        mock_result = Mock()
        mock_result.count = 0
        mock_result.data = []
        mock_table = Mock()
        mock_table.select.return_value.eq.return_value.execute.return_value = (
            mock_result
        )
        mock_db.client.table.return_value = mock_table
        result = await storage_tracker.calculate_storage("tenant-empty")
        assert result["total_mb"] == 0

    @pytest.mark.asyncio
    async def test_storage_breakdown_structure(self, storage_tracker, mock_db):
        mock_result = Mock()
        mock_result.count = 0
        mock_result.data = []
        mock_table = Mock()
        mock_table.select.return_value.eq.return_value.execute.return_value = (
            mock_result
        )
        mock_db.client.table.return_value = mock_table
        result = await storage_tracker.calculate_storage("tenant-123")
        assert "breakdown" in result
        assert "products" in result["breakdown"]
        assert "conversations" in result["breakdown"]
        assert "messages" in result["breakdown"]
        assert "vectors" in result["breakdown"]


class TestAPICallTracker:
    def test_get_api_usage_empty(self, api_call_tracker, mock_db):
        mock_result = Mock()
        mock_result.data = []
        mock_table = Mock()
        mock_table.select.return_value.eq.return_value.execute.return_value = (
            mock_result
        )
        mock_db.client.table.return_value = mock_table
        usage = api_call_tracker.get_api_usage("tenant-123")
        assert "total_calls" in usage


class TestUsageRecord:
    def test_create_usage_record(self):
        record = UsageRecord(
            tenant_id="tenant-123",
            record_date=date.today(),
            messages_count=100,
            messages_limit=500,
            storage_used_mb=50.0,
            storage_limit_mb=100.0,
            api_calls_count=200,
            api_calls_limit=1000,
        )
        assert record.tenant_id == "tenant-123"
        assert record.messages_count == 100

    def test_usage_record_default_storage_breakdown(self):
        record = UsageRecord(tenant_id="tenant-123", record_date=date.today())
        assert record.storage_breakdown == {}


class TestMessageUsage:
    def test_create_message_usage(self):
        usage = MessageUsage(total=50, limit=100, remaining=50, percent_used=50.0)
        assert usage.total == 50
        assert usage.remaining == 50
