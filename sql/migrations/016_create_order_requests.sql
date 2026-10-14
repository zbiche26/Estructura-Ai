-- Registro de pedidos por WhatsApp
CREATE TABLE IF NOT EXISTS order_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    conversation_id UUID NOT NULL,
    producto TEXT NOT NULL,
    talla TEXT,
    color TEXT,
    metodo_pago TEXT,
    direccion TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE order_requests ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Aislamiento pedidos por tenant" ON order_requests FOR ALL USING (tenant_id = (auth.jwt() ->> 'tenant_id')::uuid);
