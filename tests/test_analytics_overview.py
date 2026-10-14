from datetime import datetime
from src.services.analytics_service import (
    get_analytics_overview,
    get_conversations_by_day,
    get_conversations_by_week,
    get_conversations_by_month,
)


class _DummyDB:
    @property
    def client(self):
        return object()


def test_overview_payload(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client

        def count_all(self):
            return 10

        def count_active_users(self):
            return 2

        def get_average_response_time(self, **kwargs):
            return 3.5

        def get_conversations_per_day(self, **kwargs):
            return {"2024-03-01": 1, "2024-03-02": 2}

    monkeypatch.setattr(
        "src.services.analytics_service.ConversationRepository", _RepoStub
    )
    payload = get_analytics_overview(
        tenant_id="tenant-abc", window_days=2, db=_DummyDB()
    )
    assert payload["tenant_id"] == "tenant-abc"
    assert payload["total_conversations"] == 10
    assert payload["active_users"] == 2
    assert payload["avg_response_time_seconds"] == 3.5 * 60.0
    assert payload["window_days"] == 2
    assert payload["conversations_per_day"] == {"2024-03-01": 1, "2024-03-02": 2}


def test_overview_window_days(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client

        def count_all(self):
            return 99

        def count_active_users(self):
            return 5

        def get_average_response_time(self, **kwargs):
            return 0.0

        def get_conversations_per_day(self, **kwargs):
            last_days = kwargs.get("last_days", 5)
            return {f"2024-03-{str(i).zfill(2)}": i for i in range(1, last_days + 1)}

    monkeypatch.setattr(
        "src.services.analytics_service.ConversationRepository", _RepoStub
    )
    payload = get_analytics_overview(
        tenant_id="tenant-xyz", window_days=5, db=_DummyDB()
    )
    assert payload["tenant_id"] == "tenant-xyz"
    assert payload["total_conversations"] == 99
    assert payload["window_days"] == 5
    assert len(payload["conversations_per_day"]) == 5


def test_overview_empty_data(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client

        def count_all(self):
            return 0

        def count_active_users(self):
            return 0

        def get_average_response_time(self, **kwargs):
            return 0.0

        def get_conversations_per_day(self, **kwargs):
            return {}

    monkeypatch.setattr(
        "src.services.analytics_service.ConversationRepository", _RepoStub
    )
    payload = get_analytics_overview(
        tenant_id="tenant-empty", window_days=7, db=_DummyDB()
    )
    assert payload["total_conversations"] == 0
    assert payload["active_users"] == 0
    assert payload["conversations_per_day"] == {}


def test_overview_invalid_window(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client

        def count_all(self):
            return 1

        def count_active_users(self):
            return 1

        def get_average_response_time(self, **kwargs):
            return 1.0

        def get_conversations_per_day(self, **kwargs):
            last_days = kwargs.get("last_days", 0)
            if last_days <= 0:
                raise ValueError("last_days debe ser mayor que cero")
            return {"2024-03-01": 1}

    monkeypatch.setattr(
        "src.services.analytics_service.ConversationRepository", _RepoStub
    )
    try:
        result = get_analytics_overview(
            tenant_id="tenant-err", window_days=0, db=_DummyDB()
        )
        assert result is not None
    except ValueError as e:
        assert "last_days" in str(e)


def test_overview_integration_like(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client
            self._calls = []

        def count_all(self):
            self._calls.append("count_all")
            return 123

        def count_active_users(self):
            self._calls.append("count_active_users")
            return 8

        def get_average_response_time(self, **kwargs):
            self._calls.append("get_average_response_time")
            return 2.2

        def get_conversations_per_day(self, **kwargs):
            last_days = kwargs.get("last_days", 2)
            self._calls.append(f"get_conversations_per_day:{last_days}")
            return {"2024-03-01": 10, "2024-03-02": 20}

    repo_stub = _RepoStub(None)
    monkeypatch.setattr(
        "src.services.analytics_service.ConversationRepository",
        lambda client: repo_stub,
    )
    payload = get_analytics_overview(
        tenant_id="tenant-integration", window_days=2, db=_DummyDB()
    )
    assert payload["total_conversations"] == 123
    assert payload["active_users"] == 8
    assert payload["avg_response_time_seconds"] == 2.2 * 60.0


def test_conversations_by_day(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client

        def get_conversations_per_day(self, **kwargs):
            return {"2024-03-01": 1, "2024-03-02": 2}

    monkeypatch.setattr(
        "src.services.analytics_service.ConversationRepository", _RepoStub
    )
    payload = get_conversations_by_day(
        tenant_id="tenant-day", window_days=10, db=_DummyDB()
    )
    assert payload["data"] is not None
    assert payload["data"] == [
        {"date": "2024-03-01", "count": 1},
        {"date": "2024-03-02", "count": 2},
    ]


def test_conversations_by_week(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client

        def get_conversations_per_day(self, **kwargs):
            return {"2024-03-04": 1, "2024-03-08": 2, "2024-03-11": 3}

    monkeypatch.setattr(
        "src.services.analytics_service.ConversationRepository", _RepoStub
    )
    payload = get_conversations_by_week(tenant_id="tenant-week", weeks=2, db=_DummyDB())
    assert payload["tenant_id"] == "tenant-week"
    assert payload["window_days"] == 14
    assert payload["buckets"] == [
        {"bucket": "2024-W10", "total": 3},
        {"bucket": "2024-W11", "total": 3},
    ]


def test_conversations_by_month(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client

        def get_conversations_per_day(self, **kwargs):
            return {"2024-02-10": 2, "2024-02-20": 1, "2024-03-05": 4}

    monkeypatch.setattr(
        "src.services.analytics_service.ConversationRepository", _RepoStub
    )
    payload = get_conversations_by_month(
        tenant_id="tenant-month", months=2, db=_DummyDB()
    )
    assert payload["tenant_id"] == "tenant-month"
    assert payload["window_days"] is not None
    assert payload["buckets"] == [
        {"bucket": "2024-02", "total": 3},
        {"bucket": "2024-03", "total": 4},
    ]
