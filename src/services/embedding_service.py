"""
Embedding Service - Genera embeddings (vectores) de texto

Soporta:
- OpenAI (text-embedding-3-small, ada-002)
- Local (Sentence Transformers)
- Mock (para testing)
"""
from typing import List, Literal, Optional
from abc import ABC, abstractmethod
import os
import numpy as np

from src.core.logger import logger


# ==================== TIPOS ====================

EmbeddingProvider = Literal["openai", "local", "mock"]


# ==================== BASE CLASS ====================

class BaseEmbeddingService(ABC):
    """Clase base para servicios de embeddings"""
    
    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """
        Genera embedding de un texto
        
        Args:
            text: Texto a convertir en vector
            
        Returns:
            Vector de embeddings (lista de floats)
        """
        pass
    
    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Genera embeddings de múltiples textos
        
        Args:
            texts: Lista de textos
            
        Returns:
            Lista de vectores
        """
        pass
    
    @abstractmethod
    def get_dimension(self) -> int:
        """Retorna la dimensión del vector"""
        pass


# ==================== OPENAI EMBEDDING SERVICE ====================

class OpenAIEmbeddingService(BaseEmbeddingService):
    """Servicio de embeddings usando OpenAI"""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "text-embedding-3-small"
    ):
        """
        Inicializa servicio OpenAI
        
        Args:
            api_key: API key de OpenAI
            model: Modelo a usar (text-embedding-3-small, text-embedding-ada-002)
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model
        
        if not self.api_key:
            raise ValueError("OpenAI API key no configurada")
        
        from openai import OpenAI
        self.client = OpenAI(api_key=self.api_key)
        
        # Dimensiones por modelo
        self._dimensions = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536
        }
        
        logger.info(f"OpenAI Embedding Service inicializado: {model}")
    
    def embed(self, text: str) -> List[float]:
        """Genera embedding de un texto"""
        try:
            response = self.client.embeddings.create(
                input=text,
                model=self.model
            )
            
            embedding = response.data[0].embedding
            
            logger.debug(f"Embedding generado: {len(embedding)} dims")
            
            return embedding
            
        except Exception as e:
            logger.error(f"Error generando embedding: {e}")
            raise
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Genera embeddings de múltiples textos"""
        try:
            # OpenAI soporta hasta 2048 textos por batch
            batch_size = 2048
            all_embeddings = []
            
            for i in range(0, len(texts), batch_size):
                batch = texts[i:i + batch_size]
                
                response = self.client.embeddings.create(
                    input=batch,
                    model=self.model
                )
                
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)
            
            logger.info(f"Batch embeddings generados: {len(all_embeddings)} vectores")
            
            return all_embeddings
            
        except Exception as e:
            logger.error(f"Error generando batch embeddings: {e}")
            raise
    
    def get_dimension(self) -> int:
        """Retorna dimensión del vector"""
        return self._dimensions.get(self.model, 1536)


# ==================== LOCAL EMBEDDING SERVICE ====================

class LocalEmbeddingService(BaseEmbeddingService):
    """Servicio de embeddings local usando Sentence Transformers"""
    
    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    ):
        """
        Inicializa servicio local
        
        Args:
            model_name: Nombre del modelo de Sentence Transformers
        """
        self.model_name = model_name
        
        try:
            from sentence_transformers import SentenceTransformer
            
            logger.info(f"Cargando modelo local: {model_name}")
            self.model = SentenceTransformer(model_name)
            logger.success(f"Modelo cargado: {model_name}")
            
        except Exception as e:
            logger.error(f"Error cargando modelo: {e}")
            raise
    
    def embed(self, text: str) -> List[float]:
        """Genera embedding de un texto"""
        try:
            embedding = self.model.encode(
                text,
                convert_to_numpy=True,
                show_progress_bar=False
            )
            
            return embedding.tolist()
            
        except Exception as e:
            logger.error(f"Error generando embedding: {e}")
            raise
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Genera embeddings de múltiples textos"""
        try:
            embeddings = self.model.encode(
                texts,
                convert_to_numpy=True,
                show_progress_bar=True,
                batch_size=32
            )
            
            return embeddings.tolist()
            
        except Exception as e:
            logger.error(f"Error generando batch embeddings: {e}")
            raise
    
    def get_dimension(self) -> int:
        """Retorna dimensión del vector"""
        return self.model.get_sentence_embedding_dimension()


# ==================== MOCK EMBEDDING SERVICE ====================

class MockEmbeddingService(BaseEmbeddingService):
    """Servicio mock para testing"""
    
    def __init__(self, dimension: int = 384):
        """
        Inicializa servicio mock
        
        Args:
            dimension: Dimensión de los vectores fake
        """
        self.dimension = dimension
        logger.info(f"Mock Embedding Service inicializado: {dimension} dims")
    
    def embed(self, text: str) -> List[float]:
        """Genera embedding fake basado en hash del texto"""
        # Usar hash del texto para generar vector determinista
        import hashlib
        
        hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)
        np.random.seed(hash_val % (2**32))
        
        # Generar vector aleatorio pero determinista
        vector = np.random.randn(self.dimension)
        
        # Normalizar
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        
        return vector.tolist()
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Genera embeddings fake de múltiples textos"""
        return [self.embed(text) for text in texts]
    
    def get_dimension(self) -> int:
        """Retorna dimensión del vector"""
        return self.dimension


# ==================== FACTORY ====================

class EmbeddingServiceFactory:
    """Factory para crear servicios de embeddings"""
    
    @staticmethod
    def create(
        provider: EmbeddingProvider = "local",
        **kwargs
    ) -> BaseEmbeddingService:
        """
        Crea un servicio de embeddings
        
        Args:
            provider: Proveedor ("openai", "local", "mock")
            **kwargs: Parámetros específicos del proveedor
            
        Returns:
            Instancia del servicio
        """
        if provider == "openai":
            return OpenAIEmbeddingService(**kwargs)
        elif provider == "local":
            return LocalEmbeddingService(**kwargs)
        elif provider == "mock":
            return MockEmbeddingService(**kwargs)
        else:
            raise ValueError(f"Proveedor desconocido: {provider}")


# ==================== UNIFIED EMBEDDING SERVICE ====================

class EmbeddingService:
    """
    Servicio unificado de embeddings con fallback
    
    Intenta usar el proveedor principal, si falla usa el fallback.
    """
    
    def __init__(
        self,
        primary_provider: EmbeddingProvider = "local",
        fallback_provider: Optional[EmbeddingProvider] = "mock",
        **kwargs
    ):
        """
        Inicializa servicio unificado
        
        Args:
            primary_provider: Proveedor principal
            fallback_provider: Proveedor de fallback
            **kwargs: Parámetros para los proveedores
        """
        self.primary = EmbeddingServiceFactory.create(
            primary_provider,
            **kwargs
        )
        
        self.fallback = (
            EmbeddingServiceFactory.create(fallback_provider, **kwargs)
            if fallback_provider
            else None
        )
        
        logger.info(
            f"Embedding Service inicializado: "
            f"primary={primary_provider}, fallback={fallback_provider}"
        )
    
    def embed(
        self,
        text: str,
        use_fallback_on_error: bool = True
    ) -> List[float]:
        """
        Genera embedding con fallback automático
        
        Args:
            text: Texto a convertir
            use_fallback_on_error: Si usar fallback en caso de error
            
        Returns:
            Vector de embeddings
        """
        try:
            return self.primary.embed(text)
            
        except Exception as e:
            logger.error(f"Error en primary embedding: {e}")
            
            if use_fallback_on_error and self.fallback:
                logger.warning("Usando fallback embedding service")
                return self.fallback.embed(text)
            else:
                raise
    
    def embed_batch(
        self,
        texts: List[str],
        use_fallback_on_error: bool = True
    ) -> List[List[float]]:
        """
        Genera embeddings con fallback automático
        
        Args:
            texts: Textos a convertir
            use_fallback_on_error: Si usar fallback en caso de error
            
        Returns:
            Lista de vectores
        """
        try:
            return self.primary.embed_batch(texts)
            
        except Exception as e:
            logger.error(f"Error en primary batch embedding: {e}")
            
            if use_fallback_on_error and self.fallback:
                logger.warning("Usando fallback embedding service")
                return self.fallback.embed_batch(texts)
            else:
                raise
    
    def get_dimension(self) -> int:
        """Retorna dimensión del vector del proveedor principal"""
        return self.primary.get_dimension()


# ==================== HELPER FUNCTIONS ====================

def compute_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calcula similitud coseno entre dos vectores
    
    Args:
        vec1: Primer vector
        vec2: Segundo vector
        
    Returns:
        Similitud (0-1, donde 1 es idéntico)
    """
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    
    dot_product = np.dot(v1, v2)
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    similarity = dot_product / (norm1 * norm2)
    
    return float(similarity)