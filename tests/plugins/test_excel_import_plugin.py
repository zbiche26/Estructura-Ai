# -*- coding: utf-8 -*-
"""
test_excel_import_plugin.py - Tests del Plugin Coordinador 
=====================================================================
Cubre:
  - Ciclo de vida (initialize, start, stop)
  - Flujo completo con dry_run
  - Eventos emitidos
  - preview_file y get_columns
  - validate_file (sin guardar)
  - Resolución de tenant_id
  - ImportSummary helpers

Ejecutar: pytest tests/plugins/test_excel_import_plugin.py -v
"""

import csv
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.core.event_bus import EventBus
from src.core.tenant_context import TenantContext
from src.plugins.excel_import.plugin import ExcelImportPlugin, ImportSummary


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def csv_productos(tmp_path: Path) -> str:
    """CSV con 3 productos válidos."""
    archivo = tmp_path / "productos.csv"
    archivo.write_text(
        "name,price,stock,sku\n"
        "Camara Domo,180000,25,CAM-001\n"
        "Camara Bullet,320000,12,CAM-002\n"
        "Camara PTZ,480000,8,CAM-003\n",
        encoding="utf-8",
    )
    return str(archivo)


@pytest.fixture
def csv_con_invalidos(tmp_path: Path) -> str:
    """CSV con mezcla de válidos e inválidos."""
    archivo = tmp_path / "mixto.csv"
    archivo.write_text(
        "name,price,stock\n"
        "Camara Domo,180000,25\n"
        ",320000,12\n"          # nombre vacío → inválido
        "Camara PTZ,abc,8\n"    # precio no numérico → inválido
        "Kit DVR,950000,5\n",
        encoding="utf-8",
    )
    return str(archivo)


@pytest.fixture
def csv_vacio(tmp_path: Path) -> str:
    """CSV con encabezados pero sin datos."""
    archivo = tmp_path / "vacio.csv"
    archivo.write_text("name,price,stock\n", encoding="utf-8")
    return str(archivo)


@pytest.fixture
def plugin_dry(event_bus) -> ExcelImportPlugin:
    """Plugin inicializado en dry_run."""
    plugin = ExcelImportPlugin(event_bus=event_bus)
    plugin.initialize(config={"dry_run": True, "generate_embeddings": False})
    plugin.start()
    return plugin


@pytest.fixture
def tenant_context() -> TenantContext:
    ctx = MagicMock(spec=TenantContext)
    ctx.tenant_id = "tenant_ctx_123"
    return ctx


# ── Tests: ImportSummary ──────────────────────────────────────

class TestImportSummary:

    def test_is_success_con_guardados(self):
        s = ImportSummary(saved_count=3)
        assert s.is_success is True

    def test_is_success_false_sin_guardados(self):
        s = ImportSummary(saved_count=0)
        assert s.is_success is False

    def test_is_success_false_con_rollback(self):
        s = ImportSummary(saved_count=3, rolled_back=True)
        assert s.is_success is False

    def test_total_errors(self):
        s = ImportSummary(
            parse_errors=["e1"],
            validation_errors=["e2", "e3"],
            import_errors=["e4"],
        )
        assert s.total_errors == 4

    def test_summary_contiene_filename(self):
        s = ImportSummary(file_path="ruta/productos.csv", tenant_id="t1")
        assert "productos.csv" in s.summary()

    def test_summary_contiene_tenant(self):
        s = ImportSummary(file_path="x.csv", tenant_id="mi_tenant")
        assert "mi_tenant" in s.summary()


# ── Tests: Ciclo de vida ──────────────────────────────────────

class TestLifecycle:

    def test_initialize_exitoso(self, event_bus):
        plugin = ExcelImportPlugin(event_bus=event_bus)
        result = plugin.initialize(config={"dry_run": True})
        assert result is True

    def test_start_exitoso(self, event_bus):
        plugin = ExcelImportPlugin(event_bus=event_bus)
        plugin.initialize(config={"dry_run": True})
        result = plugin.start()
        assert result is True
        assert plugin.is_running

    def test_stop_exitoso(self, plugin_dry):
        result = plugin_dry.stop()
        assert result is True
        assert not plugin_dry.is_running

    def test_import_sin_start_lanza_error(self, event_bus, csv_productos):
        plugin = ExcelImportPlugin(event_bus=event_bus)
        plugin.initialize(config={"dry_run": True})
        # No llamamos start()
        with pytest.raises(RuntimeError, match="no está corriendo"):
            plugin.import_file(csv_productos, tenant_id="t1")

    def test_metadata_correcta(self, plugin_dry):
        assert plugin_dry.metadata.name    == "excel_import"
        assert plugin_dry.metadata.version == "1.0.0"


# ── Tests: import_file ────────────────────────────────────────

class TestImportFile:

    def test_import_retorna_summary(self, plugin_dry, csv_productos):
        result = plugin_dry.import_file(csv_productos, tenant_id="tenant_a")
        assert isinstance(result, ImportSummary)

    def test_import_cuenta_filas_leidas(self, plugin_dry, csv_productos):
        result = plugin_dry.import_file(csv_productos, tenant_id="tenant_a")
        assert result.total_rows == 3

    def test_import_cuenta_guardados(self, plugin_dry, csv_productos):
        result = plugin_dry.import_file(csv_productos, tenant_id="tenant_a")
        assert result.saved_count == 3

    def test_import_tenant_en_summary(self, plugin_dry, csv_productos):
        result = plugin_dry.import_file(csv_productos, tenant_id="tenant_xyz")
        assert result.tenant_id == "tenant_xyz"

    def test_import_con_invalidos(self, plugin_dry, csv_con_invalidos):
        result = plugin_dry.import_file(csv_con_invalidos, tenant_id="t1")
        assert result.valid_rows   == 2
        assert result.invalid_rows == 2
        assert result.saved_count  == 2

    def test_import_archivo_vacio(self, plugin_dry, csv_vacio):
        result = plugin_dry.import_file(csv_vacio, tenant_id="t1")
        assert result.saved_count == 0
        assert result.total_rows  == 0

    def test_import_archivo_no_existe(self, plugin_dry):
        with pytest.raises(FileNotFoundError):
            plugin_dry.import_file("no_existe.csv", tenant_id="t1")

    def test_import_con_column_mapping(self, event_bus, tmp_path):
        """Importar Excel con columnas del cliente mapeadas a nombre estándar."""
        archivo = tmp_path / "cliente.csv"
        archivo.write_text(
            "Nombre Producto,Valor,Cantidad\n"
            "Camara Domo,180000,25\n",
            encoding="utf-8",
        )
        plugin = ExcelImportPlugin(event_bus=event_bus)
        plugin.initialize(config={"dry_run": True})
        plugin.start()

        result = plugin.import_file(
            str(archivo),
            tenant_id      = "t1",
            column_mapping = {
                "Nombre Producto": "name",
                "Valor":           "price",
                "Cantidad":        "stock",
            },
        )
        assert result.saved_count == 1


# ── Tests: tenant_id ──────────────────────────────────────────

class TestTenantResolution:

    def test_tenant_desde_parametro(self, plugin_dry, csv_productos):
        result = plugin_dry.import_file(csv_productos, tenant_id="param_tenant")
        assert result.tenant_id == "param_tenant"

    def test_tenant_desde_context(self, event_bus, csv_productos, tenant_context):
        plugin = ExcelImportPlugin(
            event_bus      = event_bus,
            tenant_context = tenant_context,
        )
        plugin.initialize(config={"dry_run": True})
        plugin.start()

        result = plugin.import_file(csv_productos)   # sin tenant_id explícito
        assert result.tenant_id == "tenant_ctx_123"

    def test_sin_tenant_lanza_error(self, event_bus, csv_productos):
        plugin = ExcelImportPlugin(event_bus=event_bus)
        plugin.initialize(config={"dry_run": True})
        plugin.start()

        with pytest.raises(ValueError, match="tenant_id requerido"):
            plugin.import_file(csv_productos)


# ── Tests: eventos emitidos ───────────────────────────────────

class TestEventos:

    def test_emite_evento_started(self, event_bus, csv_productos):
        eventos = []
        event_bus.subscribe("excel_import.started", lambda d: eventos.append(d))

        plugin = ExcelImportPlugin(event_bus=event_bus)
        plugin.initialize(config={"dry_run": True})
        plugin.start()
        plugin.import_file(csv_productos, tenant_id="t1")

        assert len(eventos) == 1
        # El EventBus envía un objeto Event — extraer data
        evento = eventos[0]
        data = evento.data if hasattr(evento, "data") else evento
        assert data["tenant_id"] == "t1"

    def test_emite_evento_completed(self, event_bus, csv_productos):
        eventos = []
        event_bus.subscribe("excel_import.completed", lambda d: eventos.append(d))

        plugin = ExcelImportPlugin(event_bus=event_bus)
        plugin.initialize(config={"dry_run": True})
        plugin.start()
        plugin.import_file(csv_productos, tenant_id="t1")

        assert len(eventos) == 1
        evento = eventos[0]
        data = evento.data if hasattr(evento, "data") else evento
        assert data["saved_count"] == 3

    def test_emite_evento_parsed(self, event_bus, csv_productos):
        eventos = []
        event_bus.subscribe("excel_import.parsed", lambda d: eventos.append(d))

        plugin = ExcelImportPlugin(event_bus=event_bus)
        plugin.initialize(config={"dry_run": True})
        plugin.start()
        plugin.import_file(csv_productos, tenant_id="t1")

        assert len(eventos) == 1
        evento = eventos[0]
        data = evento.data if hasattr(evento, "data") else evento
        assert data["total_rows"] == 3


# ── Tests: preview y validate ─────────────────────────────────

class TestPreviewYValidate:

    def test_preview_retorna_columnas(self, plugin_dry, csv_productos):
        result = plugin_dry.preview_file(csv_productos, rows=2)
        assert "columns" in result
        assert "name" in result["columns"]

    def test_preview_limita_filas(self, plugin_dry, csv_productos):
        result = plugin_dry.preview_file(csv_productos, rows=2)
        assert result["total"] == 2

    def test_get_columns(self, plugin_dry, csv_productos):
        cols = plugin_dry.get_columns(csv_productos)
        assert "name"  in cols
        assert "price" in cols
        assert "stock" in cols

    def test_validate_file_valido(self, plugin_dry, csv_productos):
        result = plugin_dry.validate_file(csv_productos)
        assert result["is_valid"]     is True
        assert result["valid_rows"]   == 3
        assert result["invalid_rows"] == 0

    def test_validate_file_con_errores(self, plugin_dry, csv_con_invalidos):
        result = plugin_dry.validate_file(csv_con_invalidos)
        assert result["is_valid"]     is False
        assert result["invalid_rows"] == 2
        assert len(result["errors"])  > 0