from pydantic import BaseModel, Field
class RefreshTokenRequest(BaseModel):
    """Schema para solicitar refresh de token."""
    refresh_token: str = Field(..., description="Refresh token JWT")
    class Config:
        json_schema_extra = {
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }
"""
Schemas de Pydantic para Tenant

Estos schemas definen:
- Cómo validar datos de entrada (Create, Update)
- Cómo formatear datos de salida (Response)
- Documentación automática de la API

IMPORTANTE:
- El password_hash NUNCA es devuelto en respuestas (seguridad)
- El email debe ser único en la BD
"""

from pydantic import BaseModel, Field, field_validator, EmailStr
from typing import Optional
from datetime import datetime
from uuid import UUID
from enum import Enum


# ============================================
# ENUMS
# ============================================

class TenantPlanEnum(str, Enum):
    """Planes disponibles para tenants"""
    STARTER = "starter"
    GROWTH = "growth"
    SCALE = "scale"


# ============================================
# SCHEMAS DE ENTRADA (Request)
# ============================================

class TenantCreate(BaseModel):
    """
    Schema para crear un nuevo tenant
    
    Valida:
    - name: nombre de la empresa (1-255 caracteres)
    - email: email único del administrador (validación de formato)
    - password: contraseña sin hashear (será hasheada en el backend)
    - slug: identificador único (solo a-z, 0-9, guiones)
    - whatsapp_phone_number: número de WhatsApp opcional
    """
    
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Nombre de la empresa/tenant",
        examples=["Mi Empresa SAS"]
    )
    
    email: EmailStr = Field(
        ...,
        description="Email del administrador (debe ser único)",
        examples=["admin@miempresa.com"]
    )
    
    password: str = Field(
        ...,
        min_length=8,
        max_length=72,
        description="Contraseña del administrador (mínimo 8 caracteres, máx 72 para bcrypt)",
        examples=["StrongPassword123!"]
    )
    
    slug: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Identificador único (solo a-z, 0-9, guiones). Ej: mi-empresa",
        examples=["mi-empresa", "my-company"]
    )

    plan: TenantPlanEnum = Field(
        default=TenantPlanEnum.STARTER,
        description="Plan de suscripción (starter, growth, enterprise)",
        examples=[TenantPlanEnum.STARTER]
    )
    
    whatsapp_phone_number: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Número de WhatsApp del business account (formato E.164: +1234567890)",
        examples=["+573001234568"]
    )
    
    whatsapp_phone_id: Optional[str] = Field(
        default=None,
        max_length=255,
        description="WhatsApp Phone ID proporcionado por Meta Business API",
        examples=["123456789012345"]
    )
    
    @field_validator('slug')
    @classmethod
    def validate_slug(cls, v: str) -> str:
        """Valida que slug sea lowercase y solo contenga a-z, 0-9, guiones"""
        import re
        v = v.lower().strip()
        
        if not re.match(r'^[a-z0-9-]+$', v):
            raise ValueError(
                'Slug debe contener solo letras minúsculas, números y guiones'
            )
        
        if v.startswith('-') or v.endswith('-'):
            raise ValueError('Slug no puede iniciar ni terminar con guión')
        
        return v
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """
        Validaciones básicas de contraseña
        - Mínimo 8 caracteres
        - Máximo 72 caracteres (límite bcrypt)
        - Al menos una mayúscula
        - Al menos un número
        - Al menos un carácter especial
        """
        import re
        
        v = v.strip()
        
        if len(v) < 8:
            raise ValueError('Contraseña debe tener al menos 8 caracteres')

        if len(v) > 72:
            raise ValueError('Contraseña no puede exceder 72 caracteres (límite de bcrypt)')
        
        if not re.search(r'[A-Z]', v):
            raise ValueError('Contraseña debe contener al menos una mayúscula')
        
        if not re.search(r'[0-9]', v):
            raise ValueError('Contraseña debe contener al menos un número')
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Contraseña debe contener al menos un carácter especial (!@#$%^&*, etc)')
        
        return v

    @field_validator('whatsapp_phone_number')
    @classmethod
    def validate_whatsapp_phone(cls, v: Optional[str]) -> Optional[str]:
        """Normaliza y valida número en formato E.164 (+ prefijo país)."""
        import re

        if v is None:
            return v

        normalized = (
            v.replace(" ", "")
             .replace("-", "")
             .replace("(", "")
             .replace(")", "")
             .strip()
        )

        if normalized and not normalized.startswith("+"):
            normalized = "+" + normalized

        if not re.match(r'^\+[0-9]{7,20}$', normalized):
            raise ValueError('Número de WhatsApp debe estar en formato E.164, ej: +573001234567')

        return normalized
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Mi Empresa SAS",
                "email": "admin@miempresa.com",
                "password": "SecurePass123!",
                "slug": "mi-empresa",
                "plan": "starter",
                "whatsapp_phone_number": "+573001234568",
                "whatsapp_phone_id": "123456789012345"
            }
        }


class TenantUpdateRequest(BaseModel):
    """Campos actualizables de un tenant."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    slug: Optional[str] = Field(default=None, min_length=1, max_length=100)
    plan: Optional[TenantPlanEnum] = None
    whatsapp_phone_number: Optional[str] = Field(default=None, max_length=20)
    whatsapp_phone_id: Optional[str] = Field(default=None, max_length=255)

    @field_validator('slug')
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        import re
        v = v.lower().strip()
        if not re.match(r'^[a-z0-9-]+$', v):
            raise ValueError('Slug debe contener solo letras minúsculas, números y guiones')
        if v.startswith('-') or v.endswith('-'):
            raise ValueError('Slug no puede iniciar ni terminar con guión')
        return v

    @field_validator('whatsapp_phone_number')
    @classmethod
    def validate_whatsapp_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        import re
        normalized = (
            v.replace(" ", "")
             .replace("-", "")
             .replace("(", "")
             .replace(")", "")
             .strip()
        )
        if normalized and not normalized.startswith("+"):
            normalized = "+" + normalized
        if not re.match(r'^\+[0-9]{7,20}$', normalized):
            raise ValueError('Número de WhatsApp debe estar en formato E.164, ej: +573001234567')
        return normalized

    @field_validator('whatsapp_phone_id')
    @classmethod
    def validate_whatsapp_phone_id(cls, v: Optional[str]) -> Optional[str]:
        """Valida que el WhatsApp Phone ID sea un string numérico válido."""
        if v is None:
            return v
        
        v = v.strip()
        
        if not v:
            return None
            
        # Debe ser numérico (solo dígitos)
        if not v.isdigit():
            raise ValueError('WhatsApp Phone ID debe contener solo números')
        
        # Longitud típica de Phone ID de Meta (generalmente 15 dígitos)
        if len(v) < 10 or len(v) > 20:
            raise ValueError('WhatsApp Phone ID debe tener entre 10 y 20 dígitos')
        
        return v


class TenantLoginRequest(BaseModel):
    """Schema para login de tenant."""

    email: EmailStr = Field(
        ...,
        description="Email del administrador del tenant",
        examples=["admin@miempresa.com"]
    )

    password: str = Field(
        ...,
        description="Contraseña del administrador",
        examples=["SecurePass123!"]
    )


class ApiKeyCreateRequest(BaseModel):
    """Solicitud para generar una API key para un tenant."""

    name: Optional[str] = Field(default=None, description="Nombre descriptivo opcional de la API key")


class ApiKeyResponse(BaseModel):
    """Respuesta al crear o listar una API key."""

    id: UUID
    api_key: Optional[str] = Field(default=None, description="Solo se retorna al momento de crearse")
    name: Optional[str] = None
    created_at: datetime
    revoked_at: Optional[datetime] = None


class UsageLimits(BaseModel):
    products: int
    conversations_month: int


class UsageResponse(BaseModel):
    """Uso actual del tenant."""

    messages_used: int
    messages_limit: int
    storage_used_mb: int
    storage_limit_mb: int
    period_start: datetime
    period_end: datetime
    products_count: int
    conversations_month_count: int
    limits: UsageLimits


class BillingInfoResponse(BaseModel):
    """Información de facturación del tenant."""

    plan: str
    status: str
    cycle: str
    next_billing_date: datetime
    current_period_start: datetime
    current_period_end: datetime


class ForgotPasswordRequest(BaseModel):
    """Solicitud de recuperación de contraseña."""

    email: EmailStr = Field(
        ...,
        description="Email del administrador/tenant",
        examples=["admin@miempresa.com"]
    )


class ForgotPasswordResponse(BaseModel):
    """Respuesta genérica de solicitud de recuperación."""

    message: str = Field(..., examples=["Si el email existe se envió un enlace para restablecer la contraseña."])
    reset_token: Optional[str] = Field(
        default=None,
        description="Solo se devuelve en entornos de desarrollo para pruebas",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."]
    )


class ResetPasswordRequest(BaseModel):
    """Solicitud para restablecer la contraseña usando un token válido."""

    token: str = Field(..., description="Token de recuperación recibido por correo")
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=72,
        description="Nueva contraseña. Se aplican las mismas reglas de seguridad que en el registro.",
        examples=["NuevaPass123!"]
    )

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        import re

        v = v.strip()

        if len(v) < 8:
            raise ValueError('Contraseña debe tener al menos 8 caracteres')

        if len(v) > 72:
            raise ValueError('Contraseña no puede exceder 72 caracteres (límite de bcrypt)')

        if not re.search(r'[A-Z]', v):
            raise ValueError('Contraseña debe contener al menos una mayúscula')

        if not re.search(r'[0-9]', v):
            raise ValueError('Contraseña debe contener al menos un número')

        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Contraseña debe contener al menos un carácter especial (!@#$%^&*, etc)')

        return v


class MessageResponse(BaseModel):
    """Respuesta sencilla con mensaje."""

    message: str = Field(..., examples=["Operación completada"])

    class Config:
        json_schema_extra = {
            "example": {
                "email": "admin@miempresa.com",
                "password": "SecurePass123!"
            }
        }


# ============================================
# SCHEMAS DE SALIDA (Response)
# ============================================

class TenantResponse(BaseModel):
    """
    Schema para respuestas que contienen datos de un tenant
    
    IMPORTANTE:
    - NO incluye password_hash (seguridad)
    - Incluye todos los campos públicos
    """
    
    id: UUID
    name: str
    email: EmailStr
    slug: str
    is_active: bool
    plan: TenantPlanEnum
    max_products: int
    max_conversations: int
    website_url: Optional[str] = None
    whatsapp_phone_number: Optional[str]
    whatsapp_phone_id: Optional[str]
    whatsapp_enabled: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        use_enum_values = True


class TenantCreatedResponse(TenantResponse):
    """
    Respuesta específica después de crear un tenant
    
    Incluye los mismos datos que TenantResponse
    """
    
    class Config:
        from_attributes = True
        use_enum_values = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "name": "Mi Empresa SAS",
                "email": "admin@miempresa.com",
                "slug": "mi-empresa",
                "is_active": True,
                "plan": "starter",
                "max_products": 100,
                "max_conversations": 1000,
                "whatsapp_phone_number": "+573001234568",
                "whatsapp_enabled": False,
                "created_at": "2026-03-17T10:30:00Z",
                "updated_at": "2026-03-17T10:30:00Z"
            }
        }


class TenantLoginRequest(BaseModel):
    """Schema para login de tenant."""

    email: EmailStr = Field(
        ...,
        description="Email del administrador del tenant",
        examples=["admin@miempresa.com"]
    )

    password: str = Field(
        ...,
        description="Contraseña del administrador",
        examples=["SecurePass123!"]
    )

    class Config:
        json_schema_extra = {
            "example": {
                "email": "admin@miempresa.com",
                "password": "SecurePass123!"
            }
        }


class TenantLoginResponse(BaseModel):
    """Respuesta de login con tokens y datos del tenant."""

    access_token: str
    refresh_token: str
    token_type: str = Field(default="bearer")
    expires_in: int = Field(description="Expiración del access token en segundos")
    tenant: TenantResponse

    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 900,
                "tenant": {
                    "id": "550e8400-e29b-41d4-a716-446655440000",
                    "name": "Mi Empresa SAS",
                    "email": "admin@miempresa.com",
                    "slug": "mi-empresa",
                    "is_active": True,
                    "plan": "starter",
                    "max_products": 100,
                    "max_conversations": 1000,
                    "whatsapp_phone_number": "+573001234568",
                    "whatsapp_enabled": False,
                    "created_at": "2026-03-17T10:30:00Z",
                    "updated_at": "2026-03-17T10:30:00Z"
                }
            }
        }


class TenantLogoutRequest(BaseModel):
    """Schema para realizar logout invalidando tokens activos."""

    refresh_token: str = Field(
        ...,
        description="Refresh token que se invalidará",
        examples=["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."]
    )

    class Config:
        json_schema_extra = {
            "example": {
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
            }
        }


class TenantUpdate(BaseModel):
    """Schema para actualizar un tenant"""
    
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=255,
        description="Nombre de la empresa"
    )
    
    whatsapp_phone_number: Optional[str] = Field(
        None,
        max_length=20,
        description="Número de WhatsApp"
    )
    
    is_active: Optional[bool] = Field(
        None,
        description="Si el tenant está activo"
    )


# ============================================
# ERROR RESPONSES
# ============================================

class ErrorResponse(BaseModel):
    """Schema para respuestas de error"""
    
    detail: str
    error_code: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_schema_extra = {
            "example": {
                "detail": "Email ya existe en el sistema",
                "error_code": "EMAIL_ALREADY_EXISTS",
                "timestamp": "2026-03-17T10:30:00Z"
            }
        }
