# ESTRUCTURA AI
**Estructura Tech Company S.A.S.**

## Plan de trabajo — Celeste
*Entorno de desarrollo, flujo de trabajo y roadmap técnico*

**Fecha de elaboración:** 2 de julio de 2026
**Responsable:** Stephania — Full Stack Developer

---

## Objetivo de este documento

Consolidar en un solo lugar tres cosas que hoy están dispersas o sin definir: (1) cómo debe quedar organizado el entorno de desarrollo y su relación con producción, (2) qué falta exactamente para llevar a Celeste a un estado mínimo decente en producción para Eje Inmobiliario, y (3) el backlog de arquitectura, manejo de errores, seguridad y frontend que viene después, priorizado por urgencia real y no por lo que sería ideal en un mundo sin restricciones de tiempo.

> **Principio guía:** Celeste debe empezar a responder pronto — el inversionista y Eje Inmobiliario la están esperando. No se busca perfección arquitectónica antes de lanzar; se busca un piso mínimo decente y luego iterar con el flujo de trabajo ya ordenado.

---

## Índice

| Documento | Contenido |
|-----------|-----------|
| [00-entorno-dev.md](./00-entorno-dev.md) | Fase 0 — Cuadrar el entorno de desarrollo (Railway, rama `development`, flujo de git) |
| [01-produccion-mvp.md](./01-produccion-mvp.md) | Fase 1 — Celeste a producción, mínimo viable decente |
| [02-arquitectura-backend.md](./02-arquitectura-backend.md) | Fase 2 — Manejo de errores y arquitectura básica |
| [03-seguridad-escalamiento.md](./03-seguridad-escalamiento.md) | Fase 3 — Seguridad y escalamiento (rumbo a 5–15 clientes) |
| [04-seguridad-formal.md](./04-seguridad-formal.md) | Fase 4 — Seguridad formal (negocio consolidado) |
| [05-frontend.md](./05-frontend.md) | Frontend — pendiente de diagnóstico |
| [07-investigacion-mensajes-duplicados-2026-07-07.md](./07-investigacion-mensajes-duplicados-2026-07-07.md) | Investigación 2026-07-07 — P0 de cola descartado (era falso), mensajes duplicados (mitigado, causa raíz sin encontrar), 2 problemas nuevos sin investigar |

---

*Documento vivo — actualizar a medida que se resuelvan los puntos marcados y aparezcan nuevos hallazgos.*
