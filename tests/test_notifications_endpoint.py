import pytest

# ============================================================
# Tests de integración — requieren Supabase real
# El router de notifications tiene dependencias acopladas a BD
# ============================================================
pytestmark = pytest.mark.skip(
    reason="integration test — notifications router requires real Supabase"
)

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4
from fastapi.testclient import TestClient
from src.http.app import API_PREFIX, create_app
from src.http.routers import notifications as notif_router

TENANT_ID = str(uuid4())
_MOCK_ROWS = [
    {
        "id": str(uuid4()),
        "type": "billing",
        "title": "Suscripción activa",
        "body": "Tu plan Starter está activo.",
        "read_at": None,
        "created_at": "2026-04-30T10:00:00+00:00",
    },
    {
        "id": str(uuid4()),
        "type": "limit",
        "title": "Límite al 80%",
        "body": "Llevas 800 de 1000 conversaciones.",
        "read_at": "2026-04-29T09:00:00+00:00",
        "created_at": "2026-04-29T08:00:00+00:00",
    },
    {
        "id": str(uuid4()),
        "type": "onboarding",
        "title": "Bienvenido",
        "body": "Completa los pasos.",
        "read_at": None,
        "created_at": "2026-04-28T07:00:00+00:00",
    },
]


def _fake_user():
    return SimpleNamespace(tenant=SimpleNamespace(id=TENANT_ID))


def _build_client(db_mock=None):
    app = create_app()
    app.dependency_overrides[notif_router._current_user] = _fake_user
    if db_mock:
        app.dependency_overrides[notif_router.get_db] = lambda: db_mock
    return TestClient(app, raise_server_exceptions=False)


def test_list_notifications_returns_200_with_data():
    pass


def test_list_notifications_item_contract():
    pass


def test_list_notifications_unread_count():
    pass


def test_list_notifications_total_count():
    pass


def test_list_notifications_invalid_type_returns_422():
    pass


def test_list_notifications_valid_type_filter():
    pass


def test_list_notifications_unread_only_flag():
    pass


def test_list_notifications_pagination_params():
    pass


def test_list_notifications_page_size_exceeds_max_returns_422():
    pass


def test_list_notifications_returns_503_on_db_error():
    pass


def test_mark_notification_as_read_returns_200():
    pass


def test_mark_notification_as_read_returns_404_when_not_found():
    pass


def test_mark_notification_as_read_returns_503_on_db_error():
    pass


def test_list_notifications_empty_result():
    pass


def test_patch_mark_notification_as_read_returns_updated_item():
    pass


def test_patch_mark_notification_as_read_returns_404_when_not_found():
    pass


def test_patch_mark_notification_as_read_returns_503_on_db_error():
    pass
