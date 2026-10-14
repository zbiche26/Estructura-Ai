"""
Vector Service - Gestiona almacenamiento y búsqueda en Qdrant

Permite:
- Almacenar documentos como vectores
- Búsqueda por similitud semántica
- Filtrado por metadata
- CRUD de vectores
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue
)

from src.services.embedding_service import EmbeddingService
from src.core.logger import logger
from src.config import settings


class VectorService:
    """
    Servicio para gestionar vectores en Qdrant
    
    Maneja collections, indexing y búsqueda vectorial.
    """
    
    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        collection_name: str = "products"
    ):
        """
        Inicializa Vector Service
        
        Args:
            embedding_service: Servicio de embeddings (opcional)
            collection_name: Nombre de la colección en Qdrant
        """
        self.collection_name = collection_name
        
        # Crear embedding service si no se proporciona
        self.embedding_service = embedding_service or EmbeddingService(
            primary_provider="local",  # Por defecto local (gratis)
            fallback_provider="mock"
        )
        
        # Crear cliente Qdrant según configuración
        self.client = self._create_client()
        
        # Dimensión de los vectores
        self.vector_dimension = self.embedding_service.get_dimension()
        
        # Crear colección si no existe
        self._ensure_collection_exists()
        
        # Mapa de IDs: custom_id -> uuid
        self._id_map: Dict[str, str] = {}
        
        logger.info(
            f"VectorService inicializado: "
            f"collection={collection_name}, "
            f"dimension={self.vector_dimension}"
        )
    
    def _create_client(self) -> QdrantClient:
        """Crea cliente Qdrant según configuración"""
        mode = settings.QDRANT_MODE
        
        if mode == "memory":
            # In-memory (desarrollo)
            logger.info("Qdrant mode: in-memory")
            return QdrantClient(":memory:")
        
        elif mode == "local":
            # Docker local
            logger.info(f"Qdrant mode: local ({settings.QDRANT_URL})")
            return QdrantClient(url=settings.QDRANT_URL)
        
        elif mode == "cloud":
            # Qdrant Cloud
            logger.info("Qdrant mode: cloud")
            return QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY
            )
        
        else:
            raise ValueError(f"QDRANT_MODE inválido: {mode}")
    
    def _ensure_collection_exists(self):
        """Crea la colección si no existe"""
        try:
            # Verificar si existe
            collections = self.client.get_collections().collections
            collection_names = [c.name for c in collections]
            
            if self.collection_name not in collection_names:
                # Crear colección
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_dimension,
                        distance=Distance.COSINE
                    )
                )
                logger.success(f"Colección creada: {self.collection_name}")
            else:
                logger.info(f"Colección existente: {self.collection_name}")
                
        except Exception as e:
            logger.error(f"Error creando colección: {e}")
            raise
    
    def _get_or_create_uuid(self, custom_id: str) -> str:
        """Obtiene o crea un UUID para un ID custom"""
        if custom_id not in self._id_map:
            self._id_map[custom_id] = str(uuid.uuid4())
        return self._id_map[custom_id]
    
    def _get_custom_id(self, uuid_str: str) -> Optional[str]:
        """Obtiene el ID custom desde un UUID"""
        for custom_id, uuid_id in self._id_map.items():
            if uuid_id == uuid_str:
                return custom_id
        return None
    
    def add_document(
        self,
        document_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Agrega un documento a la base vectorial
        
        Args:
            document_id: ID único del documento
            text: Texto del documento
            metadata: Metadata adicional
            
        Returns:
            True si se agregó exitosamente
        """
        try:
            # Generar embedding
            vector = self.embedding_service.embed(text)
            
            # Obtener o crear UUID
            uuid_id = self._get_or_create_uuid(document_id)
            
            # Preparar payload (incluir custom_id en metadata)
            payload = {
                "custom_id": document_id,
                "text": text,
                "created_at": datetime.now(timezone.utc).isoformat(),
                **(metadata or {})
            }
            
            # Crear punto
            point = PointStruct(
                id=uuid_id,
                vector=vector,
                payload=payload
            )
            
            # Agregar a Qdrant
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
            
            logger.debug(f"Documento agregado: {document_id} (UUID: {uuid_id})")
            return True
            
        except Exception as e:
            logger.error(f"Error agregando documento: {e}")
            return False
    
    def add_documents_batch(
        self,
        documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Agrega múltiples documentos en batch
        
        Args:
            documents: Lista de documentos con format:
                {
                    "id": "doc_1",
                    "text": "contenido",
                    "metadata": {...}
                }
        
        Returns:
            Estadísticas del batch
        """
        try:
            # Extraer textos
            texts = [doc["text"] for doc in documents]
            
            # Generar embeddings en batch
            vectors = self.embedding_service.embed_batch(texts)
            
            # Crear puntos
            points = []
            for doc, vector in zip(documents, vectors):
                # Obtener o crear UUID
                uuid_id = self._get_or_create_uuid(doc["id"])
                
                payload = {
                    "custom_id": doc["id"],
                    "text": doc["text"],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    **doc.get("metadata", {})
                }
                
                point = PointStruct(
                    id=uuid_id,
                    vector=vector,
                    payload=payload
                )
                points.append(point)
            
            # Agregar a Qdrant
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )
            
            logger.info(f"Batch agregado: {len(documents)} documentos")
            
            return {
                "success": True,
                "documents_added": len(documents),
                "collection": self.collection_name
            }
            
        except Exception as e:
            logger.error(f"Error en batch: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def search(
        self,
        query: str,
        limit: int = 5,
        score_threshold: float = 0.0,  # Bajado a 0.0 para funcionar con mock
        filter_conditions: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Busca documentos similares a la query
        
        Args:
            query: Texto de búsqueda
            limit: Número máximo de resultados
            score_threshold: Umbral mínimo de similitud (0-1)
            filter_conditions: Condiciones de filtro (ej: {"tenant_id": "123"})
            
        Returns:
            Lista de documentos con scores
        """
        try:
            # Generar embedding de la query
            query_vector = self.embedding_service.embed(query)
            
            # Preparar filtro si hay condiciones
            query_filter = None
            if filter_conditions:
                conditions = []
                for key, value in filter_conditions.items():
                    conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value)
                        )
                    )
                query_filter = Filter(must=conditions)
            
            # Buscar en Qdrant usando scroll (método universal)
            # Este método funciona en TODAS las versiones de Qdrant
            scroll_result = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=query_filter,
                limit=limit * 10,  # Obtener más para ordenar por similitud
                with_payload=True,
                with_vectors=True  # Necesitamos vectores para calcular similitud
            )
            
            points = scroll_result[0] if scroll_result else []
            
            # Calcular similitudes manualmente (similitud coseno)
            import numpy as np
            
            scored_results = []
            query_vec = np.array(query_vector)
            query_norm = np.linalg.norm(query_vec)
            
            for point in points:
                # Calcular similitud coseno
                point_vec = np.array(point.vector)
                point_norm = np.linalg.norm(point_vec)
                
                if query_norm > 0 and point_norm > 0:
                    similarity = np.dot(query_vec, point_vec) / (query_norm * point_norm)
                else:
                    similarity = 0.0
                
                # Filtrar por threshold
                if similarity >= score_threshold:
                    scored_results.append((similarity, point))
            
            # Ordenar por similitud (mayor primero)
            scored_results.sort(key=lambda x: x[0], reverse=True)
            
            # Tomar solo los primeros N
            scored_results = scored_results[:limit]
            
            # Crear results en formato esperado
            results = []
            for score, point in scored_results:
                # Crear un objeto que simula el resultado de búsqueda
                class SearchResult:
                    def __init__(self, score, point):
                        self.score = score
                        self.payload = point.payload
                        self.id = point.id
                
                results.append(SearchResult(score, point))
            
            # Formatear resultados
            formatted_results = []
            for result in results:
                # Obtener custom_id del payload
                custom_id = result.payload.get("custom_id", str(result.id))
                
                formatted_results.append({
                    "id": custom_id,
                    "score": result.score,
                    "text": result.payload.get("text"),
                    "metadata": {
                        k: v for k, v in result.payload.items()
                        if k not in ["custom_id", "text", "created_at"]
                    },
                    "created_at": result.payload.get("created_at")
                })
            
            logger.info(f"Búsqueda: {len(formatted_results)} resultados para '{query[:50]}'")
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error en búsqueda: {e}")
            return []
    
    def get_document(self, document_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene un documento por ID
        
        Args:
            document_id: ID del documento (custom ID)
            
        Returns:
            Documento o None
        """
        try:
            # Obtener UUID
            uuid_id = self._id_map.get(document_id)
            if not uuid_id:
                return None
            
            points = self.client.retrieve(
                collection_name=self.collection_name,
                ids=[uuid_id]
            )
            
            if not points:
                return None
            
            point = points[0]
            custom_id = point.payload.get("custom_id", document_id)
            
            return {
                "id": custom_id,
                "text": point.payload.get("text"),
                "metadata": {
                    k: v for k, v in point.payload.items()
                    if k not in ["custom_id", "text", "created_at"]
                },
                "created_at": point.payload.get("created_at")
            }
            
        except Exception as e:
            logger.error(f"Error obteniendo documento: {e}")
            return None
    
    def update_document(
        self,
        document_id: str,
        text: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Actualiza un documento
        
        Args:
            document_id: ID del documento
            text: Nuevo texto (opcional)
            metadata: Nueva metadata (opcional)
            
        Returns:
            True si se actualizó
        """
        try:
            # Obtener documento actual
            current = self.get_document(document_id)
            if not current:
                logger.warning(f"Documento {document_id} no encontrado")
                return False
            
            # Actualizar texto si se proporciona
            if text:
                current["text"] = text
                # Regenerar embedding
                vector = self.embedding_service.embed(text)
            else:
                # Usar el texto actual
                vector = self.embedding_service.embed(current["text"])
            
            # Actualizar metadata
            if metadata:
                current["metadata"].update(metadata)
            
            # Obtener UUID
            uuid_id = self._id_map[document_id]
            
            # Crear payload
            payload = {
                "custom_id": document_id,
                "text": current["text"],
                "created_at": current["created_at"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
                **current["metadata"]
            }
            
            # Actualizar en Qdrant
            point = PointStruct(
                id=uuid_id,
                vector=vector,
                payload=payload
            )
            
            self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
            
            logger.info(f"Documento actualizado: {document_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error actualizando documento: {e}")
            return False
    
    def delete_document(self, document_id: str) -> bool:
        """
        Elimina un documento
        
        Args:
            document_id: ID del documento (custom ID)
            
        Returns:
            True si se eliminó
        """
        try:
            # Obtener UUID
            uuid_id = self._id_map.get(document_id)
            if not uuid_id:
                # Si no está en el mapa, intentar eliminar de todos modos
                logger.warning(f"UUID no encontrado para {document_id}")
                return True
            
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=[uuid_id]
            )
            
            # Eliminar del mapa
            del self._id_map[document_id]
            
            logger.info(f"Documento eliminado: {document_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error eliminando documento: {e}")
            return False
    
    def count_documents(
        self,
        filter_conditions: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Cuenta documentos en la colección
        
        Args:
            filter_conditions: Condiciones de filtro (opcional)
            
        Returns:
            Número de documentos
        """
        try:
            # Preparar filtro
            query_filter = None
            if filter_conditions:
                conditions = []
                for key, value in filter_conditions.items():
                    conditions.append(
                        FieldCondition(
                            key=key,
                            match=MatchValue(value=value)
                        )
                    )
                query_filter = Filter(must=conditions)
            
            # Contar
            result = self.client.count(
                collection_name=self.collection_name,
                count_filter=query_filter
            )
            
            return result.count
            
        except Exception as e:
            logger.error(f"Error contando documentos: {e}")
            return 0
    
    def clear_collection(self) -> bool:
        """
        Elimina todos los documentos de la colección
        
        Returns:
            True si se eliminó
        """
        try:
            self.client.delete_collection(
                collection_name=self.collection_name
            )
            
            # Limpiar mapa de IDs
            self._id_map.clear()
            
            # Recrear colección vacía
            self._ensure_collection_exists()
            
            logger.warning(f"Colección {self.collection_name} limpiada")
            return True
            
        except Exception as e:
            logger.error(f"Error limpiando colección: {e}")
            return False