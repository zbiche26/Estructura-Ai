"""
Response Generator - Genera respuestas usando templates y contexto
"""

from typing import List, Dict, Any, Optional
import random

from src.services.intent_classifier import IntentType
from src.services.context_manager import ConversationContext, ConversationStage
from src.core.logger import logger


AGENT_CONFIG = {
    "name": "Alex",
    "tone": "friendly_professional",
    "language": "es",
    "use_emojis": True,
    "max_emojis_per_message": 2,
    "max_response_paragraphs": 3,
    "max_products_shown": 5,
    "formal_address": False,
}

AGENT_RULES = {
    "never": [
        "Inventar precios o información de propiedades",
        "Mentir sobre disponibilidad",
        "Prometer visitas que no puede confirmar",
        "Dar información de propiedades que no conoce",
        "Compartir información de otros clientes",
    ],
    "always": [
        "Confirmar información antes de asumir",
        "Mencionar precio cuando habla de una propiedad",
        "Indicar disponibilidad claramente",
        "Si no sabe algo, decir 'Déjame verificar'",
        "Ser honesto si no tiene una propiedad",
        "Sugerir alternativas cuando sea relevante",
    ],
}

SYSTEM_PROMPT = f"""
Eres {AGENT_CONFIG['name']}, un asistente inmobiliario virtual profesional y amigable de Eje Inmobiliario.

PERSONALIDAD:
- Entusiasta pero nunca invasivo
- Genuinamente útil
- Conversacional y natural
- Respondes de forma concisa (máximo {AGENT_CONFIG['max_response_paragraphs']} párrafos)
- Tratas al cliente de tú (informal)

REGLAS ESTRICTAS:
NUNCA:
- Inventar precios o información de propiedades
- Mentir sobre disponibilidad
- Mencionar "stock" o "unidades" — son propiedades en arriendo

SIEMPRE:
- Mencionar precio de arriendo mensual en COP
- Indicar si la propiedad está disponible o no
- Ofrecer agendar visita cuando el cliente muestre interés

FORMATO DE RESPUESTAS:
- Saludo breve si es primer mensaje
- Respuesta directa a la pregunta
- Máximo {AGENT_CONFIG['max_products_shown']} propiedades mostradas
- Incluye precio claramente: $XXX,XXX COP
- Pregunta de seguimiento al final (opcional)
""".strip()


def format_whatsapp_catalog(products: List[Dict[str, Any]], show_limit: int = 5) -> str:
    """Formatea propiedades para WhatsApp"""
    if not products:
        return "No hay propiedades disponibles en este momento."

    lines = ["🏠 *Propiedades disponibles:*\n"]
    for idx, prod in enumerate(products[:show_limit], 1):
        metadata = prod.get("metadata", {}) or {}
        name = metadata.get("name", "Propiedad")
        price = metadata.get("precio", metadata.get("price", 0))
        tipo = metadata.get("tipo", metadata.get("category", ""))
        barrio = metadata.get("barrio", "")
        habitaciones = metadata.get("habitaciones", "")
        parqueadero = metadata.get("parqueadero", "")
        mascotas = metadata.get("mascotas", "")

        disponible = metadata.get("disponible", metadata.get("stock", 1))
        stock_str = "✅ Disponible" if disponible else "❌ No disponible"

        line = f"{idx}. *{name}*\n"
        if tipo:
            line += f"   🏘️ Tipo: {tipo}\n"
        if barrio:
            line += f"   📍 Barrio: {barrio}\n"
        line += f"   💰 Arriendo: ${price:,.0f} COP\n"
        if habitaciones:
            line += f"   🛏️ Habitaciones: {habitaciones}\n"
        if parqueadero:
            line += f"   🚗 Parqueadero: {parqueadero}\n"
        if mascotas:
            line += f"   🐾 Mascotas: {mascotas}\n"
        line += f"   {stock_str}\n"
        lines.append(line)

    if len(products) > show_limit:
        lines.append(f"Y {len(products) - show_limit} más...\n")

    lines.append("¿Cuál te interesa? 😊")
    return "\n".join(lines)


RESPONSE_TEMPLATES = {
    "product_search": {
        "with_results": [
            "¡Encontré {count} propiedades que podrían interesarte! {top_product}",
            "Tengo {count} opciones para ti. {top_product}",
        ],
        "no_results": [
            "No encontré propiedades exactas, pero déjame buscar alternativas.",
            "Actualmente no tengo esa propiedad, ¿te gustaría ver alternativas?",
        ],
    },
    "product_info": {
        "with_product": [
            "Te cuento sobre {product_name}: {features}. {additional_info}",
        ],
        "no_product": [
            "¿De cuál propiedad te gustaría saber más?",
        ],
    },
    "price_inquiry": {
        "with_price": [
            "El arriendo de {product_name} es ${price:,.0f} COP mensual. {value_prop}",
        ],
        "no_price": [
            "¿Cuál propiedad te interesa para darte el precio exacto?",
        ],
    },
    "availability": {
        "in_stock": [
            "¡Sí! {product_name} está disponible para arrendar. {urgency}",
        ],
        "out_of_stock": [
            "Lo siento, {product_name} no está disponible ahora. ¿Te gustaría ver alternativas?",
        ],
    },
    "purchase_intent": {
        "ready": [
            "¡Excelente elección! {product_name} por ${price:,.0f} COP/mes. ¿Agendamos una visita?",
        ],
        "ready_no_price": [
            "¡Excelente elección! ¿Agendamos una visita para {product_name}?",
        ],
        "need_selection": [
            "¿Cuál propiedad te gustaría visitar?",
        ],
    },
    "greeting": {
        "first_time": [
            "¡Hola! 👋 Soy Alex de Eje Inmobiliario. ¿Estás buscando propiedad para arrendar en Manizales?",
            "¡Bienvenido a Eje Inmobiliario! ¿Qué tipo de propiedad estás buscando?",
            "¡Hola! Estoy aquí para ayudarte a encontrar tu próximo hogar en Manizales. 🏠",
        ],
        "returning": [
            "¡Hola de nuevo! ¿En qué más puedo ayudarte?",
            "¡Qué bueno verte otra vez! ¿Qué necesitas hoy?",
        ],
    },
    "complaint": {
        "empathy": [
            "Lamento mucho ese inconveniente. Déjame ayudarte a resolverlo.",
        ]
    },
    "farewell": {
        "standard": [
            "¡Gracias por contactar a Eje Inmobiliario! Que tengas un excelente día. 😊",
            "¡Hasta pronto! Estoy aquí cuando me necesites.",
        ]
    },
}

VALUE_PROPOSITIONS = {
    "apartamento": [
        "Excelente ubicación en Manizales.",
        "Muy buena relación precio-calidad.",
    ],
    "apartaestudio": [
        "Ideal para estudiantes o personas solas.",
        "Precio muy accesible.",
    ],
    "default": ["Excelente opción.", "Muy buena relación precio-calidad."],
}

URGENCY_MESSAGES = ["¡Disponible ahora!", "Alta demanda en la zona.", ""]


class ResponseGenerator:
    def __init__(self, use_emojis: bool = True, personalization: bool = True):
        self.use_emojis = use_emojis
        self.personalization = personalization
        logger.info(
            f"ResponseGenerator inicializado - Agente: {AGENT_CONFIG['name']}, "
            f"Tono: {AGENT_CONFIG['tone']}"
        )

    def generate(
        self,
        intent: IntentType,
        context: Optional[ConversationContext] = None,
        rag_results: Optional[List[Dict[str, Any]]] = None,
        strategy: Optional[Any] = None,
        **kwargs,
    ) -> str:
        try:
            if intent == "product_search":
                base_response = self._generate_product_search(
                    context, rag_results, strategy, **kwargs
                )
            elif intent == "product_info":
                base_response = self._generate_product_info(
                    context, rag_results, **kwargs
                )
            elif intent == "price_inquiry":
                base_response = self._generate_price_inquiry(
                    context, rag_results, **kwargs
                )
            elif intent == "availability":
                base_response = self._generate_availability(
                    context, rag_results, **kwargs
                )
            elif intent == "purchase_intent":
                base_response = self._generate_purchase_intent(context, **kwargs)
            elif intent == "greeting":
                base_response = self._generate_greeting(context)
            elif intent == "complaint":
                base_response = self._generate_complaint_response()
            elif intent == "farewell":
                base_response = self._generate_farewell()
            else:
                base_response = self._generate_fallback()

            adjusted_response = self._adjust_tone_by_stage(base_response, context)
            final_response = self._apply_limits(adjusted_response)
            return final_response

        except Exception as e:
            logger.error(f"Error generando respuesta: {e}")
            return "Disculpa, tuve un problema. ¿Podrías repetir tu pregunta?"

    def _generate_product_search(self, context, rag_results, strategy, **kwargs) -> str:
        if not rag_results:
            return random.choice(RESPONSE_TEMPLATES["product_search"]["no_results"])
        return format_whatsapp_catalog(
            rag_results[: AGENT_CONFIG["max_products_shown"]]
        )

    def _generate_product_info(self, context, rag_results, **kwargs) -> str:
        if not rag_results:
            return random.choice(RESPONSE_TEMPLATES["product_info"]["no_product"])
        product = rag_results[0]
        metadata = product.get("metadata", {}) or {}
        features = product.get(
            "text", f"es una propiedad en {metadata.get('barrio', 'Manizales')}"
        )
        price = metadata.get("precio", metadata.get("price"))
        additional_info = f"Arriendo: ${price:,.0f} COP" if price else ""
        return random.choice(RESPONSE_TEMPLATES["product_info"]["with_product"]).format(
            product_name=metadata.get("name", "Propiedad"),
            features=features,
            additional_info=additional_info,
        )

    def _generate_price_inquiry(self, context, rag_results, **kwargs) -> str:
        if not rag_results:
            return random.choice(RESPONSE_TEMPLATES["price_inquiry"]["no_price"])
        product = rag_results[0]
        metadata = product.get("metadata", {}) or {}
        tipo = metadata.get("tipo", "default").lower()
        value_prop = random.choice(
            VALUE_PROPOSITIONS.get(tipo, VALUE_PROPOSITIONS["default"])
        )
        return random.choice(RESPONSE_TEMPLATES["price_inquiry"]["with_price"]).format(
            product_name=metadata.get("name", "Propiedad"),
            price=metadata.get("precio", metadata.get("price", 0)),
            value_prop=value_prop,
        )

    def _generate_availability(self, context, rag_results, **kwargs) -> str:
        if not rag_results:
            return random.choice(
                RESPONSE_TEMPLATES["availability"]["out_of_stock"]
            ).format(product_name="esa propiedad")
        product = rag_results[0]
        metadata = product.get("metadata", {}) or {}
        disponible = metadata.get("disponible", metadata.get("stock", 1))
        name = metadata.get("name", "La propiedad")
        if not disponible:
            return random.choice(
                RESPONSE_TEMPLATES["availability"]["out_of_stock"]
            ).format(product_name=name)
        urgency = random.choice(URGENCY_MESSAGES)
        return random.choice(RESPONSE_TEMPLATES["availability"]["in_stock"]).format(
            product_name=name, urgency=urgency
        )

    def _generate_purchase_intent(self, context, **kwargs) -> str:
        product_name = kwargs.get("product_name")
        product_price = kwargs.get("price")
        if (
            not product_name
            and context
            and hasattr(context, "mentioned_products")
            and context.mentioned_products
        ):
            product_name = context.mentioned_products[-1].product_name
        if product_name:
            if product_price is not None:
                return random.choice(
                    RESPONSE_TEMPLATES["purchase_intent"]["ready"]
                ).format(product_name=product_name, price=product_price)
            return random.choice(
                RESPONSE_TEMPLATES["purchase_intent"]["ready_no_price"]
            ).format(product_name=product_name)
        return random.choice(RESPONSE_TEMPLATES["purchase_intent"]["need_selection"])

    def _generate_greeting(self, context) -> str:
        if context and hasattr(context, "message_count") and context.message_count > 1:
            return random.choice(RESPONSE_TEMPLATES["greeting"]["returning"])
        return random.choice(RESPONSE_TEMPLATES["greeting"]["first_time"])

    def _generate_complaint_response(self) -> str:
        return random.choice(RESPONSE_TEMPLATES["complaint"]["empathy"])

    def _generate_farewell(self) -> str:
        return random.choice(RESPONSE_TEMPLATES["farewell"]["standard"])

    def _generate_fallback(self) -> str:
        fallbacks = [
            "No estoy seguro de entender. ¿Podrías reformular tu pregunta?",
            "¿Podrías darme más detalles sobre lo que necesitas?",
            "Déjame ayudarte. ¿Qué tipo de propiedad estás buscando?",
        ]
        return random.choice(fallbacks)

    def _adjust_tone_by_stage(self, base_response: str, context) -> str:
        """
        Ajusta tono según stage.
        ConversationStage valores: DISCOVERY, COMPARISON, DECISION, PURCHASE, POST_PURCHASE, SUPPORT
        """
        if not context:
            return base_response

        stage = getattr(context, "current_stage", None)
        if stage is None:
            return base_response

        if stage == ConversationStage.DISCOVERY:
            suffix = random.choice(
                [
                    "💡 ¿Quieres que te cuente más sobre las propiedades disponibles?",
                    "💡 ¿Necesitas ayuda para elegir la que mejor se ajusta a tus necesidades?",
                ]
            )
        elif stage == ConversationStage.COMPARISON:
            suffix = random.choice(
                [
                    "📊 ¿Te gustaría que compare las opciones disponibles?",
                    "📊 ¿Quieres que te explique las diferencias entre estas propiedades?",
                ]
            )
        elif stage == ConversationStage.DECISION:
            suffix = random.choice(
                [
                    "✨ ¿Agendamos una visita? Tengo disponibilidad esta semana.",
                    "✨ ¿Te interesa visitarla? Puedo coordinar una cita.",
                ]
            )
        elif stage == ConversationStage.PURCHASE:
            suffix = random.choice(
                [
                    "¿Necesitas algo más para proceder con el arriendo?",
                    "¿Listo para confirmar? 🎯",
                ]
            )
        else:
            suffix = ""

        if suffix:
            return f"{base_response}\n\n{suffix}"
        return base_response

    def _apply_limits(self, response: str) -> str:
        max_paragraphs = AGENT_CONFIG["max_response_paragraphs"]
        paragraphs = response.split("\n\n")
        if len(paragraphs) > max_paragraphs:
            response = "\n\n".join(paragraphs[:max_paragraphs])
            response += "\n\n_(¿Quieres más información?)_"

        max_chars = 1000
        if len(response) > max_chars:
            response = response[: max_chars - 50]
            response += "...\n\n_(¿Quieres más detalles?)_"

        return response


def create_response_generator(**kwargs) -> ResponseGenerator:
    return ResponseGenerator(**kwargs)
