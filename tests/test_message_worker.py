"""
Claim atómico del worker y flag WORKER_ENABLED.

Contexto (ver spec/07-investigacion-mensajes-duplicados-2026-07-07.md):
el UPDATE que marcaba un job como 'processing' no verificaba que siguiera
'pending', así que dos procesos leyendo el mismo job pendiente (p.ej. un
worker local corriendo en paralelo al de Railway) podían procesarlo
ambos. `_process_job` ahora hace el claim con
`WHERE id=? AND status='pending'` y aborta sin excepción si perdió la
carrera. Además, `should_run_worker()` evita que el worker loop arranque
solo, sin acción explícita, en una máquina que no es Railway.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services import message_worker


class _FakeMessageJobsTable:
    """Simula el claim condicional WHERE id=? AND status='pending'."""

    def __init__(self, row: dict):
        self._row = row
        self._filters: dict = {}
        self._pending_update: dict | None = None

    def update(self, values):
        self._pending_update = values
        self._filters = {}
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def execute(self):
        matches = all(self._row.get(k) == v for k, v in self._filters.items())
        if not matches:
            return SimpleNamespace(data=[])
        self._row.update(self._pending_update)
        return SimpleNamespace(data=[dict(self._row)])


class _FakeSupabase:
    def __init__(self, row: dict):
        self._table = _FakeMessageJobsTable(row)

    def table(self, name):
        assert name == "message_jobs"
        return self._table


@pytest.mark.asyncio
async def test_process_job_salta_si_ya_reclamado_por_otro_proceso():
    """Otro proceso ya movió el job a 'processing' antes de este UPDATE
    (status ya no es 'pending') -- el claim atómico debe fallar sin
    lanzar excepción, sin llamar al handler, y loguear el aviso."""
    job = {"id": "job-1", "attempts": 0, "payload": {}, "tenant_id": "t1"}
    row = {"id": "job-1", "status": "processing", "attempts": 1}
    supabase = _FakeSupabase(row)

    with patch.object(
        message_worker, "_handle_with_tenant", new=AsyncMock()
    ) as mock_handle, patch.object(message_worker.logger, "warning") as mock_warning:
        await message_worker._process_job(job, supabase)

    mock_handle.assert_not_called()
    assert any(
        "ya reclamado por otro proceso" in call.args[0]
        for call in mock_warning.call_args_list
        if call.args
    )


@pytest.mark.asyncio
async def test_process_job_gana_el_claim_y_procesa():
    """Si el job seguía 'pending', el claim gana, se procesa y se marca
    'done'; el UPDATE del claim queda con la identidad del proceso."""
    job = {"id": "job-2", "attempts": 0, "payload": {"x": 1}, "tenant_id": "t1"}
    row = {"id": "job-2", "status": "pending", "attempts": 0}
    supabase = _FakeSupabase(row)

    with patch.object(
        message_worker, "_handle_with_tenant", new=AsyncMock()
    ) as mock_handle:
        await message_worker._process_job(job, supabase)

    mock_handle.assert_awaited_once_with("t1", {"x": 1})
    assert row["status"] == "done"
    assert row.get("replied_by")
    assert ":" in row["replied_by"]


@pytest.mark.asyncio
async def test_process_job_error_en_claim_no_lanza_excepcion():
    """Si el UPDATE del claim falla (excepción de red/DB), _process_job
    debe loguear y salir sin propagar la excepción."""
    job = {"id": "job-3", "attempts": 0, "payload": {}, "tenant_id": "t1"}

    class _RaisingTable:
        def update(self, _values):
            return self

        def eq(self, _col, _value):
            return self

        def execute(self):
            raise RuntimeError("boom")

    class _RaisingSupabase:
        def table(self, _name):
            return _RaisingTable()

    with patch.object(
        message_worker, "_handle_with_tenant", new=AsyncMock()
    ) as mock_handle:
        await message_worker._process_job(job, _RaisingSupabase())

    mock_handle.assert_not_called()


def _clear_worker_env():
    for var in (
        "WORKER_ENABLED",
        "RAILWAY_ENVIRONMENT_NAME",
        "RAILWAY_PROJECT_ID",
        "RAILWAY_SERVICE_ID",
    ):
        os.environ.pop(var, None)


def test_should_run_worker_default_false_sin_railway_ni_override():
    with patch.dict(os.environ, {}, clear=False):
        _clear_worker_env()
        assert message_worker.should_run_worker() is False


def test_should_run_worker_true_si_detecta_railway():
    with patch.dict(os.environ, {}, clear=False):
        _clear_worker_env()
        os.environ["RAILWAY_ENVIRONMENT_NAME"] = "production"
        assert message_worker.should_run_worker() is True


def test_should_run_worker_true_con_cualquiera_de_las_tres_variables():
    for var in ("RAILWAY_ENVIRONMENT_NAME", "RAILWAY_PROJECT_ID", "RAILWAY_SERVICE_ID"):
        with patch.dict(os.environ, {}, clear=False):
            _clear_worker_env()
            os.environ[var] = "x"
            assert message_worker.should_run_worker() is True, var


def test_should_run_worker_override_explicito_true_en_local():
    with patch.dict(os.environ, {}, clear=False):
        _clear_worker_env()
        os.environ["WORKER_ENABLED"] = "true"
        assert message_worker.should_run_worker() is True


def test_should_run_worker_override_explicito_false_en_railway():
    with patch.dict(os.environ, {}, clear=False):
        _clear_worker_env()
        os.environ["WORKER_ENABLED"] = "false"
        os.environ["RAILWAY_ENVIRONMENT_NAME"] = "production"
        assert message_worker.should_run_worker() is False
