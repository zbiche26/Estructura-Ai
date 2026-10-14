"""
Intent Classifier - Detecta la intención del usuario

Clasifica mensajes del usuario en intents predefinidos:
- product_search: Búsqueda de productos
- product_info: Información sobre producto específico
- price_inquiry: Pregunta sobre precios
- availability: Consulta de disponibilidad/stock
- purchase_intent: Intención de compra
- greeting: Saludo
- complaint: Queja o problema
- farewell: Despedida
- other: Otro tipo de mensaje
"""
from typing import Dict, List, Any, Optional, Literal
from dataclasses import dataclass
import re

from src.core.logger import logger


# ==================== TIPOS ====================

IntentType = Literal[
    "product_search",
    "product_info",
    "price_inquiry",
    "availability",
    "purchase_intent",
    "greeting",
    "complaint",
    "farewell",
    "other"
]


@dataclass
class Intent:
    """
    Resultado de clasificación de intent
    """
    intent: IntentType
    confidence: float  # 0.0 - 1.0
    entities: Dict[str, Any]  # Entidades extraídas
    keywords_matched: List[str]  # Keywords que activaron el intent
    
    def __repr__(self):
        return f"Intent(intent={self.intent}, confidence={self.confidence:.2f})"


# ==================== INTENT PATTERNS ====================

INTENT_PATTERNS = {
    "product_search": {
        "keywords": [
            "busco", "buscar", "buscando", "necesito", "quiero", "me interesa",
            "quisiera", "estoy buscando", "me gustaría", "requiero",
            "mostrar", "ver", "tienes", "tienen", "hay", "existe",
            "opciones", "alternativas", "productos", "artículos"
        ],
        "patterns": [
            r"busco?\s+(?:una?|un)\s+(\w+)",
            r"necesito\s+(?:una?|un)\s+(\w+)",
            r"quiero\s+(?:una?|un)\s+(\w+)",
            r"tienes?\s+(\w+)",
            r"(?:qué|que)\s+(\w+)\s+(?:tienes|tienen|hay)",
        ]
    },
    
    "product_info": {
        "keywords": [
            "características", "especificaciones", "detalles", "información",
            "dime más", "cuéntame", "explica", "describe", "qué tiene",
            "incluye", "viene con", "trae", "funcionalidades", "capacidades"
        ],
        "patterns": [
            r"(?:qué|que)\s+(?:tiene|trae|incluye)",
            r"características\s+(?:de|del)",
            r"información\s+(?:sobre|de|del)",
        ]
    },
    
    "price_inquiry": {
        "keywords": [
            "precio", "costo", "vale", "cuesta", "cuánto", "cuanto",
            "valor", "cotización", "presupuesto", "económico", "barato",
            "caro", "oferta", "descuento", "promoción", "rebaja"
        ],
        "patterns": [
            r"(?:cuánto|cuanto)\s+(?:cuesta|vale|es|sale)",
            r"(?:qué|que)\s+precio",
            r"precio\s+(?:de|del)",
            r"\$?\s*\d+",  # Menciona números/precios
        ]
    },
    
    "availability": {
        "keywords": [
            "disponible", "disponibilidad", "stock", "existencia", "hay",
            "tienen", "queda", "quedan", "inventario", "en stock",
            "agotado", "sin stock", "cuándo llega", "cuando llega",
            "cuándo tienen", "cuando tienen", "entrega", "envío"
        ],
        "patterns": [
            r"(?:hay|tienen|queda)\s+(?:en\s+)?stock",
            r"(?:está|esta)\s+disponible",
            r"(?:cuándo|cuando)\s+(?:llega|tienen|está)",
        ]
    },
    
    "purchase_intent": {
        "keywords": [
            "comprar", "compro", "adquirir", "llevar", "me lo llevo",
            "lo quiero", "lo compro", "pedido", "orden", "carrito",
            "agregar al carrito", "proceder", "pagar", "factura",
            "enviar", "despachar", "confirmar compra", "finalizar"
        ],
        "patterns": [
            r"(?:quiero|voy\s+a)\s+comprar",
            r"me\s+(?:lo\s+)?llevo",
            r"(?:agregar|añadir)\s+al\s+carrito",
            r"proceder\s+(?:con|a)\s+(?:la\s+)?(?:compra|pago)",
        ]
    },
    
    "greeting": {
        "keywords": [
            "hola", "buenos días", "buenas tardes", "buenas noches",
            "buen día", "saludos", "qué tal", "que tal", "cómo estás",
            "como estas", "holi", "hey", "hi", "hello", "buenas"
        ],
        "patterns": [
            r"^(?:hola|hey|hi|buenas)",
            r"buenos?\s+(?:días|dia|tardes|tarde|noches|noche)",
        ]
    },
    
    "complaint": {
        "keywords": [
            "problema", "queja", "reclamo", "mal", "malo", "defectuoso",
            "no funciona", "roto", "dañado", "error", "falla", "fallo",
            "insatisfecho", "molesto", "enojado", "devolver", "reembolso",
            "garantía", "servicio técnico", "soporte"
        ],
        "patterns": [
            r"no\s+funciona",
            r"(?:tiene|hay)\s+(?:un\s+)?problema",
            r"(?:quiero|necesito)\s+(?:devolver|reembolso)",
        ]
    },
    
    "farewell": {
        "keywords": [
            "adiós", "adios", "chao", "chau", "hasta luego", "nos vemos",
            "me voy", "gracias", "thank you", "bye", "hasta pronto",
            "que tengas buen día", "buen día", "hasta la próxima"
        ],
        "patterns": [
            r"^(?:adiós|adios|chao|bye)",
            r"hasta\s+(?:luego|pronto|la\s+próxima)",
            r"(?:gracias|thanks)\s+(?:por\s+todo)?",
        ]
    }
}


# ==================== ENTITY EXTRACTION ====================

ENTITY_PATTERNS = {
    "price": r"\$?\s*(\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)",
    "quantity": r"(\d+)\s*(?:unidades?|piezas?|items?)?",
    "product_type": r"(?:laptop|mouse|teclado|monitor|audífonos|audifonos|tablet|celular|computador)",
    "brand": r"(?:hp|dell|lenovo|asus|acer|apple|samsung|logitech|razer|microsoft|sony)",
    "color": r"(?:negro|blanco|gris|azul|rojo|verde|plateado|dorado)",
}


# ==================== INTENT CLASSIFIER ====================

class IntentClassifier:
    """
    Clasificador de intenciones del usuario
    
    Usa keywords, patterns regex y heurísticas para
    detectar la intención del mensaje.
    """
    
    def __init__(
        self,
        confidence_threshold: float = 0.3,
        enable_multi_intent: bool = True
    ):
        """
        Inicializa el clasificador
        
        Args:
            confidence_threshold: Umbral mínimo de confianza
            enable_multi_intent: Si permitir múltiples intents
        """
        self.confidence_threshold = confidence_threshold
        self.enable_multi_intent = enable_multi_intent
        
        logger.info(
            f"IntentClassifier inicializado: "
            f"threshold={confidence_threshold}"
        )
    
    def classify(
        self,
        message: str,
        return_all: bool = False
    ) -> Intent:
        """
        Clasifica un mensaje
        
        Args:
            message: Mensaje del usuario
            return_all: Si retornar todos los intents (no solo el mejor)
            
        Returns:
            Intent con la clasificación
        """
        
        message_lower = message.lower().strip()
        
        if not message_lower:
            return Intent(
                intent="other",
                confidence=1.0,
                entities={},
                keywords_matched=[]
            )
        word_count = len(message_lower.split())
        
        if word_count <= 3:
            dynamic_threshold = 0.20  # Muy permisivo para mensajes muy cortos
        elif word_count <= 6:
            dynamic_threshold = 0.25  # Permisivo para mensajes cortos
        else:
            dynamic_threshold = self.confidence_threshold  # 0.3 para mensajes normales
        
        # Calcular scores para cada intent
        scores = self._calculate_scores(message_lower)
        
        # Obtener el mejor intent
        best_intent = max(scores.items(), key=lambda x: x[1]["score"])
        intent_name = best_intent[0]
        intent_data = best_intent[1]
        
        # Si la confianza es muy baja, clasificar como "other"
        if intent_data["score"] < dynamic_threshold:
            intent_name = "other"
            intent_data["score"] = 0.5
        
        # Extraer entidades
        entities = self._extract_entities(message)
        
        result = Intent(
            intent=intent_name,
            confidence=intent_data["score"],
            entities=entities,
            keywords_matched=intent_data["keywords"]
        )
        
        logger.debug(f"Intent clasificado: {result}")
        
        return result
    
    def _calculate_scores(
        self,
        message: str
    ) -> Dict[str, Dict[str, Any]]:
        """
        Calcula scores para cada intent
        
        Args:
            message: Mensaje en minúsculas
            
        Returns:
            Dict con scores por intent
        """
        scores = {}
        
        for intent_name, config in INTENT_PATTERNS.items():
            keyword_score = 0
            pattern_score = 0
            matched_keywords = []
            
            # 1. Score por keywords
            for keyword in config["keywords"]:
                if keyword in message:
                    keyword_score += 1
                    matched_keywords.append(keyword)
            
            # Normalizar (máximo 0.8, aumentado de 0.7)
            keyword_score = min(keyword_score * 0.25, 0.8)
            
            # 2. Score por patterns
            for pattern in config.get("patterns", []):
                if re.search(pattern, message, re.IGNORECASE):
                    pattern_score += 0.4  # Aumentado de 0.3
            
            # Normalizar (máximo 0.4, aumentado de 0.3)
            pattern_score = min(pattern_score, 0.4)
            
            # Score total
            total_score = keyword_score + pattern_score
            
            scores[intent_name] = {
                "score": total_score,
                "keywords": matched_keywords
            }
        
        return scores
    
    def _extract_entities(
        self,
        message: str
    ) -> Dict[str, Any]:
        """
        Extrae entidades del mensaje
        
        Args:
            message: Mensaje del usuario
            
        Returns:
            Dict con entidades extraídas
        """
        entities = {}
        
        for entity_name, pattern in ENTITY_PATTERNS.items():
            matches = re.findall(pattern, message, re.IGNORECASE)
            if matches:
                if entity_name == "price":
                    # Limpiar formato de precio
                    price_str = matches[0].replace(",", "").replace(".", "")
                    try:
                        entities[entity_name] = float(price_str)
                    except ValueError:
                        pass
                elif entity_name == "quantity":
                    try:
                        entities[entity_name] = int(matches[0])
                    except ValueError:
                        pass
                else:
                    entities[entity_name] = matches[0]
        
        return entities
    
    def classify_batch(
        self,
        messages: List[str]
    ) -> List[Intent]:
        """
        Clasifica múltiples mensajes
        
        Args:
            messages: Lista de mensajes
            
        Returns:
            Lista de intents
        """
        return [self.classify(msg) for msg in messages]
    
    def get_intent_confidence(
        self,
        message: str,
        target_intent: IntentType
    ) -> float:
        """
        Obtiene la confianza para un intent específico
        
        Args:
            message: Mensaje del usuario
            target_intent: Intent objetivo
            
        Returns:
            Confianza (0.0 - 1.0)
        """
        scores = self._calculate_scores(message.lower())
        return scores.get(target_intent, {}).get("score", 0.0)


# ==================== HELPER FUNCTIONS ====================

def create_intent_classifier(
    **kwargs
) -> IntentClassifier:
    """
    Helper para crear clasificador
    
    Args:
        **kwargs: Parámetros para IntentClassifier
        
    Returns:
        Clasificador configurado
    """
    return IntentClassifier(**kwargs)