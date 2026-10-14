"""
Tests de integración avanzados
"""
import pytest
import asyncio
from src.services.agent_orchestrator import create_agent_orchestrator

class TestAdvancedIntegration:
    """Tests de flujos complejos"""
    
    @pytest.mark.asyncio
    async def test_conversation_with_context_persistence(self):
        """Test conversación con contexto persistente"""
        orchestrator = create_agent_orchestrator(
            tenant_id="test_advanced",
            use_mock_llm=True,
            use_local_embeddings=True
        )
        
        conv_id = "conv_context_test"
        
        # 1. Saludo
        r1 = await orchestrator.process_message(
            message="Hola",
            conversation_id=conv_id,
            tenant_id="test_advanced"
        )
        assert "message" in r1
        assert r1["intent"]["type"] == "greeting"
        
        # 2. Búsqueda
        r2 = await orchestrator.process_message(
            message="Busco una laptop",
            conversation_id=conv_id,
            tenant_id="test_advanced"
        )
        assert r2["intent"]["type"] == "product_search"
        
        # 3. Pregunta contextual (sin mencionar "laptop")
        r3 = await orchestrator.process_message(
            message="Cuánto cuesta?",
            conversation_id=conv_id,
            tenant_id="test_advanced"
        )
        # Debe entender contexto
        assert "message" in r3
        
        print("✅ Test de contexto persistente pasó")
    
    @pytest.mark.asyncio
    async def test_error_recovery(self):
        """Test recuperación de errores"""
        orchestrator = create_agent_orchestrator(
            tenant_id="test_error",
            use_mock_llm=True
        )
        
        # Enviar mensaje vacío
        result = await orchestrator.process_message(
            message="",
            conversation_id="conv_error",
            tenant_id="test_error"
        )
        
        # Debe manejar gracefully
        assert "message" in result
        
        print("✅ Test de error recovery pasó")
    
    @pytest.mark.asyncio
    async def test_concurrent_conversations(self):
        """Test múltiples conversaciones simultáneas"""
        orchestrator = create_agent_orchestrator(
            tenant_id="test_concurrent",
            use_mock_llm=True
        )
        
        # 3 conversaciones simultáneas
        tasks = [
            orchestrator.process_message(
                f"Mensaje {i}",
                f"conv_{i}",
                "test_concurrent"
            )
            for i in range(3)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Todas deben completarse
        assert len(results) == 3
        for r in results:
            assert "message" in r
        
        print("✅ Test de concurrencia pasó")
    
    @pytest.mark.asyncio
    async def test_multiple_intents_in_sequence(self):
        """Test secuencia de diferentes intents"""
        orchestrator = create_agent_orchestrator(
            tenant_id="test_sequence",
            use_mock_llm=True
        )
        
        conv_id = "conv_sequence"
        
        messages = [
            "Hola",
            "Busco laptop",
            "Cuánto cuesta?",
            "Tienen en stock?"
        ]
        
        for message in messages:
            result = await orchestrator.process_message(
                message=message,
                conversation_id=conv_id,
                tenant_id="test_sequence"
            )
            
            assert "message" in result
            # Verificar que detectó un intent válido
            assert "intent" in result
            
        print("✅ Test de secuencia de intents pasó")
    
    @pytest.mark.asyncio
    async def test_conversation_summary(self):
        """Test resumen de conversación"""
        orchestrator = create_agent_orchestrator(
            tenant_id="test_summary",
            use_mock_llm=True
        )
        
        conv_id = "conv_summary"
        
        # Enviar varios mensajes
        messages = [
            "Hola",
            "Busco laptop",
            "Cuánto cuesta?",
            "Tienen stock?"
        ]
        
        for msg in messages:
            await orchestrator.process_message(
                message=msg,
                conversation_id=conv_id,
                tenant_id="test_summary"
            )
        
        # Obtener resumen
        summary = orchestrator.get_conversation_summary(conv_id)
        
        assert summary is not None
        assert "message_count" in summary
        assert summary["message_count"] == 4
        assert "intent_distribution" in summary
        
        print("✅ Test de resumen de conversación pasó")