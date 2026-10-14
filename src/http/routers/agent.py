from __future__ import annotations

from typing import Optional, List
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from src.core.logger import logger
from src.http.deps import CurrentUser, get_current_user, get_tenant_id
from src.http.schemas.agent_schemas import AgentConfigPatchRequest, AgentConfigResponse
from src.repositories.agent_config_repository import AgentConfigRepository

router = APIRouter(prefix="/agent", tags=["Agent"])

agent_config_repo = AgentConfigRepository()


def current_user_dep(
    tenant_id: str = Depends(get_tenant_id),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    return get_current_user(tenant_id=tenant_id, authorization=authorization)


@router.get(
    "/config",
    response_model=AgentConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtener configuración del agente IA",
)
def get_agent_config(
    current_user: CurrentUser = Depends(current_user_dep),
) -> AgentConfigResponse:
    try:
        config = agent_config_repo.get_by_tenant_id(current_user.tenant.id)
    except Exception as exc:
        logger.error(f"Error obteniendo agent config para tenant {current_user.tenant.id}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo acceder a la configuración del agente. Intenta de nuevo.",
        )
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent configuration not found",
        )
    logger.info(f"Agent config obtenida para tenant {current_user.tenant.id}")
    return config


@router.patch(
    "/config",
    response_model=AgentConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Actualizar parcialmente la configuración del agente IA",
)
def patch_agent_config(
    payload: AgentConfigPatchRequest,
    current_user: CurrentUser = Depends(current_user_dep),
) -> AgentConfigResponse:
    update_data = payload.model_dump(mode="json", exclude_unset=True)
    config = agent_config_repo.update_for_tenant(current_user.tenant.id, update_data)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent configuration not found",
        )
    logger.info(f"Agent config actualizada para tenant {current_user.tenant.id}")
    return config


# ==================== C08: TRAINING MANUAL ====================


class TrainingEntry(BaseModel):
    """Una entrada de conocimiento manual para el agente."""

    titulo: str = Field(
        ...,
        description="Título o categoría del conocimiento. Ej: 'Política de cambios'",
    )
    contenido: str = Field(
        ..., description="Texto con el conocimiento a agregar al agente"
    )


class TrainingManualRequest(BaseModel):
    """Request para agregar conocimiento manual al agente."""

    entradas: List[TrainingEntry] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Lista de entradas de conocimiento (máximo 20)",
    )


class TrainingManualResponse(BaseModel):
    """Response del entrenamiento manual."""

    status: str
    vectorizados: int
    fallidos: int
    mensaje: str
    detalles: Optional[List[str]] = None


@router.post(
    "/training/manual",
    response_model=TrainingManualResponse,
    status_code=status.HTTP_200_OK,
    summary="Agregar conocimiento extra al agente IA",
    description="""
    Permite al dueño agregar conocimiento adicional al agente sin subir un Excel.
    Útil para: políticas de cambio, horarios, métodos de pago, preguntas frecuentes.

    El contenido se vectoriza con OpenAI y se guarda en Qdrant junto al catálogo.
    El agente lo usará automáticamente en sus respuestas.
    """,
)
async def training_manual(
    payload: TrainingManualRequest,
    current_user: CurrentUser = Depends(current_user_dep),
) -> TrainingManualResponse:
    """
    ✅ C08: Vectoriza conocimiento extra y lo guarda en Qdrant.
    """
    tenant_id = str(current_user.tenant.id)
    tenant_slug = current_user.tenant.get_config("slug", tenant_id)

    vectorizados = 0
    fallidos = 0
    detalles = []

    try:
        import uuid
        import os
        from openai import OpenAI
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct

        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        qdrant = QdrantClient(
            url=os.getenv("QDRANT_URL"),
            api_key=os.getenv("QDRANT_API_KEY"),
        )

        collection_name = f"products_{tenant_id}"
        embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

        # Verificar que la colección existe
        collections = [c.name for c in qdrant.get_collections().collections]
        if collection_name not in collections:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Colección del agente no encontrada. Sube primero un Excel con el catálogo.",
            )

        for entrada in payload.entradas:
            try:
                # Construir texto para embedding
                texto = f"{entrada.titulo}\n\n{entrada.contenido}"

                # Generar embedding
                response = openai_client.embeddings.create(
                    input=[texto],
                    model=embedding_model,
                )
                vector = response.data[0].embedding

                # ID determinístico para evitar duplicados
                doc_id = f"training_{tenant_slug}_{entrada.titulo}".replace(
                    " ", "_"
                ).lower()
                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, doc_id))

                # Guardar en Qdrant
                qdrant.upsert(
                    collection_name=collection_name,
                    points=[
                        PointStruct(
                            id=point_id,
                            vector=vector,
                            payload={
                                "custom_id": doc_id,
                                "text": texto,
                                "name": entrada.titulo,
                                "tipo": "conocimiento_manual",
                                "tenant_id": tenant_id,
                                "es_entrenamiento": True,
                            },
                        )
                    ],
                )

                vectorizados += 1
                detalles.append(f"✅ '{entrada.titulo}' vectorizado correctamente")
                logger.info(
                    f"[C08] Entrada vectorizada: '{entrada.titulo}' para tenant {tenant_slug}"
                )

            except Exception as e:
                fallidos += 1
                detalles.append(f"❌ '{entrada.titulo}': {str(e)[:100]}")
                logger.error(f"[C08] Error vectorizando '{entrada.titulo}': {e}")

        mensaje = f"{vectorizados} entradas agregadas al agente exitosamente."
        if fallidos > 0:
            mensaje += f" {fallidos} fallaron."

        logger.info(
            f"[C08] Training manual completado: {vectorizados} OK, {fallidos} fallidos — tenant {tenant_slug}"
        )

        return TrainingManualResponse(
            status="completed" if fallidos == 0 else "partial",
            vectorizados=vectorizados,
            fallidos=fallidos,
            mensaje=mensaje,
            detalles=detalles,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[C08] Error crítico en training manual: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error procesando el entrenamiento: {str(e)}",
        )
