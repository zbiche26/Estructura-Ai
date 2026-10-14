# analyze_db.py
from supabase import create_client
from src.config import settings

supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

print("=== TABLAS EXISTENTES ===")
# Ver qué tablas hay
tables = ['products', 'conversations', 'messages', 'sales', 'tenants', 'users']

for table in tables:
    try:
        result = supabase.table(table).select("*", count='exact').limit(1).execute()
        print(f"✅ {table}: {result.count} registros")
    except Exception as e:
        print(f"❌ {table}: No existe o sin acceso")