# 📚 API Documentation - Autenticación

## 🔐 Autenticación con JWT

El sistema usa **JSON Web Tokens (JWT)** proporcionados por Supabase para autenticar usuarios.

---

## 🔑 Obtener un Token

### Opción 1: Login desde el Frontend

El frontend ya está configurado para obtener tokens automáticamente al hacer login.

```javascript
// El frontend envía el token en cada request
const response = await fetch("http://localhost:8000/api/v1/me", {
  headers: {
    Authorization: `Bearer ${accessToken}`,
    "X-Tenant-Id": tenantId,
  },
});
```

### Opción 2: Login desde Python (testing)

```python
from supabase import create_client

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

response = supabase.auth.sign_in_with_password({
    "email": "user@example.com",
    "password": "password123"
})

token = response.session.access_token
```

---

## 📡 Endpoints Disponibles

### GET /api/v1/me

Obtiene información del usuario autenticado.

#### Headers Requeridos

| Header          | Tipo   | Requerido     | Descripción                        |
| --------------- | ------ | ------------- | ---------------------------------- |
| `Authorization` | string | En producción | Bearer token de Supabase           |
| `X-Tenant-Id`   | string | Opcional      | ID del tenant (usa default en dev) |

#### Ejemplo de Request

```bash
curl http://localhost:8000/api/v1/me \
  -H "Authorization: Bearer eyJhbGciOiJFUzI1NiI..." \
  -H "X-Tenant-Id: tenant-123"
```

#### Ejemplo de Response (200 OK)

```json
{
  "data": {
    "user": {
      "id": "a828f16e-ff48-423f-8db9-8877f9bdac1d",
      "email": "cristian@test.com",
      "full_name": "cristian"
    },
    "tenant": {
      "id": "tenant-123",
      "name": "Tenant tenant-123"
    },
    "plan": {
      "id": "emprendedor",
      "status": "trialing",
      "trial_ends_at": "2026-02-15T00:00:00Z"
    },
    "features": ["onboarding", "billing", "training", "conversations"],
    "usage": {
      "products_count": 45,
      "conversations_month_count": 120,
      "limits": {
        "products": 500,
        "conversations_month": 1000
      }
    }
  },
  "meta": {
    "request_id": "req_...",
    "timestamp": "2026-02-16T22:14:15.581696"
  }
}
```

---

## ❌ Códigos de Error

### 401 Unauthorized

**Causa:** Token inválido, expirado o faltante (en producción).

```json
{
  "detail": "Could not validate credentials"
}
```

**Posibles razones:**

- Token expirado
- Token con firma inválida
- Token malformado
- Header Authorization faltante (en producción)

**Solución:**

- Obtener un nuevo token haciendo login
- Verificar que el header Authorization esté presente
- Verificar formato: `Bearer <token>`

---

### 400 Bad Request

**Causa:** Header X-Tenant-Id faltante (en producción).

```json
{
  "detail": "Missing X-Tenant-Id header"
}
```

**Solución:**

- Agregar header `X-Tenant-Id` con el ID del tenant

---

## 🧪 Testing

### Demo Token (Desarrollo)

Para testing sin necesidad de Supabase:

```bash
curl http://localhost:8000/api/v1/me \
  -H "Authorization: Bearer demo-token" \
  -H "X-Tenant-Id: demo-tenant"
```

**Respuesta:**

```json
{
  "data": {
    "user": {
      "id": "demo-user",
      "email": "demo@local.com",
      "full_name": "Demo User"
    },
    "tenant": {
      "id": "demo-tenant",
      "name": "Demo Tenant"
    },
    "plan": {
      "id": "emprendedor",
      "status": "trialing"
    }
  }
}
```

### Sin Token (Desarrollo)

En modo desarrollo (`APP_ENV=development`), el endpoint funciona sin autenticación:

```bash
curl http://localhost:8000/api/v1/me
```

⚠️ **Nota:** Esto solo funciona en desarrollo. En producción, se requiere token.

---

## 🔧 Ejemplos de Integración

### JavaScript / React

```javascript
// Obtener información del usuario
async function getMe(accessToken, tenantId) {
  const response = await fetch("http://localhost:8000/api/v1/me", {
    method: "GET",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "X-Tenant-Id": tenantId,
      "Content-Type": "application/json",
    },
  });

  if (!response.ok) {
    throw new Error("Authentication failed");
  }

  return await response.json();
}

// Uso
try {
  const data = await getMe(userToken, "tenant-123");
  console.log("User:", data.data.user);
} catch (error) {
  console.error("Error:", error);
}
```

---

### Python

```python
import requests

def get_me(token: str, tenant_id: str):
    """Obtener información del usuario autenticado"""
    response = requests.get(
        'http://localhost:8000/api/v1/me',
        headers={
            'Authorization': f'Bearer {token}',
            'X-Tenant-Id': tenant_id
        }
    )

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Error: {response.json()['detail']}")

# Uso
try:
    data = get_me(user_token, 'tenant-123')
    print(f"User ID: {data['data']['user']['id']}")
except Exception as e:
    print(f"Error: {e}")
```

---

### cURL

```bash
# Con token real
curl -X GET "http://localhost:8000/api/v1/me" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "X-Tenant-Id: tenant-123"

# Con demo token (solo desarrollo)
curl -X GET "http://localhost:8000/api/v1/me" \
  -H "Authorization: Bearer demo-token" \
  -H "X-Tenant-Id: demo-tenant"

# Sin auth (solo desarrollo)
curl -X GET "http://localhost:8000/api/v1/me"
```

---

## 🔒 Seguridad

### Buenas Prácticas

1. **NUNCA** expongas los tokens en logs o código cliente
2. **SIEMPRE** usa HTTPS en producción
3. **NUNCA** almacenes tokens en localStorage sin cifrar
4. **SIEMPRE** usa variables de entorno para configuración
5. **NUNCA** compartas el archivo `.env`

### Tokens en Desarrollo vs Producción

| Característica        | Desarrollo             | Producción    |
| --------------------- | ---------------------- | ------------- |
| `demo-token`          | ✅ Funciona            | ❌ Rechazado  |
| Sin token             | ✅ Permite (demo user) | ❌ Error 401  |
| Token real            | ✅ Funciona            | ✅ Funciona   |
| Verificación de firma | ⚠️ Deshabilitada       | ✅ Habilitada |

---

## 🛠️ Configuración

### Variables de Entorno

```env
# En .env
APP_ENV=development  # o production
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_JWT_SECRET=your-jwt-secret
```

### Activar Modo Desarrollo

```bash
# Linux/Mac
export APP_ENV=development

# Windows PowerShell
$env:APP_ENV = "development"

# O en .env
APP_ENV=development
```

---

## 📊 Flujo de Autenticación

```
┌──────────┐
│ Frontend │
└────┬─────┘
     │
     │ 1. Login (email + password)
     ├──────────────────────────────────────┐
     │                                       │
     │                                       ▼
     │                              ┌─────────────┐
     │                              │  Supabase   │
     │                              │    Auth     │
     │                              └──────┬──────┘
     │                                     │
     │ 2. JWT token                        │
     │◄────────────────────────────────────┘
     │
     │ 3. GET /me
     │    Authorization: Bearer <token>
     ├──────────────────────────────────────┐
     │                                       │
     │                                       ▼
     │                              ┌─────────────┐
     │                              │   Backend   │
     │                              │             │
     │                              │ 1. Verificar│
     │                              │    token    │
     │                              │ 2. Extraer  │
     │                              │    user_id  │
     │                              │ 3. Construir│
     │                              │    response │
     │                              └──────┬──────┘
     │                                     │
     │ 4. MeResponse                       │
     │◄────────────────────────────────────┘
     │
     ▼
```

---

## 🐛 Troubleshooting

### Error: "Invalid token: The specified alg value is not allowed"

**Causa:** El token usa un algoritmo no soportado.

**Solución:** El middleware soporta ES256 y HS256. Verifica que Supabase esté configurado correctamente.

---

### Error: "Token has expired"

**Causa:** El token JWT ha expirado.

**Solución:** Obtener un nuevo token haciendo login nuevamente.

```python
# Renovar token
response = supabase.auth.refresh_session()
new_token = response.session.access_token
```

---

### Error: "Missing X-Tenant-Id header"

**Causa:** Header faltante en producción.

**Solución:** Agregar el header en el request:

```javascript
headers: {
  'X-Tenant-Id': 'tenant-123'
}
```

---

## 📞 Soporte

**Documentación adicional:**

- Supabase Auth: https://supabase.com/docs/guides/auth
- FastAPI: https://fastapi.tiangolo.com
- JWT: https://jwt.io

**Repositorio:** backEstructuraAI  
**Desarrollador:** Cristian  
**Última actualización:** 16 de Febrero 2026
