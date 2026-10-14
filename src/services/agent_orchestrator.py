"""
Agent Orchestrator - Orquesta todo el flujo del agente IA

Integra todos los componentes:
- Intent Classifier
- Context Manager
- Strategy Selector
- RAG System
- Response Generator

Flujo completo: Mensaje → Intent → Contexto → Estrategia → RAG → Respuesta
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from src.services.intent_classifier import IntentClassifier, Intent
from src.services.context_manager import AdvancedContextManager, ConversationContext
from src.services.response_generator import ResponseGenerator
from src.services.rag_system import RAGSystem
from src.core.strategies import StrategySelector
from src.core.logger import logger

# ✅ C06: Palabras clave que indican que el cliente necesita atención humana
ESCALATION_KEYWORDS = [
    "hablar con alguien",
    "hablar con una persona",
    "atención humana",
    "atencion humana",
    "quiero hablar con",
    "comunicarme con",
    "me comunicas con",
    "representante",
    "asesor",
    "humano",
    "persona real",
    "no me ayudas",
    "no entiendes",
    "mal servicio",
    "queja",
    "reclamo",
    "devolución",
    "devolucion",
    "reembolso",
    "problema grave",
    "urgente",
]


class AgentOrchestrator:
    """Orquestador principal del agente IA"""

    def __init__(
        self,
        rag_system: RAGSystem,
        intent_classifier: Optional[IntentClassifier] = None,
        context_manager: Optional[AdvancedContextManager] = None,
        response_generator: Optional[ResponseGenerator] = None,
        strategy_selector: Optional[StrategySelector] = None,
    ):
        self.rag_system = rag_system
        self.intent_classifier = intent_classifier or IntentClassifier()
        self.context_manager = context_manager or AdvancedContextManager()
        self.response_generator = response_generator or ResponseGenerator()
        self.strategy_selector = strategy_selector or StrategySelector()
        logger.info("AgentOrchestrator inicializado")

    async def process_message(
        self,
        message: str,
        conversation_id: str,
        tenant_id: str,
        user_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperatura: float = 0.7,
        customer_phone: Optional[str] = None,
        customer_name: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            start_time = datetime.now(timezone.utc)

            # 1. DETECTAR INTENT
            logger.info(f"[{conversation_id}] Procesando mensaje: '{message[:50]}'")
            try:
                intent = self.intent_classifier.classify(message)
                logger.debug(
                    f"[{conversation_id}] Intent: {intent.intent} "
                    f"(confidence: {intent.confidence:.2f})"
                )
            except Exception as e:
                logger.error(f"[{conversation_id}] Error clasificando intent: {str(e)}")
                intent = Intent(
                    intent="other", confidence=0.0, entities={}, keywords_matched=[]
                )

            # 2. OBTENER/CREAR CONTEXTO
            try:
                context = self.context_manager.get_context(conversation_id)
                if not context:
                    context = self.context_manager.create_context(
                        conversation_id=conversation_id,
                        tenant_id=tenant_id,
                        user_id=user_id,
                    )
                logger.debug(
                    f"[{conversation_id}] Contexto: stage={context.current_stage.value}"
                )
            except Exception as e:
                logger.error(
                    f"[{conversation_id}] Error gestionando contexto: {str(e)}"
                )
                context = self.context_manager.create_context(
                    conversation_id=conversation_id,
                    tenant_id=tenant_id,
                    user_id=user_id or "emergency_user",
                )

            # 3. ACTUALIZAR CONTEXTO CON INTENT
            try:
                context = self.context_manager.update_with_intent(
                    conversation_id=conversation_id, intent=intent
                )
            except Exception as e:
                logger.error(
                    f"[{conversation_id}] Error actualizando contexto: {str(e)}"
                )

            # ✅ C06: DETECTAR SI NECESITA ESCALAMIENTO AL HUMANO
            needs_escalation = self._should_escalate(message, intent.intent)
            if needs_escalation:
                logger.info(f"[{conversation_id}] Escalamiento detectado — notificando al dueño")
                escalation_response = await self._handle_escalation(
                    conversation_id=conversation_id,
                    tenant_id=tenant_id,
                    customer_phone=customer_phone,
                    customer_name=customer_name,
                    message=message,
                )
                processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()
                return {
                    "message": escalation_response,
                    "conversation_id": conversation_id,
                    "intent": {
                        "type": intent.intent,
                        "confidence": intent.confidence,
                        "entities": intent.entities,
                    },
                    "strategy": "escalation",
                    "context_stage": context.current_stage.value,
                    "products_found": 0,
                    "escalated": True,
                    "processing_time_ms": int(processing_time * 1000),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

            # 4. SELECCIONAR ESTRATEGIA
            try:
                strategy = self.strategy_selector.select(context)
                logger.debug(
                    f"[{conversation_id}] Estrategia: {strategy.name} "
                    f"(prioridad: {strategy.get_priority()})"
                )
            except Exception as e:
                logger.error(
                    f"[{conversation_id}] Error seleccionando estrategia: {str(e)}"
                )
                from src.core.strategies import GeneralInquiryStrategy
                strategy = GeneralInquiryStrategy()

            # 5. BUSCAR EN KNOWLEDGE BASE (RAG)
            rag_results = []
            if self._should_search_kb(intent.intent):
                try:
                    logger.debug(f"[{conversation_id}] Buscando en Knowledge Base...")
                    rag_results = self.rag_system.kb.search_products(
                        query=message, limit=5, min_score=0.0, tenant_id=tenant_id
                    )
                    logger.debug(
                        f"[{conversation_id}] Propiedades encontradas: {len(rag_results)}"
                    )

                    for result in rag_results[:3]:
                        try:
                            self.context_manager.add_product_mention(
                                conversation_id=conversation_id,
                                product_id=result["id"],
                                product_name=result["metadata"]["name"],
                                interest_level=result["score"],
                            )
                        except Exception as e:
                            logger.error(
                                f"[{conversation_id}] Error agregando propiedad: {str(e)}"
                            )
                except Exception as e:
                    logger.error(f"[{conversation_id}] Error en búsqueda RAG: {str(e)}")
                    rag_results = []

            # ✅ C07: DETECTAR INTENCIÓN DE RESERVA
            from src.services.reservation_service import detect_reservation_intent, create_reservation
            if detect_reservation_intent(message) and rag_results:
                try:
                    top_product = rag_results[0]
                    product_id = top_product.get("id", "")
                    product_name = top_product.get("metadata", {}).get("name", "producto")

                    reservation = await create_reservation(
                        tenant_id=tenant_id,
                        conversation_id=conversation_id,
                        product_id=product_id,
                        product_name=product_name,
                        hours=24,
                        notes=f"Cliente solicitó apartar: {message[:100]}",
                    )

                    if reservation:
                        expires_at = reservation.get("expires_at", "")
                        logger.info(f"[C07] Reserva creada para '{product_name}' en conv {conversation_id}")
                except Exception as e:
                    logger.error(f"[{conversation_id}] Error en reserva C07: {e}")

            # 6. GENERAR RESPUESTA BASE
            try:
                response_text = self.response_generator.generate(
                    intent=intent.intent,
                    context=context,
                    rag_results=rag_results,
                    strategy=strategy,
                )
                logger.debug(
                    f"[{conversation_id}] Respuesta base: {len(response_text)} chars"
                )
            except Exception as e:
                logger.error(f"[{conversation_id}] Error generando respuesta: {str(e)}")
                response_text = "Disculpa, tuve un problema. ¿Podrías repetir tu mensaje?"

            # 7. USAR RAG + LLM PARA RESPUESTA FINAL
            if self._should_use_llm(intent.intent):
                try:
                    logger.debug(
                        f"[{conversation_id}] Cargando historial y mejorando con LLM..."
                    )

                    history_messages = await self._load_conversation_history(
                        conversation_id=conversation_id,
                        tenant_id=tenant_id,
                    )

                    llm_response = await self.rag_system.generate_with_context(
                        query=message,
                        tenant_id=tenant_id,
                        conversation_history=history_messages,
                        system_prompt=system_prompt,
                    )

                    if intent.intent in ("greeting", "farewell", "complaint"):
                        response_text = llm_response["response"]
                    elif llm_response.get("has_context"):
                        response_text = llm_response["response"]

                except Exception as e:
                    logger.error(
                        f"[{conversation_id}] Error mejorando con LLM: {str(e)}"
                    )

            # 8. ✅ C05: GUARDAR PEDIDO SI ESTÁ COMPLETO
            order_saved = False
            if intent.intent == "purchase_intent":
                try:
                    from src.services.order_service import (
                        extract_order_data_from_history,
                        is_order_complete,
                        save_order,
                        notify_owner_new_order,
                    )
                    history_for_order = await self._load_conversation_history(
                        conversation_id=conversation_id,
                        tenant_id=tenant_id,
                        limit=20,
                    )
                    order_data = extract_order_data_from_history(history_for_order)

                    # Intentar extraer producto de los resultados RAG
                    if not order_data.get("producto") and rag_results:
                        order_data["producto"] = rag_results[0]["metadata"].get("name", "")

                    if is_order_complete(order_data):
                        order_id = await save_order(
                            tenant_id=tenant_id,
                            conversation_id=conversation_id,
                            order_data=order_data,
                        )
                        if order_id:
                            order_saved = True
                            await notify_owner_new_order(
                                tenant_id=tenant_id,
                                order_data=order_data,
                                customer_phone=customer_phone,
                                customer_name=customer_name,
                                order_id=order_id,
                            )
                            logger.info(f"[C05] Pedido {order_id} guardado y dueño notificado")
                except Exception as e:
                    logger.error(f"[{conversation_id}] Error guardando pedido C05: {e}")

            # 9. CALCULAR METADATA
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            result = {
                "message": response_text,
                "conversation_id": conversation_id,
                "intent": {
                    "type": intent.intent,
                    "confidence": intent.confidence,
                    "entities": intent.entities,
                },
                "strategy": strategy.name,
                "context_stage": context.current_stage.value,
                "products_found": len(rag_results),
                "escalated": False,
                "order_saved": order_saved,
                "processing_time_ms": int(processing_time * 1000),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            logger.success(
                f"[{conversation_id}] Respuesta generada en {processing_time*1000:.0f}ms"
            )

            return result

        except Exception as e:
            logger.error(
                f"[{conversation_id}] Error crítico procesando mensaje: {str(e)}"
            )
            return {
                "message": "Disculpa, tuve un problema procesando tu mensaje. ¿Podrías intentar de nuevo?",
                "conversation_id": conversation_id,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def _should_escalate(self, message: str, intent: str) -> bool:
        """
        ✅ C06: Determina si el mensaje requiere escalamiento al humano.

        Criterios:
        - Intent de queja con alta confianza
        - Palabras clave explícitas de solicitud de atención humana
        """
        message_lower = message.lower()

        # Verificar palabras clave de escalamiento
        for keyword in ESCALATION_KEYWORDS:
            if keyword in message_lower:
                logger.debug(f"Escalamiento por keyword: '{keyword}'")
                return True

        return False

    async def _handle_escalation(
        self,
        conversation_id: str,
        tenant_id: str,
        customer_phone: Optional[str],
        customer_name: Optional[str],
        message: str,
    ) -> str:
        """
        ✅ C06: Maneja el escalamiento al humano.

        1. Notifica al dueño por WhatsApp
        2. Retorna mensaje al cliente informando el escalamiento
        """
        # Notificar al dueño
        try:
            await self._notify_owner(
                tenant_id=tenant_id,
                customer_phone=customer_phone,
                customer_name=customer_name,
                message=message,
                conversation_id=conversation_id,
            )
        except Exception as e:
            logger.error(f"[{conversation_id}] Error notificando al dueño: {e}")

        # Mensaje al cliente
        return (
            "Entiendo que necesitas atención personalizada 😊 "
            "Ya le avisé a nuestro equipo y pronto se pondrán en contacto contigo. "
            "¿Hay algo más en lo que pueda ayudarte mientras tanto?"
        )

    async def _notify_owner(
        self,
        tenant_id: str,
        customer_phone: Optional[str],
        customer_name: Optional[str],
        message: str,
        conversation_id: str,
    ) -> None:
        """
        ✅ C06: Envía notificación al dueño del negocio por WhatsApp.
        Lee el owner_phone desde agent_config.
        """
        try:
            from src.core.database import get_db
            db = get_db().client

            # Obtener owner_phone desde agent_config
            result = (
                db.table("agent_config")
                .select("owner_phone, nombre_agente")
                .eq("tenant_id", tenant_id)
                .limit(1)
                .execute()
            )

            if not result.data or not result.data[0].get("owner_phone"):
                logger.warning(f"[C06] owner_phone no configurado para tenant {tenant_id}")
                return

            owner_phone = result.data[0]["owner_phone"]
            agent_name = result.data[0].get("nombre_agente", "El agente")

            # Armar mensaje de notificación
            customer_info = customer_name or customer_phone or "Un cliente"
            notification = (
                f"🔔 *Escalamiento requerido*\n\n"
                f"*Cliente:* {customer_info}\n"
                f"*Teléfono:* {customer_phone or 'No disponible'}\n"
                f"*Conversación:* {conversation_id[:8]}...\n"
                f"*Último mensaje:* {message[:200]}\n\n"
                f"{agent_name} no pudo resolver la consulta y solicitó atención humana."
            )

            # Enviar por WhatsApp
            from src.core.whatsapp_handler import WhatsAppHandler
            handler = WhatsAppHandler()
            handler.send_message(to=owner_phone, message=notification)

            logger.info(f"[C06] Notificación enviada al dueño: {owner_phone}")

        except Exception as e:
            logger.error(f"[C06] Error en _notify_owner: {e}")
            raise

    async def _load_conversation_history(
        self,
        conversation_id: str,
        tenant_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Carga los últimos N mensajes reales desde Supabase.
        """
        try:
            from src.core.database import get_db
            db = get_db().client

            result = (
                db.table("messages")
                .select("sender, content, created_at")
                .eq("conversation_id", conversation_id)
                .eq("tenant_id", tenant_id)
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )

            history = []
            for row in result.data or []:
                role = "assistant" if row["sender"] in ("bot", "assistant") else "user"
                content = row.get("content", "").strip()
                if content:
                    history.append({"role": role, "content": content})

            logger.debug(
                f"[{conversation_id}] Historial cargado desde Supabase: {len(history)} mensajes"
            )
            return history

        except Exception as e:
            logger.error(f"[{conversation_id}] Error cargando historial: {e}")
            return []

    async def process_batch(
        self, messages: list, conversation_id: str, tenant_id: str, **kwargs
    ) -> list:
        results = []
        for message in messages:
            result = await self.process_message(
                message=message,
                conversation_id=conversation_id,
                tenant_id=tenant_id,
                **kwargs,
            )
            results.append(result)
        return results

    def get_conversation_summary(self, conversation_id: str) -> Dict[str, Any]:
        return self.context_manager.get_conversation_summary(conversation_id)

    def reset_conversation(self, conversation_id: str):
        self.context_manager.reset_context(conversation_id)
        logger.info(f"Conversación reseteada: {conversation_id}")

    def _should_search_kb(self, intent: str) -> bool:
        """Determina si debe buscar en la KB."""
        search_intents = [
            "product_search",
            "product_info",
            "price_inquiry",
            "availability",
            "purchase_intent",
            "other",
        ]
        return intent in search_intents

    def _should_use_llm(self, intent: str) -> bool:
        """Determina si debe usar LLM para generar respuesta."""
        llm_intents = [
            "product_search",
            "product_info",
            "price_inquiry",
            "availability",
            "purchase_intent",
            "complaint",
            "greeting",
            "farewell",
            "other",
        ]
        return intent in llm_intents


# ==================== HELPER FUNCTIONS ====================


def create_agent_orchestrator(
    tenant_id: str,
    use_mock_llm: bool = True,
    use_local_embeddings: bool = False,
    **kwargs,
) -> AgentOrchestrator:
    from src.services.rag_system import create_rag_system

    rag_system = create_rag_system(
        tenant_id=tenant_id,
        use_mock_llm=use_mock_llm,
        use_local_embeddings=use_local_embeddings,
    )

    orchestrator = AgentOrchestrator(rag_system=rag_system, **kwargs)
    logger.info(f"Agente completo creado para tenant: {tenant_id}")
    return orchestrator