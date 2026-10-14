"""
Script de verificación para Semana 4 - AI Agent
Verifica que todos los componentes estén instalados y funcionando
"""
from src.core.logger import logger


def test_imports():
    """Verificar que todo importa correctamente"""
    logger.info("🔍 Verificando imports...")
    
    try:
        # Config
        from src.config import settings
        logger.success(f"✅ Config OK - Environment: {settings.ENVIRONMENT}")
        
        # Dependencias nuevas
        import qdrant_client
        import tiktoken
        import httpx
        logger.success("✅ Dependencias (qdrant, tiktoken, httpx) OK")
        
        # Modelos de conversación
        from src.models.conversation import (
            Message,
            Conversation,
            MessageRole,
            ConversationStatus,
            create_user_message,
            create_assistant_message
        )
        logger.success("✅ Modelos de conversación OK")
        
        # Servicios LLM
        from src.services.llm_service import (
            LLMService,
            OpenAIService,
            MockLLMService,
            LLMServiceFactory
        )
        logger.success("✅ LLM Service OK")
        
        return True
        
    except ImportError as e:
        logger.error(f"❌ Error de importación: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config():
    """Verificar configuración"""
    logger.info("🔍 Verificando configuración...")
    
    from src.config import settings
    
    logger.info(f"  APP_NAME: {settings.APP_NAME}")
    logger.info(f"  ENVIRONMENT: {settings.ENVIRONMENT}")
    logger.info(f"  DEBUG: {settings.DEBUG}")
    logger.info(f"  LLM_PROVIDER: {settings.LLM_PROVIDER}")
    logger.info(f"  QDRANT_MODE: {settings.QDRANT_MODE}")
    logger.info(f"  DEFAULT_TENANT_ID: {settings.DEFAULT_TENANT_ID}")
    
    # Verificar Supabase
    if settings.SUPABASE_URL:
        logger.success(f"✅ Supabase configurado: {settings.SUPABASE_URL[:40]}...")
    else:
        logger.warning("⚠️  Supabase no configurado")
    
    return True


def test_conversation_models():
    """Probar modelos de conversación"""
    logger.info("🔍 Probando modelos de conversación...")
    
    from src.models.conversation import (
        Conversation,
        create_user_message,
        create_assistant_message,
        ConversationMetadata
    )
    
    # Crear conversación
    metadata = ConversationMetadata(
        platform="whatsapp",
        user_phone="+1234567890",
        user_name="Test User"
    )
    
    conv = Conversation(
        tenant_id="tenant_test",
        metadata=metadata
    )
    
    # Agregar mensajes
    user_msg = create_user_message("Hola, ¿tienen laptops?")
    conv.add_message(user_msg)
    
    assistant_msg = create_assistant_message(
        "¡Hola! Sí, tenemos varias laptops disponibles. ¿Buscas alguna en particular?",
        tokens_used=25
    )
    conv.add_message(assistant_msg)
    
    # Verificar
    assert len(conv.messages) == 2, f"Expected 2 messages, got {len(conv.messages)}"
    assert conv.messages[0].content == "Hola, ¿tienen laptops?", "First message content mismatch"
    assert conv.total_tokens == 25, f"Expected 25 tokens, got {conv.total_tokens}"
    
    # Obtener historial
    history = conv.get_llm_history()
    assert len(history) == 2, f"Expected 2 history items, got {len(history)}"
    assert history[0]["role"] == "user", "First message should be user"
    assert history[1]["role"] == "assistant", "Second message should be assistant"
    
    logger.success(f"✅ Conversación OK: {len(conv.messages)} mensajes, {conv.total_tokens} tokens")
    
    return True


async def test_mock_llm():
    """Probar Mock LLM Service"""
    logger.info("🔍 Probando Mock LLM Service...")
    
    from src.services.llm_service import LLMService
    from src.config import settings
    
    # Crear servicio
    llm = LLMService(
        primary_provider=settings.LLM_PROVIDER,
        fallback_provider=settings.LLM_FALLBACK_PROVIDER
    )
    
    # Generar respuesta
    messages = [
        {"role": "user", "content": "Hola, ¿tienen productos disponibles?"}
    ]
    
    response = await llm.generate(
        messages=messages,
        temperature=settings.LLM_TEMPERATURE,
        max_tokens=settings.LLM_MAX_TOKENS
    )
    
    # Verificar
    assert "content" in response, "Response missing 'content'"
    assert "tokens_used" in response, "Response missing 'tokens_used'"
    assert response["provider"] == "mock", f"Expected 'mock' provider, got {response['provider']}"
    
    logger.success(f"✅ Mock LLM OK")
    logger.info(f"  Respuesta: {response['content'][:60]}...")
    logger.info(f"  Tokens: {response['tokens_used']}")
    logger.info(f"  Provider: {response['provider']}")
    
    return True


async def test_conversation_flow():
    """Probar flujo completo de conversación con LLM"""
    logger.info("🔍 Probando flujo completo...")
    
    from src.models.conversation import (
        Conversation,
        create_user_message,
        create_assistant_message,
        ConversationMetadata
    )
    from src.services.llm_service import LLMService
    from src.config import settings
    
    # Crear conversación
    metadata = ConversationMetadata(
        platform="whatsapp",
        user_phone="+573001234567",
        user_name="Juan Pérez"
    )
    
    conv = Conversation(
        tenant_id=settings.DEFAULT_TENANT_ID,
        metadata=metadata
    )
    
    # Crear LLM service
    llm = LLMService(
        primary_provider=settings.LLM_PROVIDER
    )
    
    # Simular conversación
    user_messages = [
        "Hola, buenos días",
        "¿Tienen laptops disponibles?",
        "¿Cuál me recomiendas?"
    ]
    
    for user_text in user_messages:
        # Agregar mensaje del usuario
        user_msg = create_user_message(user_text)
        conv.add_message(user_msg)
        
        # Generar respuesta del asistente
        history = conv.get_llm_history()
        response = await llm.generate(
            messages=history,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS
        )
        
        # Agregar respuesta a conversación
        assistant_msg = create_assistant_message(
            content=response["content"],
            tokens_used=response["tokens_used"]
        )
        conv.add_message(assistant_msg)
    
    # Verificar
    assert len(conv.messages) == 6, f"Expected 6 messages, got {len(conv.messages)}"
    assert conv.total_tokens > 0, "Total tokens should be > 0"
    
    logger.success(f"✅ Flujo completo OK: {len(conv.messages)} mensajes, {conv.total_tokens} tokens")
    
    # Mostrar conversación
    logger.info("  Resumen de conversación:")
    for i, msg in enumerate(conv.messages, 1):
        role_emoji = "👤" if msg.role.value == "user" else "🤖"
        logger.info(f"    {i}. {role_emoji} {msg.role.value}: {msg.content[:50]}...")
    
    return True


async def main():
    """Ejecutar todas las verificaciones"""
    logger.info("=" * 70)
    logger.info("🚀 VERIFICACIÓN SEMANA 4 - AI AGENT")
    logger.info("=" * 70)
    
    all_passed = True
    
    try:
        # 1. Imports
        logger.info("")
        if not test_imports():
            logger.error("❌ Falló la verificación de imports")
            all_passed = False
            return False
        
        # 2. Config
        logger.info("")
        if not test_config():
            logger.error("❌ Falló la verificación de configuración")
            all_passed = False
            return False
        
        # 3. Modelos
        logger.info("")
        if not test_conversation_models():
            logger.error("❌ Falló la verificación de modelos")
            all_passed = False
            return False
        
        # 4. LLM Service
        logger.info("")
        if not await test_mock_llm():
            logger.error("❌ Falló la verificación del LLM Service")
            all_passed = False
            return False
        
        # 5. Flujo completo
        logger.info("")
        if not await test_conversation_flow():
            logger.error("❌ Falló la verificación del flujo completo")
            all_passed = False
            return False
        
        # Success
        if all_passed:
            logger.info("")
            logger.info("=" * 70)
            logger.success("🎉 ¡TODAS LAS VERIFICACIONES PASARON!")
            logger.info("=" * 70)
            logger.info("✅ Semana 4 configurada correctamente")
            logger.info("✅ Modelos de conversación funcionando")
            logger.info("✅ LLM Service (Mock) funcionando")
            logger.info("✅ Flujo completo de conversación OK")
            logger.info("✅ Listo para continuar con desarrollo")
            logger.info("")
            logger.info("🎯 Próximos pasos:")
            logger.info("   1. Crear Conversation Manager")
            logger.info("   2. Integrar Vector Database (Qdrant)")
            logger.info("   3. Implementar RAG System")
            logger.info("=" * 70)
        
        return all_passed
        
    except Exception as e:
        logger.error(f"❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())