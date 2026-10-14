"""
Enhanced Intent Classifier - Versión Mejorada Sin LLM

Mejoras sobre IntentClassifier original:
1. 3x más keywords por intent
2. Corrección de typos comunes
3. Detección de negaciones
4. Extracción de entidades mejorada (cantidad, color, producto)
5. Manejo de múltiples productos en un mensaje
6. Scoring mejorado con pesos por tipo de palabra

NO requiere LLM - Solo lógica de keywords mejorada
"""

from typing import Dict, List, Optional, Tuple
import re
from dataclasses import dataclass

from src.core.logger import logger


# ============================================
# DATA CLASSES
# ============================================

@dataclass
class IntentResult:
    """Resultado de clasificación de intent."""
    intent: str
    confidence: float
    entities: Dict
    has_negation: bool
    all_scores: Dict[str, float]
    
    def __str__(self):
        return f"Intent: {self.intent} (confidence: {self.confidence:.2f})"


@dataclass
class Entity:
    """Entidad extraída del mensaje."""
    type: str  # quantity, color, product, price_range
    value: any
    raw_text: str


# ============================================
# ENHANCED INTENT CLASSIFIER
# ============================================

class EnhancedIntentClassifier:
    """
    Clasificador de intents mejorado SIN usar LLM.
    
    Características:
    - 3x más keywords que versión original
    - Corrección automática de typos comunes
    - Detección de negaciones
    - Extracción de entidades (cantidad, color, producto)
    - Manejo de múltiples intents en un mensaje
    """
    
    def __init__(self, default_threshold: float = 0.5):
        """
        Inicializa el clasificador.
        
        Args:
            default_threshold: Confianza mínima para detectar intent
        """
        self.default_threshold = default_threshold
        
        # Keywords expandidos (PASO 3)
        self.intent_keywords = self._initialize_keywords()
        
        # Thresholds específicos por intent
        self.thresholds = {
            "greeting": 0.3,
            "product_search": 0.3,
            "price_inquiry": 0.3,
            "availability_check": 0.35,
            "complaint": 0.4,
            "purchase_intent": 0.4,
            "farewell": 0.3,
            "general_inquiry": 0.20
        }
        
        # Correcciones de typos comunes (PASO 4)
        self.typo_corrections = self._initialize_typos()
        
        # Palabras de negación (PASO 5)
        self.negations = ["no", "nunca", "jamas", "tampoco", "ni"]  # Sin acento en jamás
        
        # Productos conocidos (para extracción de entidades)
        self.known_products = [
            "silla", "sillas", "escritorio", "escritorios", "mesa", "mesas",
            "laptop", "laptops", "computador", "computadora", "pc",
            "teclado", "teclados", "mouse", "ratón", "monitor", "monitores",
            "sillón", "sillones", "estantería", "estanterías", "archivador",
            "archivadores", "lámpara", "lámparas"
        ]
        
        # Colores comunes
        self.known_colors = [
            "negro", "negra", "blanco", "blanca", "gris", "azul",
            "rojo", "roja", "verde", "amarillo", "café", "marrón",
            "beige", "plateado", "dorado"
        ]
        
        logger.info(
            f"EnhancedIntentClassifier inicializado - "
            f"{len(self.intent_keywords)} intents, "
            f"threshold default: {default_threshold}"
        )
    
    # ============================================
    # PASO 2: MÉTODO PRINCIPAL
    # ============================================
    
    def classify(self, message: str) -> IntentResult:
        """
        Clasifica el mensaje y extrae entidades.
        
        Args:
            message: Mensaje del usuario
            
        Returns:
            IntentResult con intent, confidence y entidades
            
        Example:
            >>> classifier = EnhancedIntentClassifier()
            >>> result = classifier.classify("necesito 10 sillas negras")
            >>> print(result.intent)
            'product_search'
            >>> print(result.entities)
            {'quantity': 10, 'color': 'negro', 'product': 'sillas'}
        """
        # 1. Normalizar mensaje
        normalized = self._normalize(message)
        
        # 2. Corregir typos
        corrected = self._fix_typos(normalized)
        
        # 3. Detectar negaciones
        has_negation = self._has_negation(corrected)
        
        # 4. Calcular scores para cada intent
        scores = self._calculate_scores(corrected)
        
        # 5. Ajustar scores si hay negación
        if has_negation:
            scores = self._adjust_for_negation(scores)
        
        # 6. Seleccionar mejor intent
        best_intent = max(scores, key=scores.get)
        confidence = scores[best_intent]
        
        # 7. Verificar threshold
        threshold = self.thresholds.get(best_intent, self.default_threshold)
        if confidence < threshold:
            best_intent = "general_inquiry"
            confidence = scores.get("general_inquiry", 0.5)
        
        # 8. Extraer entidades
        entities = self._extract_entities(message, corrected)
        
        # 9. Logging
        logger.debug(
            f"Intent classified: {best_intent} "
            f"(confidence: {confidence:.2f}, "
            f"negation: {has_negation})"
        )
        
        return IntentResult(
            intent=best_intent,
            confidence=confidence,
            entities=entities,
            has_negation=has_negation,
            all_scores=scores
        )
    
    # ============================================
    # PASO 3: KEYWORDS EXPANDIDOS
    # ============================================
    
    def _initialize_keywords(self) -> Dict:
        """
        Inicializa keywords expandidos (3x más que versión original).
        
        Returns:
            Dict con keywords y pesos por intent
        """
        return {
            "greeting": {
                "keywords": [
                    # Saludos formales
                    "hola", "buenos días", "buenas tardes", "buenas noches",
                    "buen día", "buena tarde", "buena noche",
                    
                    # Saludos informales
                    "hey", "holi", "holaaa", "holaa", "ola", "que tal",
                    "qué tal", "cómo estás", "como estas", "como va",
                    "cómo va", "qué hubo", "que hubo",
                    
                    # Saludos telefónicos
                    "aló", "alo", "bueno", "diga", "dígame"
                ],
                "weight": 1.0,
                "boost_words": ["buenos", "buenas", "buen", "buena"]
            },
            
            "product_search": {
                "keywords": [
                    # Verbos de búsqueda
                    "busco", "buscar", "buscando", "necesito", "necesitar",
                    "quiero", "queriendo", "quisiera", "requiero", "requerer",
                    "estoy buscando", "ando buscando", "me interesa",
                    "me gustaría", "deseo",
                    
                    # Preguntas sobre disponibilidad
                    "tienen", "hay", "venden", "manejan", "trabajan",
                    "cuentan con", "disponen", "existe", "existen",
                    
                    # Tipos de productos (genéricos)
                    "producto", "productos", "artículo", "artículos",
                    "mercancía", "cosa", "cosas",
                    
                    # Productos específicos
                    "silla", "sillas", "escritorio", "escritorios",
                    "mesa", "mesas", "laptop", "computador", "pc",
                    "teclado", "mouse", "monitor", "sillón"
                ],
                "weight": 0.8,
                "boost_words": ["busco", "necesito", "quiero"]
            },
            
            "price_inquiry": {
                "keywords": [
                    # Precio directo
                    "precio", "precios", "cuánto cuesta", "cuanto cuesta",
                    "cuánto vale", "cuanto vale", "cuánto es", "cuanto es",
                    "cuánto sale", "cuanto sale", "valor", "valores",
                    "cuál es el precio", "cual es el precio",
                    
                    # Presupuesto
                    "presupuesto", "económico", "económica", "barato",
                    "barata", "baratos", "baratas", "costoso", "costosa",
                    "caro", "cara", "caros", "caras",
                    
                    # Comparaciones
                    "más barato", "mas barato", "más económico",
                    "mejor precio", "menor precio",
                    
                    # Ofertas
                    "oferta", "ofertas", "descuento", "descuentos",
                    "promoción", "promociones", "rebaja", "rebajas",
                    "precio especial", "precio de oferta"
                ],
                "weight": 0.9,
                "boost_words": ["precio", "cuánto", "cuanto", "valor"]
            },
            
            "availability_check": {
                "keywords": [
                    # Stock
                    "disponible", "disponibles", "disponibilidad",
                    "hay stock", "tienen stock", "en stock", "stock",
                    "quedan", "quedan unidades", "hay unidades",
                    "agotado", "sin stock",
                    
                    # Envío y entrega
                    "envío", "envio", "enviar", "despacho", "entregar",
                    "entrega", "domicilio", "a domicilio",
                    "cuándo llega", "cuando llega", "tiempo de entrega",
                    "demora", "tarda", "cuánto tarda",
                    
                    # Variantes
                    "color", "colores", "talla", "tallas", "tamaño",
                    "tamaños", "modelo", "modelos", "versión", "versiones"
                ],
                "weight": 0.85,
                "boost_words": ["disponible", "hay", "stock"]
            },
            
            "complaint": {
                "keywords": [
                    # Problemas
                    "problema", "problemas", "no funciona", "no sirve",
                    "defectuoso", "defectuosa", "dañado", "dañada",
                    "roto", "rota", "malo", "mala", "malísimo",
                    "pésimo", "horrible",
                    
                    # Quejas formales
                    "queja", "quejas", "reclamo", "reclamos",
                    "reclamar", "quejar", "inconformidad",
                    
                    # Devoluciones
                    "devolver", "devolución", "reembolso", "reintegro",
                    "garantía", "garantia",
                    
                    # Incumplimientos
                    "no me llegó", "no llego", "no ha llegado",
                    "nunca llegó", "perdido", "extraviado"
                ],
                "weight": 1.0,
                "boost_words": ["problema", "queja", "reclamo", "devolver"]
            },
            
            "purchase_intent": {
                "keywords": [
                    # Compra directa
                    "comprar", "compro", "adquirir", "adquiero",
                    "llevar", "llevo", "lo quiero", "la quiero",
                    "me lo llevo", "me la llevo",
                    
                    # Cantidades
                    "cuántas unidades", "cuantas unidades", "unidades",
                    "cantidad",
                    
                    # Proceso
                    "proceder", "continuar", "seguir", "confirmar",
                    "hacer pedido", "realizar pedido",
                    
                    # Reserva
                    "separar", "apartar", "reservar", "guardar"
                ],
                "weight": 0.95,
                "boost_words": ["comprar", "llevar", "confirmar"]
            },
            
            "farewell": {
                "keywords": [
                    # Despedidas formales
                    "adiós", "adios", "hasta luego", "hasta pronto",
                    "nos vemos", "hasta la vista",
                    
                    # Despedidas informales
                    "chao", "chau", "bye", "bay", "nos vemos",
                    
                    # Agradecimientos de cierre
                    "gracias", "muchas gracias", "mil gracias",
                    "te agradezco", "agradezco", "perfecto gracias",
                    "ok gracias", "listo gracias"
                ],
                "weight": 0.9,
                "boost_words": ["adiós", "adios", "gracias", "chao"]
            },
            
            "general_inquiry": {
                "keywords": [
                    # Preguntas generales
                    "información", "informacion", "info", "detalles",
                    "ayuda", "ayúdame", "ayudame", "asesoría",
                    "asesorarme", "consulta", "pregunta",
                    
                    # Dudas
                    "duda", "dudas", "no sé", "no se", "no entiendo"
                ],
                "weight": 0.5,
                "boost_words": ["ayuda", "información", "info"]
            }
        }
    
    # ============================================
    # PASO 4: CORRECCIÓN DE TYPOS
    # ============================================
    
    def _initialize_typos(self) -> Dict[str, str]:
        """
        Diccionario de typos comunes y sus correcciones.
        
        Returns:
            Dict {typo: corrección}
        """
        return {
            # Necesito
            "nesesito": "necesito",
            "nesecito": "necesito",
            "nececito": "necesito",
            
            # Quiero
            "kiero": "quiero",
            "quero": "quiero",
            "kero": "quiero",
            
            # Silla
            "siya": "silla",
            "cilla": "silla",
            "siyya": "silla",
            
            # Precio
            "preio": "precio",
            "presio": "precio",
            "preci": "precio",
            
            # Hay
            "ai": "hay",
            "ay": "hay",
            "ahi": "hay",
            
            # Disponible
            "disponivle": "disponible",
            "disponile": "disponible",
            
            # Escritorio
            "esritorio": "escritorio",
            "ecritorio": "escritorio",
            
            # Cuánto
            "cuanto": "cuánto",
            "qanto": "cuánto",
            
            # Bueno/Buenos
            "vueno": "bueno",
            "vuenos": "buenos"
        }
    
    def _fix_typos(self, text: str) -> str:
        """
        Corrige typos comunes en el texto.
        
        Args:
            text: Texto normalizado
            
        Returns:
            Texto con typos corregidos
        """
        words = text.split()
        corrected_words = []
        
        for word in words:
            # Si hay corrección, usarla
            if word in self.typo_corrections:
                corrected = self.typo_corrections[word]
                corrected_words.append(corrected)
                logger.debug(f"Typo corregido: '{word}' -> '{corrected}'")
            else:
                corrected_words.append(word)
        
        return " ".join(corrected_words)
    
    # ============================================
    # PASO 5: DETECCIÓN DE NEGACIONES
    # ============================================
    
    def _has_negation(self, text: str) -> bool:
        """
        Detecta si el mensaje contiene negaciones.
        
        Args:
            text: Texto normalizado
            
        Returns:
            True si hay negación
            
        Examples:
            >>> classifier._has_negation("no quiero sillas")
            True
            >>> classifier._has_negation("quiero sillas")
            False
        """
        words = text.split()
        
        # Buscar negaciones
        for negation in self.negations:
            if negation in words:
                logger.debug(f"Negación detectada: '{negation}'")
                return True
        
        return False
    
    def _adjust_for_negation(self, scores: Dict[str, float]) -> Dict[str, float]:
        """
        Ajusta scores cuando hay negación en el mensaje.
        
        La negación reduce la confianza en todos los intents.
        
        Args:
            scores: Scores originales
            
        Returns:
            Scores ajustados
        """
        adjusted = {}
        
        for intent, score in scores.items():
            # Reducir confianza un 30%
            adjusted[intent] = score * 0.7
        
        logger.debug("Scores ajustados por negación")
        return adjusted
    
    # ============================================
    # PASO 6: EXTRACCIÓN DE ENTIDADES
    # ============================================
    
    def _extract_entities(
        self, 
        original_message: str, 
        normalized_message: str
    ) -> Dict:
        """
        Extrae entidades del mensaje.
        
        Entidades detectadas:
        - quantity: Números (1, 10, 50)
        - colors: Colores mencionados
        - products: Productos mencionados
        - price_range: Rangos de precio (opcional)
        
        Args:
            original_message: Mensaje original del usuario
            normalized_message: Mensaje normalizado
            
        Returns:
            Dict con entidades extraídas
        """
        entities = {}
        
        # 1. Extraer cantidad
        quantity = self._extract_quantity(original_message)
        if quantity:
            entities["quantity"] = quantity
        
        # 2. Extraer colores
        colors = self._extract_colors(normalized_message)
        if colors:
            entities["colors"] = colors
            entities["color"] = colors[0]  # Primera mención
        
        # 3. Extraer productos
        products = self._extract_products(normalized_message)
        if products:
            entities["products"] = products
            entities["product"] = products[0]  # Primera mención
        
        # 4. Extraer rango de precio (si menciona números con $ o "pesos")
        price_range = self._extract_price_range(original_message)
        if price_range:
            entities["price_range"] = price_range
        
        if entities:
            logger.debug(f"Entidades extraídas: {entities}")
        
        return entities
    
    def _extract_quantity(self, text: str) -> Optional[int]:
        """
        Extrae cantidad (números) del mensaje.
        
        Examples:
            "necesito 10 sillas" -> 10
            "busco tres escritorios" -> 3
        """
        # Números escritos
        text_to_number = {
            "un": 1, "uno": 1, "una": 1,
            "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5,
            "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10
        }
        
        # Buscar números escritos
        words = text.lower().split()
        for word in words:
            if word in text_to_number:
                return text_to_number[word]
        
        # Buscar números dígitos
        numbers = re.findall(r'\b\d+\b', text)
        if numbers:
            return int(numbers[0])
        
        return None
    
    def _extract_colors(self, text: str) -> List[str]:
        """Extrae colores mencionados (normaliza género)."""
        found_colors = []
        
        # Mapeo de colores con género a forma base
        color_mapping = {
            "negra": "negro",
            "negro": "negro",
            "blanca": "blanco",
            "blanco": "blanco",
            "roja": "rojo",
            "rojo": "rojo",
            "amarilla": "amarillo",
            "amarillo": "amarillo",
            "gris": "gris",
            "azul": "azul",
            "verde": "verde",
            "cafe": "café",
            "marron": "marrón",
        }
        
        for color in self.known_colors:
            if color in text:
                # Normalizar a masculino singular
                normalized = color_mapping.get(color, color)
                if normalized not in found_colors:
                    found_colors.append(normalized)
        
        return found_colors
    
    def _extract_products(self, text: str) -> List[str]:
        """Extrae productos mencionados."""
        found_products = []
        
        for product in self.known_products:
            if product in text:
                # Evitar duplicados (silla y sillas)
                base = product.rstrip('s')
                if base not in [p.rstrip('s') for p in found_products]:
                    found_products.append(product)
        
        return found_products
    
    def _extract_price_range(self, text: str) -> Optional[Dict]:
        """
        Extrae rango de precio si lo menciona.
        
        Examples:
            "entre $100,000 y $200,000" -> {"min": 100000, "max": 200000}
            "menos de $50,000" -> {"max": 50000}
            "más de $100,000" -> {"min": 100000}
        """
        # Buscar patrones de precio
        # Formato: $XXX,XXX o XXX,XXX pesos
        price_pattern = r'\$?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)'
        prices = re.findall(price_pattern, text)
        
        if not prices:
            return None
        
        # Convertir a números
        price_values = []
        for price in prices:
            clean = price.replace(',', '')
            try:
                price_values.append(int(float(clean)))
            except:
                continue
        
        if not price_values:
            return None
        
        # Detectar "entre X y Y"
        if "entre" in text.lower() and len(price_values) >= 2:
            return {"min": min(price_values), "max": max(price_values)}
        
        # Detectar "menos de X"
        if "menos de" in text.lower() or "menor a" in text.lower():
            return {"max": price_values[0]}
        
        # Detectar "más de X"
        if "más de" in text.lower() or "mayor a" in text.lower():
            return {"min": price_values[0]}
        
        # Un solo precio mencionado
        return {"target": price_values[0]}
    
    # ============================================
    # SCORING Y NORMALIZACIÓN
    # ============================================
    
    def _calculate_scores(self, text: str) -> Dict[str, float]:
        """
        Calcula scores para cada intent (VERSIÓN CORREGIDA).
        
        Algoritmo mejorado:
        1. Contar matches de keywords
        2. Score basado en matches, no en porcentaje del total
        3. Aplicar pesos
        4. Aplicar boost para palabras clave importantes
        
        Args:
            text: Texto normalizado y corregido
            
        Returns:
            Dict {intent: score}
        """
        scores = {}
        words_in_text = set(text.split())
        
        for intent, data in self.intent_keywords.items():
            keywords = data["keywords"]
            weight = data["weight"]
            boost_words = data.get("boost_words", [])
            
            # Contar matches
            matches = 0
            boost_matches = 0
            
            for keyword in keywords:
                # Buscar keyword en texto (substring)
                if keyword in text:
                    matches += 1
                    
                    # Boost si es palabra clave importante
                    if any(boost in keyword for boost in boost_words):
                        boost_matches += 1
            
            # Score base (CORREGIDO)
            if matches > 0:
                # Score basado en cantidad de matches
                # Normalizado a escala 0-1, pero más generoso
                base_score = min(matches / 5.0, 1.0)  # 5 matches = score de 1.0
                
                # Aplicar boost (20% extra por boost word)
                boost = 1.0 + (boost_matches * 0.2)
                
                # Aplicar peso del intent
                final_score = min(base_score * boost * weight, 1.0)
                
                scores[intent] = final_score
            else:
                scores[intent] = 0.0
        
        return scores
    
    def _normalize(self, text: str) -> str:
        """
        Normaliza el texto.
        
        - Minúsculas
        - Remueve acentos
        - Limpia espacios extras
        
        Args:
            text: Texto original
            
        Returns:
            Texto normalizado
        """
        # Minúsculas
        text = text.lower()
        
        # Remover acentos
        text = self._remove_accents(text)
        
        # Limpiar espacios
        text = " ".join(text.split())
        
        return text
    
    @staticmethod
    def _remove_accents(text: str) -> str:
        """Remueve acentos del texto."""
        replacements = {
            'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
            'ñ': 'n', 'ü': 'u',
            'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O', 'Ú': 'U',
            'Ñ': 'N', 'Ü': 'U'
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        return text


# ============================================
# HELPER FUNCTIONS
# ============================================

def create_enhanced_classifier(**kwargs) -> EnhancedIntentClassifier:
    """
    Helper para crear classifier.
    
    Args:
        **kwargs: Parámetros para EnhancedIntentClassifier
        
    Returns:
        Classifier configurado
    """
    return EnhancedIntentClassifier(**kwargs)