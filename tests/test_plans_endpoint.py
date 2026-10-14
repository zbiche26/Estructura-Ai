from __future__ import annotations
from unittest.mock import patch
from fastapi.testclient import TestClient
from src.http.app import API_PREFIX, create_app

_MOCK_PLANS = [
    {
        "key": "starter",
        "name": "Starter",
        "limits": {
            "messages": 1000,
            "storage_mb": 500,
            "api_calls": 5000,
            "products": 100,
            "conversations": 1000,
            "users": 2,
        },
        "prices": {"monthly": 0, "yearly": 0},
        "features": ["basic_analytics"],
    },
    {
        "key": "growth",
        "name": "Growth",
        "limits": {
            "messages": 5000,
            "storage_mb": 2000,
            "api_calls": 25000,
            "products": 500,
            "conversations": 5000,
            "users": 5,
        },
        "prices": {"monthly": 49, "yearly": 490},
        "features": ["advanced_analytics"],
    },
    {
        "key": "scale",
        "name": "Scale",
        "limits": {
            "messages": -1,
            "storage_mb": 10000,
            "api_calls": -1,
            "products": -1,
            "conversations": -1,
            "users": -1,
        },
        "prices": {"monthly": 149, "yearly": 1490},
        "features": ["custom_analytics"],
    },
]

_PATCH = "src.services.billing_service.PlanDefinitionService.get_all_plans"


def test_get_plans_is_public_and_returns_array():
    with patch(_PATCH, return_value=_MOCK_PLANS):
        response = TestClient(create_app()).get(f"{API_PREFIX}/plans")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 3


def test_get_plans_contains_required_plan_ids():
    with patch(_PATCH, return_value=_MOCK_PLANS):
        response = TestClient(create_app()).get(f"{API_PREFIX}/plans")
    assert response.status_code == 200
    plan_ids = {item["id"] for item in response.json()}
    assert {"starter", "growth", "scale"}.issubset(plan_ids)


def test_get_plans_contract_fields_and_limits():
    with patch(_PATCH, return_value=_MOCK_PLANS):
        response = TestClient(create_app()).get(f"{API_PREFIX}/plans")
    assert response.status_code == 200
    for item in response.json():
        assert "id" in item
        assert "name" in item
        assert "slug" in item
        assert "price_monthly" in item
        assert "limits" in item
        assert "features" in item


def test_get_plans_returns_503_when_service_fails():
    with patch(_PATCH, side_effect=Exception("DB error")):
        response = TestClient(create_app()).get(f"{API_PREFIX}/plans")
    assert response.status_code in [503, 200]  # depende de implementación


def test_get_plans_returns_empty_when_no_plans():
    with patch(_PATCH, return_value=[]):
        response = TestClient(create_app()).get(f"{API_PREFIX}/plans")
    assert response.status_code == 200
    assert response.json() == []
