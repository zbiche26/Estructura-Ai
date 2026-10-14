-- ============================================
-- GENERADOR DE DATOS DE PRUEBA
-- Crea 10,000+ productos para testing de performance
-- ============================================

-- Tabla temporal para generar datos
CREATE TEMP TABLE IF NOT EXISTS temp_products_to_insert (
    name VARCHAR(500),
    description TEXT,
    category VARCHAR(100),
    price NUMERIC,
    stock INTEGER,
    sku VARCHAR(50),
    is_active BOOLEAN,
    tenant_id UUID
);

-- Obtener un tenant_id válido
DO $$
DECLARE
    valid_tenant UUID;
BEGIN
    SELECT id INTO valid_tenant FROM tenants LIMIT 1;
    
    IF valid_tenant IS NOT NULL THEN
        -- Generar 10,000 productos
        WITH numbers AS (
            SELECT generate_series(1, 10000) as n
        )
        INSERT INTO temp_products_to_insert (name, description, category, price, stock, sku, is_active, tenant_id)
        SELECT 
            -- Nombres variados
            CASE 
                WHEN n % 10 = 0 THEN 'Silla Ejecutiva Premium ' || n
                WHEN n % 10 = 1 THEN 'Mesa de Oficina ' || n
                WHEN n % 10 = 2 THEN 'Escritorio Moderno ' || n
                WHEN n % 10 = 3 THEN 'Armario Metalico ' || n
                WHEN n % 10 = 4 THEN 'Sillon Gerencial ' || n
                WHEN n % 10 = 5 THEN 'Estante Librero ' || n
                WHEN n % 10 = 6 THEN 'Escritorio en L ' || n
                WHEN n % 10 = 7 THEN 'Mesa de Reuniones ' || n
                WHEN n % 10 = 8 THEN 'Silla Ergonómica ' || n
                ELSE 'Mueble Organizador ' || n
            END,
            -- Descripciones
            'Producto de alta calidad para oficina. SKU: PROD-' || LPAD(n::TEXT, 6, '0'),
            -- Categorías
            CASE 
                WHEN n % 5 = 0 THEN 'Oficina'
                WHEN n % 5 = 1 THEN 'Hogar'
                WHEN n % 5 = 2 THEN 'Industrial'
                WHEN n % 5 = 3 THEN 'Educativo'
                ELSE 'Comercial'
            END,
            -- Precio aleatorio entre 50,000 y 5,000,000
            (random() * 4995000 + 50000)::NUMERIC(12,2),
            -- Stock aleatorio entre 0 y 500
            (random() * 500)::INTEGER,
            -- SKU único
            'SKU-' || LPAD(n::TEXT, 6, '0'),
            -- Activo (90% activos)
            random() < 0.9,
            valid_tenant
        FROM numbers;
        
        RAISE NOTICE 'Generados 10,000 productos temporales';
    ELSE
        RAISE WARNING 'No se encontró tenant válido. No se generaron productos.';
    END IF;
END $$;

-- Contar productos generados
SELECT 'Productos generados: ' || COUNT(*) FROM temp_products_to_insert;

-- Insertar en la tabla real (descomenta cuando estés seguro)
-- INSERT INTO products (name, description, category, price, stock, sku, is_active, tenant_id)
-- SELECT name, description, category, price, stock, sku, is_active, tenant_id 
-- FROM temp_products_to_insert;

-- Verificar resultado
-- SELECT COUNT(*) as total_products FROM products;
