"""
Tests Unitarios - 
=================================

Tests para:
- Message model
- Conversation model
- LLM Service
- Conversation Manager
"""
import pytest
from datetime import datetime, timezone
import asyncio

from src.models.conversation import (
    Message,
    Conversation,
    MessageRole,
    ConversationStatus,
    ConversationMetadata,
    create_user_message,
    create_assistant_message,
    create_system_message
)
from src.services.llm_service import (
    LLMService,
    MockLLMService,
    LLMServiceFactory
)
from src.services.conversation_manager import ConversationManager


# ==================== FIXTURES ====================

@pytest.fixture
def sample_metadata():
    """Metadata de ejemplo"""
    return ConversationMetadata(
        platform="whatsapp",
        user_phone="+573001234567",
        user_name="Test User"
    )


@pytest.fixture
def sample_conversation(sample_metadata):
    """Conversación de ejemplo"""
    return Conversation(
        tenant_id="tenant_test",
        metadata=sample_metadata
    )


@pytest.fixture
def conversation_manager():
    """Conversation Manager de ejemplo"""
    return ConversationManager(
        max_active_conversations=10,
        conversation_timeout_hours=1
    )


# ==================== TESTS: MESSAGE ====================

class TestMessage:
    """Tests para el modelo Message"""
    
    def test_create_message(self):
        """Test crear mensaje básico"""
        msg = Message(
            role=MessageRole.USER,
            content="Hola"
        )
        
        assert msg.role == MessageRole.USER
        assert msg.content == "Hola"
        assert msg.created_at is not None
        assert msg.metadata == {}
    
    def test_message_with_tokens(self):
        """Test mensaje con tokens"""
        msg = Message(
            role=MessageRole.ASSISTANT,
            content="Respuesta",
            tokens_used=50
        )
        
        assert msg.tokens_used == 50
    
    def test_message_to_dict(self):
        """Test convertir mensaje a dict"""
        msg = Message(
            role=MessageRole.USER,
            content="Test",
            message_id="msg_123"
        )
        
        data = msg.to_dict()
        
        assert data["id"] == "msg_123"
        assert data["role"] == "user"
        assert data["content"] == "Test"
        assert "created_at" in data
    
    def test_message_to_llm_format(self):
        """Test formato LLM"""
        msg = Message(
            role=MessageRole.USER,
            content="Hola"
        )
        
        llm_format = msg.to_llm_format()
        
        assert llm_format == {
            "role": "user",
            "content": "Hola"
        }
    
    def test_create_user_message_helper(self):
        """Test helper crear mensaje usuario"""
        msg = create_user_message("Test")
        
        assert msg.role == MessageRole.USER
        assert msg.content == "Test"
    
    def test_create_assistant_message_helper(self):
        """Test helper crear mensaje asistente"""
        msg = create_assistant_message("Response", tokens_used=25)
        
        assert msg.role == MessageRole.ASSISTANT
        assert msg.content == "Response"
        assert msg.tokens_used == 25
    
    def test_create_system_message_helper(self):
        """Test helper crear mensaje sistema"""
        msg = create_system_message("System prompt")
        
        assert msg.role == MessageRole.SYSTEM
        assert msg.content == "System prompt"


# ==================== TESTS: CONVERSATION ====================

class TestConversation:
    """Tests para el modelo Conversation"""
    
    def test_create_conversation(self, sample_metadata):
        """Test crear conversación"""
        conv = Conversation(
            tenant_id="tenant_123",
            metadata=sample_metadata
        )
        
        assert conv.tenant_id == "tenant_123"
        assert conv.status == ConversationStatus.ACTIVE
        assert len(conv.messages) == 0
        assert conv.total_tokens == 0
    
    def test_add_message(self, sample_conversation):
        """Test agregar mensaje"""
        msg = create_user_message("Hola")
        sample_conversation.add_message(msg)
        
        assert len(sample_conversation.messages) == 1
        assert sample_conversation.messages[0].content == "Hola"
    
    def test_add_message_with_tokens(self, sample_conversation):
        """Test agregar mensaje con tokens"""
        msg1 = create_user_message("Hola")
        msg2 = create_assistant_message("Respuesta", tokens_used=50)
        
        sample_conversation.add_message(msg1)
        sample_conversation.add_message(msg2)
        
        assert sample_conversation.total_tokens == 50
    
    def test_get_history(self, sample_conversation):
        """Test obtener historial"""
        sample_conversation.add_message(create_user_message("Msg 1"))
        sample_conversation.add_message(create_assistant_message("Msg 2"))
        sample_conversation.add_message(create_user_message("Msg 3"))
        
        history = sample_conversation.get_history()
        
        assert len(history) == 3
    
    def test_get_history_with_limit(self, sample_conversation):
        """Test historial con límite"""
        for i in range(5):
            sample_conversation.add_message(create_user_message(f"Msg {i}"))
        
        history = sample_conversation.get_history(limit=3)
        
        assert len(history) == 3
        # Debe retornar los 3 más recientes
        assert history[-1].content == "Msg 4"
    
    def test_get_history_without_system(self, sample_conversation):
        """Test historial sin mensajes del sistema"""
        sample_conversation.add_message(create_system_message("System"))
        sample_conversation.add_message(create_user_message("User"))
        sample_conversation.add_message(create_assistant_message("Assistant"))
        
        history = sample_conversation.get_history(include_system=False)
        
        assert len(history) == 2
        assert all(m.role != MessageRole.SYSTEM for m in history)
    
    def test_get_llm_history(self, sample_conversation):
        """Test historial formato LLM"""
        sample_conversation.add_message(create_user_message("Hola"))
        sample_conversation.add_message(create_assistant_message("Respuesta"))
        
        llm_history = sample_conversation.get_llm_history()
        
        assert len(llm_history) == 2
        assert llm_history[0] == {"role": "user", "content": "Hola"}
        assert llm_history[1] == {"role": "assistant", "content": "Respuesta"}
    
    def test_get_last_user_message(self, sample_conversation):
        """Test obtener último mensaje del usuario"""
        sample_conversation.add_message(create_user_message("First"))
        sample_conversation.add_message(create_assistant_message("Response"))
        sample_conversation.add_message(create_user_message("Second"))
        
        last_msg = sample_conversation.get_last_user_message()
        
        assert last_msg is not None
        assert last_msg.content == "Second"
    
    def test_update_context(self, sample_conversation):
        """Test actualizar contexto"""
        sample_conversation.update_context("product_id", "prod_123")
        
        assert sample_conversation.get_context("product_id") == "prod_123"
    
    def test_close_conversation(self, sample_conversation):
        """Test cerrar conversación"""
        sample_conversation.close()
        
        assert sample_conversation.status == ConversationStatus.CLOSED
    
    def test_archive_conversation(self, sample_conversation):
        """Test archivar conversación"""
        sample_conversation.archive()
        
        assert sample_conversation.status == ConversationStatus.ARCHIVED
    
    def test_conversation_to_dict(self, sample_conversation):
        """Test convertir conversación a dict"""
        sample_conversation.add_message(create_user_message("Test"))
        
        data = sample_conversation.to_dict()
        
        assert data["tenant_id"] == "tenant_test"
        assert data["status"] == "active"
        assert len(data["messages"]) == 1
        assert "metadata" in data
        assert "context" in data


# ==================== TESTS: LLM SERVICE ====================

class TestLLMService:
    """Tests para LLM Service"""
    
    def test_create_mock_service(self):
        """Test crear servicio mock"""
        service = MockLLMService()
        
        assert service is not None
    
    def test_mock_service_custom_responses(self):
        """Test mock con respuestas personalizadas"""
        responses = ["Response 1", "Response 2"]
        service = MockLLMService(responses=responses)
        
        assert service.responses == responses
    
    @pytest.mark.asyncio
    async def test_mock_generate(self):
        """Test generar con mock"""
        service = MockLLMService()
        
        response = await service.generate(
            messages=[{"role": "user", "content": "Test"}]
        )
        
        assert "content" in response
        assert "tokens_used" in response
        assert response["provider"] == "mock"
    
    @pytest.mark.asyncio
    async def test_mock_multiple_calls(self):
        """Test múltiples llamadas rotan respuestas"""
        responses = ["First", "Second", "Third"]
        service = MockLLMService(responses=responses)
        
        r1 = await service.generate([])
        r2 = await service.generate([])
        r3 = await service.generate([])
        r4 = await service.generate([])  # Debe volver a "First"
        
        assert r1["content"] == "First"
        assert r2["content"] == "Second"
        assert r3["content"] == "Third"
        assert r4["content"] == "First"
    
    def test_mock_count_tokens(self):
        """Test contar tokens en mock"""
        service = MockLLMService()
        
        tokens = service.count_tokens("Hello world test")
        
        assert tokens == 3  # Cuenta palabras en mock
    
    def test_factory_create_mock(self):
        """Test factory crear mock"""
        service = LLMServiceFactory.create("mock")
        
        assert isinstance(service, MockLLMService)
    
    def test_factory_invalid_provider(self):
        """Test factory con proveedor inválido"""
        with pytest.raises(ValueError):
            LLMServiceFactory.create("invalid_provider")
    
    @pytest.mark.asyncio
    async def test_unified_service(self):
        """Test servicio unificado"""
        service = LLMService(
            primary_provider="mock",
            fallback_provider="mock"
        )
        
        response = await service.generate(
            messages=[{"role": "user", "content": "Test"}]
        )
        
        assert response["provider"] == "mock"
    
    def test_unified_service_count_tokens(self):
        """Test contar tokens en servicio unificado"""
        service = LLMService(primary_provider="mock")
        
        tokens = service.count_tokens("Test message")
        
        assert tokens > 0


# ==================== TESTS: CONVERSATION MANAGER ====================

class TestConversationManager:
    """Tests para Conversation Manager"""
    
    def test_create_manager(self, conversation_manager):
        """Test crear manager"""
        assert conversation_manager is not None
        assert conversation_manager.max_active_conversations == 10
    
    def test_create_conversation(self, conversation_manager):
        """Test crear conversación"""
        conv = conversation_manager.create_conversation(
            tenant_id="tenant_test",
            user_phone="+573001234567",
            user_name="Test User"
        )
        
        assert conv is not None
        assert conv.tenant_id == "tenant_test"
        assert conv.id is not None
    
    def test_get_conversation(self, conversation_manager):
        """Test obtener conversación"""
        conv = conversation_manager.create_conversation(
            tenant_id="tenant_test",
            user_phone="+573001234567"
        )
        
        retrieved = conversation_manager.get_conversation(conv.id)
        
        assert retrieved is not None
        assert retrieved.id == conv.id
    
    def test_get_nonexistent_conversation(self, conversation_manager):
        """Test obtener conversación inexistente"""
        conv = conversation_manager.get_conversation("nonexistent_id")
        
        assert conv is None
    
    def test_get_or_create_new(self, conversation_manager):
        """Test obtener o crear (crea nueva)"""
        conv = conversation_manager.get_or_create_conversation(
            tenant_id="tenant_test",
            user_id="+573001234567"
        )
        
        assert conv is not None
        assert conv.status == ConversationStatus.ACTIVE
    
    def test_get_or_create_existing(self, conversation_manager):
        """Test obtener o crear (retorna existente)"""
        # Crear primera conversación
        conv1 = conversation_manager.get_or_create_conversation(
            tenant_id="tenant_test",
            user_id="+573001234567"
        )
        
        # Intentar obtener de nuevo
        conv2 = conversation_manager.get_or_create_conversation(
            tenant_id="tenant_test",
            user_id="+573001234567"
        )
        
        assert conv1.id == conv2.id
    
    def test_save_conversation(self, conversation_manager):
        """Test guardar conversación"""
        conv = conversation_manager.create_conversation(
            tenant_id="tenant_test"
        )
        
        conv.add_message(create_user_message("Test"))
        
        success = conversation_manager.save_conversation(conv)
        
        assert success is True
    
    def test_close_conversation(self, conversation_manager):
        """Test cerrar conversación"""
        conv = conversation_manager.create_conversation(
            tenant_id="tenant_test"
        )
        
        success = conversation_manager.close_conversation(conv.id)
        
        assert success is True
        
        # Verificar que se cerró
        retrieved = conversation_manager.get_conversation(conv.id)
        assert retrieved.status == ConversationStatus.CLOSED
    
    def test_list_conversations(self, conversation_manager):
        """Test listar conversaciones"""
        # Crear varias conversaciones
        for i in range(3):
            conversation_manager.create_conversation(
                tenant_id="tenant_test",
                user_phone=f"+57300123456{i}"
            )
        
        conversations = conversation_manager.list_conversations()
        
        assert len(conversations) >= 3
    
    def test_list_conversations_by_tenant(self, conversation_manager):
        """Test listar por tenant"""
        conversation_manager.create_conversation(tenant_id="tenant_1")
        conversation_manager.create_conversation(tenant_id="tenant_2")
        conversation_manager.create_conversation(tenant_id="tenant_1")
        
        tenant1_convs = conversation_manager.list_conversations(tenant_id="tenant_1")
        
        assert len(tenant1_convs) == 2
        assert all(c.tenant_id == "tenant_1" for c in tenant1_convs)
    
    def test_list_conversations_by_status(self, conversation_manager):
        """Test listar por estado"""
        conv1 = conversation_manager.create_conversation(tenant_id="tenant_test")
        conv2 = conversation_manager.create_conversation(tenant_id="tenant_test")
        
        conversation_manager.close_conversation(conv1.id)
        
        active = conversation_manager.list_conversations(
            status=ConversationStatus.ACTIVE
        )
        closed = conversation_manager.list_conversations(
            status=ConversationStatus.CLOSED
        )
        
        assert len(closed) >= 1
        assert all(c.status == ConversationStatus.CLOSED for c in closed)
    
    def test_get_active_conversations(self, conversation_manager):
        """Test obtener conversaciones activas"""
        conversation_manager.create_conversation(tenant_id="tenant_test")
        conversation_manager.create_conversation(tenant_id="tenant_test")
        
        active = conversation_manager.get_active_conversations("tenant_test")
        
        assert len(active) == 2
        assert all(c.status == ConversationStatus.ACTIVE for c in active)
    
    def test_get_stats(self, conversation_manager):
        """Test obtener estadísticas"""
        # Crear conversaciones
        conv1 = conversation_manager.create_conversation(tenant_id="tenant_test")
        conv2 = conversation_manager.create_conversation(tenant_id="tenant_test")
        
        # Agregar mensajes
        conv1.add_message(create_user_message("Test"))
        conv1.add_message(create_assistant_message("Response", tokens_used=25))
        
        # Cerrar una
        conversation_manager.close_conversation(conv2.id)
        
        # Obtener stats
        stats = conversation_manager.get_stats(tenant_id="tenant_test")
        
        assert stats["total"] == 2
        assert stats["active"] == 1
        assert stats["closed"] == 1
        assert stats["total_messages"] == 2
        assert stats["total_tokens"] == 25


# ==================== TESTS: INTEGRATION ====================

class TestIntegration:
    """Tests de integración completos"""
    
    @pytest.mark.asyncio
    async def test_full_conversation_flow(self, conversation_manager):
        """Test flujo completo de conversación"""
        # 1. Crear conversación
        conv = conversation_manager.create_conversation(
            tenant_id="tenant_test",
            user_phone="+573001234567",
            user_name="Test User",
            system_prompt="Eres un asistente de ventas"
        )
        
        # 2. Crear LLM service
        llm = LLMService(primary_provider="mock")
        
        # 3. Simular conversación
        user_messages = ["Hola", "¿Tienen productos?", "Gracias"]
        
        for user_text in user_messages:
            # Agregar mensaje usuario
            user_msg = create_user_message(user_text)
            conv.add_message(user_msg)
            
            # Generar respuesta
            response = await llm.generate(conv.get_llm_history())
            
            # Agregar respuesta
            assistant_msg = create_assistant_message(
                response["content"],
                tokens_used=response["tokens_used"]
            )
            conv.add_message(assistant_msg)
        
        # 4. Guardar
        conversation_manager.save_conversation(conv)
        
        # 5. Verificar
        assert len(conv.messages) == 7  # 1 system + 3 user + 3 assistant
        assert conv.total_tokens > 0
        
        # 6. Verificar que se puede recuperar
        retrieved = conversation_manager.get_conversation(conv.id)
        assert retrieved is not None
        assert len(retrieved.messages) == 7