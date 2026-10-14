"""
Tests de Integración WhatsApp + Agente IA

"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.integrations.whatsapp_agent_bridge import WhatsAppAgentBridge
from src.services.agent_orchestrator import AgentOrchestrator
from src.core.whatsapp_handler import WhatsAppHandler


# ============================================
# FIXTURES
# ============================================

@pytest.fixture
def tenant_id():
    """ID del tenant de prueba."""
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def whatsapp_mock():
    """Mock del WhatsAppHandler."""
    mock = MagicMock(spec=WhatsAppHandler)
    # Simular métodos async
    mock.send_message = AsyncMock()
    mock.send_image = AsyncMock()
    mock.last_sent_message = None
    mock.last_sent_image = None
    # Side effect para send_message
    async def mock_send_message(phone_number, message):
        mock.last_sent_message = message
        return True
    mock.send_message.side_effect = mock_send_message
    # Side effect para send_image
    async def mock_send_image(phone_number, image_url, caption=None):
        mock.last_sent_image = image_url
        return True
    mock.send_image.side_effect = mock_send_image
    return mock


@pytest.fixture
def agent_orchestrator_mock():
    """Mock del AgentOrchestrator."""
    mock = MagicMock(spec=AgentOrchestrator)
    
    # Simular respuesta del agente
    mock.process_message = AsyncMock(return_value={
        "response": "¡Hola! Claro, tenemos sillas ejecutivas disponibles.",
        "intent": "product_search",
        "confidence": 0.95,
        "products": [
            {
                "id": "prod_123",
                "name": "Silla Ejecutiva Premium",
                "price": 250000,
                "image_url": "https://example.com/silla.jpg"
            }
        ]
    })
    
    return mock


@pytest.fixture
def bridge(whatsapp_mock, agent_orchestrator_mock):
    """Instancia del bridge con mocks."""
    return WhatsAppAgentBridge(
        whatsapp_handler=whatsapp_mock,
        agent_orchestrator=agent_orchestrator_mock
    )


# ============================================
# TESTS E2E
# ============================================

@pytest.mark.asyncio
async def test_full_flow_whatsapp_to_agent(bridge, whatsapp_mock, agent_orchestrator_mock, tenant_id):
    """
    Test E2E: Mensaje WhatsApp → Agente → Respuesta WhatsApp
    """
    # 1. Simular mensaje entrante
    phone = "+573001234567"
    message = "Hola, busco sillas ejecutivas"
    
    # 2. Procesar con bridge
    await bridge.handle_incoming_message(
        phone_number=phone,
        message_text=message,
        tenant_id=tenant_id
    )
    
    # 3. Verificar que el agente fue llamado
    agent_orchestrator_mock.process_message.assert_called_once()
    call_args = agent_orchestrator_mock.process_message.call_args
    
    assert call_args.kwargs["message"] == message
    assert call_args.kwargs["tenant_id"] == tenant_id
    assert f"wa_{tenant_id}_{phone}" in call_args.kwargs["conversation_id"]
    
    # 4. Verificar que se envió respuesta por WhatsApp
    whatsapp_mock.send_message.assert_called()
    assert whatsapp_mock.last_sent_message is not None
    assert "sillas" in whatsapp_mock.last_sent_message.lower()


@pytest.mark.asyncio
async def test_greeting_flow(bridge, whatsapp_mock, agent_orchestrator_mock, tenant_id):
    """
    Test: Usuario saluda por WhatsApp
    """
    # Configurar respuesta del agente
    agent_orchestrator_mock.process_message.return_value = {
        "response": "¡Hola! ¿En qué puedo ayudarte hoy?",
        "intent": "greeting",
        "confidence": 0.98
    }
    
    # Ejecutar
    await bridge.handle_incoming_message(
        phone_number="+573001234567",
        message_text="Hola",
        tenant_id=tenant_id
    )
    
    # Verificar
    assert "Hola" in whatsapp_mock.last_sent_message


@pytest.mark.asyncio
async def test_product_search_flow(bridge, whatsapp_mock, agent_orchestrator_mock, tenant_id):
    """
    Test: Usuario busca producto
    """
    # Configurar respuesta con productos
    agent_orchestrator_mock.process_message.return_value = {
        "response": "Encontré 3 escritorios disponibles:\n1. Escritorio Ejecutivo...",
        "intent": "product_search",
        "confidence": 0.92,
        "products": [
            {"id": "1", "name": "Escritorio A", "price": 500000, "image_url": "http://img1.jpg"},
            {"id": "2", "name": "Escritorio B", "price": 600000, "image_url": "http://img2.jpg"},
        ]
    }
    
    # Ejecutar
    await bridge.handle_incoming_message(
        phone_number="+573001234567",
        message_text="Busco escritorios",
        tenant_id=tenant_id
    )
    
    # Verificar respuesta
    assert "Escritorio" in whatsapp_mock.last_sent_message
    
    # Verificar que envió imágenes
    assert whatsapp_mock.send_image.call_count == 2


@pytest.mark.asyncio
async def test_price_inquiry_flow(bridge, whatsapp_mock, agent_orchestrator_mock, tenant_id):
    """
    Test: Usuario pregunta precio
    """
    agent_orchestrator_mock.process_message.return_value = {
        "response": "La silla ejecutiva cuesta $250,000 pesos.",
        "intent": "price_inquiry",
        "confidence": 0.88
    }
    
    await bridge.handle_incoming_message(
        phone_number="+573001234567",
        message_text="Cuánto cuesta la silla?",
        tenant_id=tenant_id
    )
    
    assert "250,000" in whatsapp_mock.last_sent_message or "250000" in whatsapp_mock.last_sent_message


@pytest.mark.asyncio
async def test_multi_turn_conversation(bridge, whatsapp_mock, agent_orchestrator_mock, tenant_id):
    """
    Test: Conversación multi-turno mantiene contexto
    """
    phone = "+573001234567"
    
    # Turno 1: Buscar producto
    agent_orchestrator_mock.process_message.return_value = {
        "response": "Tenemos escritorios en varios materiales",
        "intent": "product_search",
        "confidence": 0.90
    }
    
    await bridge.handle_incoming_message(phone, "Busco escritorios", tenant_id)
    
    # Turno 2: Especificar material
    agent_orchestrator_mock.process_message.return_value = {
        "response": "Perfecto, tenemos 5 escritorios en madera",
        "intent": "product_search",
        "confidence": 0.93
    }
    
    await bridge.handle_incoming_message(phone, "En madera", tenant_id)
    
    # Verificar que se llamó 2 veces con el mismo conversation_id
    assert agent_orchestrator_mock.process_message.call_count == 2
    
    # Ambas llamadas deben tener el mismo conversation_id
    calls = agent_orchestrator_mock.process_message.call_args_list
    conv_id_1 = calls[0].kwargs["conversation_id"]
    conv_id_2 = calls[1].kwargs["conversation_id"]
    
    assert conv_id_1 == conv_id_2  # Mismo ID = mismo contexto


@pytest.mark.asyncio
async def test_error_recovery(bridge, whatsapp_mock, agent_orchestrator_mock, tenant_id):
    """
    Test: Error en agente envía mensaje de fallback
    """
    # Configurar agente para fallar
    agent_orchestrator_mock.process_message.side_effect = Exception("Error interno del agente")
    
    # Ejecutar
    await bridge.handle_incoming_message(
        phone_number="+573001234567",
        message_text="Cualquier mensaje",
        tenant_id=tenant_id
    )
    
    # Verificar que se envió mensaje de error
    assert whatsapp_mock.send_message.call_count >= 1
    assert "problema" in whatsapp_mock.last_sent_message.lower() or "disculpa" in whatsapp_mock.last_sent_message.lower()


@pytest.mark.asyncio
async def test_products_without_images(bridge, whatsapp_mock, agent_orchestrator_mock, tenant_id):
    """
    Test: Productos sin imagen no rompen el flujo
    """
    # Productos sin image_url
    agent_orchestrator_mock.process_message.return_value = {
        "response": "Encontré productos",
        "intent": "product_search",
        "confidence": 0.85,
        "products": [
            {"id": "1", "name": "Producto A", "price": 100000},  # Sin image_url
            {"id": "2", "name": "Producto B", "price": 200000, "image_url": None},  # image_url null
        ]
    }
    
    # No debe fallar
    await bridge.handle_incoming_message(
        phone_number="+573001234567",
        message_text="Busco productos",
        tenant_id=tenant_id
    )
    
    # Debe responder pero no enviar imágenes
    assert whatsapp_mock.send_message.called
    assert whatsapp_mock.send_image.call_count == 0


@pytest.mark.asyncio
async def test_max_3_product_images(bridge, whatsapp_mock, agent_orchestrator_mock, tenant_id):
    """
    Test: Máximo 3 imágenes de productos aunque haya más
    """
    # 5 productos con imagen
    agent_orchestrator_mock.process_message.return_value = {
        "response": "Encontré 5 productos",
        "intent": "product_search",
        "confidence": 0.90,
        "products": [
            {"id": str(i), "name": f"Producto {i}", "price": 100000, "image_url": f"http://img{i}.jpg"}
            for i in range(1, 6)
        ]
    }
    
    await bridge.handle_incoming_message(
        phone_number="+573001234567",
        message_text="Busco productos",
        tenant_id=tenant_id
    )
    
    # Solo debe enviar 3 imágenes
    assert whatsapp_mock.send_image.call_count == 3


# ============================================
# TESTS DE METADATA
# ============================================

@pytest.mark.asyncio
async def test_metadata_includes_whatsapp_source(bridge, whatsapp_mock, agent_orchestrator_mock, tenant_id):
    """
    Test: Metadata incluye fuente WhatsApp
    """
    phone = "+573001234567"
    
    await bridge.handle_incoming_message(phone, "Test", tenant_id)
    
    # Verificar metadata
    call_args = agent_orchestrator_mock.process_message.call_args
    metadata = call_args.kwargs.get("metadata", {})
    
    assert metadata["source"] == "whatsapp"
    assert metadata["phone_number"] == phone


# ============================================
# TESTS DE CONVERSACIÓN
# ============================================

@pytest.mark.asyncio
async def test_conversation_id_format(bridge, whatsapp_mock, agent_orchestrator_mock, tenant_id):
    """
    Test: conversation_id tiene formato correcto
    """
    phone = "+573001234567"
    
    await bridge.handle_incoming_message(phone, "Test", tenant_id)
    
    call_args = agent_orchestrator_mock.process_message.call_args
    conv_id = call_args.kwargs["conversation_id"]
    
    # Formato: wa_{tenant_id}_{phone}
    assert conv_id.startswith("wa_")
    assert tenant_id in conv_id
    assert phone.replace("+", "") in conv_id or phone in conv_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])