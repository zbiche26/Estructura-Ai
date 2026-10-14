-- Optimización de tabla messages para Analytics
ALTER TABLE messages
ADD COLUMN IF NOT EXISTS intent VARCHAR(100),
ADD COLUMN IF NOT EXISTS sentiment VARCHAR(20),
ADD COLUMN IF NOT EXISTS sentiment_score FLOAT;

-- Índices de alto rendimiento
CREATE INDEX IF NOT EXISTS idx_messages_intent ON messages(tenant_id, intent);
CREATE INDEX IF NOT EXISTS idx_messages_sentiment ON messages(tenant_id, sentiment, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_tenant_date ON messages(tenant_id, created_at);
