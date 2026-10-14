"""
Tests - Intent Recognition & Response Generation

Tests para:
- IntentClassifier
- AdvancedContextManager  
- ResponseGenerator
- AgentOrchestrator
"""
import pytest
from datetime import datetime

from src.services.intent_classifier import (
    IntentClassifier,
    Intent,
    create_intent_classifier
)
from src.services.context_manager import (
    AdvancedContextManager,
    ConversationContext,
    ConversationStage,
    ProductMention,
    UserPreferences,
    create_advanced_context_manager
)
from src.services.response_generator import (
    ResponseGenerator,
    create_response_generator
)
from src.services.agent_orchestrator import (
    AgentOrchestrator,
    create_agent_orchestrator
)


# ==================== FIXTURES ====================

@pytest.fixture
def intent_classifier():
    """Fixture para IntentClassifier"""
    return IntentClassifier(confidence_threshold=0.3)


@pytest.fixture
def context_manager():
    """Fixture para AdvancedContextManager"""
    return AdvancedContextManager()


@pytest.fixture
def response_generator():
    """Fixture para ResponseGenerator"""
    return ResponseGenerator()


@pytest.fixture
def sample_context(context_manager):
    """Fixture para contexto de ejemplo"""
    return context_manager.create_context(
        conversation_id="conv_test_123",
        tenant_id="tenant_test",
        user_id="user_001"
    )


@pytest.fixture
def sample_rag_results():
    """Fixture para resultados RAG de ejemplo"""
    return [
        {
            "id": "prod_1",
            "score": 0.85,
            "text": "Laptop para programación con Intel i7, 16GB RAM",
            "metadata": {
                "name": "Laptop HP",
                "price": 1200,
                "stock": 5,
                "category": "laptops"
            }
        },
        {
            "id": "prod_2",
            "score": 0.75,
            "text": "Mouse gamer RGB con 16000 DPI",
            "metadata": {
                "name": "Mouse Gamer",
                "price": 80,
                "stock": 15,
                "category": "mouse"
            }
        }
    ]


# ==================== TESTS INTENT CLASSIFIER ====================

class TestIntentClassifier:
    """Tests para IntentClassifier"""
    
    def test_create_classifier(self, intent_classifier):
        """Test crear clasificador"""
        assert intent_classifier is not None
        assert intent_classifier.confidence_threshold == 0.3
    
    def test_classify_product_search(self, intent_classifier):
        """Test clasificar búsqueda de producto"""
        messages = [
            "Busco una laptop para programar",
            "Necesito un mouse gamer",
            "Quiero ver teclados mecánicos",
            "Tienes laptops disponibles?"
        ]
        
        for msg in messages:
            result = intent_classifier.classify(msg)
            assert result.intent == "product_search"
            assert result.confidence > 0.3
    
    def test_classify_price_inquiry(self, intent_classifier):
        """Test clasificar consulta de precio"""
        messages = [
            "Cuánto cuesta la laptop?",
            "Qué precio tiene el mouse?",
            "Cuál es el valor del teclado?",
            "Es muy caro?"
        ]
        
        for msg in messages:
            result = intent_classifier.classify(msg)
            assert result.intent == "price_inquiry"
    
    def test_classify_availability(self, intent_classifier):
        """Test clasificar disponibilidad"""
        messages = [
            "Hay stock de laptops?",
            "Está disponible el mouse?",
            "Tienen en inventario?",
            "Cuándo llega?"
        ]
        
        for msg in messages:
            result = intent_classifier.classify(msg)
            assert result.intent == "availability"
    
    def test_classify_purchase_intent(self, intent_classifier):
        """Test clasificar intención de compra"""
        messages = [
            "Quiero comprar la laptop",
            "Me lo llevo",
            "Agregar al carrito",
            "Proceder con la compra"
        ]
        
        for msg in messages:
            result = intent_classifier.classify(msg)
            assert result.intent == "purchase_intent"
    
    def test_classify_greeting(self, intent_classifier):
        """Test clasificar saludo"""
        messages = [
            "Hola",
            "Buenos días",
            "Qué tal?",
            "Buenas tardes"
        ]
        
        for msg in messages:
            result = intent_classifier.classify(msg)
            assert result.intent == "greeting"
    
    def test_classify_complaint(self, intent_classifier):
        """Test clasificar queja"""
        messages = [
            "El producto no funciona",
            "Tengo un problema",
            "Quiero devolver esto",
            "Producto defectuoso"
        ]
        
        for msg in messages:
            result = intent_classifier.classify(msg)
            assert result.intent == "complaint"
    
    def test_extract_entities(self, intent_classifier):
        """Test extracción de entidades"""
        message = "Busco una laptop HP de $1000 con 2 unidades"
        result = intent_classifier.classify(message)
        
        assert "price" in result.entities or "quantity" in result.entities
    
    def test_confidence_scores(self, intent_classifier):
        """Test scores de confianza"""
        # Alta confianza
        result1 = intent_classifier.classify("Busco una laptop para programar")
        assert result1.confidence > 0.5
        
        # Baja confianza (ambiguo)
        result2 = intent_classifier.classify("ok")
        assert result2.confidence <= 0.5 or result2.intent == "other"
    
    def test_classify_batch(self, intent_classifier):
        """Test clasificación en batch"""
        messages = [
            "Hola",
            "Busco laptops",
            "Cuánto cuesta?"
        ]
        
        results = intent_classifier.classify_batch(messages)
        assert len(results) == 3
        assert all(isinstance(r, Intent) for r in results)
    
    def test_factory_create(self):
        """Test factory para crear clasificador"""
        classifier = create_intent_classifier(confidence_threshold=0.5)
        assert classifier.confidence_threshold == 0.5


# ==================== TESTS CONTEXT MANAGER ====================

class TestAdvancedContextManager:
    """Tests para AdvancedContextManager"""
    
    def test_create_context(self, context_manager):
        """Test crear contexto"""
        context = context_manager.create_context(
            conversation_id="test_123",
            tenant_id="tenant_1",
            user_id="user_1"
        )
        
        assert context.conversation_id == "test_123"
        assert context.tenant_id == "tenant_1"
        assert context.user_id == "user_1"
        assert context.current_stage == ConversationStage.DISCOVERY
    
    def test_get_context(self, context_manager, sample_context):
        """Test obtener contexto"""
        retrieved = context_manager.get_context(sample_context.conversation_id)
        assert retrieved is not None
        assert retrieved.conversation_id == sample_context.conversation_id
    
    def test_update_with_intent(self, context_manager, sample_context):
        """Test actualizar con intent"""
        intent = Intent(
            intent="product_search",
            confidence=0.8,
            entities={"product_type": "laptop"},
            keywords_matched=["busco", "laptop"]
        )
        
        updated = context_manager.update_with_intent(
            sample_context.conversation_id,
            intent
        )
        
        assert len(updated.intent_history) == 1
        assert updated.intent_history[0].intent == "product_search"
        assert updated.message_count == 1
    
    def test_intent_history_limit(self, context_manager, sample_context):
        """Test límite de historial de intents"""
        # Agregar más intents que el límite
        for i in range(25):
            intent = Intent(
                intent="product_search",
                confidence=0.8,
                entities={},
                keywords_matched=[]
            )
            context_manager.update_with_intent(
                sample_context.conversation_id,
                intent
            )
        
        context = context_manager.get_context(sample_context.conversation_id)
        assert len(context.intent_history) <= 20  # Max por defecto
    
    def test_add_product_mention(self, context_manager, sample_context):
        """Test agregar producto mencionado"""
        context_manager.add_product_mention(
            sample_context.conversation_id,
            product_id="prod_1",
            product_name="Laptop HP",
            interest_level=0.8
        )
        
        context = context_manager.get_context(sample_context.conversation_id)
        assert len(context.mentioned_products) == 1
        assert context.mentioned_products[0].product_id == "prod_1"
    
    def test_product_mention_update(self, context_manager, sample_context):
        """Test actualizar producto mencionado"""
        # Agregar producto
        context_manager.add_product_mention(
            sample_context.conversation_id,
            product_id="prod_1",
            product_name="Laptop",
            interest_level=0.5
        )
        
        # Mencionar de nuevo con mayor interés
        context_manager.add_product_mention(
            sample_context.conversation_id,
            product_id="prod_1",
            product_name="Laptop",
            interest_level=0.9
        )
        
        context = context_manager.get_context(sample_context.conversation_id)
        assert len(context.mentioned_products) == 1
        assert context.mentioned_products[0].interest_level == 0.9
    
    def test_get_last_intents(self, context_manager, sample_context):
        """Test obtener últimos intents"""
        # Agregar intents
        for i in range(10):
            intent = Intent(
                intent="product_search",
                confidence=0.8,
                entities={},
                keywords_matched=[]
            )
            context_manager.update_with_intent(
                sample_context.conversation_id,
                intent
            )
        
        last_5 = context_manager.get_last_intents(
            sample_context.conversation_id,
            n=5
        )
        assert len(last_5) == 5
    
    def test_get_mentioned_products(self, context_manager, sample_context):
        """Test obtener productos mencionados"""
        context_manager.add_product_mention(
            sample_context.conversation_id,
            product_name="Laptop",
            interest_level=0.8
        )
        context_manager.add_product_mention(
            sample_context.conversation_id,
            product_name="Mouse",
            interest_level=0.3
        )
        
        products = context_manager.get_mentioned_products(
            sample_context.conversation_id,
            min_interest=0.5
        )
        
        assert len(products) == 1  # Solo laptop >= 0.5
    
    def test_conversation_summary(self, context_manager, sample_context):
        """Test resumen de conversación"""
        # Agregar datos
        intent = Intent(
            intent="product_search",
            confidence=0.8,
            entities={},
            keywords_matched=[]
        )
        context_manager.update_with_intent(sample_context.conversation_id, intent)
        
        summary = context_manager.get_conversation_summary(
            sample_context.conversation_id
        )
        
        assert "conversation_id" in summary
        assert "stage" in summary
        assert "message_count" in summary
    
    def test_reset_context(self, context_manager, sample_context):
        """Test resetear contexto"""
        context_manager.reset_context(sample_context.conversation_id)
        
        retrieved = context_manager.get_context(sample_context.conversation_id)
        assert retrieved is None
    
    def test_stage_inference(self, context_manager, sample_context):
        """Test inferencia de stage"""
        # Agregar intents de búsqueda → DISCOVERY
        for i in range(2):
            intent = Intent(
                intent="product_search",
                confidence=0.8,
                entities={},
                keywords_matched=[]
            )
            context_manager.update_with_intent(sample_context.conversation_id, intent)
        
        context = context_manager.get_context(sample_context.conversation_id)
        assert context.current_stage == ConversationStage.DISCOVERY
        
        # Agregar intents de info → COMPARISON
        for i in range(2):
            intent = Intent(
                intent="product_info",
                confidence=0.8,
                entities={},
                keywords_matched=[]
            )
            context_manager.update_with_intent(sample_context.conversation_id, intent)
        
        context = context_manager.get_context(sample_context.conversation_id)
        assert context.current_stage == ConversationStage.COMPARISON
    
    def test_factory_create(self):
        """Test factory para crear context manager"""
        manager = create_advanced_context_manager(max_intent_history=10)
        assert manager.max_intent_history == 10


# ==================== TESTS RESPONSE GENERATOR ====================

class TestResponseGenerator:
    """Tests para ResponseGenerator"""
    
    def test_create_generator(self, response_generator):
        """Test crear generador"""
        assert response_generator is not None
    
    def test_generate_product_search_with_results(
        self,
        response_generator,
        sample_context,
        sample_rag_results
    ):
        """Test generar respuesta para búsqueda con resultados"""
        response = response_generator.generate(
            intent="product_search",
            context=sample_context,
            rag_results=sample_rag_results
        )
        
        assert response is not None
        assert len(response) > 0
        assert "Laptop HP" in response or "producto" in response.lower()
    
    def test_generate_product_search_no_results(
        self,
        response_generator,
        sample_context
    ):
        """Test generar respuesta para búsqueda sin resultados"""
        response = response_generator.generate(
            intent="product_search",
            context=sample_context,
            rag_results=[]
        )
        
        assert response is not None
        assert "alternativa" in response.lower() or "similar" in response.lower()
    
    def test_generate_price_inquiry(
        self,
        response_generator,
        sample_context,
        sample_rag_results
    ):
        """Test generar respuesta para precio"""
        response = response_generator.generate(
            intent="price_inquiry",
            context=sample_context,
            rag_results=sample_rag_results[:1]
        )
        
        assert response is not None
        assert "$" in response or "precio" in response.lower()
    
    def test_generate_availability(
        self,
        response_generator,
        sample_context,
        sample_rag_results
    ):
        """Test generar respuesta para disponibilidad"""
        response = response_generator.generate(
            intent="availability",
            context=sample_context,
            rag_results=sample_rag_results[:1]
        )
        
        assert response is not None
        assert "disponible" in response.lower() or "stock" in response.lower()
    
    def test_generate_greeting(self, response_generator, sample_context):
        """Test generar respuesta para saludo"""
        response = response_generator.generate(
            intent="greeting",
            context=sample_context
        )
        
        assert response is not None
        assert any(word in response.lower() for word in ["hola", "bienvenido", "ayud"])
    
    def test_generate_fallback(self, response_generator):
        """Test generar respuesta fallback"""
        response = response_generator.generate(
            intent="other",
            context=None,
            rag_results=None
        )
        
        assert response is not None
        assert len(response) > 0
    
    def test_factory_create(self):
        """Test factory para crear response generator"""
        generator = create_response_generator(use_emojis=False)
        assert generator.use_emojis is False


# ==================== TESTS AGENT ORCHESTRATOR ====================

class TestAgentOrchestrator:
    """Tests para AgentOrchestrator"""
    
    @pytest.mark.asyncio
    async def test_process_message_product_search(self):
        """Test procesar mensaje de búsqueda de producto"""
        orchestrator = create_agent_orchestrator(
            tenant_id="test_tenant",
            use_mock_llm=True,
            use_local_embeddings=False
        )
        
        result = await orchestrator.process_message(
            message="Busco una laptop para programar",
            conversation_id="conv_test_1",
            tenant_id="test_tenant"
        )
        
        assert "message" in result
        assert "intent" in result
        assert result["intent"]["type"] == "product_search"
        assert "conversation_id" in result
    
    @pytest.mark.asyncio
    async def test_process_message_greeting(self):
        """Test procesar saludo"""
        orchestrator = create_agent_orchestrator(
            tenant_id="test_tenant",
            use_mock_llm=True
        )
        
        result = await orchestrator.process_message(
            message="Hola",
            conversation_id="conv_test_2",
            tenant_id="test_tenant"
        )
        
        assert "message" in result
        assert result["intent"]["type"] == "greeting"
    
    @pytest.mark.asyncio
    async def test_process_batch(self):
        """Test procesar múltiples mensajes"""
        orchestrator = create_agent_orchestrator(
            tenant_id="test_tenant",
            use_mock_llm=True
        )
        
        messages = [
            "Hola",
            "Busco laptops",
            "Cuánto cuesta?"
        ]
        
        results = await orchestrator.process_batch(
            messages=messages,
            conversation_id="conv_test_3",
            tenant_id="test_tenant"
        )
        
        assert len(results) == 3
        assert all("message" in r for r in results)
    
    @pytest.mark.asyncio
    async def test_conversation_summary(self):
        """Test obtener resumen de conversación"""
        orchestrator = create_agent_orchestrator(
            tenant_id="test_tenant",
            use_mock_llm=True
        )
        
        # Procesar mensajes
        await orchestrator.process_message(
            message="Hola",
            conversation_id="conv_test_4",
            tenant_id="test_tenant"
        )
        
        await orchestrator.process_message(
            message="Busco laptops",
            conversation_id="conv_test_4",
            tenant_id="test_tenant"
        )
        
        # Obtener resumen
        summary = orchestrator.get_conversation_summary("conv_test_4")
        
        assert "conversation_id" in summary
        assert "message_count" in summary
        assert summary["message_count"] == 2
    
    @pytest.mark.asyncio
    async def test_reset_conversation(self):
        """Test resetear conversación"""
        orchestrator = create_agent_orchestrator(
            tenant_id="test_tenant",
            use_mock_llm=True
        )
        
        # Crear conversación
        await orchestrator.process_message(
            message="Hola",
            conversation_id="conv_test_5",
            tenant_id="test_tenant"
        )
        
        # Resetear
        orchestrator.reset_conversation("conv_test_5")
        
        # Verificar que se reseteó
        summary = orchestrator.get_conversation_summary("conv_test_5")
        assert summary == {}


# ==================== TEST INTEGRACIÓN DÍA 3 ====================

class TestIntegrationDay3:
    """Tests de integración para Día 3"""
    
    @pytest.mark.asyncio
    async def test_full_conversation_flow(self):
        """Test flujo completo de conversación"""
        orchestrator = create_agent_orchestrator(
            tenant_id="integration_test",
            use_mock_llm=True,
            use_local_embeddings=False
        )
        
        # 1. Saludo
        r1 = await orchestrator.process_message(
            message="Hola",
            conversation_id="conv_integration",
            tenant_id="integration_test"
        )
        assert r1["intent"]["type"] == "greeting"
        
        # 2. Búsqueda
        r2 = await orchestrator.process_message(
            message="Busco una laptop para programar",
            conversation_id="conv_integration",
            tenant_id="integration_test"
        )
        assert r2["intent"]["type"] == "product_search"
        
        # 3. Precio
        r3 = await orchestrator.process_message(
            message="Cuánto cuesta?",
            conversation_id="conv_integration",
            tenant_id="integration_test"
        )
        assert r3["intent"]["type"] == "price_inquiry"
        
        # 4. Resumen
        summary = orchestrator.get_conversation_summary("conv_integration")
        assert summary["message_count"] == 3


# ==================== PYTEST CONFIG ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])