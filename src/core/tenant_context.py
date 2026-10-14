"""
Tenant Context
Este módulo implementa el sistema de contexto multi-tenant del núcleo de la aplicación. 
Su responsabilidad es identificar y aislar al cliente (tenant) activo durante la ejecución de una request, 
garantizando seguridad, consistencia y escalabilidad en entornos concurrentes. 
El TenantContext encapsula la identidad, plan, configuración y features del tenant, mientras que 
TenantContextManager gestiona su ciclo de vida de forma thread-safe.
"""

from dataclasses import dataclass, field # Importa herramientas para crear clases de datos de forma limpia y declarativa y field Permite definir valores por defecto seguros, especialmente para listas y diccionarios.
from typing import List, Dict, Any, Optional # Importa tipos estáticos para mejorar: legibilidad ,autocompletado ,validación ,documentación Hace el core auto-documentado , Reduce errores en plugins , Permite contracts claros entre capas
from datetime import datetime # Importa la clase datetime para manejar fechas y horas, útil para marcar cuándo se creó el contexto del tenant.
import contextvars
from src.core.logger import logger # Importa el logger centralizado para registrar eventos, advertencias y errores relacionados con el contexto multi-tenant.


# ============================================
# MODELO: TENANT CONTEXT
# ============================================

@dataclass
class TenantContext:
    """
    Representa el estado del tenant activo durante una ejecución.
    
    Attributes:
        tenant_id: ID único del tenant (UUID Usado para aislamiento de datos)
        tenant_name: Nombre de la empresa
        plan: Plan contratado ('free', 'pro', 'enterprise') Define límites, capacidades y features
        features_enabled: Lista de features habilitadas para este tenant
        config: Configuración personalizada del tenant
        created_at: Fecha de creación del contexto
    """
    
    tenant_id: str
    tenant_name: str
    plan: str  # 'free', 'pro', 'enterprise'
    features_enabled: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def has_feature(self, feature: str) -> bool:
        """
        👉 Implementa Feature Toggles por tenant , Un Feature Toggle es un interruptor que enciende o apaga funcionalidades sin cambiar el código.
        Arquitectónicamente: Permite vender planes distintos ,Evita if plan == ... repartidos por el código
        """
        return feature in self.features_enabled
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        👉 Configuración dinámica sin hardcodear valores : modelo LLM por tenant ,límites de ventas ,reglas comerciales
        """
        return self.config.get(key, default)
    
    def is_plan(self, plan: str) -> bool:
        """Verifica si el tenant tiene un plan específico"""
        return self.plan.lower() == plan.lower()
    
    def __str__(self):
        return f"TenantContext({self.tenant_name}, Plan: {self.plan})"
    
    def __repr__(self):
        return self.__str__()


# ============================================
# GESTOR DEL CONTEXTO (Thread-Safe)
# ============================================

class TenantContextManager:
    """
    Gestor del contexto de tenant - Thread-Safe
    
    Este gestor asegura que cada request tenga su propio contexto
    de tenant sin interferir con otros requests que están siendo
    procesados al mismo tiempo.
    
    ¿Por qué Thread-Safe?
    Imagina que 3 clientes diferentes hacen requests al mismo tiempo:
    - Request 1: Tienda ABC pide sus productos
    - Request 2: Librería XYZ pide sus ventas
    - Request 3: Ferretería 123 pide su inventario
    
    Sin thread-safety, podrían mezclarse los datos.
    Con thread-safety, cada request mantiene su propio contexto.
    """
    
    # ContextVar garantiza aislamiento seguro en entornos async/await
    _tenant_ctx_var: contextvars.ContextVar[Optional[TenantContext]] = contextvars.ContextVar("tenant_context", default=None)
    
    @classmethod
    def set_current(cls, tenant: TenantContext):
        """
        Establece el tenant actual para este thread/request
        Responsabilidad: Asociar el tenant a la ejecución actual (“Desde este momento, todo lo que ocurra en este request pertenece a este tenant”.)
        """
        cls._tenant_ctx_var.set(tenant)
        logger.debug(f" Tenant establecido: {tenant.tenant_name}")
    
    @classmethod
    def get_current(cls) -> Optional[TenantContext]:
        """
        Obtiene el tenant actual de este thread/request
        Responsabilidad:
        Acceder al tenant desde cualquier parte del core
        Esto es fundamental para: repositorios , servicios ,estrategias ,plugins
        Obtiene el contexto del tenant activo para el request actual.
        Permite que cualquier componente del sistema opere de forma aislada sin necesidad de pasar explícitamente el tenant_id.
        """
        tenant = cls._tenant_ctx_var.get()
        if not tenant:
            logger.warning("⚠️  No hay tenant en el contexto")
        return tenant
    
    @classmethod
    def get_current_or_fail(cls) -> TenantContext:
        """
        Obtiene el contexto del tenant activo o lanza una excepción si no existe.
        Se utiliza para enforzar precondiciones en lógica crítica y prevenir ejecuciones fuera de un contexto multi-tenant.
        Arquitectónicamente: Enforza una precondición , Evita errores silenciosos 👉 Ideal para: lógica crítica ,servicios internos
        """
        tenant = cls.get_current()
        if not tenant:
            raise ValueError("No hay tenant establecido en el contexto actual")
        return tenant
    
    @classmethod
    def clear(cls):
        """
        Limpia el contexto del thread actual
        evita : memory leaks , contaminación de contexto entre requests , bugs imposibles de debuggear
        """
        tenant = cls._tenant_ctx_var.get()
        if tenant:
            logger.debug(f"🧹 Contexto limpiado: {tenant.tenant_name}")
        cls._tenant_ctx_var.set(None)
    
    @classmethod
    def get_all_active(cls) -> List[TenantContext]:
        """
        Devuelve todos los contextos de tenant activos en memoria, uno por cada request concurrente. Útil para debugging, métricas y observabilidad del sistema.
        """
        current = cls._tenant_ctx_var.get()
        return [current] if current else []
    
    @classmethod
    def count_active(cls) -> int:
        """
        Cuenta cuántos tenants están activos simultaneame, Returns: Número de tenants  activos
        """
        return 1 if cls._tenant_ctx_var.get() else 0


# ============================================
# DECORADOR PARA FUNCIONES
# ============================================

def require_tenant(func):
    """
    Decorador de infraestructura que garantiza que una función solo pueda ejecutarse dentro de un contexto multi-tenant válido.
    Evita ejecuciones inseguras y errores silenciosos.
    """
    def wrapper(*args, **kwargs):
        tenant = TenantContextManager.get_current()
        if not tenant:
            raise ValueError(f"La función '{func.__name__}' requiere un tenant en el contexto")
        return func(*args, **kwargs)
    return wrapper


# ============================================
# SCRIPT DE PRUEBA
# ============================================

if __name__ == "__main__":
    """
    Script de prueba del sistema Multi-Tenant
    """
    
    logger.info("=" * 60)
    logger.info("🧪 PROBANDO SISTEMA MULTI-TENANT")
    logger.info("=" * 60)
    
    # 1. Crear un tenant
    logger.info("\n1️⃣  Creando tenant...")
    tenant1 = TenantContext(
        tenant_id="tenant-abc-123",
        tenant_name="Tienda Electrónica ABC",
        plan="pro",
        features_enabled=["ai_agent", "excel_import", "analytics"],
        config={
            "max_products": 1000,
            "max_monthly_sales": 5000,
            "llm_model": "gpt-4o-mini"
        }
    )
    logger.success(f"✅ Tenant creado: {tenant1}")
    
    # 2. Establecer tenant en el contexto
    logger.info("\n2️⃣  Estableciendo tenant en el contexto...")
    TenantContextManager.set_current(tenant1)
    
    # 3. Obtener tenant del contexto
    logger.info("\n3️⃣  Obteniendo tenant del contexto...")
    current = TenantContextManager.get_current()
    logger.success(f"✅ Tenant obtenido: {current.tenant_name}")
    
    # 4. Verificar features
    logger.info("\n4️⃣  Verificando features...")
    if current.has_feature("ai_agent"):
        logger.success("✅ Tenant tiene acceso a AI Agent")
    if current.has_feature("whatsapp"):
        logger.warning("⚠️  Tenant NO tiene acceso a WhatsApp")
    
    # 5. Obtener configuración
    logger.info("\n5️⃣  Obteniendo configuración...")
    max_products = current.get_config("max_products")
    logger.success(f"✅ Max productos permitidos: {max_products}")
    
    # 6. Verificar plan
    logger.info("\n6️⃣  Verificando plan...")
    if current.is_plan("pro"):
        logger.success("✅ Tenant tiene plan PRO")
    
    # 7. Contar contextos activos
    logger.info("\n7️⃣  Contextos activos...")
    count = TenantContextManager.count_active()
    logger.info(f"📊 Contextos activos: {count}")
    
    # 8. Limpiar contexto
    logger.info("\n8️⃣  Limpiando contexto...")
    TenantContextManager.clear()
    
    # 9. Verificar que se limpió
    logger.info("\n9️⃣  Verificando limpieza...")
    current_after_clear = TenantContextManager.get_current()
    if current_after_clear is None:
        logger.success("✅ Contexto limpiado correctamente")
    
    logger.info("\n" + "=" * 60)
    logger.success("🎉 ¡TODAS LAS PRUEBAS PASARON!")
    logger.info("=" * 60)
    
