import pytest
from src.services.analytics_service import (
    get_intent_distribution,
    get_top_products_consulted,
    get_top_products_sold,
)


class _DummyDB:
    @property
    def client(self):
        return object()


def test_intent_distribution_basic(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client
        def get_intent_distribution(self, **kwargs):
            return {"purchase": 5, "support": 2}
    monkeypatch.setattr("src.services.analytics_service.ConversationRepository", _RepoStub)
    payload = get_intent_distribution(tenant_id="tenant-abc", window_days=14, db=_DummyDB())
    assert payload["data"] is not None
    # window removed
    assert {b["name"]: b["total"] for b in payload["data"]} == {"purchase": 5, "support": 2}


def test_intent_distribution_empty(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client
        def get_intent_distribution(self, **kwargs):
            return {}
    monkeypatch.setattr("src.services.analytics_service.ConversationRepository", _RepoStub)
    payload = get_intent_distribution(tenant_id="tenant-empty", window_days=10, db=_DummyDB())
    assert payload["data"] == []
    assert payload["data"] == []


def test_intent_distribution_error(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client
        def get_intent_distribution(self, **kwargs):
            raise RuntimeError("boom")
    monkeypatch.setattr("src.services.analytics_service.ConversationRepository", _RepoStub)
    payload = get_intent_distribution(tenant_id="tenant-err", window_days=15, db=_DummyDB())
    assert payload["data"] == []
    # window removed


def test_top_products_consulted_basic(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client
        def get_top_consulted_products(self, **kwargs):
            return [
                {"product_id": "p1", "product_name": "Prod 1", "views": 7},
                {"product_id": "p2", "product_name": "Prod 2", "views": 5},
            ]
    monkeypatch.setattr("src.services.analytics_service.ProductRepository", _RepoStub)
    payload = get_top_products_consulted(tenant_id="tenant-prod", window_days=20, limit=5, db=_DummyDB())
    assert payload["tenant_id"] == "tenant-prod"
    assert payload["limit"] == 5
    assert len(payload["items"]) == 2
    assert payload["items"][0]["views"] == 7


def test_top_products_consulted_empty(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client
        def get_top_consulted_products(self, **kwargs):
            return []
    monkeypatch.setattr("src.services.analytics_service.ProductRepository", _RepoStub)
    payload = get_top_products_consulted(tenant_id="tenant-empty", window_days=5, limit=3, db=_DummyDB())
    assert payload["items"] == []
    assert payload["limit"] == 3


def test_top_products_sold_basic(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client
        def get_top_selling_products(self, **kwargs):
            return [
                {"product_id": "p1", "product_name": "Prod 1", "total_quantity": 10},
                {"product_id": "p3", "product_name": "Prod 3", "total_quantity": 4},
            ]
    monkeypatch.setattr("src.services.analytics_service.SaleRepository", _RepoStub)
    payload = get_top_products_sold(tenant_id="tenant-sale", window_days=45, limit=4, db=_DummyDB())
    assert payload["tenant_id"] == "tenant-sale"
    assert payload["items"][0]["total_quantity"] == 10
    assert payload["limit"] == 4


def test_top_products_sold_error(monkeypatch):
    class _RepoStub:
        def __init__(self, client):
            self.client = client
        def get_top_selling_products(self, **kwargs):
            raise RuntimeError("db down")
    monkeypatch.setattr("src.services.analytics_service.SaleRepository", _RepoStub)
    payload = get_top_products_sold(tenant_id="tenant-err", window_days=7, limit=2, db=_DummyDB())
    assert payload["items"] == []
    # window field removed
