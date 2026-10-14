# -*- coding: utf-8 -*-
"""
plugin.py - Plugin Coordinador de Importación Excel
=====================================================
Coordina parser + validator + importer en un flujo único.
Hereda de BasePlugin para integrarse con el sistema de plugins
existente (base.py, manager.py, orchestrator.py).

Responsabilidad: orquestar el flujo completo de importación:
    1. Parsear archivo (ExcelParser)
    2. Validar datos   (ProductValidator)
    3. Importar a BD   (ProductImporter → Supabase + Qdrant)
    4. Emitir eventos  (EventBus → Observer Pattern)
    5. Reportar stats  (ImportSummary)

Multi-Tenant:
    - Cada operación usa el tenant_id del contexto activo
    - Datos aislados en Supabase y Qdrant por tenant

Uso:
    plugin = ExcelImportPlugin(event_bus=bus, tenant_context=ctx)
    plugin.initialize(config={
        "supabase_client": supabase,
        "openai_client":   openai,
        "qdrant_client":   qdrant,
    })
    plugin.start()

    result = plugin.import_file("productos.xlsx")
    print(result.summary())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.event_bus import EventBus
from src.core.logger import logger
from src.core.tenant_context import TenantContext
from src.plugins.base import BasePlugin, PluginMetadata
from src.plugins.decorators import log_execution, measure_time, require_running
from src.plugins.excel_import.importer import ImporterConfig, ProductImporter
from src.plugins.excel_import.parser import ExcelParser, ParserConfig
from src.plugins.excel_import.validator import ProductValidator, ValidatorConfig


# ── Value Object: resumen completo ───────────────────────────

@dataclass
class ImportSummary:
    """
    Resumen completo de una importación.
    Agrega resultados de parser + validator + importer.

    Attributes:
        file_path:      Archivo procesado
        tenant_id:      Tenant propietario
        total_rows:     Filas leídas del archivo
        valid_rows:     Filas que pasaron validación
        invalid_rows:   Filas rechazadas por validación
        saved_count:    Productos guardados en BD
        failed_count:   Productos que fallaron al guardar
        skipped_count:  Productos omitidos (duplicados)
        parse_errors:   Errores durante lectura
        validation_errors: Errores de validación
        import_errors:  Errores durante guardado
        duration_ms:    Tiempo total en ms
        rolled_back:    True si hubo rollback
    """
    file_path:          str       = ""
    tenant_id:          str       = ""
    total_rows:         int       = 0
    valid_rows:         int       = 0
    invalid_rows:       int       = 0
    saved_count:        int       = 0
    failed_count:       int       = 0
    skipped_count:      int       = 0
    parse_errors:       List[str] = field(default_factory=list)
    validation_errors:  List[str] = field(default_factory=list)
    import_errors:      List[str] = field(default_factory=list)
    duration_ms:        float     = 0.0
    rolled_back:        bool      = False

    @property
    def is_success(self) -> bool:
        """True si se guardó al menos un producto sin rollback."""
        return self.saved_count > 0 and not self.rolled_back

    @property
    def total_errors(self) -> int:
        return (
            len(self.parse_errors)
            + len(self.validation_errors)
            + len(self.import_errors)
        )

    def summary(self) -> str:
        return (
            f"Importación '{Path(self.file_path).name}' | "
            f"tenant='{self.tenant_id}' | "
            f"leídas={self.total_rows} | "
            f"válidas={self.valid_rows} | "
            f"guardadas={self.saved_count} | "
            f"errores={self.total_errors} | "
            f"{self.duration_ms:.0f}ms"
        )

    def __repr__(self) -> str:
        return (
            f"ImportSummary("
            f"saved={self.saved_count}, "
            f"invalid={self.invalid_rows}, "
            f"errors={self.total_errors})"
        )


# ── Plugin Coordinador ───────────────────────────────────────

class ExcelImportPlugin(BasePlugin):
    """
    Plugin coordinador de importación Excel/CSV.

    Hereda de BasePlugin e integra:
      - ExcelParser    → leer archivos
      - ProductValidator → validar datos
      - ProductImporter  → guardar en Supabase + Qdrant

    Configuración (on_initialize):
        supabase_client: Cliente Supabase (requerido en prod)
        openai_client:   Cliente OpenAI   (requerido en prod)
        qdrant_client:   Cliente Qdrant   (requerido en prod)
        batch_size:      Lote de guardado (default: 100)
        dry_run:         Sin escritura en BD (default: False)
        column_mapping:  Mapeo de columnas del cliente

    Eventos emitidos:
        excel_import.started    → inicio de importación
        excel_import.parsed     → archivo leído
        excel_import.validated  → datos validados
        excel_import.completed  → importación exitosa
        excel_import.failed     → error en importación
    """

    def __init__(
        self,
        event_bus:      EventBus,
        tenant_context: Optional[TenantContext] = None,
    ) -> None:
        super().__init__(event_bus, tenant_context)

        self._metadata = PluginMetadata(
            name          = "excel_import",
            version       = "1.0.0",
            description   = "Importa productos desde archivos Excel/CSV a Supabase + Qdrant",
            author        = "EstructuraAI Team",
            dependencies  = [],
            tenant_specific = True,
        )

        # Componentes — se inicializan en on_initialize()
        self._parser:    Optional[ExcelParser]      = None
        self._validator: Optional[ProductValidator] = None
        self._importer:  Optional[ProductImporter]  = None

        # Config opcional del cliente
        self._column_mapping: Dict[str, str] = {}
        self._dry_run: bool = False

    # ── Lifecycle Hooks ──────────────────────────────────────

    def on_initialize(self) -> None:
        """
        Construye parser, validator e importer con la config recibida.
        Llamado automáticamente por BasePlugin.initialize().
        """
        self._dry_run       = self.get_config("dry_run", False)
        self._column_mapping= self.get_config("column_mapping", {})

        # Parser — sin config especial requerida
        self._parser = ExcelParser()

        # Validator — config personalizable
        validator_config = ValidatorConfig(
            allow_zero_price = self.get_config("allow_zero_price", False),
            allow_duplicates = self.get_config("allow_duplicates", False),
            required_columns = self.get_config(
                "required_columns", ["name", "price"]
            ),
        )
        self._validator = ProductValidator(validator_config)

        # Importer — conecta con Supabase y Qdrant
        importer_config = ImporterConfig(
            batch_size          = self.get_config("batch_size", 100),
            rollback_on_error   = self.get_config("rollback_on_error", True),
            generate_embeddings = self.get_config("generate_embeddings", True),
        )
        self._importer = ProductImporter(
            supabase_client = self.get_config("supabase_client"),
            openai_client   = self.get_config("openai_client"),
            qdrant_client   = self.get_config("qdrant_client"),
            config          = importer_config,
            dry_run         = self._dry_run,
        )

        logger.info(
            f"ExcelImportPlugin configurado | "
            f"dry_run={self._dry_run} | "
            f"batch_size={importer_config.batch_size}"
        )

    def on_start(self) -> None:
        """Emite evento de disponibilidad."""
        self._emit_event("excel_import.ready", {
            "plugin":   self.metadata.name,
            "version":  self.metadata.version,
            "dry_run":  self._dry_run,
        })

    def on_stop(self) -> None:
        """Limpia referencias a clientes externos."""
        self._parser    = None
        self._validator = None
        self._importer  = None
        logger.info("ExcelImportPlugin detenido — recursos liberados")

    # ── API pública ──────────────────────────────────────────

    @require_running
    @measure_time
    @log_execution
    def import_file(
        self,
        file_path:      str,
        tenant_id:      Optional[str]        = None,
        column_mapping: Optional[Dict[str, str]] = None,
        skip_rows:      int                  = 0,
    ) -> ImportSummary:
        """
        Flujo completo: parsear → validar → importar.

        Args:
            file_path:      Ruta al archivo Excel/CSV.
            tenant_id:      ID del tenant. Si no se provee, usa
                            el tenant del contexto activo.
            column_mapping: Mapeo de columnas del cliente.
                            Ej: {"Nombre": "name", "Valor": "price"}
            skip_rows:      Filas a saltar al inicio del archivo.

        Returns:
            ImportSummary con estadísticas completas.

        Raises:
            ValueError: Si no hay tenant_id disponible.
            FileNotFoundError: Si el archivo no existe.
        """
        # Resolver tenant_id
        resolved_tenant = self._resolve_tenant(tenant_id)

        # Mapeo de columnas: parámetro > config > vacío
        mapping = (
            column_mapping
            or self._column_mapping
            or {}
        )

        summary = ImportSummary(
            file_path = file_path,
            tenant_id = resolved_tenant,
        )

        # Emitir inicio
        self._emit_event("excel_import.started", {
            "file":      file_path,
            "tenant_id": resolved_tenant,
        })

        try:
            # ── PASO 1: Parsear ──────────────────────────────
            logger.info(f"[1/3] Parseando: {Path(file_path).name}")

            parser_config = ParserConfig(
                skip_rows      = skip_rows,
                column_mapping = mapping,
            )
            parse_result = self._parser.parse(file_path, parser_config)

            summary.total_rows   = parse_result.total
            summary.parse_errors = parse_result.errors

            self._emit_event("excel_import.parsed", {
                "tenant_id":  resolved_tenant,
                "total_rows": parse_result.total,
                "columns":    parse_result.columns,
            })

            if parse_result.is_empty():
                logger.warning("Archivo vacío — nada que importar")
                return summary

            # ── PASO 2: Validar ──────────────────────────────
            logger.info(f"[2/3] Validando {parse_result.total} filas...")

            val_result = self._validator.validate(parse_result.rows)

            summary.valid_rows        = val_result.valid_count
            summary.invalid_rows      = val_result.invalid_count
            summary.validation_errors = [str(e) for e in val_result.errors]

            self._emit_event("excel_import.validated", {
                "tenant_id":   resolved_tenant,
                "valid_rows":  val_result.valid_count,
                "invalid_rows": val_result.invalid_count,
            })

            if val_result.valid_count == 0:
                logger.warning("Ninguna fila válida — nada que importar")
                return summary

            # ── PASO 3: Importar ─────────────────────────────
            logger.info(
                f"[3/3] Importando {val_result.valid_count} productos "
                f"→ tenant='{resolved_tenant}'"
            )

            import_result = self._importer.import_products(
                rows      = val_result.valid_rows,
                tenant_id = resolved_tenant,
            )

            summary.saved_count   = import_result.saved_count
            summary.failed_count  = import_result.failed_count
            summary.skipped_count = import_result.skipped_count
            summary.import_errors = import_result.errors
            summary.duration_ms   = import_result.duration_ms
            summary.rolled_back   = import_result.rolled_back

            # Emitir resultado
            event = (
                "excel_import.completed"
                if import_result.is_success
                else "excel_import.failed"
            )
            self._emit_event(event, {
                "tenant_id":   resolved_tenant,
                "saved_count": import_result.saved_count,
                "file":        file_path,
            })

            logger.success(summary.summary())
            return summary

        except Exception as exc:
            summary.import_errors.append(str(exc))
            self._emit_event("excel_import.failed", {
                "tenant_id": resolved_tenant,
                "error":     str(exc),
                "file":      file_path,
            })
            logger.error(f"Error en import_file: {exc}")
            raise

    @require_running
    def preview_file(
        self,
        file_path: str,
        rows:      int = 5,
    ) -> Dict[str, Any]:
        """
        Previsualiza las primeras N filas del archivo.

        Args:
            file_path: Ruta al archivo.
            rows:      Filas a mostrar (default: 5).

        Returns:
            Dict con columnas y primeras filas.
        """
        result = self._parser.preview(file_path, rows=rows)
        return {
            "file":    file_path,
            "columns": result.columns,
            "rows":    result.rows,
            "total":   result.total,
        }

    @require_running
    def get_columns(self, file_path: str) -> List[str]:
        """
        Retorna las columnas del archivo sin importarlo.

        Útil para que el cliente configure el column_mapping
        antes de hacer la importación real.
        """
        return self._parser.get_columns(file_path)

    @require_running
    def validate_file(
        self,
        file_path:      str,
        column_mapping: Optional[Dict[str, str]] = None,
        skip_rows:      int = 0,
    ) -> Dict[str, Any]:
        """
        Solo parsea y valida — sin guardar en BD.

        Útil para dar feedback al cliente antes de importar.

        Returns:
            Dict con resultado de validación.
        """
        mapping = column_mapping or self._column_mapping or {}

        parser_config = ParserConfig(
            skip_rows      = skip_rows,
            column_mapping = mapping,
        )
        parse_result = self._parser.parse(file_path, parser_config)
        val_result   = self._validator.validate(parse_result.rows)

        return {
            "file":          file_path,
            "total_rows":    parse_result.total,
            "valid_rows":    val_result.valid_count,
            "invalid_rows":  val_result.invalid_count,
            "is_valid":      val_result.is_valid,
            "errors":        [str(e) for e in val_result.errors],
            "warnings":      val_result.warnings,
        }

    # ── Helpers ──────────────────────────────────────────────

    def _resolve_tenant(self, tenant_id: Optional[str]) -> str:
        """
        Resuelve el tenant_id a usar.
        Prioridad: parámetro > tenant_context > error
        """
        if tenant_id and tenant_id.strip():
            return tenant_id.strip()

        if self._tenant_context and self._tenant_context.tenant_id:
            return self._tenant_context.tenant_id

        raise ValueError(
            "tenant_id requerido — provéelo como parámetro "
            "o configura un TenantContext activo"
        )