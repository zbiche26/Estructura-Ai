# -*- coding: utf-8 -*-
"""
parser.py - Parser de archivos Excel y CSV
==========================================
Extrae y mejora la lógica de lectura del ExcelImportPlugin.

Responsabilidad única: leer archivos y convertirlos a
estructuras de datos Python limpias.

Formatos soportados:
    - .xlsx  (Excel moderno)
    - .xls   (Excel legacy)
    - .csv   (valores separados por coma/punto y coma)

Uso:
    parser = ExcelParser()
    resultado = parser.parse("productos.xlsx")

    # Con opciones
    resultado = parser.parse(
        "productos.csv",
        encoding="utf-8",
        separator=","
    )

    print(resultado.rows)      # Lista de dicts
    print(resultado.columns)   # Columnas detectadas
    print(resultado.total)     # Total de filas
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.logger import logger

# pandas es opcional — si no está disponible se usa csv nativo
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    logger.warning("pandas no disponible — usando parser CSV nativo")

try:
    import openpyxl  # noqa: F401
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

try:
    import xlrd  # noqa: F401
    XLRD_AVAILABLE = True
except ImportError:
    XLRD_AVAILABLE = False


# ── Formatos soportados ──────────────────────────────────────
SUPPORTED_FORMATS = {".csv", ".xlsx", ".xls"}


# ── Value Objects ────────────────────────────────────────────

@dataclass
class ParseResult:
    """
    Resultado de parsear un archivo.

    Attributes:
        rows:        Lista de filas como dicts {columna: valor}
        columns:     Lista de nombres de columnas detectadas
        total:       Total de filas (sin contar encabezado)
        file_path:   Ruta del archivo parseado
        file_format: Extensión del archivo (.csv, .xlsx, .xls)
        encoding:    Encoding detectado/usado (solo CSV)
        errors:      Advertencias durante el parseo
    """
    rows:        List[Dict[str, Any]]
    columns:     List[str]
    total:       int
    file_path:   str
    file_format: str
    encoding:    Optional[str] = None
    errors:      List[str]     = field(default_factory=list)

    def is_empty(self) -> bool:
        """Retorna True si no hay filas."""
        return self.total == 0

    def has_column(self, name: str) -> bool:
        """Verifica si una columna existe (case-insensitive)."""
        return name.lower() in [c.lower() for c in self.columns]

    def __repr__(self) -> str:
        return (
            f"ParseResult(total={self.total}, "
            f"columns={self.columns}, "
            f"format='{self.file_format}')"
        )


@dataclass
class ParserConfig:
    """
    Configuración del parser.

    Attributes:
        skip_rows:       Filas a saltar al inicio (default: 0)
        sheet_name:      Hoja de Excel a leer (default: 0 = primera)
        encoding:        Encoding para CSV (default: 'utf-8-sig')
        csv_separator:   Separador CSV (default: auto-detectar)
        max_rows:        Máximo de filas a leer (0 = sin límite)
        strip_spaces:    Limpiar espacios en valores (default: True)
        skip_empty_rows: Saltar filas completamente vacías (default: True)
        column_mapping:  Renombrar columnas {original: nuevo}
    """
    skip_rows:       int                    = 0
    sheet_name:      Any                    = 0
    encoding:        str                    = "utf-8-sig"
    csv_separator:   Optional[str]          = None   # None = auto-detectar
    max_rows:        int                    = 0
    strip_spaces:    bool                   = True
    skip_empty_rows: bool                   = True
    column_mapping:  Dict[str, str]         = field(default_factory=dict)


# ── Parser principal ─────────────────────────────────────────

class ExcelParser:
    """
    Parser de archivos Excel y CSV.

    Detecta automáticamente el formato y usa la librería
    apropiada para leer el archivo.

    Uso básico:
        parser = ExcelParser()
        result = parser.parse("productos.xlsx")
        for row in result.rows:
            print(row["name"], row["price"])

    Con configuración:
        config = ParserConfig(skip_rows=1, max_rows=1000)
        result = parser.parse("productos.csv", config=config)
    """

    def __init__(self) -> None:
        logger.debug("ExcelParser inicializado")

    # ── API pública ──────────────────────────────────────────

    def parse(
        self,
        file_path: str,
        config: Optional[ParserConfig] = None,
    ) -> ParseResult:
        """
        Parsea un archivo Excel o CSV.

        Args:
            file_path: Ruta al archivo.
            config:    Configuración del parser (opcional).

        Returns:
            ParseResult con todas las filas y metadatos.

        Raises:
            FileNotFoundError: Si el archivo no existe.
            ValueError:        Si el formato no es soportado.
        """
        cfg  = config or ParserConfig()
        path = Path(file_path)

        self._validate_file(path)

        ext = path.suffix.lower()
        logger.info(f"Parseando archivo: {path.name} ({ext})")

        try:
            if ext == ".csv":
                result = self._parse_csv(path, cfg)
            elif ext in (".xlsx", ".xls"):
                result = self._parse_excel(path, cfg, ext)
            else:
                raise ValueError(
                    f"Formato '{ext}' no soportado. "
                    f"Use: {', '.join(SUPPORTED_FORMATS)}"
                )

            # Aplicar mapeo de columnas si se especificó
            if cfg.column_mapping:
                result = self._apply_mapping(result, cfg.column_mapping)

            logger.success(
                f"Archivo parseado: {result.total} filas, "
                f"{len(result.columns)} columnas"
            )
            return result

        except (FileNotFoundError, ValueError):
            raise
        except Exception as exc:
            logger.error(f"Error parseando '{path.name}': {exc}")
            raise RuntimeError(f"Error al parsear '{path.name}': {exc}") from exc

    def detect_format(self, file_path: str) -> str:
        """
        Detecta el formato de un archivo por su extensión.

        Returns:
            Extensión en minúsculas (.csv, .xlsx, .xls)

        Raises:
            ValueError: Si el formato no es soportado.
        """
        ext = Path(file_path).suffix.lower()
        if ext not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Formato '{ext}' no soportado. "
                f"Formatos válidos: {', '.join(SUPPORTED_FORMATS)}"
            )
        return ext

    def preview(
        self,
        file_path: str,
        rows: int = 5,
        config: Optional[ParserConfig] = None,
    ) -> ParseResult:
        """
        Lee solo las primeras N filas para previsualización.

        Args:
            file_path: Ruta al archivo.
            rows:      Número de filas a leer (default: 5).
            config:    Configuración base (optional).

        Returns:
            ParseResult con las primeras N filas.
        """
        preview_cfg       = config or ParserConfig()
        preview_cfg.max_rows = rows
        return self.parse(file_path, preview_cfg)

    def get_columns(self, file_path: str) -> List[str]:
        """
        Retorna solo los nombres de columnas sin leer todo el archivo.

        Args:
            file_path: Ruta al archivo.

        Returns:
            Lista de nombres de columnas.
        """
        result = self.preview(file_path, rows=1)
        return result.columns

    # ── Parsers por formato ──────────────────────────────────

    def _parse_csv(self, path: Path, cfg: ParserConfig) -> ParseResult:
        """Parsea un archivo CSV."""
        errors: List[str] = []

        if PANDAS_AVAILABLE:
            return self._parse_csv_pandas(path, cfg, errors)
        return self._parse_csv_native(path, cfg, errors)

    def _parse_csv_pandas(
        self,
        path: Path,
        cfg: ParserConfig,
        errors: List[str],
    ) -> ParseResult:
        """Parsea CSV usando pandas."""
        # Auto-detectar separador si no se especificó
        separator = cfg.csv_separator or self._detect_separator(path, cfg.encoding)

        kwargs: Dict[str, Any] = {
            "skiprows": cfg.skip_rows,
            "encoding": cfg.encoding,
            "sep":      separator,
            "dtype":    str,          # Leer todo como string primero
            "keep_default_na": False,
        }
        if cfg.max_rows > 0:
            kwargs["nrows"] = cfg.max_rows

        df = pd.read_csv(path, **kwargs)
        return self._df_to_result(df, str(path), ".csv", cfg, errors, cfg.encoding)

    def _parse_csv_native(
        self,
        path: Path,
        cfg: ParserConfig,
        errors: List[str],
    ) -> ParseResult:
        """Parsea CSV sin pandas (fallback)."""
        rows: List[Dict[str, Any]] = []

        with open(path, encoding=cfg.encoding, newline="") as f:
            # Auto-detectar separador
            sample = f.read(4096)
            f.seek(0)

            sep = cfg.csv_separator
            if not sep:
                try:
                    dialect = csv.Sniffer().sniff(sample)
                    sep = dialect.delimiter
                except csv.Error:
                    sep = ","

            reader = csv.DictReader(f, delimiter=sep)
            columns = list(reader.fieldnames or [])

            for i, row in enumerate(reader):
                if i < cfg.skip_rows:
                    continue
                if cfg.max_rows > 0 and len(rows) >= cfg.max_rows:
                    break

                cleaned = self._clean_row(dict(row), cfg)
                if cfg.skip_empty_rows and self._is_empty_row(cleaned):
                    continue
                rows.append(cleaned)

        return ParseResult(
            rows=rows,
            columns=columns,
            total=len(rows),
            file_path=str(path),
            file_format=".csv",
            encoding=cfg.encoding,
            errors=errors,
        )

    def _parse_excel(
        self,
        path: Path,
        cfg: ParserConfig,
        ext: str,
    ) -> ParseResult:
        """Parsea un archivo Excel (.xlsx o .xls)."""
        errors: List[str] = []

        if not PANDAS_AVAILABLE:
            raise RuntimeError(
                "pandas es requerido para leer archivos Excel. "
                "Instala con: pip install pandas openpyxl xlrd"
            )

        if ext == ".xlsx" and not OPENPYXL_AVAILABLE:
            errors.append("openpyxl no instalado — intentando con engine=None")

        if ext == ".xls" and not XLRD_AVAILABLE:
            raise RuntimeError(
                "xlrd es requerido para leer archivos .xls. "
                "Instala con: pip install xlrd"
            )

        engine = "openpyxl" if ext == ".xlsx" else "xlrd"

        kwargs: Dict[str, Any] = {
            "sheet_name": cfg.sheet_name,
            "skiprows":   cfg.skip_rows,
            "dtype":      str,
            "engine":     engine,
            "keep_default_na": False,
        }
        if cfg.max_rows > 0:
            kwargs["nrows"] = cfg.max_rows

        df = pd.read_excel(path, **kwargs)
        return self._df_to_result(df, str(path), ext, cfg, errors)

    # ── Helpers ──────────────────────────────────────────────

    def _df_to_result(
        self,
        df:          "pd.DataFrame",
        file_path:   str,
        file_format: str,
        cfg:         ParserConfig,
        errors:      List[str],
        encoding:    Optional[str] = None,
    ) -> ParseResult:
        """Convierte un DataFrame de pandas a ParseResult."""
        columns = list(df.columns)
        rows: List[Dict[str, Any]] = []

        for _, row in df.iterrows():
            cleaned = self._clean_row(row.to_dict(), cfg)
            if cfg.skip_empty_rows and self._is_empty_row(cleaned):
                continue
            rows.append(cleaned)

        return ParseResult(
            rows=rows,
            columns=columns,
            total=len(rows),
            file_path=file_path,
            file_format=file_format,
            encoding=encoding,
            errors=errors,
        )

    def _clean_row(
        self,
        row: Dict[str, Any],
        cfg: ParserConfig,
    ) -> Dict[str, Any]:
        """Limpia espacios en los valores de una fila."""
        if not cfg.strip_spaces:
            return row
        return {
            k: v.strip() if isinstance(v, str) else v
            for k, v in row.items()
        }

    def _is_empty_row(self, row: Dict[str, Any]) -> bool:
        """Retorna True si todos los valores de la fila están vacíos."""
        return all(
            v is None or (isinstance(v, str) and not v.strip())
            for v in row.values()
        )

    def _detect_separator(self, path: Path, encoding: str) -> str:
        """Auto-detecta el separador de un CSV leyendo las primeras líneas."""
        try:
            with open(path, encoding=encoding, newline="") as f:
                sample = f.read(4096)
            dialect = csv.Sniffer().sniff(sample)
            return dialect.delimiter
        except Exception:
            return ","

    def _apply_mapping(
        self,
        result: ParseResult,
        mapping: Dict[str, str],
    ) -> ParseResult:
        """Renombra columnas según el mapeo dado."""
        missing = set(mapping.keys()) - set(result.columns)
        if missing:
            logger.warning(f"Columnas no encontradas para mapear: {missing}")

        new_columns = [mapping.get(c, c) for c in result.columns]
        new_rows = [
            {mapping.get(k, k): v for k, v in row.items()}
            for row in result.rows
        ]
        result.errors.extend(
            [f"Columna no encontrada para mapear: '{c}'" for c in missing]
        )

        return ParseResult(
            rows=new_rows,
            columns=new_columns,
            total=result.total,
            file_path=result.file_path,
            file_format=result.file_format,
            encoding=result.encoding,
            errors=result.errors,
        )

    def _validate_file(self, path: Path) -> None:
        """Valida que el archivo exista y tenga formato soportado."""
        if not path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {path}")
        if not path.is_file():
            raise ValueError(f"La ruta no es un archivo: {path}")
        ext = path.suffix.lower()
        if ext not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Formato '{ext}' no soportado. "
                f"Use: {', '.join(SUPPORTED_FORMATS)}"
            )