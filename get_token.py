"""
Script para obtener token JWT de Supabase
"""
from supabase import create_client
from src.config import settings

# Crear cliente de Supabase
supabase = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_ANON_KEY  # Usar ANON_KEY para login
)

# Hacer login
email = "cristian@test.com"
password = "123456"

print("🔐 Intentando login...")
print(f"Email: {email}")
print()

try:
    # Login
    response = supabase.auth.sign_in_with_password({
        "email": email,
        "password": password
    })
    
    print("✅ Login exitoso!")
    print()
    print("=" * 60)
    print("INFORMACIÓN DEL USUARIO")
    print("=" * 60)
    print(f"User ID: {response.user.id}")
    print(f"Email: {response.user.email}")
    print()
    print("=" * 60)
    print("TOKEN JWT (copia esto)")
    print("=" * 60)
    print(response.session.access_token)
    print()
    print("=" * 60)
    print("COMANDO CURL PARA PROBAR")
    print("=" * 60)
    print(f'curl http://localhost:8000/api/v1/me \\')
    print(f'  -H "Authorization: Bearer {response.session.access_token}" \\')
    print(f'  -H "X-Tenant-Id: tenant-cristian"')
    print()
    
except Exception as e:
    print(f"❌ Error en login: {str(e)}")
    print()
    print("Posibles causas:")
    print("1. El usuario no existe en Supabase")
    print("2. La contraseña es incorrecta")
    print("3. El usuario no está confirmado")
    print()
    print("Solución: Ve a Supabase Dashboard > Authentication > Users")
    print("         y verifica que el usuario existe y está confirmado")