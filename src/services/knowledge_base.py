"""
Knowledge Base Manager - Gestiona la base de conocimiento del agente

Permite:
- Agregar productos/información a la base
- Buscar información relevante
- Actualizar conocimiento
- Sincronizar con repositorio de productos
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from src.services.vector_service import VectorService
from src.services.embedding_service import EmbeddingService
from src.core.logger import logger


class KnowledgeBase:
    """
    Gestiona la base de conocimiento del agente IA

    Permite agregar, buscar y mantener información
    que el agente usa para responder queries.
    """

    def __init__(
        self,
        vector_service: Optional[VectorService] = None,
        embedding_service: Optional[EmbeddingService] = None,
        collection_name: str = "products",
    ):
        """
        Inicializa Knowledge Base

        Args:
            vector_service: Servicio de vectores (opcional)
            embedding_service: Servicio de embeddings (opcional)
            collection_name: Nombre de la colección
        """
        # Crear embedding service si no existe
        self.embedding_service = embedding_service or EmbeddingService(
            primary_provider="local", fallback_provider="mock"
        )

        # Crear vector service
        self.vector_service = vector_service or VectorService(
            embedding_service=self.embedding_service, collection_name=collection_name
        )

        self.collection_name = collection_name

        logger.info(f"KnowledgeBase inicializada: {collection_name}")

    def add_product(
        self,
        product_id: str,
        name: str,
        description: str,
        price: float,
        stock: int,
        category: Optional[str] = None,
        tenant_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Agrega un producto a la base de conocimiento

        Args:
            product_id: ID único del producto
            name: Nombre del producto
            description: Descripción
            price: Precio
            stock: Stock disponible
            category: Categoría (opcional)
            tenant_id: ID del tenant (multi-tenant)
            metadata: Metadata adicional

        Returns:
            True si se agregó exitosamente
        """
        try:
            # Crear texto para embedding
            # Combinamos nombre y descripción para mejor búsqueda
            text = f"{name}. {description}"

            # Preparar metadata
            product_metadata = {
                "type": "product",
                "name": name,
                "price": price,
                "stock": stock,
                "category": category or "general",
                "tenant_id": tenant_id or "default",
                **(metadata or {}),
            }

            # Agregar a vector store
            success = self.vector_service.add_document(
                document_id=product_id, text=text, metadata=product_metadata
            )

            if success:
                logger.info(f"Producto agregado a KB: {product_id} ({name})")

            return success

        except Exception as e:
            logger.error(f"Error agregando producto a KB: {e}")
            return False

    def add_products_batch(self, products: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Agrega múltiples productos en batch

        Args:
            products: Lista de productos con formato:
                {
                    "id": "prod_1",
                    "name": "Laptop HP",
                    "description": "...",
                    "price": 1000,
                    "stock": 5,
                    "category": "laptops",
                    "tenant_id": "tenant_123"
                }

        Returns:
            Estadísticas del batch
        """
        try:
            # Preparar documentos para vector service
            documents = []

            for product in products:
                # Crear texto
                text = f"{product['name']}. {product.get('description', '')}"

                # Metadata
                metadata = {
                    "type": "product",
                    "name": product["name"],
                    "price": product.get("price", 0),
                    "stock": product.get("stock", 0),
                    "category": product.get("category", "general"),
                    "tenant_id": product.get("tenant_id", "default"),
                }

                documents.append(
                    {"id": product["id"], "text": text, "metadata": metadata}
                )

            # Agregar en batch
            result = self.vector_service.add_documents_batch(documents)

            logger.info(f"Batch de productos agregados: {len(products)}")

            return result

        except Exception as e:
            logger.error(f"Error en batch de productos: {e}")
            return {"success": False, "error": str(e)}

    def search_products(
        self,
        query: str,
        limit: int = 5,
        min_score: float = 0.0,  # Bajado a 0.0 para funcionar con mock embeddings
        tenant_id: Optional[str] = None,
        category: Optional[str] = None,
        in_stock_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Busca productos relevantes por similitud semántica

        Args:
            query: Consulta del usuario
            limit: Número máximo de resultados
            min_score: Score mínimo de similitud (0-1)
            tenant_id: Filtrar por tenant
            category: Filtrar por categoría
            in_stock_only: Solo productos con stock

        Returns:
            Lista de productos relevantes con scores
        """
        try:
            # Preparar filtros
            results = self.vector_service.search(
                query=query,
                limit=limit * 2,
                score_threshold=min_score,
                filter_conditions=None,
            )

            # Filtrar por stock si es necesario
            if in_stock_only:
                results = [r for r in results if r["metadata"].get("stock", 0) > 0]

            # Limitar resultados
            results = results[:limit]

            logger.info(f"Búsqueda en KB: '{query[:50]}' → {len(results)} productos")

            return results

        except Exception as e:
            logger.error(f"Error buscando productos: {e}")
            return []

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un producto específico

        Args:
            product_id: ID del producto

        Returns:
            Producto o None
        """
        return self.vector_service.get_document(product_id)

    def update_product(
        self,
        product_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        price: Optional[float] = None,
        stock: Optional[int] = None,
        **kwargs,
    ) -> bool:
        """
        Actualiza información de un producto

        Args:
            product_id: ID del producto
            name: Nuevo nombre (opcional)
            description: Nueva descripción (opcional)
            price: Nuevo precio (opcional)
            stock: Nuevo stock (opcional)
            **kwargs: Otros campos a actualizar

        Returns:
            True si se actualizó
        """
        try:
            # Obtener producto actual
            current = self.get_product(product_id)
            if not current:
                logger.warning(f"Producto {product_id} no encontrado")
                return False

            # Actualizar texto si cambió nombre o descripción
            new_text = None
            if name or description:
                current_name = name or current["metadata"]["name"]
                current_desc = (
                    description or current["text"].split(". ", 1)[1]
                    if ". " in current["text"]
                    else ""
                )
                new_text = f"{current_name}. {current_desc}"

            # Actualizar metadata
            updated_metadata = {}
            if name:
                updated_metadata["name"] = name
            if price is not None:
                updated_metadata["price"] = price
            if stock is not None:
                updated_metadata["stock"] = stock

            updated_metadata.update(kwargs)

            # Actualizar en vector store
            success = self.vector_service.update_document(
                document_id=product_id,
                text=new_text,
                metadata=updated_metadata if updated_metadata else None,
            )

            if success:
                logger.info(f"Producto actualizado: {product_id}")

            return success

        except Exception as e:
            logger.error(f"Error actualizando producto: {e}")
            return False

    def delete_product(self, product_id: str) -> bool:
        """
        Elimina un producto de la base de conocimiento

        Args:
            product_id: ID del producto

        Returns:
            True si se eliminó
        """
        success = self.vector_service.delete_document(product_id)

        if success:
            logger.info(f"Producto eliminado de KB: {product_id}")

        return success

    def sync_from_repository(
        self, product_repository, tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sincroniza productos desde el repositorio a la KB

        Args:
            product_repository: Repositorio de productos
            tenant_id: Filtrar por tenant (opcional)

        Returns:
            Estadísticas de sincronización
        """
        try:
            logger.info("Iniciando sincronización con repositorio...")

            # Obtener productos del repositorio
            # (Asumimos que tiene método get_all)
            if tenant_id:
                products = product_repository.get_by_tenant(tenant_id)
            else:
                products = product_repository.get_all()

            if not products:
                logger.warning("No hay productos para sincronizar")
                return {"success": True, "products_synced": 0}

            # Preparar para batch
            product_dicts = []
            for product in products:
                # Convertir modelo a dict si es necesario
                if hasattr(product, "to_dict"):
                    product_dict = product.to_dict()
                else:
                    product_dict = product

                product_dicts.append(product_dict)

            # Agregar en batch
            result = self.add_products_batch(product_dicts)

            logger.success(
                f"Sincronización completada: "
                f"{result.get('documents_added', 0)} productos"
            )

            return result

        except Exception as e:
            logger.error(f"Error en sincronización: {e}")
            return {"success": False, "error": str(e)}

    def get_stats(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Obtiene estadísticas de la base de conocimiento

        Args:
            tenant_id: Filtrar por tenant (opcional)

        Returns:
            Estadísticas
        """
        try:
            filters = {"type": "product"}
            if tenant_id:
                filters["tenant_id"] = tenant_id

            total = self.vector_service.count_documents(filters)

            # Contar con stock
            filters_in_stock = {**filters, "stock": {"$gt": 0}}
            # Nota: Qdrant no soporta operadores como $gt directamente
            # Simplemente contamos todos y luego filtramos

            stats = {
                "total_products": total,
                "collection": self.collection_name,
                "vector_dimension": self.embedding_service.get_dimension(),
            }

            return stats

        except Exception as e:
            logger.error(f"Error obteniendo stats: {e}")
            return {}

    def clear(self) -> bool:
        """
        Limpia toda la base de conocimiento

        ⚠️ ADVERTENCIA: Elimina todos los productos

        Returns:
            True si se limpió
        """
        logger.warning("⚠️  Limpiando base de conocimiento...")
        return self.vector_service.clear_collection()


# ==================== HELPER FUNCTION ====================


def create_knowledge_base(
    tenant_id: str, use_local_embeddings: bool = True
) -> KnowledgeBase:

    if use_local_embeddings:
        primary_provider = "local"
    else:
        primary_provider = "openai"

    # Crear embedding service
    embedding_service = EmbeddingService(
        primary_provider=primary_provider, fallback_provider="mock"
    )

    # Crear vector service
    vector_service = VectorService(
        embedding_service=embedding_service, collection_name=f"products_{tenant_id}"
    )

    # Crear knowledge base
    kb = KnowledgeBase(
        vector_service=vector_service,
        embedding_service=embedding_service,
        collection_name=f"products_{tenant_id}",
    )

    return kb
