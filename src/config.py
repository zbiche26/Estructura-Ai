"""
Configuración del Sistema
========================

Este archivo carga las variables de entorno desde .env
y las hace disponibles para todo el proyecto.

Ejemplo de uso:
    from src.config import settings

    print(settings.APP_NAME)
    # Output: "Agente Ventas IA"
"""

from dotenv import load_dotenv
import os

# Cargar variables de entorno desde archivo .env
load_dotenv()


class Settings:
    """
    Clase que contiene toda la configuración del sistema

    Las variables se cargan automáticamente desde el archivo .env
    """

    # ============================================
    # GENERAL
    # ============================================
    APP_NAME: str = os.getenv("APP_NAME", "Agente Ventas IA")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

    # ============================================
    # APIs DE IA
    # ============================================
    # OpenAI (para GPT y embeddings)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

    # Anthropic Claude (alternativa a GPT)
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")

    # ============================================
    # LLM CONFIGURATION (WEEK 4)
    # ============================================
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "mock")
    LLM_FALLBACK_PROVIDER: str = os.getenv("LLM_FALLBACK_PROVIDER", "mock")
    LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.7"))
    LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "1000"))

    # ============================================
    # SUPABASE (Base de Datos PostgreSQL)
    # ============================================
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "")
    SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    SUPABASE_JWT_SECRET: str = os.getenv("SUPABASE_JWT_SECRET", "")

    # ============================================
    # QDRANT (Vector Database)
    # ============================================
    QDRANT_MODE: str = os.getenv("QDRANT_MODE", "memory")  # memory, local, cloud
    QDRANT_URL: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_API_KEY: str = os.getenv("QDRANT_API_KEY", "")

    # ============================================
    # MULTI-TENANT (WEEK 4)
    # ============================================
    DEFAULT_TENANT_ID: str = os.getenv("DEFAULT_TENANT_ID", "tenant_dev")

    # ============================================
    # LOGGING
    # ============================================
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "app.log")

    # ============================================
    # DATABASE
    # ============================================
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))

    # ============================================
    # MÉTODOS DE UTILIDAD
    # ============================================
    def is_development(self) -> bool:
        """Verifica si estamos en desarrollo"""
        return self.ENVIRONMENT == "development"

    def is_production(self) -> bool:
        """Verifica si estamos en producción"""
        return self.ENVIRONMENT == "production"

    def validate(self) -> bool:
        """
        Valida que las configuraciones requeridas estén presentes

        Returns:
            bool: True si la configuración es válida

        Raises:
            ValueError: Si faltan configuraciones requeridas
        """
        required = []

        # Supabase es requerido
        if not self.SUPABASE_URL:
            required.append("SUPABASE_URL")
        if not self.SUPABASE_SERVICE_ROLE_KEY:
            required.append("SUPABASE_SERVICE_ROLE_KEY")

        # Si no es mock, verificar API keys
        if self.LLM_PROVIDER == "openai" and not self.OPENAI_API_KEY:
            required.append("OPENAI_API_KEY")

        if self.LLM_PROVIDER == "anthropic" and not self.ANTHROPIC_API_KEY:
            required.append("ANTHROPIC_API_KEY")

        # Qdrant cloud requiere API key
        if self.QDRANT_MODE == "cloud" and not self.QDRANT_API_KEY:
            required.append("QDRANT_API_KEY")

        if required:
            raise ValueError(
                f"❌ Faltan variables de entorno requeridas: {', '.join(required)}"
            )

        return True


# Crear instancia global de configuración
settings = Settings()

# comentario
