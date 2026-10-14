from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import AnyHttpUrl, BaseModel, field_validator

from src.core.database import get_db
from src.core.logger import logger
from src.repositories.tenant_repository import TenantRepository
from ..deps import CurrentUser, get_current_user, get_tenant_id
from ..schemas.common import MeResponse
from ._me_builder import build_me_response


router = APIRouter(prefix="/me", tags=["me"])


def current_user_dep(
    tenant_id: str = Depends(get_tenant_id),
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    return get_current_user(tenant_id=tenant_id, authorization=authorization)


class WebsiteUrlPayload(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        v = v.strip()
        if len(v) > 2048:
            raise ValueError("URL demasiado larga (máximo 2048 caracteres)")
        AnyHttpUrl(v)  # lanza ValueError si no es una URL HTTP/HTTPS válida
        return v


class WebsiteUrlResponse(BaseModel):
    tenant_id: str
    website_url: str


@router.get("", response_model=MeResponse, summary="Get current context (canonical)")
def me(current: CurrentUser = Depends(current_user_dep)) -> MeResponse:
    return build_me_response(current)


@router.patch(
    "/website-url",
    response_model=WebsiteUrlResponse,
    summary="Save website URL",
    description="Guarda la URL del sitio web del tenant en su registro de base de datos.",
)
def save_website_url(
    data: WebsiteUrlPayload,
    current: CurrentUser = Depends(current_user_dep),
    db=Depends(get_db),
) -> WebsiteUrlResponse:
    tenant_id = str(current.tenant.id)
    repo = TenantRepository(client=db.client)

    try:
        updated = repo.update(tenant_id, {"website_url": data.url})
    except Exception as e:
        logger.error(f"[ME] Error saving website_url tenant={tenant_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al guardar la URL del sitio web",
        )

    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant no encontrado",
        )

    logger.info(f"[ME] website_url guardada tenant={tenant_id}")
    return WebsiteUrlResponse(tenant_id=tenant_id, website_url=data.url)
