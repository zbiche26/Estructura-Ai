# -*- coding: utf-8 -*-
"""
test_validator.py - Tests del ProductValidator 
=========================================================
Cubre:
  - Validación de columnas requeridas
  - Validación de nombre (vacío, longitud)
  - Validación de precio (negativo, cero, no numérico)
  - Validación de stock (negativo, no entero)
  - Detección de SKUs duplicados
  - Validación de categoría
  - ValidationResult helpers
  - ValidatorConfig personalizada

Ejecutar: pytest tests/plugins/test_validator.py -v
"""

import pytest

from src.plugins.excel_import.validator import (
    ProductValidator,
    ValidationResult,
    ValidatorConfig,
    RowError,
)


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def validator() -> ProductValidator:
    return ProductValidator()


@pytest.fixture
def producto_valido() -> dict:
    return {
        "name":     "Camara Domo HD",
        "price":    "180000",
        "stock":    "25",
        "sku":      "CAM-001",
        "category": "Seguridad",
    }


@pytest.fixture
def productos_validos() -> list:
    return [
        {"name": "Camara Domo",   "price": "180000", "stock": "25", "sku": "CAM-001"},
        {"name": "Camara Bullet", "price": "320000", "stock": "12", "sku": "CAM-002"},
        {"name": "Camara PTZ",    "price": "480000", "stock": "8",  "sku": "CAM-003"},
    ]


# ── Tests: ValidationResult ──────────────────────────────────

class TestValidationResult:

    def test_is_valid_sin_invalidas(self):
        result = ValidationResult(valid_rows=[{"name": "x"}])
        assert result.is_valid is True

    def test_is_valid_false_con_invalidas(self):
        result = ValidationResult(invalid_rows=[{"name": "x"}])
        assert result.is_valid is False

    def test_valid_count(self):
        result = ValidationResult(valid_rows=[{}, {}, {}])
        assert result.valid_count == 3

    def test_invalid_count(self):
        result = ValidationResult(invalid_rows=[{}, {}])
        assert result.invalid_count == 2

    def test_total(self):
        result = ValidationResult(
            valid_rows=[{}, {}],
            invalid_rows=[{}]
        )
        assert result.total == 3

    def test_errors_for_row(self):
        errors = [
            RowError(row=0, field="name", value="", message="vacío"),
            RowError(row=1, field="price", value="-1", message="negativo"),
            RowError(row=0, field="price", value="abc", message="no numérico"),
        ]
        result = ValidationResult(errors=errors)
        assert len(result.errors_for_row(0)) == 2
        assert len(result.errors_for_row(1)) == 1

    def test_summary_formato(self):
        result = ValidationResult(
            valid_rows=[{}, {}],
            invalid_rows=[{}],
            errors=[RowError(0, "f", None, "msg")]
        )
        summary = result.summary()
        assert "2" in summary
        assert "1" in summary


# ── Tests: columnas requeridas ────────────────────────────────

class TestColumnasRequeridas:

    def test_sin_columna_name_retorna_error(self, validator):
        rows = [{"price": "100"}]
        result = validator.validate(rows)
        assert not result.is_valid
        assert any(e.field == "name" for e in result.errors)

    def test_sin_columna_price_retorna_error(self, validator):
        rows = [{"name": "Producto"}]
        result = validator.validate(rows)
        assert not result.is_valid
        assert any(e.field == "price" for e in result.errors)

    def test_columnas_presentes_no_genera_error(self, validator, producto_valido):
        result = validator.validate([producto_valido])
        assert result.is_valid

    def test_validate_columns_retorna_faltantes(self, validator):
        faltantes = validator.validate_columns(["name", "stock"])
        assert "price" in faltantes

    def test_validate_columns_ok(self, validator):
        faltantes = validator.validate_columns(["name", "price", "stock"])
        assert faltantes == []

    def test_lista_vacia_retorna_warning(self, validator):
        result = validator.validate([])
        assert result.is_valid
        assert len(result.warnings) > 0


# ── Tests: validación de nombre ───────────────────────────────

class TestValidacionNombre:

    def test_nombre_vacio_invalido(self, validator):
        rows = [{"name": "", "price": "100"}]
        result = validator.validate(rows)
        assert not result.is_valid
        assert any(e.field == "name" for e in result.errors)

    def test_nombre_none_invalido(self, validator):
        rows = [{"name": None, "price": "100"}]
        result = validator.validate(rows)
        assert not result.is_valid

    def test_nombre_espacios_invalido(self, validator):
        rows = [{"name": "   ", "price": "100"}]
        result = validator.validate(rows)
        assert not result.is_valid

    def test_nombre_muy_largo_invalido(self):
        config    = ValidatorConfig(max_name_length=10)
        validator = ProductValidator(config)
        rows      = [{"name": "Nombre muy largo que supera el limite", "price": "100"}]
        result    = validator.validate(rows)
        assert not result.is_valid
        assert any("largo" in e.message for e in result.errors)

    def test_nombre_valido_pasa(self, validator):
        rows = [{"name": "Camara Domo", "price": "180000"}]
        result = validator.validate(rows)
        assert result.is_valid


# ── Tests: validación de precio ───────────────────────────────

class TestValidacionPrecio:

    def test_precio_negativo_invalido(self, validator):
        rows = [{"name": "Producto", "price": "-100"}]
        result = validator.validate(rows)
        assert not result.is_valid
        assert any("negativo" in e.message for e in result.errors)

    def test_precio_cero_invalido_por_defecto(self, validator):
        rows = [{"name": "Producto", "price": "0"}]
        result = validator.validate(rows)
        assert not result.is_valid
        assert any("mayor que 0" in e.message for e in result.errors)

    def test_precio_cero_valido_con_config(self):
        config    = ValidatorConfig(allow_zero_price=True)
        validator = ProductValidator(config)
        rows      = [{"name": "Producto", "price": "0"}]
        result    = validator.validate(rows)
        assert result.is_valid

    def test_precio_no_numerico_invalido(self, validator):
        rows = [{"name": "Producto", "price": "abc"}]
        result = validator.validate(rows)
        assert not result.is_valid
        assert any("numérico" in e.message for e in result.errors)

    def test_precio_vacio_invalido(self, validator):
        rows = [{"name": "Producto", "price": ""}]
        result = validator.validate(rows)
        assert not result.is_valid

    def test_precio_valido_entero(self, validator):
        rows = [{"name": "Producto", "price": "180000"}]
        result = validator.validate(rows)
        assert result.is_valid

    def test_precio_valido_decimal(self, validator):
        rows = [{"name": "Producto", "price": "99.99"}]
        result = validator.validate(rows)
        assert result.is_valid

    def test_precio_maximo_invalido(self):
        config    = ValidatorConfig(max_price=100.0)
        validator = ProductValidator(config)
        rows      = [{"name": "Producto", "price": "999"}]
        result    = validator.validate(rows)
        assert not result.is_valid
        assert any("máximo" in e.message for e in result.errors)


# ── Tests: validación de stock ────────────────────────────────

class TestValidacionStock:

    def test_stock_negativo_invalido(self, validator):
        rows = [{"name": "Producto", "price": "100", "stock": "-5"}]
        result = validator.validate(rows)
        assert not result.is_valid
        assert any(e.field == "stock" for e in result.errors)

    def test_stock_no_entero_invalido(self, validator):
        rows = [{"name": "Producto", "price": "100", "stock": "abc"}]
        result = validator.validate(rows)
        assert not result.is_valid

    def test_stock_cero_valido(self, validator):
        rows = [{"name": "Producto", "price": "100", "stock": "0"}]
        result = validator.validate(rows)
        assert result.is_valid

    def test_stock_ausente_valido(self, validator):
        """Stock es opcional."""
        rows = [{"name": "Producto", "price": "100"}]
        result = validator.validate(rows)
        assert result.is_valid

    def test_stock_valido(self, validator):
        rows = [{"name": "Producto", "price": "100", "stock": "25"}]
        result = validator.validate(rows)
        assert result.is_valid


# ── Tests: validación de SKU ──────────────────────────────────

class TestValidacionSKU:

    def test_sku_duplicado_invalido(self, validator):
        rows = [
            {"name": "Producto A", "price": "100", "sku": "SKU-001"},
            {"name": "Producto B", "price": "200", "sku": "SKU-001"},
        ]
        result = validator.validate(rows)
        assert not result.is_valid
        assert any("duplicado" in e.message for e in result.errors)

    def test_sku_duplicado_case_insensitive(self, validator):
        rows = [
            {"name": "Producto A", "price": "100", "sku": "sku-001"},
            {"name": "Producto B", "price": "200", "sku": "SKU-001"},
        ]
        result = validator.validate(rows)
        assert not result.is_valid

    def test_sku_duplicado_permitido_con_config(self):
        config    = ValidatorConfig(allow_duplicates=True)
        validator = ProductValidator(config)
        rows      = [
            {"name": "Producto A", "price": "100", "sku": "SKU-001"},
            {"name": "Producto B", "price": "200", "sku": "SKU-001"},
        ]
        result = validator.validate(rows)
        assert result.is_valid

    def test_sin_sku_es_valido(self, validator):
        rows = [{"name": "Producto", "price": "100"}]
        result = validator.validate(rows)
        assert result.is_valid

    def test_skus_unicos_validos(self, validator, productos_validos):
        result = validator.validate(productos_validos)
        assert result.is_valid


# ── Tests: validación de categoría ───────────────────────────

class TestValidacionCategoria:

    def test_categoria_muy_larga_invalida(self, validator):
        rows = [{"name": "Producto", "price": "100", "category": "x" * 101}]
        result = validator.validate(rows)
        assert not result.is_valid
        assert any(e.field == "category" for e in result.errors)

    def test_categoria_ausente_valida(self, validator):
        rows = [{"name": "Producto", "price": "100"}]
        result = validator.validate(rows)
        assert result.is_valid

    def test_categoria_valida(self, validator):
        rows = [{"name": "Producto", "price": "100", "category": "Seguridad"}]
        result = validator.validate(rows)
        assert result.is_valid


# ── Tests: múltiples filas ────────────────────────────────────

class TestMultiplesFilas:

    def test_mezcla_validas_invalidas(self, validator):
        rows = [
            {"name": "Valido",   "price": "100"},
            {"name": "",         "price": "200"},   # inválido
            {"name": "Valido 2", "price": "300"},
            {"name": "Valido 3", "price": "-10"},   # inválido
        ]
        result = validator.validate(rows)
        assert result.valid_count == 2
        assert result.invalid_count == 2

    def test_todos_validos(self, validator, productos_validos):
        result = validator.validate(productos_validos)
        assert result.is_valid
        assert result.valid_count == 3

    def test_todos_invalidos(self, validator):
        rows = [
            {"name": "", "price": "abc"},
            {"name": "", "price": "-1"},
        ]
        result = validator.validate(rows)
        assert result.invalid_count == 2
        assert result.valid_count == 0