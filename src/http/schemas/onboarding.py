from __future__ import annotations

from pydantic import BaseModel, Field


class OnboardingStatus(BaseModel):
    whatsapp_connected: bool = Field(..., description="Si WhatsApp Business está conectado y configurado")
    training_done: bool = Field(..., description="Si el entrenamiento inicial del agente está completado")
    first_conversation_done: bool = Field(..., description="Si se ha completado al menos una conversación")


class OnboardingStatusResponse(BaseModel):
    data: OnboardingStatus = Field(..., description="Estado actual del proceso de onboarding")
