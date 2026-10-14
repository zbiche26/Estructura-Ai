import datetime

import pytest

from src.services.performance_service import (
    get_agent_response_time,
    get_agent_uptime,
    get_error_logs,
    START_TIME,
)


class _DummyDB:
    @property
    def client(self):
        return object()


def test_agent_response_time_ok(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client
        def get_average_response_time(self, window_minutes: int = 60, max_pairs: int = 500):
            return 2.5
    monkeypatch.setattr(
        "src.services.performance_service.ConversationRepository",
        _RepoStub,
    )
    payload = get_agent_response_time(
        tenant_id="tenant-abc",
        window_minutes=30,
        db=_DummyDB(),
    )
    assert payload["tenant_id"] == "tenant-abc"
    assert payload["avg_response_time_seconds"] == 2.5
    assert payload["window_minutes"] == 30


def test_agent_response_time_error(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client
        def get_average_response_time(self, window_minutes: int = 60, max_pairs: int = 500):
            raise RuntimeError("boom")
    monkeypatch.setattr(
        "src.services.performance_service.ConversationRepository",
        _RepoStub,
    )
    payload = get_agent_response_time(
        tenant_id="tenant-err",
        window_minutes=15,
        db=_DummyDB(),
    )
    assert payload["avg_response_time_seconds"] is None
    assert payload["window_minutes"] == 15


def test_agent_uptime_positive():
    payload = get_agent_uptime()
    assert payload["uptime_seconds"] >= 0
    assert payload["started_at"] == START_TIME.isoformat()
    assert payload["started_source"] in {"env", "process"}
    assert isinstance(payload["process_id"], int)


def test_error_logs_ok(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client
        def get_recent_errors(self, tenant_id: str, limit: int = 50):
            return [
                {"id": "1", "message": "e1", "level": "error", "created_at": datetime.datetime.utcnow().isoformat()},
                {"id": "2", "message": "e2", "level": "error", "created_at": datetime.datetime.utcnow().isoformat()},
            ]
    monkeypatch.setattr(
        "src.services.performance_service.ErrorLogRepository",
        _RepoStub,
    )
    payload = get_error_logs(
        tenant_id="tenant-log",
        limit=5,
        db=_DummyDB(),
    )
    assert payload["tenant_id"] == "tenant-log"
    assert len(payload["items"]) == 2
    assert payload["limit"] == 5


def test_error_logs_error(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client
        def get_recent_errors(self, tenant_id: str, limit: int = 50):
            raise RuntimeError("db down")
    monkeypatch.setattr(
        "src.services.performance_service.ErrorLogRepository",
        _RepoStub,
    )
    payload = get_error_logs(
        tenant_id="tenant-log",
        limit=3,
        db=_DummyDB(),
    )
    assert payload["items"] == []
    assert payload["limit"] == 3
