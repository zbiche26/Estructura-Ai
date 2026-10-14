rag_system.py — El cerebro de la respuesta
Toma el mensaje del usuario, busca en Qdrant, arma el contexto, y llama al LLM con todo junto. El \_build_system_prompt son las reglas. El \_format_context es cómo le presenta las propiedades al LLM.

agent_orchestrator.py — El director de orquesta
Coordina todo el flujo en orden: detecta intent → crea contexto → selecciona estrategia → busca en KB → genera respuesta base → llama al RAG con historial real. No genera nada solo, solo coordina quién hace qué.

context_manager.py — Memoria en RAM (el problema que encontramos)
Guarda el stage de la conversación (DISCOVERY, COMPARISON, DECISION...) en un diccionario en memoria. Se pierde entre requests. Por eso añadimos \_load_conversation_history que lee desde Supabase.

intent_classifier.py — El clasificador de intención
Lee el mensaje y decide qué quiere el cliente: product_search, price_inquiry, greeting, availability, etc. Con eso el orquestador decide si buscar en Qdrant o no.

whatsapp_handler.py — El portero
Recibe el payload crudo de Meta, lo parsea, lo persiste en Supabase, y publica el evento en el event bus. No sabe nada de IA.

message_worker.py — El procesador asíncrono
Lee jobs de la tabla message_jobs, carga el tenant context, y llama al WhatsAppHandler. Existe para no bloquear el webhook de Meta que exige respuesta en menos de 500ms.

tenant_service.py — El cargador de configuración
Carga desde Supabase todo lo del tenant: token de WhatsApp, plan, features, whatsapp_enabled. Tiene caché de 5 minutos — ese era el bug de hoy.
