# Arquitectura del Agente IA de Ventas

**Autor:** Camilo Salazar - Tech Lead  
**Fecha:** Febrero 2026  
**Versión:** 1.0

---

## 📋 Tabla de Contenidos

1. [Introducción](#introducción)
2. [Diagrama de Flujo](#diagrama-de-flujo)
3. [Componentes Principales](#componentes-principales)
4. [Casos de Uso](#casos-de-uso)
5. [Configuración](#configuración)
6. [Mejoras Futuras](#mejoras-futuras)

---

## 1. Introducción

### 1.1 Propósito

El **Agente IA de Ventas** es un asistente conversacional inteligente diseñado para:

- ✅ Atender clientes 24/7 por WhatsApp
- ✅ Buscar productos usando RAG (Retrieval Augmented Generation)
- ✅ Responder preguntas sobre precios y disponibilidad
- ✅ Mantener contexto de conversaciones multi-turno
- ✅ Adaptar el tono según la etapa del customer journey
- ✅ Operar en modo multi-tenant (múltiples clientes)

### 1.2 Capacidades Principales

| Capacidad | Descripción |
|-----------|-------------|
| **Detección de Intenciones** | 6 intents: greeting, product_search, price_inquiry, availability, complaint, farewell |
| **Búsqueda Semántica** | RAG con Qdrant (vectores) + OpenAI embeddings |
| **Gestión de Contexto** | Historial de conversación + productos mencionados |
| **Estrategias de Venta** | 5 estrategias dinámicas según situación |
| **Personalidad** | "Alex" - Tono amigable pero profesional |
| **Multi-tenant** | Aislamiento de datos por tenant |

### 1.3 Stack Tecnológico

- **LLM:** OpenAI GPT-4 / Claude (Anthropic)
- **Vector DB:** Qdrant
- **Base de datos:** Supabase (PostgreSQL)
- **Backend:** FastAPI + Python 3.13
- **Mensajería:** WhatsApp Business API (heyoo)

---

## 2. Diagrama de Flujo

### 2.1 Flujo General

```
┌─────────────┐
│   Usuario   │
│  WhatsApp   │
└──────┬──────┘
       │ Mensaje: "Busco sillas ejecutivas"
       ▼
┌─────────────────────┐
│ WhatsAppHandler     │ Recibe webhook de Meta
│ (Daniel)            │ Parsea payload
└──────┬──────────────┘
       │
       ▼
┌─────────────────────┐
│ Event Bus           │ Publica evento:
│                     │ "whatsapp.message.received"
└──────┬──────────────┘
       │
       ▼
┌─────────────────────────────────────────────┐
│ AgentOrchestrator (Camilo)                  │
│                                             │
│  1. Recibe mensaje                          │
│  2. Coordina componentes                    │
│  3. Genera respuesta                        │
└──────┬──────────────────────────────────────┘
       │
       ├─────────────────┬─────────────────┬──────────────────┐
       │                 │                 │                  │
       ▼                 ▼                 ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ Intent       │  │ Context      │  │ Knowledge    │  │ Strategy     │
│ Classifier   │  │ Manager      │  │ Base (RAG)   │  │ Selector     │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │                  │
       │ Intent:         │ Contexto:       │ Productos:       │ Estrategia:
       │ "product_       │ - Historial     │ - Silla A        │ "consultive"
       │  search"        │ - Stage         │ - Silla B        │
       │                 │ - Productos     │ - Silla C        │
       │                 │   mencionados   │                  │
       └─────────────────┴─────────────────┴──────────────────┘
                                  │
                                  ▼
                         ┌─────────────────┐
                         │  Response       │
                         │  Generator      │
                         │  (Alex)         │
                         └────────┬────────┘
                                  │
                                  ▼
                    "¡Encontré 3 sillas! Te cuento..."
                                  │
                                  ▼
                         ┌─────────────────┐
                         │ WhatsAppHandler │
                         │ Envía respuesta │
                         └────────┬────────┘
                                  │
                                  ▼
                              ┌────────┐
                              │Usuario │
                              │Recibe  │
                              └────────┘
```

### 2.2 Flujo Detallado por Componente

```
1. RECEPCIÓN
   WhatsAppHandler
   ↓
   parse_meta_payload()
   ↓
   Event Bus publica

2. PROCESAMIENTO
   AgentOrchestrator.process_message()
   ↓
   IntentClassifier.classify()
   ↓
   AdvancedContextManager.get_context()
   ↓
   KnowledgeBase.search() [RAG con Qdrant]
   ↓
   StrategySelector.select()

3. GENERACIÓN
   ResponseGenerator.generate()
   ↓
   Ajustar tono por stage
   ↓
   Aplicar límites

4. ENVÍO
   WhatsAppHandler.send_message()
```

---

## 3. Componentes Principales

### 3.1 IntentClassifier

**Ubicación:** `src/services/intent_classifier.py`

**Función:** Detecta qué quiere hacer el usuario

**Intents Soportados:**

| Intent | Descripción | Keywords | Threshold |
|--------|-------------|----------|-----------|
| `greeting` | Saludos | hola, buenos días, hey | 0.7 |
| `product_search` | Buscar productos | busco, necesito, quiero | 0.6 |
| `price_inquiry` | Preguntar precios | cuánto cuesta, precio | 0.65 |
| `availability_check` | Verificar stock | hay disponible, tienen | 0.70 |
| `complaint` | Quejas | problema, no funciona | 0.75 |
| `farewell` | Despedida | adiós, gracias, hasta luego | 0.7 |

**Algoritmo:**

```python
def classify(message: str) -> IntentResult:
    # 1. Normalizar mensaje (minúsculas, sin acentos)
    normalized = normalize(message)
    
    # 2. Calcular score por cada intent
    scores = {}
    for intent in INTENTS:
        score = calculate_score(normalized, intent.keywords)
        scores[intent.name] = score
    
    # 3. Seleccionar intent con mayor score > threshold
    best_intent = max(scores, key=scores.get)
    
    if scores[best_intent] > THRESHOLDS[best_intent]:
        return IntentResult(intent=best_intent, confidence=scores[best_intent])
    
    # 4. Fallback: general_inquiry
    return IntentResult(intent="general_inquiry", confidence=0.5)
```

**Extracción de Entidades:**

```python
# Ejemplos
"Busco sillas ejecutivas negras" →
  entities = {
    "product": "sillas ejecutivas",
    "color": "negras"
  }

"Necesito 10 escritorios" →
  entities = {
    "product": "escritorios",
    "quantity": 10
  }
```

---

### 3.2 AdvancedContextManager

**Ubicación:** `src/services/context_manager.py`

**Función:** Mantiene el contexto de la conversación

**Datos Almacenados:**

```python
class ConversationContext:
    conversation_id: str         # Identificador único
    tenant_id: str              # ID del cliente
    messages: List[Message]     # Historial completo
    mentioned_products: List    # Productos mencionados
    stage: str                  # awareness | consideration | decision | purchase
    message_count: int          # Contador de mensajes
    last_intent: str           # Último intent detectado
    metadata: dict             # Datos adicionales
```

**Tracking de Stage:**

| Stage | Descripción | Indicadores |
|-------|-------------|-------------|
| **awareness** | Cliente apenas conoce | Primera interacción, preguntas generales |
| **consideration** | Comparando opciones | Pregunta por múltiples productos, comparaciones |
| **decision** | Listo para comprar | Pregunta precio específico, disponibilidad |
| **purchase** | En proceso de compra | Confirmación, cantidad, envío |
| **retention** | Cliente existente | Historial de compras previas |

**Ejemplo de Evolución:**

```
Turno 1: "Hola, qué productos tienen?"
→ Stage: awareness

Turno 2: "Busco sillas ejecutivas"
→ Stage: consideration

Turno 3: "Cuánto cuesta la Silla Premium?"
→ Stage: decision

Turno 4: "Ok, quiero 2 unidades"
→ Stage: purchase
```

---

### 3.3 KnowledgeBase (RAG)

**Ubicación:** `src/services/knowledge_base.py`

**Función:** Búsqueda semántica de productos usando vectores

**Arquitectura RAG:**

```
Query: "sillas ejecutivas"
↓
OpenAI Embeddings
↓
Vector: [0.234, -0.543, 0.876, ...]
↓
Qdrant Vector Search
↓
Top 5 productos más similares
↓
[
  {score: 0.92, product: "Silla Ejecutiva Premium"},
  {score: 0.88, product: "Silla Gerencial Deluxe"},
  ...
]
```

**Ventajas sobre búsqueda tradicional:**

| Búsqueda SQL | Búsqueda RAG |
|--------------|--------------|
| "silla ejecutiva" = match exacto | "silla de oficina" → encuentra "silla ejecutiva" |
| No entiende sinónimos | Entiende: escritorio = mesa de trabajo |
| Sensible a typos | Tolerante: "esritorio" → escritorio |

**Implementación:**

```python
async def search(query: str, tenant_id: str, limit: int = 5):
    # 1. Generar embedding del query
    embedding = await openai.embeddings.create(
        model="text-embedding-3-small",
        input=query
    )
    
    # 2. Buscar en Qdrant
    results = qdrant_client.search(
        collection_name=f"products_{tenant_id}",
        query_vector=embedding.data[0].embedding,
        limit=limit
    )
    
    # 3. Filtrar solo con stock > 0
    available = [r for r in results if r.payload["stock"] > 0]
    
    return available
```

---

### 3.4 Strategies (Estrategias de Venta)

**Ubicación:** `src/core/strategies.py`

**Función:** Diferentes enfoques de venta según la situación

**5 Estrategias Implementadas:**

#### 1. **ProductRecommendationStrategy**

```python
# Cuándo: Cliente busca producto
# Cómo: Recomendar basado en popularidad y similitud

Ejemplo:
Usuario: "Busco sillas"
Agente: "Te recomiendo la Silla Premium porque es la más 
         popular y tiene excelentes calificaciones."
```

#### 2. **PriceNegotiationStrategy**

```python
# Cuándo: Cliente pregunta por descuentos
# Cómo: Ofrecer alternativas, comparar costo/beneficio

Ejemplo:
Usuario: "Es muy caro"
Agente: "Entiendo tu presupuesto. Tengo la Silla Económica 
         a $180,000 con características similares."
```

#### 3. **AvailabilityCheckStrategy**

```python
# Cuándo: Cliente pregunta por stock
# Cómo: Crear urgencia si hay poco stock

Ejemplo:
Usuario: "Hay disponible?"
Agente: "⚠️ Solo quedan 2 unidades. ¡Es tu oportunidad!"
```

#### 4. **ComplaintHandlingStrategy**

```python
# Cuándo: Cliente se queja
# Cómo: Empatía + solución + escalación

Ejemplo:
Usuario: "El producto llegó dañado"
Agente: "Lamento mucho eso. Vamos a solucionarlo de inmediato.
         ¿Prefieres reemplazo o reembolso?"
```

#### 5. **GeneralInquiryStrategy**

```python
# Cuándo: Pregunta general o ambigua
# Cómo: Clarificar, hacer preguntas, ofrecer opciones

Ejemplo:
Usuario: "Qué me recomiendas?"
Agente: "Con gusto te ayudo. ¿Buscas para oficina o para casa?
         ¿Tienes algún presupuesto en mente?"
```

**Selector Automático:**

```python
def select_strategy(intent, context, confidence):
    if intent == "product_search" and confidence > 0.8:
        return ProductRecommendationStrategy()
    elif intent == "price_inquiry" and context.stage == "consideration":
        return PriceNegotiationStrategy()
    elif intent == "availability":
        return AvailabilityCheckStrategy()
    elif intent == "complaint":
        return ComplaintHandlingStrategy()
    else:
        return GeneralInquiryStrategy()
```

---

### 3.5 ResponseGenerator (Alex)

**Ubicación:** `src/services/response_generator.py`

**Función:** Genera respuestas naturales con personalidad

**Personalidad de Alex:**

```python
AGENT_CONFIG = {
    "name": "Alex",
    "tone": "friendly_professional",
    "use_emojis": True,
    "max_emojis_per_message": 2,
    "max_response_paragraphs": 3,
    "max_products_shown": 3,
    "formal_address": False  # "tú" en lugar de "usted"
}
```

**Reglas Estrictas:**

**NUNCA:**
- ❌ Inventar precios o información
- ❌ Mentir sobre stock
- ❌ Prometer entregas imposibles
- ❌ Dar info de productos desconocidos
- ❌ Hacer cálculos incorrectos
- ❌ Compartir datos de otros clientes

**SIEMPRE:**
- ✅ Confirmar antes de asumir
- ✅ Mencionar precio cuando habla de producto
- ✅ Indicar disponibilidad claramente
- ✅ Si no sabe algo: "Déjame verificar"
- ✅ Ser honesto
- ✅ Sugerir alternativas

**Ajuste de Tono por Stage:**

```python
# Stage: AWARENESS (educativo)
"💡 ¿Quieres que te cuente más sobre este tipo de productos?"

# Stage: CONSIDERATION (comparativo)
"📊 ¿Te gustaría que compare las opciones para que elijas mejor?"

# Stage: DECISION (persuasivo suave)
"✨ ¿Te lo aparto? Tengo stock disponible ahora mismo."

# Stage: PURCHASE (facilitar compra)
"¿Cuántas unidades necesitas?"
```

**Límites Aplicados:**

```python
def _apply_limits(response):
    # Máximo 3 párrafos
    if len(paragraphs) > 3:
        response = paragraphs[:3] + "\n\n_(Tengo más info si la necesitas)_"
    
    # Máximo 2 emojis
    if emoji_count > 2:
        # Eliminar emojis excedentes
    
    # Máximo 1000 caracteres (WhatsApp recomienda)
    if len(response) > 1000:
        response = response[:950] + "...\n\n_(¿Quieres más detalles?)_"
    
    return response
```

---

## 4. Casos de Uso

### 4.1 Caso de Uso 1: Búsqueda Simple

**Escenario:** Usuario busca un producto

**Input:** Usuario: "Hola, busco sillas ejecutivas"

**Procesamiento:**

```
Paso 1: IntentClassifier
├─ Detecta: greeting + product_search
├─ Confianza: 0.95
└─ Entidades: {product: "sillas ejecutivas"}

Paso 2: ContextManager
├─ Verifica contexto previo: No existe
├─ Crea nueva conversación
└─ Stage: awareness (primera interacción)

Paso 3: KnowledgeBase (RAG)
├─ Query: "sillas ejecutivas"
├─ Embedding: [0.234, -0.543, ...]
├─ Qdrant search
└─ Resultados: 5 sillas (filtrado por stock > 0)

Paso 4: Strategy Selection
├─ Intent = product_search
└─ Selecciona: ProductRecommendationStrategy

Paso 5: ResponseGenerator
├─ Template: "with_results"
├─ Personalidad: Alex (friendly_professional)
├─ Ajuste de tono: awareness → educativo
└─ Límites: max 3 productos
```

**Output:**

```
¡Hola! 😊 Claro, tengo sillas ejecutivas disponibles.
Te cuento sobre las más populares:

📦 Silla Ejecutiva Premium
💰 $250,000
✅ Disponible (8 unidades)

📦 Silla Gerencial Deluxe
💰 $320,000
✅ Disponible (3 unidades)

📦 Silla Económica Pro
💰 $180,000
✅ Disponible (15 unidades)

💡 ¿Quieres que te cuente más sobre estas opciones?
```

---

### 4.2 Caso de Uso 2: Pregunta de Precio

**Escenario:** Usuario pregunta precio de producto específico

**Input:** Usuario: "Cuánto cuesta la Silla Premium?"

**Procesamiento:**

```
Paso 1: IntentClassifier
└─ Detecta: price_inquiry (confidence: 0.88)

Paso 2: ContextManager
├─ Recupera contexto previo
├─ Encuentra "Silla Premium" en productos mencionados
└─ Stage: consideration

Paso 3: KnowledgeBase
├─ Busca: "Silla Premium"
└─ Resultado: 1 producto

Paso 4: ResponseGenerator
├─ Template: price_inquiry.with_price
├─ Propuesta de valor: "Excelente calidad"
└─ Ajuste de tono: consideration → comparativo
```

**Output:**

```
El precio de la Silla Ejecutiva Premium es $250,000.
Excelente relación calidad-precio.

📊 ¿Te gustaría que compare esta opción con otras 
    para que elijas mejor?
```

---

### 4.3 Caso de Uso 3: Conversación Multi-turno

**Escenario:** Conversación larga manteniendo contexto

**Turno 1:**
```
Usuario: "Busco sillas"
Agente: [Lista de sillas]
Context: 
  - stage: awareness
  - mentioned_products: [Silla A, Silla B, Silla C]
```

**Turno 2:**
```
Usuario: "Cuánto cuesta?" [NO especifica cuál]
Agente: "La Silla A cuesta $250,000"
Context:
  - Recupera última silla mencionada (Silla A)
  - stage: consideration → decision
  - mentioned_products: [Silla A] (actualiza a más reciente)
```

**Turno 3:**
```
Usuario: "Hay en color negro?"
Agente: "Sí, la Silla A viene en negro. ¿Quieres que te la aparte?"
Context:
  - Entiende que habla de Silla A (contexto)
  - stage: decision
  - Tono persuasivo
```

**Turno 4:**
```
Usuario: "Ok perfecto"
Agente: "¡Excelente! ¿Cuántas unidades necesitas?"
Context:
  - Interpreta "ok" como confirmación
  - stage: purchase
  - Facilita siguiente paso
```

---

## 5. Configuración

### 5.1 Variables de Entorno

**Archivo:** `.env`

```bash
# OpenAI (LLM + Embeddings)
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4-turbo
OPENAI_TEMPERATURE=0.7
OPENAI_MAX_TOKENS=500

# Anthropic Claude (Alternativa)
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-sonnet-20240229

# Qdrant (Vector Database)
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your-api-key
QDRANT_COLLECTION=products

# Supabase (PostgreSQL)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key

# WhatsApp Business API
WHATSAPP_TOKEN=your-whatsapp-token
WHATSAPP_PHONE_ID=your-phone-id
WHATSAPP_VERIFY_TOKEN=your-verify-token

# Agente IA
AGENT_NAME=Alex
AGENT_TONE=friendly_professional
AGENT_MAX_PRODUCTS=3
AGENT_MAX_PARAGRAPHS=3
```

### 5.2 Thresholds de Confianza

**Archivo:** `src/services/intent_classifier.py`

```python
INTENT_THRESHOLDS = {
    "greeting": 0.7,
    "product_search": 0.6,
    "price_inquiry": 0.65,
    "availability_check": 0.70,
    "complaint": 0.75,
    "general_inquiry": 0.50,
    "farewell": 0.7
}
```

**Ajustar si:**
- **Muchos falsos positivos** → Aumentar threshold
- **No detecta intents válidos** → Disminuir threshold

### 5.3 System Prompt (LLM)

**Archivo:** `src/services/response_generator.py`

```python
SYSTEM_PROMPT = """
Eres Alex, un asistente de ventas virtual profesional y amigable.

PERSONALIDAD:
- Entusiasta pero nunca invasivo
- Genuinamente útil, no solo vendes
- Conversacional y natural
- Usas emojis ocasionalmente (máx 2 por mensaje)
- Respondes de forma concisa (máximo 3 párrafos)
- Tratas al cliente de tú (informal)

REGLAS ESTRICTAS:
NUNCA:
- Inventar precios o información de productos
- Mentir sobre disponibilidad de stock
...

SIEMPRE:
- Confirmar información antes de asumir
- Mencionar precio cuando habla de un producto
...
"""
```

---

## 6. Mejoras Futuras

### 6.1 Limitaciones Actuales

| Limitación | Impacto | Prioridad |
|------------|---------|-----------|
| No maneja imágenes de productos | Usuario no puede ver fotos | Alta |
| No integra pagos | Usuario debe pagar fuera del chat | Media |
| No maneja múltiples idiomas | Solo español | Baja |
| Intent classifier básico | Confianza puede mejorar | Media |
| No aprende de interacciones | No mejora con uso | Alta |

### 6.2 Roadmap

**Corto Plazo (1-2 meses):**
- ✅ Envío de imágenes de productos en WhatsApp
- ✅ Mejorar extracción de entidades (cantidades, colores)
- ✅ Dashboard de métricas (conversiones, preguntas frecuentes)

**Mediano Plazo (3-6 meses):**
- 🔄 Fine-tuning del modelo con conversaciones reales
- 🔄 Integración con sistema de pagos
- 🔄 Soporte para voz (Audio messages)
- 🔄 Multi-idioma (inglés, portugués)

**Largo Plazo (6-12 meses):**
- 📅 Proactive outreach (seguimiento automático)
- 📅 Análisis de sentimiento en tiempo real
- 📅 Generación de cotizaciones complejas
- 📅 Integración con CRM

### 6.3 Métricas de Éxito

**KPIs a Monitorear:**

```python
# Efectividad del Agente
- Intent classification accuracy: >85%
- Response time: <2 segundos
- Conversation completion rate: >70%

# Experiencia del Usuario
- User satisfaction (CSAT): >4.0/5.0
- Average conversation length: 3-7 turnos
- Escalation rate (a humano): <15%

# Negocio
- Conversion rate: >5%
- Average order value: $XXX
- Customer retention: >40%
```

---

## 7. Referencias

### 7.1 Documentación Relacionada

- [README.md](../README.md) - Instalación y quick start
- [API_DOCUMENTATION.md](./API_DOCUMENTATION.md) - Endpoints REST
- [DEPLOYMENT.md](./DEPLOYMENT.md) - Guía de deployment
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) - Problemas comunes

### 7.2 Recursos Externos

- [OpenAI Embeddings](https://platform.openai.com/docs/guides/embeddings)
- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [WhatsApp Business API](https://developers.facebook.com/docs/whatsapp)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

### 7.3 Contacto

**Equipo:**
- Camilo Salazar - Tech Lead (Agente IA)
- Daniel Martínez - Integration Engineer (WhatsApp)
- Cristian López - Backend Developer (Database)

**Repositorio:** [GitHub - estructuraAI](https://github.com/your-org/estructuraAI)

---

**Última actualización:** 23 de Febrero 2026  
**Versión:** 1.0