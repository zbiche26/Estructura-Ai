"""
Strategy Pattern - Comportamiento Dinámico del Agente
======================================================

Este módulo implementa el patrón Strategy para definir diferentes
comportamientos del agente de ventas según el contexto de la conversación.

Conceptos clave:
- Strategy: Algoritmo encapsulado que puede intercambiarse
- Context: Información necesaria para elegir la estrategia
- Selector: Elige la estrategia más apropiada

Estrategias implementadas:
1. WelcomeStrategy: Primer contacto con el cliente
2. ProductSearchStrategy: Cliente busca productos específicos
3. ClosingStrategy: Cliente muestra intención de compra
4. PersonalizedRecommendationStrategy: Recomendar según presupuesto
5. GeneralInquiryStrategy: Consultas generales (fallback)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any
from src.core.logger import logger

# Importar ConversationContext desde context_manager (evitar duplicación)
from src.services.context_manager import ConversationContext


# ============================================
# INTERFAZ BASE: STRATEGY
# ============================================

class IAgentStrategy(ABC):
    """
    Interfaz base para todas las estrategias del agente
    
    Cada estrategia define cómo el agente debe comportarse
    en una situación específica.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre identificador de la estrategia"""
        pass
    
    @abstractmethod
    def is_applicable(self, context: ConversationContext) -> bool:
        """
        Determina si esta estrategia aplica al contexto actual
        
        Args:
            context: Contexto de la conversación
        
        Returns:
            True si la estrategia es apropiada, False si no
        """
        pass
    
    @abstractmethod
    def generate_prompt(self, mensaje_usuario: str, 
                       context: ConversationContext) -> str:
        """
        Genera el prompt para el LLM según esta estrategia
        
        Args:
            mensaje_usuario: Último mensaje del usuario
            context: Contexto de la conversación
        
        Returns:
            Prompt optimizado para el LLM
        """
        pass
    
    @abstractmethod
    def get_priority(self) -> int:
        """
        Prioridad de la estrategia (mayor = más prioritaria)
        
        Útil cuando múltiples estrategias son aplicables.
        
        Returns:
            Número de prioridad (0-100)
        """
        pass


# ============================================
# ESTRATEGIA 1: BIENVENIDA
# ============================================

class WelcomeStrategy(IAgentStrategy):
    """
    Estrategia para el primer contacto con el cliente
    
    Se activa cuando:
    - No hay historial de conversación
    - Es el primer mensaje del cliente
    """
    
    @property
    def name(self) -> str:
        return "welcome"
    
    def is_applicable(self, context: ConversationContext) -> bool:
        """
        Aplica solo si no hay historial previo
        """
        # CORREGIDO: usar intent_history en lugar de tiene_historial()
        return len(context.intent_history) == 0
    
    def generate_prompt(self, mensaje_usuario: str, 
                       context: ConversationContext) -> str:
        """
        Genera prompt de bienvenida cálido y profesional
        """
        return f"""Eres un asistente de ventas amigable y profesional.

Un cliente nuevo te ha contactado por primera vez y dice:
"{mensaje_usuario}"

OBJETIVOS:
1. Dale una bienvenida cálida y profesional
2. Preséntate brevemente como su asistente de ventas
3. Pregunta cómo puedes ayudarle hoy
4. Mantén un tono conversacional y natural
5. NO menciones productos aún, primero entiende qué necesita

IMPORTANTE:
- Sé breve (máximo 3-4 líneas)
- Sé amigable pero profesional
- No uses emojis excesivos

Responde:"""
    
    def get_priority(self) -> int:
        return 100  # Máxima prioridad (primer mensaje)


# ============================================
# ESTRATEGIA 2: BÚSQUEDA DE PRODUCTOS
# ============================================

class ProductSearchStrategy(IAgentStrategy):
    """
    Estrategia cuando el cliente busca productos específicos
    
    Se activa cuando:
    - El cliente menciona palabras clave de búsqueda
    - Hay productos disponibles en el catálogo
    """
    
    # Palabras clave que indican búsqueda
    BUSQUEDA_KEYWORDS = [
        'necesito', 'busco', 'quiero', 'tienen', 'venden',
        'hay', 'existe', 'disponible', 'me interesa',
        'cuánto cuesta', 'precio', 'cuál'
    ]
    
    @property
    def name(self) -> str:
        return "product_search"
    
    def is_applicable(self, context: ConversationContext) -> bool:
        """
        Aplica si el mensaje contiene palabras de búsqueda
        """
        # Obtener último intent
        if not context.intent_history:
            return False
        
        ultimo_intent = context.intent_history[-1].intent.lower()
        return "product" in ultimo_intent or "search" in ultimo_intent
    
    def generate_prompt(self, mensaje_usuario: str, 
                       context: ConversationContext) -> str:
        """
        Genera prompt enfocado en mostrar productos relevantes
        """
        return f"""Eres un experto asesor de ventas.

El cliente dice:
"{mensaje_usuario}"

OBJETIVOS:
1. Identifica qué productos se ajustan a lo que busca
2. Presenta los productos de forma atractiva
3. Menciona características relevantes, precio y disponibilidad
4. Sé específico con los números (precios, stock)
5. Pregunta para entender mejor sus necesidades

IMPORTANTE:
- Menciona máximo 2-3 productos
- Siempre incluye precio y stock
- Destaca beneficios, no solo características
- Pregunta para clarificar necesidades

Responde de forma consultiva y útil:"""
    
    def get_priority(self) -> int:
        return 80


# ============================================
# ESTRATEGIA 3: CIERRE DE VENTA
# ============================================

class ClosingStrategy(IAgentStrategy):
    """
    Estrategia para cerrar la venta
    
    Se activa cuando:
    - El cliente muestra intención clara de compra
    - Usa palabras como "comprar", "llevar", "quiero"
    """
    
    COMPRA_KEYWORDS = [
        'comprar', 'llevar', 'me llevo', 'quiero',
        'precio final', 'cuánto es', 'cómo pago',
        'factura', 'pedido', 'confirmar', 'purchase'
    ]
    
    @property
    def name(self) -> str:
        return "closing"
    
    def is_applicable(self, context: ConversationContext) -> bool:
        """
        Aplica si hay intención de compra clara
        """
        # Verificar si último intent es purchase_intent
        if context.intent_history:
            ultimo_intent = context.intent_history[-1].intent
            if "purchase" in ultimo_intent.lower():
                return True
        
        return False
    
    def generate_prompt(self, mensaje_usuario: str, 
                       context: ConversationContext) -> str:
        """
        Genera prompt enfocado en cerrar la venta
        """
        productos_mencionados = ""
        if context.mentioned_products:
            productos_mencionados = "\n".join([
                f"- {p.product_name}" 
                for p in context.mentioned_products[-3:]
            ])
        else:
            productos_mencionados = "Ningún producto específico seleccionado aún"
        
        return f"""Eres un vendedor experto cerrando una venta.

El cliente dice:
"{mensaje_usuario}"

Productos en los que ha mostrado interés:
{productos_mencionados}

OBJETIVOS:
1. Confirma qué producto(s) quiere comprar
2. Pregunta la cantidad deseada
3. Verifica que hay stock suficiente
4. Calcula el total claramente
5. Explica los siguientes pasos (pago, entrega)
6. Mantén tono entusiasta pero profesional

IMPORTANTE:
- Sé claro con precios y cantidades
- Verifica stock antes de confirmar
- Da un resumen claro del pedido
- Pregunta por detalles de entrega

Si el cliente confirma, proporciona resumen del pedido.

Responde de forma clara y profesional:"""
    
    def get_priority(self) -> int:
        return 90  # Alta prioridad


# ============================================
# ESTRATEGIA 4: RECOMENDACIÓN PERSONALIZADA
# ============================================

class PersonalizedRecommendationStrategy(IAgentStrategy):
    """
    Estrategia de recomendación según presupuesto/preferencias
    
    Se activa cuando:
    - El cliente menciona un presupuesto
    - Pide recomendaciones
    """
    
    RECOMENDACION_KEYWORDS = [
        'recomienda', 'sugieres', 'recomendar',
        'presupuesto', 'cuánto', 'precio',
        'económico', 'barato', 'mejor opción'
    ]
    
    @property
    def name(self) -> str:
        return "personalized_recommendation"
    
    def is_applicable(self, context: ConversationContext) -> bool:
        """
        Aplica si hay preferencias de presupuesto
        """
        # CORREGIDO: usar getattr para evitar AttributeError
        if context.preferences:
            budget = getattr(context.preferences, 'estimated_budget', None)
            if budget and budget > 0:
                return True
        
        return False
    
    def generate_prompt(self, mensaje_usuario: str, 
                       context: ConversationContext) -> str:
        """
        Genera prompt enfocado en recomendar
        """
        presupuesto_info = ""
        # CORREGIDO: usar getattr para evitar AttributeError
        if context.preferences:
            budget = getattr(context.preferences, 'estimated_budget', None)
            if budget and budget > 0:
                presupuesto_info = f"Presupuesto del cliente: ${budget:.2f}"
        
        return f"""Eres un asesor experto en recomendar productos.

{presupuesto_info}

El cliente dice:
"{mensaje_usuario}"

OBJETIVOS:
1. Analiza las necesidades del cliente
2. Recomienda los mejores productos para su caso
3. Explica POR QUÉ recomiendas cada producto
4. Ofrece alternativas (más económica o premium)
5. Sé honesto sobre relación calidad-precio

IMPORTANTE:
- Personaliza según el cliente
- Justifica tus recomendaciones
- Ofrece 2-3 opciones
- Menciona pros y contras

Responde de forma consultiva y personalizada:"""
    
    def get_priority(self) -> int:
        return 70


# ============================================
# ESTRATEGIA 5: CONSULTA GENERAL (FALLBACK)
# ============================================

class GeneralInquiryStrategy(IAgentStrategy):
    """
    Estrategia para consultas generales
    
    Esta es la estrategia por defecto (fallback).
    Se usa cuando ninguna otra estrategia aplica.
    """
    
    @property
    def name(self) -> str:
        return "general_inquiry"
    
    def is_applicable(self, context: ConversationContext) -> bool:
        """
        Siempre aplicable (estrategia por defecto)
        """
        return True
    
    def generate_prompt(self, mensaje_usuario: str, 
                       context: ConversationContext) -> str:
        """
        Genera prompt general y flexible
        """
        return f"""Eres un asistente de ventas útil y amigable.

El cliente dice:
"{mensaje_usuario}"

OBJETIVOS:
1. Responde su consulta de forma clara
2. Si no entiendes, pregunta para clarificar
3. Ofrece ayuda adicional si es relevante
4. Mantén la conversación fluida y natural
5. Sé proactivo en sugerir soluciones

IMPORTANTE:
- Sé conversacional
- Usa un tono amigable
- No fuerces ventas
- Ayuda genuinamente

Responde de forma natural y útil:"""
    
    def get_priority(self) -> int:
        return 1  # Prioridad más baja (fallback)


# ============================================
# SELECTOR DE ESTRATEGIA
# ============================================

class StrategySelector:
    """
    Selecciona la estrategia más apropiada según el contexto
    
    Analiza el contexto de la conversación y elige la estrategia
    con mayor prioridad entre las que son aplicables.
    """
    
    def __init__(self):
        """Inicializa el selector con todas las estrategias"""
        self.strategies: List[IAgentStrategy] = [
            WelcomeStrategy(),
            ProductSearchStrategy(),
            ClosingStrategy(),
            PersonalizedRecommendationStrategy(),
            GeneralInquiryStrategy()  # Siempre al final (fallback)
        ]
        
        logger.info(f"📋 StrategySelector inicializado con {len(self.strategies)} estrategias")
    
    def select(self, context: ConversationContext) -> IAgentStrategy:
        """
        Selecciona la mejor estrategia para el contexto
        
        Args:
            context: Contexto de la conversación
        
        Returns:
            Estrategia seleccionada
        """
        # Filtrar estrategias aplicables
        applicable = [
            s for s in self.strategies 
            if s.is_applicable(context)
        ]
        
        if not applicable:
            logger.warning("⚠️  No hay estrategias aplicables, usando fallback")
            return self.strategies[-1]  # GeneralInquiryStrategy
        
        # Ordenar por prioridad (mayor primero)
        applicable.sort(key=lambda s: s.get_priority(), reverse=True)
        
        # Seleccionar la de mayor prioridad
        selected = applicable[0]
        
        logger.info(f"🎯 Estrategia seleccionada: {selected.name} (prioridad: {selected.get_priority()})")
        
        return selected
    
    def register_strategy(self, strategy: IAgentStrategy):
        """
        Registra una nueva estrategia personalizada
        
        Args:
            strategy: Nueva estrategia a registrar
        """
        # Insertar antes del fallback (último elemento)
        self.strategies.insert(-1, strategy)
        logger.info(f"✅ Estrategia registrada: {strategy.name}")
    
    def get_all_strategies(self) -> List[IAgentStrategy]:
        """Retorna todas las estrategias registradas"""
        return self.strategies.copy()