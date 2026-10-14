from __future__ import annotations

from pydantic import BaseModel, Field


class PlanPublicLimits(BaseModel):
    max_agents: int = Field(..., description="Máximo de agentes permitidos por plan")
    max_conversations_month: int = Field(
        ..., description="Máximo de conversaciones por mes (-1 significa ilimitado)"
    )
    max_team_members: int = Field(
        ..., description="Máximo de miembros de equipo permitidos (-1 significa ilimitado)"
    )


class PlanPublicItem(BaseModel):
    id: str = Field(..., description="Identificador único del plan")
    name: str = Field(..., description="Nombre comercial del plan")
    slug: str = Field(..., description="Slug estable del plan (ej: starter, growth, scale)")
    price_monthly: float = Field(..., ge=0, description="Precio mensual del plan")
    limits: PlanPublicLimits
    features: list[str] = Field(default_factory=list)
