from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, status

from ..deps import CurrentUser, get_current_user, get_tenant_id, is_dev
from ..schemas.common import LoginRequest, LoginResponse, MeResponse
from ._me_builder import build_me_response

router = APIRouter(prefix="/auth", tags=["auth"])


def current_user_dep(
    tenant_id: str = Depends(get_tenant_id),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    return get_current_user(tenant_id=tenant_id, authorization=authorization)


@router.post(
    "/login",
    response_model=LoginResponse,
    status_code=status.HTTP_200_OK,
    summary="Login (stub)",
    description="Stub login: devuelve un token demo. Luego se reemplaza por auth real.",
)
def login(payload: LoginRequest) -> LoginResponse:
    if not is_dev():
        return LoginResponse(access_token="disabled", token_type="bearer")

    return LoginResponse(access_token="demo-token", token_type="bearer")


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get current user (stub)",
)
def me(current: CurrentUser = Depends(current_user_dep)) -> MeResponse:
    return build_me_response(current)
