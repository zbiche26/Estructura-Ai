# -*- coding: utf-8 -*-
"""
test_parser.py - Tests del ExcelParser 
=================================================
Cubre:
  - Detección de formato
  - Parseo de CSV
  - Parseo de Excel
  - Configuración (skip_rows, max_rows, mapping)
  - Manejo de errores
  - Preview y get_columns

Ejecutar: pytest tests/plugins/test_parser.py -v
"""

import csv
import os
import tempfile
from pathlib import Path

import pytest

from src.plugins.excel_import.parser import (
    ExcelParser,
    ParseResult,
    ParserConfig,
    SUPPORTED_FORMATS,
)


# ── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def parser() -> ExcelParser:
    return ExcelParser()


@pytest.fixture
def csv_simple(tmp_path: Path) -> str:
    """CSV simple con 3 productos."""
    archivo = tmp_path / "productos.csv"
    archivo.write_text(
        "name,price,stock\n"
        "Camara Domo,180000,25\n"
        "Camara Bullet,320000,12\n"
        "Camara PTZ,480000,8\n",
        encoding="utf-8",
    )
    return str(archivo)


@pytest.fixture
def csv_semicolon(tmp_path: Path) -> str:
    """CSV con separador punto y coma."""
    archivo = tmp_path / "productos_sc.csv"
    archivo.write_text(
        "name;price;stock\n"
        "Camara Domo;180000;25\n"
        "Camara Bullet;320000;12\n",
        encoding="utf-8",
    )
    return str(archivo)


@pytest.fixture
def csv_con_vacias(tmp_path: Path) -> str:
    """CSV con filas vacías intercaladas."""
    archivo = tmp_path / "vacias.csv"
    archivo.write_text(
        "name,price,stock\n"
        "Camara Domo,180000,25\n"
        "\n"
        "Camara Bullet,320000,12\n"
        "\n",
        encoding="utf-8",
    )
    return str(archivo)


@pytest.fixture
def xlsx_simple(tmp_path: Path) -> str:
    """Excel simple si openpyxl está disponible."""
    pytest.importorskip("openpyxl")
    import openpyxl
    archivo = tmp_path / "productos.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["name", "price", "stock"])
    ws.append(["Camara Domo", 180000, 25])
    ws.append(["Camara Bullet", 320000, 12])
    wb.save(str(archivo))
    return str(archivo)


# ── Tests: detect_format ─────────────────────────────────────

class TestDetectFormat:

    def test_detecta_csv(self, parser):
        assert parser.detect_format("archivo.csv") == ".csv"

    def test_detecta_xlsx(self, parser):
        assert parser.detect_format("archivo.xlsx") == ".xlsx"

    def test_detecta_xls(self, parser):
        assert parser.detect_format("archivo.xls") == ".xls"

    def test_formato_invalido_lanza_error(self, parser):
        with pytest.raises(ValueError, match="no soportado"):
            parser.detect_format("archivo.pdf")

    def test_case_insensitive(self, parser):
        assert parser.detect_format("ARCHIVO.CSV") == ".csv"
        assert parser.detect_format("ARCHIVO.XLSX") == ".xlsx"


# ── Tests: parseo CSV ────────────────────────────────────────

class TestParseCSV:

    def test_parse_csv_retorna_parse_result(self, parser, csv_simple):
        result = parser.parse(csv_simple)
        assert isinstance(result, ParseResult)

    def test_parse_csv_filas_correctas(self, parser, csv_simple):
        result = parser.parse(csv_simple)
        assert result.total == 3

    def test_parse_csv_columnas_detectadas(self, parser, csv_simple):
        result = parser.parse(csv_simple)
        assert "name" in result.columns
        assert "price" in result.columns
        assert "stock" in result.columns

    def test_parse_csv_valores_correctos(self, parser, csv_simple):
        result = parser.parse(csv_simple)
        primera = result.rows[0]
        assert primera["name"] == "Camara Domo"
        assert primera["price"] == "180000"

    def test_parse_csv_separador_punto_coma(self, parser, csv_semicolon):
        result = parser.parse(csv_semicolon)
        assert result.total == 2
        assert result.rows[0]["name"] == "Camara Domo"

    def test_parse_csv_salta_filas_vacias(self, parser, csv_con_vacias):
        result = parser.parse(csv_con_vacias)
        assert result.total == 2

    def test_parse_csv_max_rows(self, parser, csv_simple):
        cfg = ParserConfig(max_rows=2)
        result = parser.parse(csv_simple, config=cfg)
        assert result.total == 2

    def test_parse_csv_skip_rows(self, tmp_path, parser):
        archivo = tmp_path / "skip.csv"
        archivo.write_text(
            "# comentario\n"
            "name,price\n"
            "Camara,180000\n",
            encoding="utf-8",
        )
        cfg = ParserConfig(skip_rows=1)
        result = parser.parse(str(archivo), config=cfg)
        assert result.total == 1

    def test_parse_csv_formato_en_resultado(self, parser, csv_simple):
        result = parser.parse(csv_simple)
        assert result.file_format == ".csv"

    def test_parse_csv_file_path_en_resultado(self, parser, csv_simple):
        result = parser.parse(csv_simple)
        assert result.file_path == csv_simple


# ── Tests: parseo Excel ──────────────────────────────────────

class TestParseExcel:

    def test_parse_xlsx_retorna_result(self, parser, xlsx_simple):
        result = parser.parse(xlsx_simple)
        assert isinstance(result, ParseResult)

    def test_parse_xlsx_filas_correctas(self, parser, xlsx_simple):
        result = parser.parse(xlsx_simple)
        assert result.total == 2

    def test_parse_xlsx_columnas_detectadas(self, parser, xlsx_simple):
        result = parser.parse(xlsx_simple)
        assert "name" in result.columns
        assert "price" in result.columns

    def test_parse_xlsx_formato_en_resultado(self, parser, xlsx_simple):
        result = parser.parse(xlsx_simple)
        assert result.file_format == ".xlsx"


# ── Tests: column_mapping ────────────────────────────────────

class TestColumnMapping:

    def test_mapeo_renombra_columnas(self, parser, csv_simple):
        cfg = ParserConfig(column_mapping={"name": "nombre", "price": "precio"})
        result = parser.parse(csv_simple, config=cfg)
        assert "nombre" in result.columns
        assert "precio" in result.columns
        assert "name" not in result.columns

    def test_mapeo_columna_inexistente_genera_advertencia(self, parser, csv_simple):
        cfg = ParserConfig(column_mapping={"no_existe": "nuevo"})
        result = parser.parse(csv_simple, config=cfg)
        assert any("no_existe" in e for e in result.errors)

    def test_apply_mapping_directo(self, parser, csv_simple):
        result = parser.parse(csv_simple)
        mapped = parser._apply_mapping(result, {"name": "producto"})
        assert "producto" in mapped.columns


# ── Tests: preview y get_columns ─────────────────────────────

class TestPreviewYColumnas:

    def test_preview_limita_filas(self, parser, csv_simple):
        result = parser.preview(csv_simple, rows=2)
        assert result.total == 2

    def test_get_columns_retorna_lista(self, parser, csv_simple):
        cols = parser.get_columns(csv_simple)
        assert isinstance(cols, list)
        assert "name" in cols
        assert "price" in cols


# ── Tests: ParseResult helpers ───────────────────────────────

class TestParseResult:

    def test_is_empty_false_con_datos(self, parser, csv_simple):
        result = parser.parse(csv_simple)
        assert not result.is_empty()

    def test_is_empty_true_sin_datos(self):
        result = ParseResult(
            rows=[], columns=[], total=0,
            file_path="", file_format=".csv"
        )
        assert result.is_empty()

    def test_has_column_true(self, parser, csv_simple):
        result = parser.parse(csv_simple)
        assert result.has_column("name")
        assert result.has_column("NAME")   # case-insensitive

    def test_has_column_false(self, parser, csv_simple):
        result = parser.parse(csv_simple)
        assert not result.has_column("no_existe")


# ── Tests: manejo de errores ─────────────────────────────────

class TestErrores:

    def test_archivo_no_encontrado(self, parser):
        with pytest.raises(FileNotFoundError):
            parser.parse("no_existe.csv")

    def test_formato_no_soportado(self, parser, tmp_path):
        archivo = tmp_path / "archivo.pdf"
        archivo.write_text("contenido")
        with pytest.raises(ValueError, match="no soportado"):
            parser.parse(str(archivo))

    def test_ruta_no_es_archivo(self, parser, tmp_path):
        with pytest.raises(ValueError, match="no es un archivo"):
            parser.parse(str(tmp_path))   # directorio, no archivo