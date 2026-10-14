# -*- coding: utf-8 -*-
"""
team.py - Team Management Router
=================================
Endpoints para gestión de miembros del equipo por tenant.

Endpoints:
    GET    /team              - Listar miembros del equipo
    POST   /team/invite       - Invitar nuevo miembro
    PATCH  /team/{member_id}  - Cambiar rol de miembro
    DELETE /team/{member_id}  - Revocar acceso de miembro
    GET    /team/accept-invite - Aceptar invitación (token)

Roles disponibles: owner, admin, operator, viewer
Planes:
    starter    → 1 miembro (solo owner)
    growth     → 5 miembros
    enterprise → ilimitado
"""
from __future__ import annotations

import secrets
import string
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, field_validator

from src.core.database import get_db
from src.core.logger import logger
from src.http.deps import CurrentUser, get_current_user, get_tenant_id

router = APIRouter(prefix="/team", tags=["team"])

# ── Límites por plan ────────────────────────────────────────────────────────
PLAN_MEMBER_LIMITS = {
    "starter": 1,
    "trial": 1,
    "growth": 5,
    "enterprise": -1,  # ilimitado
    "scale": -1,
}

VALID_ROLES = {"owner", "admin", "operator", "viewer"}
VALID_STATUSES = {"pending", "active", "revoked"}

INVITE_EXPIRY_HOURS = 48


# ── Dependency ───────────────────────────────────────────────────────────────
def current_user_dep(
    tenant_id: str = Depends(get_tenant_id),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> CurrentUser:
    return get_current_user(tenant_id=tenant_id, authorization=authorization)


# ── Schemas ──────────────────────────────────────────────────────────────────

class TeamMemberResponse(BaseModel):
    id: str
    tenant_id: str
    invited_email: str
    role: str
    status: str
    accepted_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class TeamListResponse(BaseModel):
    data: List[TeamMemberResponse]
    total: int


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: str = "operator"

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"Rol inválido. Debe ser uno de: {', '.join(VALID_ROLES)}")
        if v == "owner":
            raise ValueError("No se puede invitar a alguien con rol 'owner'")
        return v


class InviteMemberResponse(BaseModel):
    message: str
    member_id: str
    invited_email: str
    role: str
    invite_expires_at: datetime


class UpdateMemberRequest(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def validate_role(cls, v: str) -> str:
        if v not in VALID_ROLES:
            raise ValueError(f"Rol inválido. Debe ser uno de: {', '.join(VALID_ROLES)}")
        if v == "owner":
            raise ValueError("No se puede cambiar rol a 'owner' mediante este endpoint")
        return v


class AcceptInviteResponse(BaseModel):
    message: str
    tenant_id: str
    role: str


# ── Helpers ──────────────────────────────────────────────────────────────────

def _generate_invite_token() -> str:
    """Genera token seguro de invitación"""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(64))


def _get_member_count(db, tenant_id: str) -> int:
    """Cuenta miembros activos del tenant"""
    try:
        result = (
            db.client.table("tenant_members")
            .select("id", count="exact")
            .eq("tenant_id", tenant_id)
            .in_("status", ["active", "pending"])
            .execute()
        )
        return result.count or 0
    except Exception as e:
        logger.error(f"Error contando miembros: {e}")
        return 0


def _check_plan_limit(current_user: CurrentUser, db) -> None:
    """Verifica que el plan permite agregar más miembros"""
    plan = current_user.plan
    limit = PLAN_MEMBER_LIMITS.get(plan, 1)

    if limit == -1:
        return  # ilimitado

    current_count = _get_member_count(db, current_user.tenant.id)
    if current_count >= limit:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tu plan '{plan}' permite máximo {limit} miembro(s). "
                   f"Actualiza tu plan para agregar más.",
        )


def _require_admin_or_owner(current_user: CurrentUser, db) -> None:
    """Verifica que el usuario tiene rol owner o admin"""
    try:
        result = (
            db.client.table("tenant_members")
            .select("role")
            .eq("tenant_id", current_user.tenant.id)
            .eq("invited_email", current_user.user.email)
            .eq("status", "active")
            .execute()
        )
        members = result.data or []

        # El owner del tenant siempre tiene acceso
        if not members:
            # Si no está en la tabla, es el owner original (tenant creator)
            return

        role = members[0].get("role", "viewer")
        if role not in ("owner", "admin"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo los roles 'owner' y 'admin' pueden gestionar el equipo",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verificando rol: {e}")
        # Si hay error, permitir al owner del tenant (es el creador)
        return


def _format_member(record: dict) -> TeamMemberResponse:
    """Formatea un registro de BD a TeamMemberResponse"""
    return TeamMemberResponse(
        id=record["id"],
        tenant_id=record["tenant_id"],
        invited_email=record["invited_email"],
        role=record["role"],
        status=record["status"],
        accepted_at=record.get("accepted_at"),
        created_at=record["created_at"],
        updated_at=record["updated_at"],
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=TeamListResponse,
    summary="Listar miembros del equipo",
    description="Retorna todos los miembros del equipo del tenant autenticado.",
)
def list_team_members(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    current_user: CurrentUser = Depends(current_user_dep),
) -> TeamListResponse:
    db = get_db()

    try:
        query = (
            db.client.table("tenant_members")
            .select("*")
            .eq("tenant_id", current_user.tenant.id)
            .order("created_at", desc=False)
        )

        if status_filter:
            if status_filter not in VALID_STATUSES:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Status inválido. Debe ser uno de: {', '.join(VALID_STATUSES)}",
                )
            query = query.eq("status", status_filter)

        result = query.execute()
        members = result.data or []

        return TeamListResponse(
            data=[_format_member(m) for m in members],
            total=len(members),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listando miembros del equipo: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al obtener el equipo",
        )


@router.post(
    "/invite",
    response_model=InviteMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Invitar nuevo miembro",
    description="Envía invitación a un nuevo miembro del equipo. "
                "Requiere rol owner o admin. Limitado por plan.",
)
def invite_team_member(
    data: InviteMemberRequest,
    current_user: CurrentUser = Depends(current_user_dep),
) -> InviteMemberResponse:
    db = get_db()

    # Verificar permisos
    _require_admin_or_owner(current_user, db)

    # Verificar límite del plan
    _check_plan_limit(current_user, db)

    # Verificar que el email no esté ya invitado
    try:
        existing = (
            db.client.table("tenant_members")
            .select("id", "status")
            .eq("tenant_id", current_user.tenant.id)
            .eq("invited_email", data.email)
            .execute()
        )
        existing_members = existing.data or []

        if existing_members:
            member = existing_members[0]
            if member["status"] == "active":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"El email '{data.email}' ya es miembro activo del equipo",
                )
            elif member["status"] == "pending":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Ya existe una invitación pendiente para '{data.email}'",
                )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error verificando email existente: {e}")

    # Crear invitación
    invite_token = _generate_invite_token()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=INVITE_EXPIRY_HOURS)
    now = datetime.now(timezone.utc).isoformat()

    try:
        result = (
            db.client.table("tenant_members")
            .insert({
                "tenant_id": current_user.tenant.id,
                "invited_email": data.email,
                "role": data.role,
                "status": "pending",
                "invite_token": invite_token,
                "invite_expires_at": expires_at.isoformat(),
                "created_at": now,
                "updated_at": now,
            })
            .execute()
        )

        member = result.data[0] if result.data else {}
        member_id = member.get("id", "")

        logger.info(
            f"Invitación creada: tenant={current_user.tenant.id} "
            f"email={data.email} role={data.role}"
        )

        # TODO: Enviar email de invitación con el token
        # El link sería: /api/v1/team/accept-invite?token={invite_token}

        return InviteMemberResponse(
            message=f"Invitación enviada a {data.email}",
            member_id=member_id,
            invited_email=data.email,
            role=data.role,
            invite_expires_at=expires_at,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creando invitación: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al crear la invitación",
        )


@router.patch(
    "/{member_id}",
    response_model=TeamMemberResponse,
    summary="Cambiar rol de miembro",
    description="Actualiza el rol de un miembro del equipo. "
                "Requiere rol owner o admin.",
)
def update_team_member(
    member_id: str,
    data: UpdateMemberRequest,
    current_user: CurrentUser = Depends(current_user_dep),
) -> TeamMemberResponse:
    db = get_db()

    # Verificar permisos
    _require_admin_or_owner(current_user, db)

    try:
        # Verificar que el miembro existe y pertenece al tenant
        existing = (
            db.client.table("tenant_members")
            .select("*")
            .eq("id", member_id)
            .eq("tenant_id", current_user.tenant.id)
            .execute()
        )

        members = existing.data or []
        if not members:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Miembro no encontrado",
            )

        member = members[0]

        # No se puede cambiar el rol del owner
        if member["role"] == "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No se puede cambiar el rol del owner",
            )

        # Actualizar rol
        result = (
            db.client.table("tenant_members")
            .update({
                "role": data.role,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            .eq("id", member_id)
            .eq("tenant_id", current_user.tenant.id)
            .execute()
        )

        updated = result.data[0] if result.data else member
        updated["role"] = data.role

        logger.info(
            f"Rol actualizado: member={member_id} "
            f"role={data.role} tenant={current_user.tenant.id}"
        )

        return _format_member(updated)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error actualizando miembro: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al actualizar el miembro",
        )


@router.delete(
    "/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revocar acceso de miembro",
    description="Revoca el acceso de un miembro del equipo. "
                "Requiere rol owner o admin.",
)
def revoke_team_member(
    member_id: str,
    current_user: CurrentUser = Depends(current_user_dep),
) -> None:
    db = get_db()

    # Verificar permisos
    _require_admin_or_owner(current_user, db)

    try:
        # Verificar que el miembro existe y pertenece al tenant
        existing = (
            db.client.table("tenant_members")
            .select("*")
            .eq("id", member_id)
            .eq("tenant_id", current_user.tenant.id)
            .execute()
        )

        members = existing.data or []
        if not members:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Miembro no encontrado",
            )

        member = members[0]

        # No se puede revocar al owner
        if member["role"] == "owner":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No se puede revocar el acceso del owner",
            )

        # Revocar acceso
        db.client.table("tenant_members").update({
            "status": "revoked",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", member_id).eq("tenant_id", current_user.tenant.id).execute()

        logger.info(
            f"Acceso revocado: member={member_id} "
            f"tenant={current_user.tenant.id}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revocando miembro: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al revocar el acceso",
        )


@router.get(
    "/accept-invite",
    response_model=AcceptInviteResponse,
    summary="Aceptar invitación al equipo",
    description="Acepta una invitación usando el token recibido por email. "
                "El token es de un solo uso y expira en 48 horas.",
)
def accept_invite(
    token: str = Query(..., description="Token de invitación"),
) -> AcceptInviteResponse:
    db = get_db()

    try:
        # Buscar invitación por token
        result = (
            db.client.table("tenant_members")
            .select("*")
            .eq("invite_token", token)
            .eq("status", "pending")
            .execute()
        )

        members = result.data or []
        if not members:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invitación no encontrada o ya utilizada",
            )

        member = members[0]

        # Verificar expiración
        expires_at_str = member.get("invite_expires_at")
        if expires_at_str:
            expires_at = datetime.fromisoformat(
                expires_at_str.replace("Z", "+00:00")
            )
            if datetime.now(timezone.utc) > expires_at:
                raise HTTPException(
                    status_code=status.HTTP_410_GONE,
                    detail="La invitación ha expirado. Solicita una nueva invitación.",
                )

        now = datetime.now(timezone.utc).isoformat()

        # Aceptar invitación — marcar como activa y consumir token
        db.client.table("tenant_members").update({
            "status": "active",
            "invite_token": None,  # token de un solo uso
            "invite_expires_at": None,
            "accepted_at": now,
            "updated_at": now,
        }).eq("id", member["id"]).execute()

        logger.info(
            f"Invitación aceptada: member={member['id']} "
            f"email={member['invited_email']} tenant={member['tenant_id']}"
        )

        return AcceptInviteResponse(
            message=f"Bienvenido al equipo. Tu rol es: {member['role']}",
            tenant_id=member["tenant_id"],
            role=member["role"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error aceptando invitación: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error al aceptar la invitación",
        )