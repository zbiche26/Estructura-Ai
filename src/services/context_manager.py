"""
Advanced Context Manager - Gestión avanzada de contexto conversacional

Mantiene y actualiza el contexto completo de la conversación:
- Historial de intents
- Productos mencionados
- Preferencias del usuario
- Estado de la conversación
- Perfil del usuario
"""
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from src.services.intent_classifier import Intent, IntentType
from src.core.logger import logger


# ==================== TIPOS ====================

class ConversationStage(Enum):
    """Etapas de la conversación"""
    DISCOVERY = "discovery"  # Explorando opciones
    COMPARISON = "comparison"  # Comparando productos
    DECISION = "decision"  # Decidiendo compra
    PURCHASE = "purchase"  # Comprando
    POST_PURCHASE = "post_purchase"  # Después de compra
    SUPPORT = "support"  # Soporte/problema


@dataclass
class ProductMention:
    """Producto mencionado en la conversación"""
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    mentioned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    interest_level: float = 0.5  # 0.0 - 1.0
    questions_about: List[str] = field(default_factory=list)


@dataclass
class UserPreferences:
    """Preferencias inferidas del usuario"""
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    preferred_brands: List[str] = field(default_factory=list)
    preferred_categories: List[str] = field(default_factory=list)
    preferred_features: List[str] = field(default_factory=list)
    price_sensitivity: float = 0.5  # 0.0 (no le importa) - 1.0 (muy sensible)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "budget_min": self.budget_min,
            "budget_max": self.budget_max,
            "preferred_brands": self.preferred_brands,
            "preferred_categories": self.preferred_categories,
            "preferred_features": self.preferred_features,
            "price_sensitivity": self.price_sensitivity
        }


@dataclass
class ConversationContext:
    """Contexto completo de la conversación"""
    conversation_id: str
    tenant_id: str
    user_id: Optional[str] = None
    
    # Historial
    intent_history: List[Intent] = field(default_factory=list)
    mentioned_products: List[ProductMention] = field(default_factory=list)
    
    # Estado
    current_stage: ConversationStage = ConversationStage.DISCOVERY
    preferences: UserPreferences = field(default_factory=UserPreferences)
    
    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    message_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario"""
        return {
            "conversation_id": self.conversation_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "intent_history": [
                {
                    "intent": i.intent,
                    "confidence": i.confidence,
                    "entities": i.entities
                }
                for i in self.intent_history
            ],
            "mentioned_products": [
                {
                    "product_id": p.product_id,
                    "product_name": p.product_name,
                    "interest_level": p.interest_level
                }
                for p in self.mentioned_products
            ],
            "current_stage": self.current_stage.value,
            "preferences": self.preferences.to_dict(),
            "message_count": self.message_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }


# ==================== ADVANCED CONTEXT MANAGER ====================

class AdvancedContextManager:
    """
    Gestor avanzado de contexto conversacional
    
    Mantiene el estado completo de múltiples conversaciones
    y actualiza el contexto dinámicamente.
    """
    
    def __init__(
        self,
        max_intent_history: int = 20,
        max_product_mentions: int = 10
    ):
        """
        Inicializa el gestor
        
        Args:
            max_intent_history: Máximo de intents en historial
            max_product_mentions: Máximo de productos en memoria
        """
        self.contexts: Dict[str, ConversationContext] = {}
        self.max_intent_history = max_intent_history
        self.max_product_mentions = max_product_mentions
        
        logger.info("AdvancedContextManager inicializado")
    
    def create_context(
        self,
        conversation_id: str,
        tenant_id: str,
        user_id: Optional[str] = None
    ) -> ConversationContext:
        """
        Crea un nuevo contexto
        
        Args:
            conversation_id: ID de la conversación
            tenant_id: ID del tenant
            user_id: ID del usuario (opcional)
            
        Returns:
            Contexto creado
        """
        context = ConversationContext(
            conversation_id=conversation_id,
            tenant_id=tenant_id,
            user_id=user_id
        )
        
        self.contexts[conversation_id] = context
        
        logger.info(f"Contexto creado: {conversation_id}")
        
        return context
    
    def get_context(
        self,
        conversation_id: str
    ) -> Optional[ConversationContext]:
        """
        Obtiene un contexto existente
        
        Args:
            conversation_id: ID de la conversación
            
        Returns:
            Contexto o None
        """
        return self.contexts.get(conversation_id)
    
    def update_with_intent(
        self,
        conversation_id: str,
        intent: Intent
    ) -> ConversationContext:
        """
        Actualiza contexto con un nuevo intent
        
        Args:
            conversation_id: ID de la conversación
            intent: Intent detectado
            
        Returns:
            Contexto actualizado
        """
        context = self.get_context(conversation_id)
        
        if not context:
            raise ValueError(f"Contexto {conversation_id} no encontrado")
        
        # 1. Agregar a historial
        context.intent_history.append(intent)
        
        # Limitar tamaño
        if len(context.intent_history) > self.max_intent_history:
            context.intent_history = context.intent_history[-self.max_intent_history:]
        
        # 2. Actualizar stage según intent
        context.current_stage = self._infer_stage(context.intent_history)
        
        # 3. Extraer preferencias de entidades
        if intent.entities:
            self._update_preferences(context, intent.entities)
        
        # 4. Actualizar metadata
        context.updated_at = datetime.now(timezone.utc)
        context.message_count += 1
        
        logger.debug(
            f"Contexto actualizado: {conversation_id}, "
            f"stage={context.current_stage.value}"
        )
        
        return context
    
    def add_product_mention(
        self,
        conversation_id: str,
        product_id: Optional[str] = None,
        product_name: Optional[str] = None,
        interest_level: float = 0.5
    ):
        """
        Agrega un producto mencionado
        
        Args:
            conversation_id: ID de la conversación
            product_id: ID del producto (opcional)
            product_name: Nombre del producto (opcional)
            interest_level: Nivel de interés (0.0 - 1.0)
        """
        context = self.get_context(conversation_id)
        
        if not context:
            raise ValueError(f"Contexto {conversation_id} no encontrado")
        
        # Verificar si ya existe
        for mention in context.mentioned_products:
            if (mention.product_id == product_id or 
                mention.product_name == product_name):
                # Actualizar interés
                mention.interest_level = max(
                    mention.interest_level,
                    interest_level
                )
                mention.mentioned_at = datetime.now(timezone.utc)
                return
        
        # Agregar nuevo
        mention = ProductMention(
            product_id=product_id,
            product_name=product_name,
            interest_level=interest_level
        )
        
        context.mentioned_products.append(mention)
        
        # Limitar tamaño
        if len(context.mentioned_products) > self.max_product_mentions:
            # Ordenar por interés y mantener los más relevantes
            context.mentioned_products.sort(
                key=lambda x: x.interest_level,
                reverse=True
            )
            context.mentioned_products = context.mentioned_products[:self.max_product_mentions]
        
        logger.debug(
            f"Producto agregado: {product_name or product_id}, "
            f"interest={interest_level:.2f}"
        )
    
    def get_last_intents(
        self,
        conversation_id: str,
        n: int = 5
    ) -> List[Intent]:
        """
        Obtiene los últimos N intents
        
        Args:
            conversation_id: ID de la conversación
            n: Número de intents
            
        Returns:
            Lista de intents
        """
        context = self.get_context(conversation_id)
        
        if not context:
            return []
        
        return context.intent_history[-n:]
    
    def get_mentioned_products(
        self,
        conversation_id: str,
        min_interest: float = 0.0
    ) -> List[ProductMention]:
        """
        Obtiene productos mencionados
        
        Args:
            conversation_id: ID de la conversación
            min_interest: Nivel mínimo de interés
            
        Returns:
            Lista de productos
        """
        context = self.get_context(conversation_id)
        
        if not context:
            return []
        
        return [
            p for p in context.mentioned_products
            if p.interest_level >= min_interest
        ]
    
    def get_conversation_summary(
        self,
        conversation_id: str
    ) -> Dict[str, Any]:
        """
        Obtiene un resumen del contexto
        
        Args:
            conversation_id: ID de la conversación
            
        Returns:
            Resumen del contexto
        """
        context = self.get_context(conversation_id)
        
        if not context:
            return {}
        
        # Contar intents por tipo
        intent_counts = {}
        for intent in context.intent_history:
            intent_counts[intent.intent] = intent_counts.get(intent.intent, 0) + 1
        
        # Productos más mencionados
        top_products = sorted(
            context.mentioned_products,
            key=lambda x: x.interest_level,
            reverse=True
        )[:3]
        
        summary = {
            "conversation_id": conversation_id,
            "stage": context.current_stage.value,
            "message_count": context.message_count,
            "intent_distribution": intent_counts,
            "top_products": [
                {
                    "name": p.product_name,
                    "interest": p.interest_level
                }
                for p in top_products
            ],
            "preferences": context.preferences.to_dict(),
            "duration_minutes": (
                datetime.now(timezone.utc) - context.created_at
            ).total_seconds() / 60
        }
        
        return summary
    
    def reset_context(self, conversation_id: str):
        """
        Resetea un contexto
        
        Args:
            conversation_id: ID de la conversación
        """
        if conversation_id in self.contexts:
            del self.contexts[conversation_id]
            logger.info(f"Contexto reseteado: {conversation_id}")
    
    def _infer_stage(
        self,
        intent_history: List[Intent]
    ) -> ConversationStage:
        """
        Infiere el stage de la conversación
        
        Args:
            intent_history: Historial de intents
            
        Returns:
            Stage inferido
        """
        if not intent_history:
            return ConversationStage.DISCOVERY
        
        # Últimos 3 intents
        recent = [i.intent for i in intent_history[-3:]]
        
        # Reglas de inferencia
        if "purchase_intent" in recent:
            return ConversationStage.PURCHASE
        
        if "complaint" in recent:
            return ConversationStage.SUPPORT
        
        if recent.count("product_info") >= 2:
            return ConversationStage.COMPARISON
        
        if "price_inquiry" in recent or "availability" in recent:
            return ConversationStage.DECISION
        
        return ConversationStage.DISCOVERY
    
    def _update_preferences(
        self,
        context: ConversationContext,
        entities: Dict[str, Any]
    ):
        """
        Actualiza preferencias desde entidades
        
        Args:
            context: Contexto actual
            entities: Entidades extraídas
        """
        prefs = context.preferences
        
        # Budget
        if "price" in entities:
            price = entities["price"]
            if prefs.budget_max is None or price > prefs.budget_max:
                prefs.budget_max = price * 1.2  # +20% margen
        
        # Brands
        if "brand" in entities:
            brand = entities["brand"]
            if brand not in prefs.preferred_brands:
                prefs.preferred_brands.append(brand)
        
        # Product types (como categorías)
        if "product_type" in entities:
            ptype = entities["product_type"]
            if ptype not in prefs.preferred_categories:
                prefs.preferred_categories.append(ptype)
        
        # Price sensitivity (si pregunta mucho por precio)
        intent_history_types = [i.intent for i in context.intent_history]
        price_inquiries = intent_history_types.count("price_inquiry")
        total_intents = len(intent_history_types)
        
        if total_intents > 0:
            prefs.price_sensitivity = min(
                price_inquiries / total_intents,
                1.0
            )


# ==================== HELPER FUNCTIONS ====================

def create_advanced_context_manager(
    **kwargs
) -> AdvancedContextManager:
    """
    Helper para crear context manager
    
    Args:
        **kwargs: Parámetros para AdvancedContextManager
        
    Returns:
        Context manager configurado
    """
    return AdvancedContextManager(**kwargs)