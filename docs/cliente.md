¿Cómo funciona por cliente?

CLIENTE A (Cámaras de seguridad)
├── Supabase: tenant_id = "cliente_a"
│   └── productos: cámaras, DVRs, kits
├── Qdrant: colección = "cliente_a_productos"
│   └── embeddings de sus productos
└── Excel: columnas [nombre, precio, stock, referencia]

CLIENTE B (Ropa)
├── Supabase: tenant_id = "cliente_b"
│   └── productos: camisas, pantalones, tallas
├── Qdrant: colección = "cliente_b_productos"  
│   └── embeddings de SUS productos
└── Excel: columnas [nombre, precio, talla, color]

CLIENTE C (Repuestos)
├── Supabase: tenant_id = "cliente_c"
│   └── productos: repuestos, referencias técnicas
├── Qdrant: colección = "cliente_c_productos"
│   └── embeddings de SUS productos
└── Excel: columnas [referencia, descripcion, precio, marca]

El aislamiento está garantizado porque:
python# El importer.py que vamos a crear usará el tenant_id
# para separar datos en Qdrant y Supabase

# Supabase — Row Level Security por tenant
productos.insert({
    "tenant_id": "cliente_a",   # ← aislamiento en BD
    "name": "Camara Domo",
    "price": 180000
})

# Qdrant — colección separada por tenant
collection_name = f"{tenant_id}_productos"
# cliente_a → "cliente_a_productos"
# cliente_b → "cliente_b_productos"
```

---

**El Excel flexible funciona así:**
```
Cliente sube su Excel con sus columnas
            │
            ▼
column_mapping (ya lo tienes en parser.py)
{"Nombre Producto": "name", "Valor": "price"}
            │
            ▼
validator.py valida con las reglas de negocio
            │
            ▼
importer.py guarda en Supabase + Qdrant
con el tenant_id correcto
```

---

**El RAG por cliente:**
```
Usuario WhatsApp pregunta:
"¿tienen cámaras 4K?"
        │
        ▼
Qdrant busca en "cliente_a_productos"
Solo encuentra productos DE ESE CLIENTE
        │
        ▼
GPT-4 responde con información
exclusiva del cliente A