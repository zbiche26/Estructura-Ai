"""
RAG System - Retrieval Augmented Generation

Integra:
- Knowledge Base (búsqueda vectorial en Qdrant)
- LLM Service (generación con OpenAI gpt-4o-mini)
- Conversation Manager (contexto)

Genera respuestas contextualizadas usando información relevante.
Soporta dos modos: inmobiliario y moda/boutique (detección automática por metadata).

MEJORAS v2:
- Clasificador de intención antes de buscar en Qdrant
- Qdrant solo se consulta cuando el cliente busca propiedades
- Saludos, despedidas, requisitos y preguntas fuera de tema no tocan Qdrant
- Reduce alucinaciones al no contaminar el contexto con búsquedas irrelevantes

MEJORAS v3:
- Score mínimo de Qdrant 0.3 — descarta resultados poco relevantes
- Historial limitado a 10 mensajes — evita confusión del LLM en conversaciones largas
- Log de intención con tag [INTENT] — monitoreo en Railway logs
"""

from typing import List, Dict, Any, Optional
import re

from src.services.llm_service import LLMService
from src.services.knowledge_base import KnowledgeBase
from src.services.conversation_manager import ConversationManager
from src.models.conversation import (
    Conversation,
    create_user_message,
    create_assistant_message,
    create_system_message,
)
from src.core.logger import logger

# ── Constantes configurables ──────────────────────────────────────────────────
MIN_RELEVANCE_SCORE = 0.3  # Documentos Qdrant con score menor se descartan
MAX_HISTORY_MESSAGES = 10  # Máximo de mensajes del historial que recibe el LLM


# ==================== CLASIFICADOR DE INTENCIÓN ====================

_PATTERNS_SALUDO = re.compile(
    r"^\s*(hola(\s+buenas?(\s*(días?|tardes?|noches?))?)?|"
    r"buenas?(\s*(días?|tardes?|noches?))?|"
    r"buenos?\s*(días?|tardes?|noches?)|"
    r"hi|hey|saludos?|buen\s*día|qué\s*tal|"
    r"cómo\s*est(á|a)(s|n)?|quién\s*er(es|a)s?)\s*[!.]*\s*$",
    re.IGNORECASE,
)

_PATTERNS_DESPEDIDA = re.compile(
    r"^\s*(adiós|adios|hasta\s*(luego|pronto|mañana)|chao|chau|bye|gracias.*adiós?|"
    r"te\s*agradezco|muchas?\s*gracias|ok\s*gracias?|listo\s*gracias?|"
    r"ya\s*no\s*necesito|no\s*gracias?|eso\s*es\s*todo)\s*[!.]*\s*$",
    re.IGNORECASE,
)

_PATTERNS_REQUISITOS = re.compile(
    r"(requisito|require|necesito\s*para\s*arrendar|cómo\s*(hago|aplico|arriendo)|"
    r"qué\s*necesito|documentos?\s*(necesarios?|requeridos?)|"
    r"cómo\s*es\s*el\s*proceso|qué\s*piden|qué\s*pide|"
    r"central(es)?\s*de\s*riesgo|fiador|codeudor|estudio\s*de\s*crédito)",
    re.IGNORECASE,
)

_PATTERNS_FUERA_TEMA = re.compile(
    r"(receta|cocina|película|fútbol|deporte|política|clima|temperatura|"
    r"chiste|cuéntame\s*algo|qué\s*hora\s*es|qué\s*día\s*es|"
    r"calculadora|matemática|historia\s*de|cuánto\s*es\s*\d)",
    re.IGNORECASE,
)

_PATTERNS_AGRADECIMIENTO = re.compile(
    r"^\s*(gracias?|mil\s*gracias?|muy\s*amable|excelente|perfecto|"
    r"genial|ok|listo|entendido|de\s*acuerdo|claro)\s*[!.]*\s*$",
    re.IGNORECASE,
)

_PATTERNS_BUSQUEDA_PROPIEDAD = re.compile(
    r"(busco|buscando|quiero|necesito|tienes?|hay|disponible|"
    r"apartamento|apartaestudio|casa|local|oficina|bodega|inmueble|"
    r"arrendar|alquilar|arriendo|alquiler|propiedad|propiedades|"
    r"barrio|sector|zona|precio|canon|habitaci[oó]n|cuarto|baño|"
    r"parqueadero|mascota|piso|estrato|norte|sur|centro|"
    r"cuánto\s*(vale|cuesta|es)|cuántas?\s*habitaci)",
    re.IGNORECASE,
)


def classify_intent(message: str) -> str:
    """
    Clasifica la intención del mensaje.

    Returns:
        'saludo' | 'despedida' | 'requisitos' | 'agradecimiento' |
        'fuera_tema' | 'busqueda_propiedad' | 'general'
    """
    msg = message.strip()

    if _PATTERNS_SALUDO.match(msg):
        return "saludo"
    if _PATTERNS_DESPEDIDA.match(msg):
        return "despedida"
    if _PATTERNS_AGRADECIMIENTO.match(msg):
        return "agradecimiento"
    if _PATTERNS_REQUISITOS.search(msg):
        return "requisitos"
    if _PATTERNS_FUERA_TEMA.search(msg):
        return "fuera_tema"
    if _PATTERNS_BUSQUEDA_PROPIEDAD.search(msg):
        return "busqueda_propiedad"
    return "general"


def needs_qdrant_search(intent: str) -> bool:
    """Solo busca en Qdrant cuando el cliente quiere encontrar propiedades."""
    return intent in ("busqueda_propiedad", "general")


# ==================== RESPUESTAS DIRECTAS SIN QDRANT ====================

_RESPUESTAS_REQUISITOS = """Para arrendar con nosotros necesitas:
• Dos personas: un tomador y un fiador
• Ambos sin reportes en centrales de riesgo
• Los dos deben tener ingresos de al menos el doble del canon mensual
• El estudio de crédito con la aseguradora tiene un costo del 10% del canon

¿Tienes alguna duda sobre los requisitos?"""

_RESPUESTAS_FUERA_TEMA = "Eso está fuera de lo que manejo 😄 Pero si necesitas ayuda con propiedades en Manizales, aquí estoy."


class RAGSystem:
    """
    Sistema RAG completo — v3.

    v2: Clasificador de intención evita búsquedas innecesarias en Qdrant.
    v3: Score mínimo 0.3, historial limitado a 10 msgs, logs de intención.
    """

    def __init__(
        self,
        llm_service: LLMService,
        knowledge_base: KnowledgeBase,
        conversation_manager: Optional[ConversationManager] = None,
        max_context_items: int = 5,
        min_relevance_score: float = MIN_RELEVANCE_SCORE,
    ):
        self.llm = llm_service
        self.kb = knowledge_base
        self.conversation_manager = conversation_manager
        self.max_context_items = max_context_items
        self.min_relevance_score = min_relevance_score
        logger.info("RAG System v3 inicializado")

    async def generate_with_context(
        self,
        query: str,
        conversation: Optional[Conversation] = None,
        tenant_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, Any]]] = None,
        nombre_agente: Optional[str] = None,
        nombre_tienda: Optional[str] = None,
        **search_kwargs,
    ) -> Dict[str, Any]:
        """
        Genera una respuesta usando RAG + historial de conversación.

        v3:
        - Clasifica intención → decide si consultar Qdrant
        - Filtra docs Qdrant con score < MIN_RELEVANCE_SCORE
        - Limita historial a MAX_HISTORY_MESSAGES
        - Loguea intención con tag [INTENT] para monitoreo
        """
        try:
            # ── 1. Clasificar intención ───────────────────────────────────
            intent = classify_intent(query)

            # MEJORA 3: Log con tag [INTENT] para monitoreo en Railway
            logger.info(
                f"[INTENT] tenant={tenant_id} | intent={intent} | query='{query[:60]}'"
            )

            # ── 2. Buscar en Qdrant solo si es necesario ──────────────────
            relevant_docs = []
            if needs_qdrant_search(intent):
                raw_docs = self.kb.search_products(
                    query=query,
                    limit=self.max_context_items,
                    min_score=self.min_relevance_score,
                    tenant_id=tenant_id,
                    **search_kwargs,
                )
                # MEJORA 1: Filtrar por score mínimo para evitar contexto irrelevante
                relevant_docs = [
                    d for d in raw_docs if d.get("score", 0) >= self.min_relevance_score
                ]
                logger.info(
                    f"Qdrant: {len(raw_docs)} docs → {len(relevant_docs)} con score >= {self.min_relevance_score}"
                )
            else:
                logger.info(
                    f"Qdrant omitido — intención '{intent}' no requiere búsqueda"
                )

            # ── 3. Construir mensajes ─────────────────────────────────────
            context_text = self._format_context(relevant_docs) if relevant_docs else ""
            messages = []

            if system_prompt:
                system_msg_text = system_prompt
            else:
                system_msg_text = self._build_system_prompt(
                    context_text=context_text,
                    nombre_agente=nombre_agente,
                    nombre_tienda=nombre_tienda,
                    intent=intent,
                )

            messages.append({"role": "system", "content": system_msg_text})

            # MEJORA 2: Limitar historial a MAX_HISTORY_MESSAGES
            if conversation_history:
                recent_history = conversation_history[-MAX_HISTORY_MESSAGES:]
                if len(conversation_history) > MAX_HISTORY_MESSAGES:
                    logger.debug(
                        f"Historial truncado: {len(conversation_history)} → {MAX_HISTORY_MESSAGES} mensajes"
                    )
                for msg in recent_history:
                    messages.append(msg)
            elif conversation:
                history = conversation.get_llm_history()
                history_msgs = [m for m in history if m["role"] != "system"]
                for msg in history_msgs[-MAX_HISTORY_MESSAGES:]:
                    messages.append(msg)

            messages.append({"role": "user", "content": query})

            logger.debug(
                f"LLM recibirá {len(messages)} mensajes "
                f"(historial: {min(len(conversation_history or []), MAX_HISTORY_MESSAGES)}/{len(conversation_history or [])}) "
                f"| Qdrant: {len(relevant_docs)} docs"
            )

            # ── 4. Generar respuesta ──────────────────────────────────────
            response = await self.llm.generate(messages=messages)

            result = {
                "response": response["content"],
                "context": relevant_docs,
                "intent": intent,
                "sources": [
                    {
                        "id": doc["id"],
                        "name": doc["metadata"].get("name")
                        or doc["metadata"].get("nombre", "Sin nombre"),
                        "score": doc["score"],
                    }
                    for doc in relevant_docs
                ],
                "tokens_used": response["tokens_used"],
                "model": response.get("model"),
                "has_context": len(relevant_docs) > 0,
            }

            logger.success(
                f"Respuesta generada: intent={intent} | "
                f"docs={len(relevant_docs)} | "
                f"tokens={response['tokens_used']}"
            )

            return result

        except Exception as e:
            logger.error(f"Error en RAG generation: {e}")
            raise

    async def chat(
        self,
        user_message: str,
        conversation_id: Optional[str] = None,
        tenant_id: str = "default",
        user_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        nombre_agente: Optional[str] = None,
        nombre_tienda: Optional[str] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        try:
            if self.conversation_manager:
                if conversation_id:
                    conversation = self.conversation_manager.get_conversation(
                        conversation_id
                    )
                elif user_id:
                    conversation = self.conversation_manager.get_or_create_conversation(
                        tenant_id=tenant_id, user_id=user_id
                    )
                else:
                    conversation = self.conversation_manager.create_conversation(
                        tenant_id=tenant_id, system_prompt=system_prompt
                    )
            else:
                conversation = Conversation(tenant_id=tenant_id)
                if system_prompt:
                    conversation.add_message(create_system_message(system_prompt))

            user_msg = create_user_message(user_message)
            conversation.add_message(user_msg)

            result = await self.generate_with_context(
                query=user_message,
                conversation=conversation,
                tenant_id=tenant_id,
                system_prompt=system_prompt,
                nombre_agente=nombre_agente,
                nombre_tienda=nombre_tienda,
                **kwargs,
            )

            assistant_msg = create_assistant_message(
                content=result["response"], tokens_used=result["tokens_used"]
            )
            conversation.add_message(assistant_msg)

            if self.conversation_manager:
                self.conversation_manager.save_conversation(conversation)

            return {
                "message": result["response"],
                "conversation_id": conversation.id,
                "sources": result["sources"],
                "tokens_used": result["tokens_used"],
                "has_context": result["has_context"],
                "context_items": len(result["context"]),
                "intent": result.get("intent", "general"),
            }

        except Exception as e:
            logger.error(f"Error en RAG chat: {e}")
            raise

    # ==================== FORMAT CONTEXT ====================

    def _format_context(self, documents: List[Dict[str, Any]]) -> str:
        if not documents:
            return ""
        first_meta = documents[0].get("metadata", {})
        modo = first_meta.get("modo", "inmobiliario")
        if modo == "moda":
            return self._format_context_moda(documents)
        return self._format_context_inmobiliario(documents)

    def _format_context_inmobiliario(self, documents: List[Dict[str, Any]]) -> str:
        if not documents:
            return ""
        context_parts = []
        for i, doc in enumerate(documents, 1):
            metadata = doc["metadata"]
            disponible = metadata.get("disponible", metadata.get("stock", 1))
            estado = "✅ Disponible para arriendo" if disponible else "❌ No disponible"
            part = f"""--- Propiedad {i} ---
Nombre: {metadata.get('name', 'Sin nombre')}
Tipo: {metadata.get('tipo', metadata.get('type', 'No especificado'))}
Barrio: {metadata.get('barrio', metadata.get('neighborhood', 'No especificado'))}
Precio arriendo: ${metadata.get('precio', metadata.get('price', 0)):,} COP/mes
Habitaciones: {metadata.get('habitaciones', metadata.get('bedrooms', 'N/A'))}
Baños: {metadata.get('banos', metadata.get('bathrooms', 'N/A'))}
Parqueadero: {metadata.get('parqueadero', 'N/A')}
Mascotas: {metadata.get('mascotas', 'N/A')}
Estado: {estado}
Descripción: {metadata.get('description', metadata.get('descripcion', 'Sin descripción'))}"""
            context_parts.append(part)
        return "\n\n".join(context_parts)

    def _format_context_moda(self, documents: List[Dict[str, Any]]) -> str:
        if not documents:
            return ""
        context_parts = []
        for i, doc in enumerate(documents, 1):
            m = doc["metadata"]
            disponible = "✅ Disponible" if m.get("disponible", True) else "❌ Agotado"
            precio = m.get("precio", 0)
            descuento = m.get("descuento_pct", 0)
            part = f"""--- Producto {i} ---
Nombre: {m.get('name', 'Sin nombre')}
Referencia: {m.get('referencia', 'N/A')}
Categoría: {m.get('categoria', 'N/A')}
Precio: ${int(precio):,} COP"""
            if descuento and float(descuento) > 0:
                precio_final = int(precio) * (1 - float(descuento) / 100)
                part += f"\nDescuento: {descuento}% → Precio final: ${precio_final:,.0f} COP"
            part += f"""
Tallas disponibles: {m.get('tallas', 'N/A')}
Colores disponibles: {m.get('colores', 'N/A')}
Stock: {m.get('stock', 0)} unidades
Estado: {disponible}
Descripción: {m.get('description', m.get('descripcion', 'Sin descripción'))}"""
            context_parts.append(part)
        return "\n\n".join(context_parts)

    # ==================== BUILD SYSTEM PROMPT ====================

    def _build_system_prompt(
        self,
        context_text: str,
        nombre_agente: Optional[str] = None,
        nombre_tienda: Optional[str] = None,
        intent: Optional[str] = None,
    ) -> str:
        if "Tallas disponibles" in context_text:
            return self._build_system_prompt_moda(
                context_text=context_text,
                nombre_agente=nombre_agente,
                nombre_tienda=nombre_tienda,
            )
        return self._build_system_prompt_inmobiliario(
            context_text=context_text,
            intent=intent,
        )

    def _build_system_prompt_inmobiliario(self, context_text: str, intent: Optional[str] = None) -> str:
        """System prompt para Eje Inmobiliario — Celeste."""
        tiene_propiedades = (
            bool(context_text)
            and context_text.strip() != ""
            and "No hay propiedades" not in context_text
            and "No hay productos" not in context_text
        )

        catalogo_section = (
            f"CATÁLOGO ACTUAL DE PROPIEDADES:\n{context_text}"
            if tiene_propiedades
            else "CATÁLOGO: En este momento no tengo propiedades cargadas en el sistema."
        )

        return f"""Eres Celeste, asistente virtual de Eje Inmobiliario en Manizales. Eres amable, directa y cálida.

IMPORTANTE: Siempre debes identificarte como asistente virtual, nunca como una persona real. Manejamos casas, apartamentos, apartaestudios y locales en Manizales. Si preguntan por otra ciudad: "Solo manejamos propiedades en Manizales por ahora 😊"

{catalogo_section}

━━━ TU ROL ES GUIAR, NO ESPERAR ━━━

Tú llevas la conversación. No recopiles filtros a ciegas — haz una pregunta mínima, busca en el catálogo con lo que tienes, y propón opciones reales de inmediato.

El flujo que sigues SIEMPRE:
1. Saludar e identificarte como asistente virtual (solo en el primer mensaje)
2. Hacer UNA pregunta mínima si es necesario → buscar en el catálogo → proponer 2-3 opciones concretas
3. Refinar según la reacción del cliente
4. Si piden fotos o más detalles → dar el link de la publicación si está disponible
5. Si hay interés real → dar requisitos y escalar al asesor humano

━━━ CASOS ESPECÍFICOS ━━━

SALUDO GENÉRICO ("hola", "buenos días", sin más contexto):
Responde exactamente: "¡Hola! Soy Celeste, asistente virtual de Eje Inmobiliario 😊 ¿Estás buscando una propiedad en arriendo?"
NUNCA vuelvas a presentarte después del primer mensaje.

SALUDO CON LINK DE FACEBOOK O REFERENCIA A UNA PUBLICACIÓN:
Responde: "¡Hola! Soy Celeste, asistente virtual de Eje Inmobiliario 😊 Vi que preguntas por esa publicación — ¿me confirmas qué propiedad te interesa para darte la información completa?"

SALUDO CON REFERENCIA DIRECTA A UNA PROPIEDAD (nombre, barrio, precio):
Responde: "¡Hola! Soy Celeste, asistente virtual de Eje Inmobiliario 😊" y ve directo a dar la información de esa propiedad sin preguntar de nuevo qué busca.

CUANDO EL CLIENTE RESPONDE CON "sí", "ok", "claro" O AFIRMACIONES CORTAS:
NUNCA repitas la pregunta anterior. Interpreta como confirmación y AVANZA al siguiente paso. Si no sabes a qué confirma, di: "Perfecto 😊 ¿Qué tipo de propiedad buscas — apartamento, casa, apartaestudio, local?"

CUANDO NO ENTIENDES UN MENSAJE (confuso, muy corto, mal escrito):
Di: "No entendí bien tu mensaje 😊 ¿Me puedes contar qué tipo de propiedad estás buscando?"
NUNCA inventes una respuesta ni vuelvas a presentarte.

LINKS COMPARTIDOS POR EL CLIENTE:
Responde: "Vi que compartiste un link, pero no puedo abrirlo 😊 ¿Me cuentas qué propiedad te interesa?"

CUANDO NO HAY PROPIEDADES EN EL CATÁLOGO:
Di: "En este momento no tengo propiedades disponibles en el sistema, pero un asesor puede ayudarte directamente. Escríbenos al 3116457633 😊"
NO sigas haciendo preguntas de filtro si no tienes nada que mostrar.

PREGUNTAS FUERA DEL TEMA:
Di: "Eso está fuera de lo que manejo 😄 Pero si necesitas ayuda con propiedades en Manizales, aquí estoy."

DESPEDIDAS O AGRADECIMIENTOS:
Di: "Con gusto 😊 Si en algún momento buscas propiedad en Manizales, aquí estaré."

IMÁGENES, AUDIO, VIDEO, STICKERS, DOCUMENTOS (llegan como "[imagen]", "[audio]", etc.):
Di: "Recibí tu mensaje, pero como soy asistente virtual solo puedo leer texto 😊 Cuéntame con palabras en qué te puedo ayudar."

━━━ PRESENTACIÓN DE PROPIEDADES ━━━

Muestra máximo 2-3 propiedades. Por cada una incluye:
- Nombre y barrio
- Precio en formato $1.200.000 COP/mes
- Habitaciones y baños
- Si incluye parqueadero y si acepta mascotas
- Link de la publicación (si está disponible en los datos)

Cierra con: "¿Cuál te llama más la atención?"
Al dar detalles de una propiedad específica, cierra con: "¿Te gustaría agendar una visita o tienes alguna duda?"

━━━ REQUISITOS DE ARRIENDO ━━━

Cuando pregunten por requisitos, responde EXACTAMENTE:
"Para arrendar con nosotros necesitas:
- Dos personas: un tomador y un fiador
- Ambos sin reportes en centrales de riesgo
- Ingresos de al menos el doble del canon mensual
- Estudio de crédito con aseguradora: 10% del canon

¿Tienes alguna duda? Si quieres avanzar, escríbenos al 3116457633 y un asesor te acompaña 😊"

━━━ ESCALAMIENTO AL ASESOR ━━━

Escala al asesor humano (3116457633) cuando:
- El cliente dice "me interesa", "quiero verla", "quiero aplicar"
- Pregunta algo que no está en el catálogo
- La conversación lleva más de 4 turnos sin resolución

Mensaje de escalamiento: "Para continuar, te recomiendo escribirle a nuestro equipo al 3116457633 — un asesor te va a atender personalmente 😊"

━━━ REGLAS ABSOLUTAS ━━━
1. NUNCA inventes propiedades, precios o datos que no estén en el catálogo
2. SIEMPRE identifícate como asistente virtual, nunca como persona real
3. NUNCA repitas la presentación después del primer mensaje
4. NUNCA repitas la misma pregunta dos veces seguidas
5. NUNCA dejes al cliente en un loop — si no puedes ayudar, escala al asesor
6. NUNCA cambies los requisitos de arriendo

━━━ FORMATO ━━━
- Español colombiano, trato de "tú"
- Respuestas cortas y directas (máximo 3 párrafos)
- Precios en formato $1.200.000 COP
- Emojis con moderación — máximo 1 o 2 por mensaje"""

    def _build_system_prompt_moda(
        self,
        context_text: str,
        nombre_agente: Optional[str] = None,
        nombre_tienda: Optional[str] = None,
    ) -> str:
        agente = nombre_agente or "Asistente"
        tienda = f" de {nombre_tienda}" if nombre_tienda else ""
        catalogo_section = (
            f"CATÁLOGO ACTUAL:\n{context_text}"
            if context_text
            else "CATÁLOGO: No se encontraron productos que coincidan con la búsqueda actual."
        )

        return f"""Eres {agente}, asistente virtual{tienda}. Eres amable, apasionada por la moda y experta en el catálogo de la tienda. Tu función es ayudar a los clientes a encontrar el producto perfecto según su talla, color y estilo.

{catalogo_section}

━━━ INSTRUCCIONES DE COMPORTAMIENTO ━━━

REGLA 0 — SALUDOS (PRIORIDAD MÁXIMA):
- Si el cliente saluda, SIEMPRE responde con un saludo amable y preséntate.
- Un saludo NO es un mensaje confuso.

REGLA 1 — PRESENTACIÓN:
- Preséntate UNA SOLA VEZ en toda la conversación.
- A partir del segundo mensaje, retoma el hilo directamente sin volver a presentarte.

REGLA 2 — BÚSQUEDA DE PRODUCTO:
- Muestra máximo 2-3 opciones relevantes.
- Por cada producto: nombre, precio, tallas disponibles, colores, estado.
- Cierra siempre con: "¿Cuál te llama más la atención?" o "¿Quieres más detalles?"

REGLA 3 — CONSULTA POR TALLA O COLOR:
- Si no hay en esa talla/color: "Ese producto no está disponible en esa talla/color por ahora 😊 ¿Te interesa otra opción?"

REGLA 4 — FLUJO DE COMPRA:
1. Confirma producto + talla + color
2. Pregunta método de pago (efectivo, transferencia, contra entrega)
3. Pregunta dirección de entrega o si recoge en tienda
4. Confirma el pedido con un resumen completo
5. Di: "¡Listo! Le avisaré a nuestro equipo para coordinar tu pedido 🎉"

REGLA 5 — IMÁGENES, AUDIO, VIDEO:
- Responde: "Recibí tu mensaje, pero como soy un asistente virtual solo puedo leer texto 😊 Cuéntame con palabras qué estás buscando."

REGLA 6 — DESPEDIDAS Y AGRADECIMIENTOS:
- Acepta amablemente: "¡Con gusto! Si quieres ver nuestro catálogo, aquí estaré 😊"

REGLA 7 — PREGUNTAS FUERA DEL TEMA:
- Responde: "Eso está fuera de lo que manejo 😄 Pero si buscas algo de moda, aquí estoy."

━━━ REGLAS ABSOLUTAS ━━━
1. NUNCA inventes productos, tallas, colores o precios que no estén en el catálogo
2. NUNCA repitas la presentación después del primer mensaje
3. NUNCA trates saludos o despedidas como mensajes confusos
4. Si el producto no está disponible, dilo claramente y ofrece alternativas

━━━ FORMATO ━━━
- Español colombiano, trato de "tú"
- Respuestas cortas y directas (máximo 3 párrafos)
- Precios en formato $89.900 COP
- Emojis con moderación — máximo 1 o 2 por mensaje"""


# ==================== FACTORY FUNCTION ====================


def create_rag_system(
    tenant_id: str,
    use_mock_llm: bool = False,
    use_local_embeddings: bool = False,
    **kwargs,
) -> RAGSystem:
    from src.services.embedding_service import EmbeddingService

    llm = LLMService()
    embedding_service = EmbeddingService(
        primary_provider="openai",
        fallback_provider="mock",
    )

    collection_name = f"products_{tenant_id}"
    kb = KnowledgeBase(
        embedding_service=embedding_service,
        collection_name=collection_name,
    )

    return RAGSystem(
        llm_service=llm,
        knowledge_base=kb,
        **kwargs,
    )
