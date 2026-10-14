# test_env.py
import os
from dotenv import load_dotenv

load_dotenv()

print("🔍 Verificando variables de entorno...\n")

variables = {
    "SUPABASE_URL": os.getenv("SUPABASE_URL"),
    "SUPABASE_ANON_KEY": os.getenv("SUPABASE_ANON_KEY"),
    "SUPABASE_SERVICE_KEY": os.getenv("SUPABASE_SERVICE_KEY"),
    "SUPABASE_JWT_SECRET": os.getenv("SUPABASE_JWT_SECRET"),
}

all_ok = True
for name, value in variables.items():
    if value and value != f"tu-{name.lower().replace('_', '-')}-aqui":
        # Mostrar solo primeros 30 caracteres
        display_value = value[:30] + "..." if len(value) > 30 else value
        if "secret" in name.lower() or "key" in name.lower():
            display_value = "*" * 20 + "..."
        print(f"✅ {name}: {display_value}")
    else:
        print(f"❌ {name}: NO CONFIGURADO")
        all_ok = False

print()
if all_ok:
    print("🎉 ¡Todas las variables están configuradas!")
else:
    print("⚠️  Faltan variables por configurar")