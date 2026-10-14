# -*- coding: utf-8 -*-
"""
test_importer.py - Tests del ProductImporter 
=======================================================
Usa mocks para Supabase, OpenAI y Qdrant — sin conexiones reales.

Cubre:
  - Importación exitosa en dry_run
  - Nombre de colección por tenant
  - Multi-tenant aislamiento
  - Rollback en caso de error
  - Duplicados omitidos
  - ImportResult helpers
  - Procesamiento en lotes
  - Construcción de texto para embedding

Ejecutar: pytest tests/plugins/test_importer.py -v
"""

import pytest
from unittest.mock import MagicMock, patch, call

from src.plugins.excel_import.importer import (
    ProductImporter,
    ImportResult,
    ImporterConfig,
)


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def importer_dry() -> ProductImporter:
    """Importador en modo dry_run — sin BD real."""
    return ProductImporter(dry_run=True)


@pytest.fixture
def config_batch2() -> ImporterConfig:
    """Config con batch_size=2 para testear lotes."""
    return ImporterConfig(batch_size=2, generate_embeddings=False)


@pytest.fixture
def productos_validos() -> list:
    return [
        {"name": "Camara Domo",   "price": "180000", "stock": "25", "sku": "CAM-001"},
        {"name": "Camara Bullet", "price": "320000", "stock": "12", "sku": "CAM-002"},
        {"name": "Camara PTZ",    "price": "480000", "stock": "8",  "sku": "CAM-003"},
    ]


@pytest.fixture
def mock_supabase() -> MagicMock:
    """Mock de cliente Supabase."""
    client = MagicMock()
    # Simular respuesta exitosa de insert
    client.table.return_value.insert.return_value.execute.return_value \
        .data = [{"id": "test-uuid-123"}]
    # Simular que no hay duplicados
    client.table.return_value.select.return_value.eq.return_value \
        .eq.return_value.execute.return_value.data = []
    return client


@pytest.fixture
def mock_openai() -> MagicMock:
    """Mock de cliente OpenAI."""
    client = MagicMock()
    client.embeddings.create.return_value.data = [
        MagicMock(embedding=[0.1] * 1536)
    ]
    return client


@pytest.fixture
def mock_qdrant() -> MagicMock:
    """Mock de cliente Qdrant."""
    client = MagicMock()
    client.get_collections.return_value.collections = []
    return client


# ── Tests: ImportResult ───────────────────────────────────────

class TestImportResult:

    def test_is_success_sin_errores(self):
        result = ImportResult(saved_count=3)
        assert result.is_success is True

    def test_is_success_false_con_rollback(self):
        result = ImportResult(rolled_back=True)
        assert result.is_success is False

    def test_is_success_false_con_fallidos(self):
        result = ImportResult(failed_count=1)
        assert result.is_success is False

    def test_total_processed(self):
        result = ImportResult(saved_count=2, failed_count=1, skipped_count=1)
        assert result.total_processed == 4

    def test_success_rate_cien(self):
        result = ImportResult(saved_count=3)
        assert result.success_rate == 100.0

    def test_success_rate_cero_sin_datos(self):
        result = ImportResult()
        assert result.success_rate == 0.0

    def test_success_rate_parcial(self):
        result = ImportResult(saved_count=3, failed_count=1)
        assert result.success_rate == 75.0

    def test_summary_contiene_tenant(self):
        result = ImportResult(saved_count=3, tenant_id="cliente_a")
        assert "cliente_a" in result.summary()


# ── Tests: colección Qdrant ───────────────────────────────────

class TestCollectionName:

    def test_formato_basico(self, importer_dry):
        name = importer_dry.get_collection_name("cliente_a")
        assert name == "cliente_a_productos"

    def test_guiones_a_underscores(self, importer_dry):
        name = importer_dry.get_collection_name("cliente-abc-123")
        assert name == "cliente_abc_123_productos"

    def test_mayusculas_a_minusculas(self, importer_dry):
        name = importer_dry.get_collection_name("ClienteA")
        assert name == "clientea_productos"

    def test_sufijo_personalizado(self):
        config   = ImporterConfig(qdrant_collection_suffix="catalogo")
        importer = ProductImporter(config=config, dry_run=True)
        name     = importer.get_collection_name("tenant_1")
        assert name == "tenant_1_catalogo"

    def test_tenants_diferentes_colecciones_diferentes(self, importer_dry):
        col_a = importer_dry.get_collection_name("cliente_a")
        col_b = importer_dry.get_collection_name("cliente_b")
        assert col_a != col_b


# ── Tests: dry_run ────────────────────────────────────────────

class TestDryRun:

    def test_dry_run_retorna_import_result(self, importer_dry, productos_validos):
        result = importer_dry.import_products(productos_validos, "tenant_test")
        assert isinstance(result, ImportResult)

    def test_dry_run_cuenta_productos(self, importer_dry, productos_validos):
        result = importer_dry.import_products(productos_validos, "tenant_test")
        assert result.saved_count == 3

    def test_dry_run_sin_fallos(self, importer_dry, productos_validos):
        result = importer_dry.import_products(productos_validos, "tenant_test")
        assert result.failed_count == 0
        assert result.is_success

    def test_dry_run_tenant_en_resultado(self, importer_dry, productos_validos):
        result = importer_dry.import_products(productos_validos, "cliente_x")
        assert result.tenant_id == "cliente_x"

    def test_dry_run_coleccion_en_resultado(self, importer_dry, productos_validos):
        result = importer_dry.import_products(productos_validos, "cliente_x")
        assert result.collection == "cliente_x_productos"

    def test_dry_run_lista_vacia(self, importer_dry):
        result = importer_dry.import_products([], "tenant_test")
        assert result.saved_count == 0
        assert result.is_success

    def test_tenant_vacio_lanza_error(self, importer_dry, productos_validos):
        with pytest.raises(ValueError, match="tenant_id"):
            importer_dry.import_products(productos_validos, "")

    def test_dry_run_mide_duracion(self, importer_dry, productos_validos):
        result = importer_dry.import_products(productos_validos, "tenant_test")
        assert result.duration_ms >= 0


# ── Tests: procesamiento en lotes ────────────────────────────

class TestLotes:

    def test_lote_mas_pequeno_que_total(self, config_batch2, productos_validos):
        importer = ProductImporter(config=config_batch2, dry_run=True)
        result   = importer.import_products(productos_validos, "tenant_test")
        # 3 productos en lotes de 2 = 2 lotes, todos guardados
        assert result.saved_count == 3

    def test_un_producto_un_lote(self, importer_dry):
        rows   = [{"name": "Solo uno", "price": "100"}]
        result = importer_dry.import_products(rows, "tenant_test")
        assert result.saved_count == 1


# ── Tests: con Supabase mock ──────────────────────────────────

class TestConSupabase:

    def test_guarda_en_supabase(self, mock_supabase, productos_validos):
        config   = ImporterConfig(generate_embeddings=False)
        importer = ProductImporter(
            supabase_client=mock_supabase,
            config=config,
        )
        result = importer.import_products(productos_validos, "tenant_a")
        assert result.saved_count == 3
        # Verificar que se llamó insert por cada producto
        assert mock_supabase.table.call_count == len(productos_validos) * 2  # select + insert

    def test_producto_tiene_tenant_id(self, importer_dry):
        """_prepare_product agrega tenant_id correctamente."""
        row     = {"name": "Camara", "price": "100", "stock": "5"}
        product = importer_dry._prepare_product(row, "mi_tenant")
        assert product["tenant_id"] == "mi_tenant"

    def test_producto_tiene_uuid(self, importer_dry):
        """_prepare_product genera UUID único."""
        row      = {"name": "Camara", "price": "100"}
        product1 = importer_dry._prepare_product(row, "tenant")
        product2 = importer_dry._prepare_product(row, "tenant")
        assert product1["id"] != product2["id"]

    def test_precio_convertido_a_float(self, importer_dry):
        row     = {"name": "Camara", "price": "180.000"}
        product = importer_dry._prepare_product(row, "tenant")
        assert isinstance(product["price"], float)

    def test_stock_convertido_a_int(self, importer_dry):
        row     = {"name": "Camara", "price": "100", "stock": "25"}
        product = importer_dry._prepare_product(row, "tenant")
        assert isinstance(product["stock"], int)
        assert product["stock"] == 25


# ── Tests: duplicados ─────────────────────────────────────────

class TestDuplicados:

    def test_skip_duplicates_por_defecto(self, mock_supabase):
        """Cuando el SKU ya existe en Supabase, se omite."""
        # Simular que el SKU ya existe
        mock_supabase.table.return_value.select.return_value \
            .eq.return_value.eq.return_value.execute.return_value \
            .data = [{"id": "existing"}]

        config   = ImporterConfig(
            skip_duplicates=True,
            generate_embeddings=False
        )
        importer = ProductImporter(
            supabase_client=mock_supabase,
            config=config,
        )
        rows   = [{"name": "Camara", "price": "100", "sku": "CAM-001"}]
        result = importer.import_products(rows, "tenant_a")

        assert result.skipped_count == 1
        assert result.saved_count   == 0

    def test_sin_sku_no_verifica_duplicado(self, mock_supabase):
        """Productos sin SKU no verifican duplicados."""
        config   = ImporterConfig(
            skip_duplicates=True,
            generate_embeddings=False,
        )
        importer = ProductImporter(
            supabase_client=mock_supabase,
            config=config,
        )
        rows   = [{"name": "Camara sin SKU", "price": "100"}]
        result = importer.import_products(rows, "tenant_a")
        assert result.saved_count == 1


# ── Tests: rollback ───────────────────────────────────────────

class TestRollback:

    def test_rollback_en_dry_run(self, importer_dry):
        """dry_run no lanza excepción en rollback."""
        importer_dry._rollback(["id1", "id2"], "tenant", "coleccion")

    def test_rollback_activado_en_error(self, mock_supabase):
        """Si falla un producto y rollback_on_error=True, se revierte."""
        # Primer insert falla
        mock_supabase.table.return_value.insert.return_value \
            .execute.side_effect = Exception("DB Error")
        # select retorna vacío (no duplicado)
        mock_supabase.table.return_value.select.return_value \
            .eq.return_value.eq.return_value.execute.return_value.data = []

        config   = ImporterConfig(
            rollback_on_error=True,
            generate_embeddings=False,
        )
        importer = ProductImporter(
            supabase_client=mock_supabase,
            config=config,
        )
        rows   = [{"name": "Camara", "price": "100"}]
        result = importer.import_products(rows, "tenant_a")

        assert result.rolled_back  is True
        assert result.saved_count  == 0


# ── Tests: embedding text ─────────────────────────────────────

class TestEmbeddingText:

    def test_incluye_nombre(self, importer_dry):
        product = {"name": "Camara Domo", "price": 180000, "stock": 25}
        text    = importer_dry._build_embedding_text(product)
        assert "Camara Domo" in text

    def test_incluye_precio(self, importer_dry):
        product = {"name": "X", "price": 180000, "stock": 0}
        text    = importer_dry._build_embedding_text(product)
        assert "180" in text

    def test_incluye_categoria_si_existe(self, importer_dry):
        product = {
            "name": "X", "price": 100, "stock": 0,
            "category": "Seguridad"
        }
        text = importer_dry._build_embedding_text(product)
        assert "Seguridad" in text

    def test_incluye_descripcion_si_existe(self, importer_dry):
        product = {
            "name": "X", "price": 100, "stock": 0,
            "description": "Cámara de alta resolución"
        }
        text = importer_dry._build_embedding_text(product)
        assert "alta resolución" in text

    def test_uuid_to_int_consistente(self, importer_dry):
        uid = "550e8400-e29b-41d4-a716-446655440000"
        assert importer_dry._uuid_to_int(uid) == importer_dry._uuid_to_int(uid)

    def test_uuid_to_int_positivo(self, importer_dry):
        import uuid as uuid_mod
        uid = str(uuid_mod.uuid4())
        assert importer_dry._uuid_to_int(uid) >= 0