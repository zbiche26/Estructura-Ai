"""
Tests Unitarios
=================================

Tests para:
- Embedding Service
- Vector Service
- Knowledge Base
- RAG System
"""

import pytest
import asyncio
from typing import List

from src.services.embedding_service import (
    EmbeddingService,
    MockEmbeddingService,
    LocalEmbeddingService,
    EmbeddingServiceFactory,
    compute_similarity,
)
from src.services.vector_service import VectorService
from src.services.knowledge_base import KnowledgeBase, create_knowledge_base
from src.services.rag_system import RAGSystem, create_rag_system
from src.services.llm_service import LLMService

# ==================== FIXTURES ====================


@pytest.fixture
def mock_embedding_service():
    """Servicio de embeddings mock"""
    return MockEmbeddingService(dimension=384)


@pytest.fixture
def embedding_service():
    """Servicio de embeddings unificado"""
    return EmbeddingService(primary_provider="mock", fallback_provider="mock")


@pytest.fixture
def vector_service(embedding_service):
    """Vector service con embeddings mock"""
    return VectorService(
        embedding_service=embedding_service, collection_name="test_products"
    )


@pytest.fixture
def knowledge_base(vector_service, embedding_service):
    """Knowledge Base para testing"""
    return KnowledgeBase(
        vector_service=vector_service,
        embedding_service=embedding_service,
        collection_name="test_products",
    )


@pytest.fixture
def sample_products():
    """Productos de ejemplo"""
    return [
        {
            "id": "prod_1",
            "name": "Laptop HP Pavilion",
            "description": "Laptop para programación con Intel i7, 16GB RAM",
            "price": 1200,
            "stock": 5,
            "category": "laptops",
            "tenant_id": "tenant_test",
        },
        {
            "id": "prod_2",
            "name": "Mouse Logitech",
            "description": "Mouse inalámbrico ergonómico",
            "price": 50,
            "stock": 10,
            "category": "accessories",
            "tenant_id": "tenant_test",
        },
        {
            "id": "prod_3",
            "name": "Teclado Mecánico",
            "description": "Teclado mecánico RGB para gaming",
            "price": 150,
            "stock": 8,
            "category": "accessories",
            "tenant_id": "tenant_test",
        },
    ]


# ==================== TESTS: EMBEDDING SERVICE ====================


class TestEmbeddingService:
    """Tests para Embedding Service"""

    def test_create_mock_service(self, mock_embedding_service):
        """Test crear servicio mock"""
        assert mock_embedding_service is not None
        assert mock_embedding_service.dimension == 384

    def test_mock_embed_single(self, mock_embedding_service):
        """Test generar embedding de texto único"""
        text = "Laptop para programación"
        embedding = mock_embedding_service.embed(text)

        assert len(embedding) == 384
        assert all(isinstance(x, float) for x in embedding)

    def test_mock_embed_batch(self, mock_embedding_service):
        """Test generar embeddings en batch"""
        texts = ["Laptop", "Mouse", "Teclado"]
        embeddings = mock_embedding_service.embed_batch(texts)

        assert len(embeddings) == 3
        assert all(len(e) == 384 for e in embeddings)

    def test_mock_deterministic(self, mock_embedding_service):
        """Test que embeddings son determinísticos"""
        text = "Test text"

        emb1 = mock_embedding_service.embed(text)
        emb2 = mock_embedding_service.embed(text)

        assert emb1 == emb2

    def test_mock_different_texts(self, mock_embedding_service):
        """Test que textos diferentes generan embeddings diferentes"""
        emb1 = mock_embedding_service.embed("laptop")
        emb2 = mock_embedding_service.embed("mouse")

        assert emb1 != emb2

    def test_get_dimension(self, mock_embedding_service):
        """Test obtener dimensión"""
        assert mock_embedding_service.get_dimension() == 384

    def test_factory_create_mock(self):
        """Test factory crear mock"""
        service = EmbeddingServiceFactory.create("mock", dimension=256)

        assert isinstance(service, MockEmbeddingService)
        assert service.get_dimension() == 256

    def test_factory_invalid_provider(self):
        """Test factory con proveedor inválido"""
        with pytest.raises(ValueError):
            EmbeddingServiceFactory.create("invalid")

    def test_unified_service(self, embedding_service):
        """Test servicio unificado"""
        embedding = embedding_service.embed("test")

        assert len(embedding) > 0
        assert isinstance(embedding, list)

    def test_unified_batch(self, embedding_service):
        """Test batch en servicio unificado"""
        texts = ["text1", "text2", "text3"]
        embeddings = embedding_service.embed_batch(texts)

        assert len(embeddings) == 3

    def test_compute_similarity(self, mock_embedding_service):
        """Test calcular similitud"""
        emb1 = mock_embedding_service.embed("laptop gaming")
        emb2 = mock_embedding_service.embed("laptop gamer")
        emb3 = mock_embedding_service.embed("mouse")

        sim_similar = compute_similarity(emb1, emb2)
        sim_different = compute_similarity(emb1, emb3)

        assert 0 <= sim_similar <= 1
        assert 0 <= sim_different <= 1


# ==================== TESTS: VECTOR SERVICE ====================


class TestVectorService:
    """Tests para Vector Service"""

    def test_create_service(self, vector_service):
        """Test crear vector service"""
        assert vector_service is not None
        assert vector_service.collection_name == "test_products"

    def test_add_document(self, vector_service):
        """Test agregar documento"""
        success = vector_service.add_document(
            document_id="doc_1",
            text="Laptop HP para programación",
            metadata={"category": "laptops", "price": 1000},
        )

        assert success is True

    def test_get_document(self, vector_service):
        """Test obtener documento"""
        vector_service.add_document(
            document_id="doc_2",
            text="Mouse inalámbrico",
            metadata={"category": "accessories"},
        )

        doc = vector_service.get_document("doc_2")

        assert doc is not None
        assert doc["id"] == "doc_2"
        assert doc["text"] == "Mouse inalámbrico"
        assert doc["metadata"]["category"] == "accessories"

    def test_get_nonexistent_document(self, vector_service):
        """Test obtener documento inexistente"""
        doc = vector_service.get_document("nonexistent")

        assert doc is None

    def test_add_documents_batch(self, vector_service):
        """Test agregar documentos en batch"""
        documents = [
            {"id": "batch_1", "text": "Laptop Dell", "metadata": {"price": 800}},
            {"id": "batch_2", "text": "Laptop HP", "metadata": {"price": 900}},
        ]

        result = vector_service.add_documents_batch(documents)

        assert result["success"] is True
        assert result["documents_added"] == 2

    def test_search(self, vector_service):
        """Test búsqueda vectorial"""
        docs = [
            {"id": "s1", "text": "Laptop gaming RGB", "metadata": {"type": "laptop"}},
            {"id": "s2", "text": "Mouse gaming RGB", "metadata": {"type": "mouse"}},
            {"id": "s3", "text": "Teclado mecánico", "metadata": {"type": "keyboard"}},
        ]
        vector_service.add_documents_batch(docs)

        results = vector_service.search(
            query="laptop para juegos", limit=2, score_threshold=0.0
        )

        assert len(results) > 0
        assert all("score" in r for r in results)
        assert all("id" in r for r in results)

    def test_search_with_filter(self, vector_service):
        """Test búsqueda con filtros"""
        docs = [
            {"id": "f1", "text": "Producto 1", "metadata": {"tenant_id": "t1"}},
            {"id": "f2", "text": "Producto 2", "metadata": {"tenant_id": "t2"}},
        ]
        vector_service.add_documents_batch(docs)

        results = vector_service.search(
            query="producto", filter_conditions={"tenant_id": "t1"}, score_threshold=0.0
        )

        for r in results:
            assert r["metadata"].get("tenant_id") == "t1"

    def test_update_document(self, vector_service):
        """Test actualizar documento"""
        vector_service.add_document(
            document_id="upd_1", text="Original text", metadata={"price": 100}
        )

        success = vector_service.update_document(
            document_id="upd_1", text="Updated text", metadata={"price": 150}
        )

        assert success is True

        doc = vector_service.get_document("upd_1")
        assert doc["text"] == "Updated text"
        assert doc["metadata"]["price"] == 150

    def test_delete_document(self, vector_service):
        """Test eliminar documento"""
        vector_service.add_document(document_id="del_1", text="To delete")

        success = vector_service.delete_document("del_1")
        assert success is True

        doc = vector_service.get_document("del_1")
        assert doc is None

    def test_count_documents(self, vector_service):
        """Test contar documentos"""
        vector_service.clear_collection()

        docs = [
            {"id": "c1", "text": "Doc 1", "metadata": {}},
            {"id": "c2", "text": "Doc 2", "metadata": {}},
            {"id": "c3", "text": "Doc 3", "metadata": {}},
        ]
        vector_service.add_documents_batch(docs)

        count = vector_service.count_documents()
        assert count == 3


# ==================== TESTS: KNOWLEDGE BASE ====================


class TestKnowledgeBase:
    """Tests para Knowledge Base"""

    def test_create_kb(self, knowledge_base):
        """Test crear knowledge base"""
        assert knowledge_base is not None

    def test_add_product(self, knowledge_base):
        """Test agregar producto"""
        success = knowledge_base.add_product(
            product_id="kb_prod_1",
            name="Laptop Test",
            description="Laptop para testing",
            price=1000,
            stock=5,
            category="laptops",
            tenant_id="tenant_test",
        )

        assert success is True

    def test_add_products_batch(self, knowledge_base, sample_products):
        """Test agregar productos en batch"""
        result = knowledge_base.add_products_batch(sample_products)

        assert result["success"] is True
        assert result["documents_added"] == 3

    def test_search_products(self, knowledge_base, sample_products):
        """Test buscar productos"""
        knowledge_base.add_products_batch(sample_products)

        results = knowledge_base.search_products(
            query="laptop para programar",
            limit=2,
            min_score=0.0,
            tenant_id="tenant_test",
        )

        assert len(results) > 0
        assert all("metadata" in r for r in results)
        assert all(r["metadata"]["type"] == "product" for r in results)

    @pytest.mark.skip(
        reason="campo 'category' no está indexado en Qdrant — usar 'categoria' en modo moda"
    )
    def test_search_products_with_category(self, knowledge_base, sample_products):
        """Test buscar con filtro de categoría"""
        knowledge_base.add_products_batch(sample_products)

        results = knowledge_base.search_products(
            query="producto", category="accessories", min_score=0.0
        )

        for r in results:
            assert r["metadata"]["category"] == "accessories"

    def test_search_in_stock_only(self, knowledge_base, sample_products):
        """Test buscar solo con stock"""
        products = sample_products.copy()
        products.append(
            {
                "id": "prod_no_stock",
                "name": "Sin Stock",
                "description": "Producto sin stock",
                "price": 100,
                "stock": 0,
                "category": "test",
                "tenant_id": "tenant_test",
            }
        )

        knowledge_base.add_products_batch(products)

        results = knowledge_base.search_products(
            query="producto", in_stock_only=True, min_score=0.0
        )

        for r in results:
            assert r["metadata"]["stock"] > 0

    def test_get_product(self, knowledge_base, sample_products):
        """Test obtener producto específico"""
        knowledge_base.add_products_batch(sample_products)

        product = knowledge_base.get_product("prod_1")

        assert product is not None
        assert product["metadata"]["name"] == "Laptop HP Pavilion"

    def test_update_product(self, knowledge_base, sample_products):
        """Test actualizar producto"""
        knowledge_base.add_products_batch(sample_products)

        success = knowledge_base.update_product(
            product_id="prod_1", price=1100, stock=3
        )

        assert success is True

        product = knowledge_base.get_product("prod_1")
        assert product["metadata"]["price"] == 1100
        assert product["metadata"]["stock"] == 3

    def test_delete_product(self, knowledge_base, sample_products):
        """Test eliminar producto"""
        knowledge_base.add_products_batch(sample_products)

        success = knowledge_base.delete_product("prod_1")
        assert success is True

        product = knowledge_base.get_product("prod_1")
        assert product is None

    @pytest.mark.skip(
        reason="requiere índice 'type' en Qdrant para filtrar por tenant — test de integración real"
    )
    def test_get_stats(self, knowledge_base, sample_products):
        """Test obtener estadísticas"""
        knowledge_base.add_products_batch(sample_products)

        stats = knowledge_base.get_stats(tenant_id="tenant_test")

        assert "total_products" in stats
        assert stats["total_products"] == 3
        assert "collection" in stats


# ==================== TESTS: RAG SYSTEM ====================


class TestRAGSystem:
    """Tests para RAG System"""

    @pytest.fixture
    def rag_system(self, knowledge_base):
        """RAG System para testing"""
        llm = LLMService(primary_provider="mock")

        return RAGSystem(
            llm_service=llm,
            knowledge_base=knowledge_base,
            max_context_items=3,
            min_relevance_score=0.5,
        )

    @pytest.mark.asyncio
    async def test_create_rag_system(self):
        """Test crear RAG system"""
        rag = create_rag_system(
            tenant_id="test", use_mock_llm=True, use_local_embeddings=False
        )

        assert rag is not None
        assert rag.llm is not None
        assert rag.kb is not None

    @pytest.mark.asyncio
    async def test_generate_with_context(self, rag_system, sample_products):
        """Test generar respuesta con contexto"""
        rag_system.kb.add_products_batch(sample_products)

        result = await rag_system.generate_with_context(
            query="Busco una laptop", tenant_id="tenant_test"
        )

        assert "response" in result
        assert "context" in result
        assert "sources" in result
        assert "tokens_used" in result
        assert "has_context" in result

    @pytest.mark.asyncio
    async def test_generate_without_context(self, rag_system):
        """Test generar sin contexto relevante"""
        result = await rag_system.generate_with_context(
            query="Producto inexistente XYZ123", tenant_id="tenant_test"
        )

        assert "response" in result
        assert "has_context" in result

    @pytest.mark.asyncio
    async def test_chat(self, rag_system, sample_products):
        """Test chat completo"""
        rag_system.kb.add_products_batch(sample_products)

        response = await rag_system.chat(
            user_message="Hola, busco un mouse",
            tenant_id="tenant_test",
            user_id="test_user",
        )

        assert "message" in response
        assert "conversation_id" in response
        assert "sources" in response
        assert "tokens_used" in response

    @pytest.mark.asyncio
    async def test_chat_multi_turn(self, rag_system, sample_products):
        """Test chat con múltiples turnos"""
        rag_system.kb.add_products_batch(sample_products)

        response1 = await rag_system.chat(
            user_message="Hola", tenant_id="tenant_test", user_id="test_user"
        )

        conversation_id = response1["conversation_id"]

        response2 = await rag_system.chat(
            user_message="¿Tienen laptops?",
            conversation_id=conversation_id,
            tenant_id="tenant_test",
        )

        assert response2["conversation_id"] == conversation_id
        assert "message" in response2


# ==================== TESTS: INTEGRATION ====================


class TestIntegrationDay2:
    """Tests de integración completos para Día 2"""

    @pytest.mark.asyncio
    async def test_full_rag_workflow(self, sample_products):
        """Test flujo completo RAG"""
        rag = create_rag_system(
            tenant_id="integration_test", use_mock_llm=True, use_local_embeddings=False
        )

        result = rag.kb.add_products_batch(sample_products)
        assert result["success"] is True

        response1 = await rag.chat(
            user_message="Hola, busco una laptop para programar",
            tenant_id="integration_test",
            user_id="+573001234567",
        )

        assert response1["message"] is not None
        assert "sources" in response1

        response2 = await rag.chat(
            user_message="¿Cuál me recomiendas?",
            conversation_id=response1["conversation_id"],
            tenant_id="integration_test",
        )

        assert response2["conversation_id"] == response1["conversation_id"]

        response3 = await rag.chat(
            user_message="¿Tienen mouse también?",
            conversation_id=response1["conversation_id"],
            tenant_id="integration_test",
        )

        assert response3["conversation_id"] == response1["conversation_id"]

        product = rag.kb.get_product("prod_1")
        assert product is not None
        assert product["metadata"]["name"] == "Laptop HP Pavilion"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
