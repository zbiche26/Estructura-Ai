from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentConfigBase(BaseModel):
    """
    Base con todos los campos opcionales para evitar 500
    cuando el tenant no ha configurado todos los valores.
    """

    nombre_agente: str | None = Field(
        default=None,
        max_length=255,
        description="Nombre del agente IA",
    )
    system_prompt: str | None = Field(
        default=None,
        description="Prompt del sistema que define el comportamiento del agente",
    )
    welcome_message: str | None = Field(
        default=None,
        description="Mensaje de bienvenida que envía el agente",
    )
    temperatura: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Temperatura de creatividad (0.0 = determinista, 1.0 = creativo)",
    )
    idioma: str = Field(
        default="es",
        min_length=2,
        max_length=50,
        description="Idioma principal del agente (ej: 'es', 'en')",
    )
    owner_phone: str | None = Field(
        default=None,
        description="Teléfono del dueño para notificaciones de escalamiento",
    )


class AgentConfigResponse(AgentConfigBase):
    model_config = ConfigDict(from_attributes=True)


class AgentConfigPatchRequest(BaseModel):
    """
    Request para actualización parcial del agente.
    Todos los campos son opcionales — solo se actualizan los enviados.
    """

    nombre_agente: str | None = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Nombre del agente IA",
    )
    system_prompt: str | None = Field(
        default=None,
        min_length=1,
        description="Prompt del sistema que define el comportamiento del agente",
    )
    welcome_message: str | None = Field(
        default=None,
        min_length=1,
        description="Mensaje de bienvenida que envía el agente",
    )
    temperatura: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Temperatura de creatividad (0.0 = determinista, 1.0 = creativo)",
    )
    idioma: str | None = Field(
        default=None,
        min_length=2,
        max_length=50,
        description="Idioma principal del agente (ej: 'es', 'en')",
    )
    owner_phone: str | None = Field(
        default=None,
        description="Teléfono del dueño para notificaciones de escalamiento",
    )

    model_config = ConfigDict(from_attributes=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def validate_patch_request(cls, values):
        """
        Valida que:
        1. Haya al menos un campo para actualizar
        2. No intente modificar tenant_id (seguridad multi-tenant)
        """
        if isinstance(values, dict):
            if "tenant_id" in values:
                raise ValueError("tenant_id no puede ser modificado")
            valid_fields = {
                "nombre_agente",
                "system_prompt",
                "welcome_message",
                "temperatura",
                "idioma",
                "owner_phone",
            }
            provided_fields = {
                k for k in values.keys() if k in valid_fields and values[k] is not None
            }
            if not provided_fields:
                raise ValueError(
                    "Al menos un campo debe ser proporcionado para la actualización"
                )
        return values
