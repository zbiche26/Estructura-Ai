"""
Generador de datos de prueba para testing de performance
Crea 10,000+ productos para probar índices y cache
"""

import random
from supabase import create_client
from src.config import settings


def generate_test_products(count: int = 10000):
    """Genera productos de prueba"""
    
    # Conectar a Supabase
    supabase = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY
    )
    
    # Obtener tenant_id válido
    tenants = supabase.table('tenants').select('id').limit(1).execute()
    if not tenants.data:
        print("❌ No hay tenants en la base de datos")
        return
    
    tenant_id = tenants.data[0]['id']
    
    # Categorías
    categories = ['Oficina', 'Hogar', 'Industrial', 'Educativo', 'Comercial']
    
    # Tipos de productos
    product_types = [
        'Silla Ejecutiva', 'Mesa de Oficina', 'Escritorio Moderno',
        'Armario Metálico', 'Sillón Gerencial', 'Estante Librero',
        'Escritorio en L', 'Mesa de Reuniones', 'Silla Ergonómica',
        'Mueble Organizador'
    ]
    
    print(f"🚀 Generando {count:,} productos...")
    
    products = []
    batch_size = 1000
    
    for i in range(1, count + 1):
        product_type = random.choice(product_types)
        category = random.choice(categories)
        
        product = {
            'name': f"{product_type} {i}",
            'description': f"Producto de alta calidad para {category.lower()}. SKU: PROD-{i:06d}",
            'category': category,
            'price': round(random.uniform(50000, 5000000), 2),
            'stock': random.randint(0, 500),
            'sku': f"SKU-{i:06d}",
            'is_active': random.random() < 0.9,  # 90% activos
            'tenant_id': tenant_id
        }
        
        products.append(product)
        
        # Insertar en batches de 1000
        if len(products) >= batch_size:
            result = supabase.table('products').insert(products).execute()
            print(f"   ✅ Insertados {len(products)} productos (total: {i:,})")
            products = []
    
    # Insertar los restantes
    if products:
        result = supabase.table('products').insert(products).execute()
        print(f"   ✅ Insertados {len(products)} productos restantes")
    
    print(f"\n🎉 Total de productos en DB: {count:,}")


def generate_conversations_and_messages(count: int = 5000):
    """Genera conversaciones y mensajes de prueba"""
    
    supabase = create_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_SERVICE_ROLE_KEY
    )
    
    # Obtener tenant y conversaciones existentes
    tenants = supabase.table('tenants').select('id').limit(1).execute()
    if not tenants.data:
        print("❌ No hay tenants")
        return
    
    tenant_id = tenants.data[0]['id']
    
    print(f"🚀 Generando {count:,} conversaciones...")
    
    # Generar conversaciones
    conversations = []
    for i in range(1, count + 1):
        phone = f"+57300{random.randint(1000000, 9999999)}"
        conversations.append({
            'tenant_id': tenant_id,
            'phone_number': phone,
            'customer_name': f"Cliente {i}",
            'status': 'active' if random.random() < 0.7 else 'closed'
        })
    
    # Insertar en batches
    for i in range(0, len(conversations), 1000):
        batch = conversations[i:i+1000]
        result = supabase.table('conversations').insert(batch).execute()
        print(f"   ✅ {i + len(batch):,} conversaciones")
    
    # Obtener IDs de conversaciones creadas
    convs = supabase.table('conversations').select('id').limit(count).execute()
    conv_ids = [c['id'] for c in convs.data]
    
    print(f"🚀 Generando mensajes de prueba...")
    
    # Generar mensajes
    messages = []
    sample_messages = [
        "Hola, necesito información sobre productos",
        "¿Tienen sillas ejecutivas?",
        "¿Cuál es el precio de este producto?",
        "Me interesa comprar 5 unidades",
        "Gracias por la información",
        "¿Hacen envíos a otras ciudades?",
        "¿Tienen garantía los productos?",
        "¿Cuál es el tiempo de entrega?"
    ]
    
    for conv_id in conv_ids[:1000]:  # 1000 conversaciones con mensajes
        for j in range(random.randint(3, 15)):  # 3-15 mensajes por conversación
            messages.append({
                'conversation_id': conv_id,
                'role': 'user' if j % 2 == 0 else 'assistant',
                'content': random.choice(sample_messages),
                'message_type': 'text'
            })
    
    # Insertar mensajes en batches
    for i in range(0, len(messages), 1000):
        batch = messages[i:i+1000]
        result = supabase.table('messages').insert(batch).execute()
        print(f"   ✅ {i + len(batch):,} mensajes")
    
    print(f"\n🎉 Datos de prueba generados")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "products":
            count = int(sys.argv[2]) if len(sys.argv) > 2 else 10000
            generate_test_products(count)
        elif sys.argv[1] == "conversations":
            count = int(sys.argv[2]) if len(sys.argv) > 2 else 5000
            generate_conversations_and_messages(count)
        elif sys.argv[1] == "all":
            generate_test_products(10000)
            generate_conversations_and_messages(5000)
    else:
        print("Usage:")
        print("  python scripts/generate_test_data.py products [count]")
        print("  python scripts/generate_test_data.py conversations [count]")
        print("  python scripts/generate_test_data.py all")
        print("\nExamples:")
        print("  python scripts/generate_test_data.py products 10000")
        print("  python scripts/generate_test_data.py all")
