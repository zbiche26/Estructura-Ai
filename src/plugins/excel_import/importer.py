# -*- coding: utf-8 -*-
"""
importer.py - Importador de productos a Supabase + Qdrant
==========================================================
Responsabilidad única: tomar filas validadas y persistirlas
en Supabase (datos) y Qdrant (embeddings para RAG).

Flujo completo:
    1. Recibe filas válidas del validator
    2. Guarda en Supabase (tabla productos) por tenant
    3. Genera embeddings con OpenAI
    4. Guarda embeddings en Qdrant (colección por tenant)
    5. Rollback si algo falla

Multi-Tenant:
    - Supabase: cada producto tiene tenant_id
    - Qdrant: colección separada por tenant
      formato: "{tenant_id}_productos"

Uso:
    importer = ProductImporter(
        supabase_client=supabase,
        openai_client=openai,
        qdrant_client=qdrant,
    )
    result = importer.import_products(
        rows=validated_rows,
        tenant_id="cliente_a",
    )
    print(result.saved_count)
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.logger import logger

# ── Value Objects ────────────────────────────────────────────


@dataclass
class ImportResult:
    """
    Resultado de una importación.

    Attributes:
        saved_count:    Productos guardados exitosamente
        failed_count:   Productos que fallaron
        skipped_count:  Productos omitidos (duplicados)
        tenant_id:      Tenant al que pertenece la importación
        collection:     Colección de Qdrant utilizada
        errors:         Lista de errores ocurridos
        duration_ms:    Duración total en milisegundos
        rolled_back:    True si se hizo rollback
    """

    saved_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    tenant_id: str = ""
    collection: str = ""
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0
    rolled_back: bool = False

    @property
    def total_processed(self) -> int:
        return self.saved_count + self.failed_count + self.skipped_count

    @property
    def success_rate(self) -> float:
        if self.total_processed == 0:
            return 0.0
        return (self.saved_count / self.total_processed) * 100

    @property
    def is_success(self) -> bool:
        return self.failed_count == 0 and not self.rolled_back

    def summary(self) -> str:
        return (
            f"Importación tenant='{self.tenant_id}': "
            f"{self.saved_count} guardados | "
            f"{self.failed_count} fallidos | "
            f"{self.skipped_count} omitidos | "
            f"{self.duration_ms:.0f}ms"
        )

    def __repr__(self) -> str:
        return (
            f"ImportResult("
            f"saved={self.saved_count}, "
            f"failed={self.failed_count}, "
            f"tenant='{self.tenant_id}')"
        )


@dataclass
class ImporterConfig:
    """
    Configuración del importador.

    Attributes:
        batch_size:         Productos por lote (default: 100)
        rollback_on_error:  Revertir todo si falla (default: True)
        skip_duplicates:    Omitir SKUs ya existentes (default: True)
        generate_embeddings: Generar embeddings para Qdrant (default: True)
        embedding_model:    Modelo de OpenAI para embeddings
        qdrant_collection_suffix: Sufijo para colecciones Qdrant
    """

    batch_size: int = 100
    rollback_on_error: bool = True
    skip_duplicates: bool = True
    generate_embeddings: bool = True
    embedding_model: str = "text-embedding-3-small"
    qdrant_collection_suffix: str = "productos"


# ── Importador principal ─────────────────────────────────────


class ProductImporter:
    """
    Importador de productos a Supabase + Qdrant.

    Diseño Multi-Tenant:
    - Supabase: cada producto lleva tenant_id
    - Qdrant: colección separada "{tenant_id}_productos"

    Uso con clientes reales:
        importer = ProductImporter(
            supabase_client=supabase,
            openai_client=openai,
            qdrant_client=qdrant,
        )
        result = importer.import_products(rows, tenant_id="cliente_a")

    Uso en modo dry-run (sin BD, para tests):
        importer = ProductImporter(dry_run=True)
        result = importer.import_products(rows, tenant_id="test")
    """

    def __init__(
        self,
        supabase_client: Any = None,
        openai_client: Any = None,
        qdrant_client: Any = None,
        config: Optional[ImporterConfig] = None,
        dry_run: bool = False,
    ) -> None:
        """
        Args:
            supabase_client: Cliente de Supabase (supabase-py)
            openai_client:   Cliente de OpenAI
            qdrant_client:   Cliente de Qdrant
            config:          Configuración del importador
            dry_run:         Si True, simula sin guardar en BD
        """
        self._supabase = supabase_client
        self._openai = openai_client
        self._qdrant = qdrant_client
        self._config = config or ImporterConfig()
        self._dry_run = dry_run

        if dry_run:
            logger.info("ProductImporter en modo dry_run — sin escritura en BD")

    # ── API pública ──────────────────────────────────────────

    def import_products(
        self,
        rows: List[Dict[str, Any]],
        tenant_id: str,
    ) -> ImportResult:
        """
        Importa productos a Supabase y Qdrant.

        Args:
            rows:      Lista de dicts con datos válidos de productos.
            tenant_id: ID del tenant propietario de los productos.

        Returns:
            ImportResult con estadísticas de la importación.
        """
        if not tenant_id or not tenant_id.strip():
            raise ValueError("tenant_id no puede estar vacío")

        if not rows:
            logger.warning("No hay productos para importar")
            return ImportResult(tenant_id=tenant_id)

        collection = self._get_collection_name(tenant_id)
        result = ImportResult(tenant_id=tenant_id, collection=collection)
        start_time = time.time()

        logger.info(
            f"Iniciando importación: {len(rows)} productos | "
            f"tenant='{tenant_id}' | colección='{collection}'"
        )

        # IDs guardados en Supabase para rollback
        saved_ids: List[str] = []

        try:
            # Procesar en lotes
            for batch_start in range(0, len(rows), self._config.batch_size):
                batch = rows[batch_start : batch_start + self._config.batch_size]

                logger.debug(
                    f"Procesando lote {batch_start // self._config.batch_size + 1} "
                    f"({len(batch)} productos)"
                )

                batch_ids = self._process_batch(
                    batch=batch,
                    tenant_id=tenant_id,
                    collection=collection,
                    result=result,
                )
                saved_ids.extend(batch_ids)

        except Exception as exc:
            logger.error(f"Error en importación: {exc}")
            result.errors.append(str(exc))

            if self._config.rollback_on_error:
                if saved_ids:
                    logger.warning(
                        f"Iniciando rollback de {len(saved_ids)} productos..."
                    )
                    self._rollback(saved_ids, tenant_id, collection)
                result.rolled_back = True
                result.saved_count = 0
                result.failed_count = len(rows)

        result.duration_ms = (time.time() - start_time) * 1000
        logger.info(result.summary())
        return result

    def get_collection_name(self, tenant_id: str) -> str:
        """Retorna el nombre de la colección Qdrant para un tenant."""
        return self._get_collection_name(tenant_id)

    def ensure_collection(self, tenant_id: str) -> bool:
        """
        Crea la colección Qdrant si no existe.

        Returns:
            True si la colección existe o fue creada.
        """
        collection = self._get_collection_name(tenant_id)

        if self._dry_run:
            logger.debug(f"[dry_run] Colección asegurada: '{collection}'")
            return True

        if not self._qdrant:
            logger.warning("Qdrant no disponible — omitiendo ensure_collection")
            return False

        try:
            from qdrant_client.models import Distance, VectorParams

            collections = self._qdrant.get_collections().collections
            names = [c.name for c in collections]

            if collection not in names:
                self._qdrant.create_collection(
                    collection_name=collection,
                    vectors_config=VectorParams(
                        size=1536,  # text-embedding-3-small
                        distance=Distance.COSINE,
                    ),
                )
                logger.success(f"Colección Qdrant creada: '{collection}'")
            else:
                logger.debug(f"Colección Qdrant ya existe: '{collection}'")

            return True

        except Exception as exc:
            logger.error(f"Error asegurando colección '{collection}': {exc}")
            return False

    # ── Procesamiento por lote ───────────────────────────────

    def _process_batch(
        self,
        batch: List[Dict[str, Any]],
        tenant_id: str,
        collection: str,
        result: ImportResult,
    ) -> List[str]:
        """
        Procesa un lote de productos.

        Returns:
            Lista de IDs guardados en Supabase.
        """
        saved_ids: List[str] = []

        for row in batch:
            try:
                # 1. Preparar producto con tenant_id
                product = self._prepare_product(row, tenant_id)

                # 2. Verificar duplicado por SKU
                if self._config.skip_duplicates and product.get("sku"):
                    if self._exists_in_supabase(product["sku"], tenant_id):
                        logger.debug(f"SKU duplicado omitido: '{product['sku']}'")
                        result.skipped_count += 1
                        continue

                # 3. Guardar en Supabase
                product_id = self._save_to_supabase(product)
                saved_ids.append(product_id)

                # 4. Generar embedding y guardar en Qdrant
                if self._config.generate_embeddings:
                    self._save_to_qdrant(product, product_id, collection)

                result.saved_count += 1

            except Exception as exc:
                logger.error(
                    f"Error procesando producto '{row.get('name', '?')}': {exc}"
                )
                result.failed_count += 1
                result.errors.append(f"Producto '{row.get('name', '?')}': {exc}")

                if self._config.rollback_on_error:
                    raise  # Propagar para activar rollback global

        return saved_ids

    # ── Supabase ─────────────────────────────────────────────

    def _prepare_product(
        self,
        row: Dict[str, Any],
        tenant_id: str,
    ) -> Dict[str, Any]:
        """Construye el dict del producto listo para guardar."""
        return {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "name": str(row.get("name", "")).strip(),
            "price": float(str(row.get("price", 0)).replace(",", ".")),
            "stock": int(float(str(row.get("stock", 0)).strip() or "0")),
            "description": str(row.get("description", "")).strip() or None,
            "sku": str(row.get("sku", "")).strip() or None,
            "category": str(row.get("category", "")).strip() or None,
        }

    def _save_to_supabase(self, product: Dict[str, Any]) -> str:
        """
        Guarda un producto en Supabase.

        Returns:
            ID del producto guardado.
        """
        if self._dry_run:
            logger.debug(f"[dry_run] Supabase ← '{product['name']}'")
            return product["id"]

        if not self._supabase:
            raise RuntimeError("Supabase client no configurado")

        try:
            response = self._supabase.table("products").insert(product).execute()

            if not response.data:
                raise RuntimeError("Supabase no retornó datos al insertar")

            saved_id = response.data[0].get("id", product["id"])
            logger.debug(f"Supabase ← '{product['name']}' id={saved_id}")
            return saved_id

        except Exception as exc:
            raise RuntimeError(f"Error guardando en Supabase: {exc}") from exc

    def _exists_in_supabase(self, sku: str, tenant_id: str) -> bool:
        """Verifica si un SKU ya existe para el tenant."""
        if self._dry_run:
            return False

        if not self._supabase:
            return False

        try:
            response = (
                self._supabase.table("products")
                .select("id")
                .eq("tenant_id", tenant_id)
                .eq("sku", sku)
                .execute()
            )
            return len(response.data) > 0

        except Exception:
            return False

    # ── Qdrant ───────────────────────────────────────────────

    def _save_to_qdrant(
        self,
        product: Dict[str, Any],
        product_id: str,
        collection: str,
    ) -> None:
        """Genera embedding y guarda en Qdrant."""
        if self._dry_run:
            logger.debug(f"[dry_run] Qdrant ← '{product['name']}'")
            return

        if not self._qdrant or not self._openai:
            logger.warning("Qdrant o OpenAI no configurados — omitiendo embedding")
            return

        try:
            # Construir texto para embedding
            text = self._build_embedding_text(product)

            # Generar embedding con OpenAI
            embedding = self._generate_embedding(text)

            # Guardar en Qdrant
            from qdrant_client.models import PointStruct

            self._qdrant.upsert(
                collection_name=collection,
                points=[
                    PointStruct(
                        id=self._uuid_to_int(product_id),
                        vector=embedding,
                        payload={
                            "product_id": product_id,
                            "tenant_id": product["tenant_id"],
                            "name": product["name"],
                            "price": product["price"],
                            "stock": product["stock"],
                            "sku": product.get("sku"),
                            "category": product.get("category"),
                            "description": product.get("description"),
                        },
                    )
                ],
            )

            logger.debug(f"Qdrant ← '{product['name']}' → colección '{collection}'")

        except Exception as exc:
            # Embedding falla → log pero no bloquea la importación
            logger.warning(f"Error generando embedding para '{product['name']}': {exc}")

    def _build_embedding_text(self, product: Dict[str, Any]) -> str:
        """
        Construye el texto que se convertirá en embedding.
        Incluye todos los campos relevantes para búsqueda semántica.
        """
        parts = [f"Producto: {product['name']}"]

        if product.get("description"):
            parts.append(f"Descripción: {product['description']}")

        if product.get("category"):
            parts.append(f"Categoría: {product['category']}")

        parts.append(f"Precio: ${product['price']:,.0f} COP")
        parts.append(f"Stock disponible: {product['stock']} unidades")

        if product.get("sku"):
            parts.append(f"SKU: {product['sku']}")

        return " | ".join(parts)

    def _generate_embedding(self, text: str) -> List[float]:
        """Genera embedding usando OpenAI."""
        response = self._openai.embeddings.create(
            model=self._config.embedding_model,
            input=text,
        )
        return response.data[0].embedding

    # ── Rollback ─────────────────────────────────────────────

    def _rollback(
        self,
        product_ids: List[str],
        tenant_id: str,
        collection: str,
    ) -> None:
        """
        Revierte la importación eliminando productos guardados.

        Args:
            product_ids: IDs de productos a eliminar en Supabase
            tenant_id:   Tenant de los productos
            collection:  Colección Qdrant a limpiar
        """
        if self._dry_run:
            logger.debug(f"[dry_run] Rollback de {len(product_ids)} productos")
            return

        errors = 0

        # Rollback Supabase
        if self._supabase and product_ids:
            try:
                self._supabase.table("products").delete().in_(
                    "id", product_ids
                ).execute()

                logger.info(
                    f"Rollback Supabase: {len(product_ids)} productos eliminados"
                )
            except Exception as exc:
                errors += 1
                logger.error(f"Error en rollback Supabase: {exc}")

        # Rollback Qdrant
        if self._qdrant and product_ids:
            try:
                from qdrant_client.models import PointIdsList

                int_ids = [self._uuid_to_int(pid) for pid in product_ids]
                self._qdrant.delete(
                    collection_name=collection,
                    points_selector=PointIdsList(points=int_ids),
                )
                logger.info(f"Rollback Qdrant: {len(product_ids)} puntos eliminados")
            except Exception as exc:
                errors += 1
                logger.error(f"Error en rollback Qdrant: {exc}")

        if errors == 0:
            logger.success("Rollback completado exitosamente")
        else:
            logger.warning(f"Rollback completado con {errors} error(es)")

    # ── Helpers ──────────────────────────────────────────────

    def _get_collection_name(self, tenant_id: str) -> str:
        """Retorna el nombre de la colección Qdrant para el tenant."""
        # Limpiar tenant_id para uso como nombre de colección
        clean = tenant_id.lower().replace("-", "_").replace(" ", "_")
        return f"{clean}_{self._config.qdrant_collection_suffix}"

    def _uuid_to_int(self, uuid_str: str) -> int:
        """
        Convierte UUID a entero para Qdrant.
        Qdrant requiere IDs numéricos o UUIDs válidos.
        """
        try:
            return uuid.UUID(uuid_str).int % (2**63)
        except ValueError:
            return abs(hash(uuid_str)) % (2**63)
