import pytest

pytestmark = pytest.mark.skip(
    reason="integration test — calls Supabase real for tenant lookup"
)

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from fastapi.testclient import TestClient
from src.http import deps as http_deps
import src.http.app as http_app
from src.http.app import API_PREFIX, create_app
from src.http.routers import billing as billing_router
from src.http.routers import tenants as tenants_router
from src.core.tenant_context import TenantContext

app = create_app()
client = TestClient(app)


def test_billing_summary_with_valid_authorization_header(monkeypatch):
    pass


def test_onboarding_status_with_valid_authorization_header(monkeypatch):
    pass
