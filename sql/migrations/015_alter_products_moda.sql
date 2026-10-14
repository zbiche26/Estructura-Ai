-- Adaptación a Nicho de Moda
ALTER TABLE products
ADD COLUMN IF NOT EXISTS tallas TEXT,
ADD COLUMN IF NOT EXISTS colores TEXT,
ADD COLUMN IF NOT EXISTS referencia VARCHAR(100);

-- Índices para búsqueda por talla y color
CREATE INDEX IF NOT EXISTS idx_products_tallas ON products USING gin(to_tsvector('spanish', tallas));
CREATE INDEX IF NOT EXISTS idx_products_colores ON products USING gin(to_tsvector('spanish', colores));
