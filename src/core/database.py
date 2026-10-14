"""
Cliente de Supabase - Versión simplificada para Repositories

Basado en verify_supabase.py pero adaptado para uso en repositories
"""

from typing import Optional, Dict, Any
from supabase import create_client, Client
import threading

from src.config import settings
from src.core.logger import logger


class SupabaseClient:
    """
    Cliente singleton de Supabase
    
    Proporciona acceso a la base de datos para los repositories
    """
    
    _instance: Optional['SupabaseClient'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'SupabaseClient':
        """Singleton pattern: solo una instancia"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """Inicializa el cliente de Supabase"""
        # Evitar re-inicialización
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        
        # Validar configuración. Preferir la service_role_key para evitar RLS con anon.
        if not settings.SUPABASE_URL or not (settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY):
            logger.warning(
                "⚠️ SUPABASE_URL o SUPABASE_ANON_KEY no configurados. "
                "Usando configuración por defecto."
            )
            self._client = None
            return
        
        # Crear cliente
        try:
            # Usa service role si está disponible; si no, cae a la anon key.
            supabase_key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY
            self._client: Client = create_client(
                settings.SUPABASE_URL,
                supabase_key
            )
            logger.info("✅ Supabase client initialized")
        except Exception as e:
            logger.error(f"❌ Error al inicializar Supabase: {e}")
            self._client = None
    
    @property
    def client(self) -> Client:
        """
        Cliente de Supabase
        
        Returns:
            Cliente de Supabase conectado
        """
        if not self._client:
            raise ValueError(
                "Supabase client no está inicializado. "
                "Verifica SUPABASE_URL y SUPABASE_ANON_KEY en .env"
            )
        return self._client
    
    def health_check(self) -> Dict[str, Any]:
        """
        Verifica que la conexión a Supabase esté funcionando
        
        Returns:
            Dict con status y detalles de la conexión
        """
        if not self._client:
            return {
                "status": "unhealthy",
                "connected": False,
                "error": "Cliente no inicializado"
            }
        
        try:
            # Intentar hacer una query simple
            result = self._client.table('tenants').select('count').limit(0).execute()
            
            return {
                "status": "healthy",
                "connected": True,
                "url": settings.SUPABASE_URL
            }
        except Exception as e:
            logger.error(f"❌ Supabase health check failed: {e}")
            return {
                "status": "unhealthy",
                "connected": False,
                "error": str(e)
            }


# ============================================
# INSTANCIA GLOBAL
# ============================================
db = SupabaseClient()


# ============================================
# FUNCIONES DE UTILIDAD
# ============================================

def get_db() -> SupabaseClient:
    """Obtiene la instancia del cliente de Supabase"""
    return db


def verify_connection() -> bool:
    """Verifica que la conexión a Supabase funcione"""
    health = db.health_check()
    return health["connected"]
