# src/http/middleware/auth.py 
# Objetivo: Middleware para verificar JWT con Supabase y extraer el usuario del header Authorization

#from fastapi.params import Header # esta liena es necesaria para extraer el header Authorization


"""
Middleware de Autenticación JWT
Verifica tokens de Supabase y extrae información del usuario
"""

import jwt
from typing import Optional, Dict
from fastapi import HTTPException, status
from src.config import settings


class AuthenticationError(HTTPException):
    """Excepción personalizada para errores de autenticación"""
    
    def __init__(self, detail: str = "Could not validate credentials"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


def extract_token_from_header(authorization: str) -> str:
    """
    Extrae el token JWT del header Authorization
    
    Args:
        authorization: Header Authorization completo (ej: "Bearer eyJhbG...")
    
    Returns:
        str: Token JWT sin el prefijo "Bearer"
    
    Raises:
        AuthenticationError: Si el formato del header es inválido
    """
    if not authorization:
        raise AuthenticationError("Authorization header missing")
    
    # Verificar formato: "Bearer <token>"
    parts = authorization.split()
    
    if len(parts) != 2:
        raise AuthenticationError("Invalid authorization header format")
    
    if parts[0].lower() != "bearer":
        raise AuthenticationError("Authorization header must start with Bearer")
    
    return parts[1]


def verify_jwt_token(token: str) -> Dict:
    """
    Verifica y decodifica un token JWT de Supabase
    
    Args:
        token: Token JWT a verificar
    
    Returns:
        dict: Payload del token decodificado con información del usuario
        Ejemplo: {
            "sub": "user-id-123",
            "email": "user@example.com",
            "role": "authenticated",
            "exp": 1234567890,
            ...
        }
    
    Raises:
        AuthenticationError: Si el token es inválido, expirado o malformado
    """
    try:
        from jwt import PyJWKClient
        from src.core.logger import logger as _log

        jwks_url = f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        jwks_client = PyJWKClient(jwks_url)
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256", "HS256"],
            audience="authenticated",
        )
        
        # Verificar que el token tiene la información mínima necesaria
        if not payload.get("sub"):
            raise AuthenticationError("Token missing user ID (sub claim)")
        
        return payload
        
    except jwt.ExpiredSignatureError: # Si el token ha expirado, lanzamos un error de autenticación específico
        raise AuthenticationError("Token has expired")
    
    except jwt.InvalidTokenError as e:
        raise AuthenticationError(f"Invalid token: {str(e)}")
    
    except Exception as e:
        raise AuthenticationError(f"Token verification failed: {str(e)}")


def get_user_from_token(token: str) -> Dict:
    """
    Extrae información del usuario desde un token JWT
    
    Args:
        token: Token JWT ya extraído del header
    
    Returns:
        dict: Información del usuario
        Ejemplo: {
            "user_id": "uuid-user-123",
            "email": "user@example.com",
            "role": "authenticated"
        }
    """
    payload = verify_jwt_token(token)
    
    return {
        "user_id": payload.get("sub"),
        "email": payload.get("email"),
        "role": payload.get("role", "authenticated"),
        "raw_payload": payload  # Incluir payload completo por si se necesita
    }


def verify_authorization_header(authorization: Optional[str]) -> Dict:
    """
    Función completa que verifica el header Authorization y retorna el usuario
    
    Esta es la función principal que usarás en los endpoints.
    
    Args:
        authorization: Header Authorization (ej: "Bearer eyJhbG...")
    
    Returns:
        dict: Información del usuario autenticado
    
    Raises:
        AuthenticationError: Si hay cualquier problema con la autenticación
    
    Example:
        ```python
        @router.get("/me")
        async def get_me(authorization: str = Header(...)):
            user = verify_authorization_header(authorization)
            return {"user_id": user["user_id"]}
        ```
    """
    # 1. Extraer token del header
    token = extract_token_from_header(authorization)
    
    # 2. Verificar y decodificar token
    user_info = get_user_from_token(token)
    
    return user_info


# ============================================
# FUNCIONES AUXILIARES PARA CASOS ESPECIALES
# ============================================

def verify_tenant_access(user_id: str, tenant_id: str) -> bool:
    """
    Verifica que un usuario tenga acceso a un tenant específico
    
    TODO: Implementar consulta a la base de datos
    Por ahora retorna True (permitir todo en desarrollo)
    
    Args:
        user_id: ID del usuario
        tenant_id: ID del tenant a verificar
    
    Returns:
        bool: True si el usuario tiene acceso, False si no
    """
    # TODO: Consultar en Supabase si user_id pertenece a tenant_id
    # Por ahora, en desarrollo, permitimos todo
    return True


def get_user_tenants(user_id: str) -> list:
    """
    Obtiene la lista de tenants a los que un usuario tiene acceso
    
    TODO: Implementar consulta a la base de datos
    
    Args:
        user_id: ID del usuario
    
    Returns:
        list: Lista de tenant_ids
    """
    # TODO: Consultar en Supabase los tenants del usuario
    # Por ahora retornamos una lista vacía
    return []


# ============================================
# UTILIDAD PARA DEBUGGING
# ============================================

def decode_token_without_verification(token: str) -> Dict:
    """
    Decodifica un token sin verificar la firma (SOLO PARA DEBUGGING)
    
    ⚠️ NUNCA uses esto en producción para autenticación real
    
    Args:
        token: Token JWT
    
    Returns:
        dict: Payload del token decodificado
    """
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except Exception as e:
        return {"error": str(e)}
