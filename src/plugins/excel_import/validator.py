# -*- coding: utf-8 -*-
"""
validator.py - Validador de datos de productos
===============================================
Extrae y mejora la lógica de _validate_data() del ExcelImportPlugin.

Responsabilidad única: validar que los datos de productos
cumplan las reglas de negocio antes de importarlos.

Reglas de validación:
    - Columnas requeridas presentes (name, price)
    - Nombre no vacío y longitud válida
    - Precio > 0 y numérico
    - Stock >= 0 y entero
    - SKU único dentro del lote (sin duplicados)
    - Categoría opcional pero válida si se provee

Uso:
    validator = ProductValidator()
    result = validator.validate(rows)

    if result.is_valid:
        print(f"{result.valid_count} productos válidos")
    else:
        for error in result.errors:
            print(error)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


# ── Value Objects ────────────────────────────────────────────

@dataclass
class RowError:
    """
    Error en una fila específica.

    Attributes:
        row:     Índice de la fila (0-based)
        field:   Campo que falló la validación
        value:   Valor que causó el error
        message: Descripción del error
    """
    row:     int
    field:   str
    value:   Any
    message: str

    def __str__(self) -> str:
        return f"Fila {self.row} | {self.field}: {self.message} (valor: {self.value!r})"


@dataclass
class ValidationResult:
    """
    Resultado completo de la validación.

    Attributes:
        valid_rows:   Filas que pasaron todas las validaciones
        invalid_rows: Filas que fallaron al menos una validación
        errors:       Lista de todos los errores encontrados
        warnings:     Advertencias no bloqueantes
    """
    valid_rows:   List[Dict[str, Any]] = field(default_factory=list)
    invalid_rows: List[Dict[str, Any]] = field(default_factory=list)
    errors:       List[RowError]       = field(default_factory=list)
    warnings:     List[str]            = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True si no hay filas inválidas."""
        return len(self.invalid_rows) == 0

    @property
    def valid_count(self) -> int:
        """Número de filas válidas."""
        return len(self.valid_rows)

    @property
    def invalid_count(self) -> int:
        """Número de filas inválidas."""
        return len(self.invalid_rows)

    @property
    def total(self) -> int:
        """Total de filas procesadas."""
        return self.valid_count + self.invalid_count

    @property
    def error_count(self) -> int:
        """Total de errores encontrados."""
        return len(self.errors)

    def errors_for_row(self, row: int) -> List[RowError]:
        """Retorna todos los errores de una fila específica."""
        return [e for e in self.errors if e.row == row]

    def summary(self) -> str:
        """Resumen legible del resultado."""
        return (
            f"Validación: {self.valid_count}/{self.total} válidas | "
            f"{self.invalid_count} inválidas | "
            f"{self.error_count} errores"
        )

    def __repr__(self) -> str:
        return (
            f"ValidationResult("
            f"valid={self.valid_count}, "
            f"invalid={self.invalid_count}, "
            f"errors={self.error_count})"
        )


@dataclass
class ValidatorConfig:
    """
    Configuración del validador.

    Attributes:
        required_columns:   Columnas que deben existir en los datos
        max_name_length:    Longitud máxima del nombre (default: 255)
        min_name_length:    Longitud mínima del nombre (default: 1)
        max_price:          Precio máximo permitido (0 = sin límite)
        max_stock:          Stock máximo permitido (0 = sin límite)
        allow_zero_price:   Permitir precio = 0 (default: False)
        allow_duplicates:   Permitir SKUs duplicados (default: False)
        strict_mode:        Fallar ante cualquier campo desconocido
    """
    required_columns:  List[str] = field(
        default_factory=lambda: ["name", "price"]
    )
    max_name_length:   int  = 255
    min_name_length:   int  = 1
    max_price:         float = 0.0
    max_stock:         int   = 0
    allow_zero_price:  bool  = False
    allow_duplicates:  bool  = False
    strict_mode:       bool  = False


# ── Validador principal ──────────────────────────────────────

class ProductValidator:
    """
    Validador de datos de productos.

    Valida filas de datos antes de importarlas a Supabase,
    asegurando que cumplen las reglas de negocio.

    Uso básico:
        validator = ProductValidator()
        result = validator.validate(rows)

        for row in result.valid_rows:
            # guardar en BD
            pass

        for error in result.errors:
            print(error)

    Con configuración:
        config = ValidatorConfig(
            required_columns=["name", "price", "sku"],
            allow_zero_price=False,
            allow_duplicates=False,
        )
        validator = ProductValidator(config)
        result = validator.validate(rows)
    """

    def __init__(self, config: Optional[ValidatorConfig] = None) -> None:
        self._config = config or ValidatorConfig()

    # ── API pública ──────────────────────────────────────────

    def validate(self, rows: List[Dict[str, Any]]) -> ValidationResult:
        """
        Valida una lista de filas de productos.

        Args:
            rows: Lista de dicts con datos de productos.

        Returns:
            ValidationResult con filas válidas, inválidas y errores.
        """
        result = ValidationResult()

        if not rows:
            result.warnings.append("No hay filas para validar")
            return result

        # Validar columnas requeridas en el primer registro
        missing_cols = self._check_required_columns(rows[0])
        if missing_cols:
            for col in missing_cols:
                result.errors.append(RowError(
                    row=-1,
                    field=col,
                    value=None,
                    message=f"Columna requerida '{col}' no encontrada en los datos"
                ))
            # Marcar todas las filas como inválidas
            result.invalid_rows.extend(rows)
            result.warnings.append(
                f"Columnas faltantes: {missing_cols}. "
                "No se puede continuar la validación."
            )
            return result

        # Validar cada fila individualmente
        seen_skus: Set[str] = set()

        for idx, row in enumerate(rows):
            row_errors = self._validate_row(idx, row, seen_skus)

            if row_errors:
                result.invalid_rows.append(row)
                result.errors.extend(row_errors)
            else:
                result.valid_rows.append(row)

                # Registrar SKU si existe
                sku = self._get_str(row, "sku")
                if sku:
                    seen_skus.add(sku.lower())

        # Advertencias globales
        if result.invalid_count > 0:
            result.warnings.append(
                f"{result.invalid_count} fila(s) inválida(s) serán omitidas"
            )

        return result

    def validate_columns(self, columns: List[str]) -> List[str]:
        """
        Verifica si las columnas requeridas están presentes.

        Args:
            columns: Lista de nombres de columnas disponibles.

        Returns:
            Lista de columnas requeridas que faltan (vacía si todo OK).
        """
        cols_lower = [c.lower() for c in columns]
        return [
            req for req in self._config.required_columns
            if req.lower() not in cols_lower
        ]

    # ── Validación por fila ──────────────────────────────────

    def _validate_row(
        self,
        idx:      int,
        row:      Dict[str, Any],
        seen_skus: Set[str],
    ) -> List[RowError]:
        """Valida una fila individual. Retorna lista de errores."""
        errors: List[RowError] = []

        errors.extend(self._validate_name(idx, row))
        errors.extend(self._validate_price(idx, row))
        errors.extend(self._validate_stock(idx, row))
        errors.extend(self._validate_sku(idx, row, seen_skus))
        errors.extend(self._validate_category(idx, row))

        return errors

    # ── Validaciones por campo ───────────────────────────────

    def _validate_name(
        self,
        idx: int,
        row: Dict[str, Any],
    ) -> List[RowError]:
        """Valida el campo 'name'."""
        errors: List[RowError] = []
        value  = self._get_str(row, "name")

        if not value:
            errors.append(RowError(
                row=idx, field="name",
                value=value,
                message="El nombre no puede estar vacío"
            ))
            return errors

        if len(value) < self._config.min_name_length:
            errors.append(RowError(
                row=idx, field="name",
                value=value,
                message=(
                    f"Nombre demasiado corto "
                    f"(mínimo {self._config.min_name_length} caracteres)"
                )
            ))

        if len(value) > self._config.max_name_length:
            errors.append(RowError(
                row=idx, field="name",
                value=value,
                message=(
                    f"Nombre demasiado largo "
                    f"(máximo {self._config.max_name_length} caracteres)"
                )
            ))

        return errors

    def _validate_price(
        self,
        idx: int,
        row: Dict[str, Any],
    ) -> List[RowError]:
        """Valida el campo 'price'."""
        errors: List[RowError] = []
        raw    = row.get("price")

        # Vacío
        if raw is None or str(raw).strip() == "":
            errors.append(RowError(
                row=idx, field="price",
                value=raw,
                message="El precio no puede estar vacío"
            ))
            return errors

        # Numérico
        try:
            price = float(str(raw).replace(",", ".").replace(" ", ""))
        except (ValueError, TypeError):
            errors.append(RowError(
                row=idx, field="price",
                value=raw,
                message=f"Precio no numérico: '{raw}'"
            ))
            return errors

        # Negativo
        if price < 0:
            errors.append(RowError(
                row=idx, field="price",
                value=price,
                message="El precio no puede ser negativo"
            ))

        # Cero
        if price == 0 and not self._config.allow_zero_price:
            errors.append(RowError(
                row=idx, field="price",
                value=price,
                message="El precio debe ser mayor que 0"
            ))

        # Máximo
        if self._config.max_price > 0 and price > self._config.max_price:
            errors.append(RowError(
                row=idx, field="price",
                value=price,
                message=(
                    f"Precio supera el máximo permitido "
                    f"(${self._config.max_price:,.0f})"
                )
            ))

        return errors

    def _validate_stock(
        self,
        idx: int,
        row: Dict[str, Any],
    ) -> List[RowError]:
        """Valida el campo 'stock' (opcional)."""
        errors: List[RowError] = []
        raw    = row.get("stock")

        # Stock es opcional — si no existe, OK
        if raw is None or str(raw).strip() == "":
            return errors

        # Entero
        try:
            stock = int(float(str(raw).strip()))
        except (ValueError, TypeError):
            errors.append(RowError(
                row=idx, field="stock",
                value=raw,
                message=f"Stock no es un número entero: '{raw}'"
            ))
            return errors

        # Negativo
        if stock < 0:
            errors.append(RowError(
                row=idx, field="stock",
                value=stock,
                message="El stock no puede ser negativo"
            ))

        # Máximo
        if self._config.max_stock > 0 and stock > self._config.max_stock:
            errors.append(RowError(
                row=idx, field="stock",
                value=stock,
                message=(
                    f"Stock supera el máximo permitido "
                    f"({self._config.max_stock})"
                )
            ))

        return errors

    def _validate_sku(
        self,
        idx:       int,
        row:       Dict[str, Any],
        seen_skus: Set[str],
    ) -> List[RowError]:
        """Valida el campo 'sku' — duplicados dentro del lote."""
        errors: List[RowError] = []
        sku    = self._get_str(row, "sku")

        # SKU es opcional
        if not sku:
            return errors

        if not self._config.allow_duplicates:
            if sku.lower() in seen_skus:
                errors.append(RowError(
                    row=idx, field="sku",
                    value=sku,
                    message=f"SKU duplicado en el lote: '{sku}'"
                ))

        return errors

    def _validate_category(
        self,
        idx: int,
        row: Dict[str, Any],
    ) -> List[RowError]:
        """Valida el campo 'category' (opcional)."""
        errors:   List[RowError] = []
        category = self._get_str(row, "category")

        # Categoría es opcional
        if not category:
            return errors

        # Longitud máxima
        if len(category) > 100:
            errors.append(RowError(
                row=idx, field="category",
                value=category,
                message="Categoría demasiado larga (máximo 100 caracteres)"
            ))

        return errors

    # ── Helpers ──────────────────────────────────────────────

    def _check_required_columns(
        self,
        row: Dict[str, Any],
    ) -> List[str]:
        """Retorna columnas requeridas que faltan en la fila."""
        cols_lower = [k.lower() for k in row.keys()]
        return [
            req for req in self._config.required_columns
            if req.lower() not in cols_lower
        ]

    def _get_str(self, row: Dict[str, Any], key: str) -> str:
        """
        Obtiene un valor como string limpio.
        Retorna '' si es None o vacío.
        """
        value = row.get(key)
        if value is None:
            return ""
        cleaned = str(value).strip()
        return "" if cleaned.lower() in ("nan", "none", "") else cleaned