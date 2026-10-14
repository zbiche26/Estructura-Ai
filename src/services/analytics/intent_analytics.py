# -*- coding: utf-8 -*-
"""
intent_analytics.py - Métricas de Intents
==========================================
Calcula métricas sobre los intents detectados por el agente Alex
en las conversaciones de cada tenant.

Métricas calculadas:
    - Distribución de intents (%)
    - Confidence promedio por intent
    - Intents más frecuentes (top N)
    - Intents con baja confianza
    - Tendencia de intents por período

Uso:
    analytics = IntentAnalytics()
    metrics = analytics.calculate(messages)
    print(metrics.top_intents)
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# ── Value Objects ────────────────────────────────────────────

@dataclass
class IntentStat:
    """
    Estadísticas de un intent específico.

    Attributes:
        intent:         Nombre del intent
        count:          Veces que apareció
        percentage:     % del total de mensajes con intent
        avg_confidence: Confianza promedio (0.0 - 1.0)
        min_confidence: Confianza mínima detectada
        max_confidence: Confianza máxima detectada
    """
    intent:         str
    count:          int   = 0
    percentage:     float = 0.0
    avg_confidence: float = 0.0
    min_confidence: float = 1.0
    max_confidence: float = 0.0

    def __repr__(self) -> str:
        return (
            f"IntentStat(intent='{self.intent}', "
            f"count={self.count}, "
            f"avg_conf={self.avg_confidence:.2f})"
        )


@dataclass
class IntentMetrics:
    """
    Métricas completas de intents de un conjunto de mensajes.

    Attributes:
        total_messages:     Total de mensajes analizados
        messages_with_intent: Mensajes que tienen intent detectado
        unique_intents:     Número de intents únicos
        top_intents:        Lista de IntentStat ordenados por frecuencia
        low_confidence:     Intents con confianza por debajo del umbral
        distribution:       Dict {intent: porcentaje}
        avg_confidence_global: Confianza promedio global
        period_label:       Etiqueta del período
    """
    total_messages:        int              = 0
    messages_with_intent:  int              = 0
    unique_intents:        int              = 0
    top_intents:           List[IntentStat] = field(default_factory=list)
    low_confidence:        List[IntentStat] = field(default_factory=list)
    distribution:          Dict[str, float] = field(default_factory=dict)
    avg_confidence_global: float            = 0.0
    period_label:          str              = ""

    @property
    def coverage_rate(self) -> float:
        """% de mensajes con intent detectado."""
        if self.total_messages == 0:
            return 0.0
        return round((self.messages_with_intent / self.total_messages) * 100, 2)

    def summary(self) -> str:
        top = self.top_intents[0].intent if self.top_intents else "ninguno"
        return (
            f"Intents: {self.unique_intents} únicos | "
            f"cobertura={self.coverage_rate:.1f}% | "
            f"top='{top}' | "
            f"conf_avg={self.avg_confidence_global:.2f}"
        )

    def __repr__(self) -> str:
        return (
            f"IntentMetrics("
            f"unique={self.unique_intents}, "
            f"coverage={self.coverage_rate:.1f}%)"
        )


# ── Analizador principal ─────────────────────────────────────

class IntentAnalytics:
    """
    Calcula métricas de intents detectados por el agente.

    Los intents se leen desde el campo `metadata` de los mensajes
    (Message.metadata["intent"] y Message.metadata["confidence"]).

    Uso:
        analytics = IntentAnalytics(low_confidence_threshold=0.5)
        metrics   = analytics.calculate(messages)

        # Top 5 intents
        for stat in metrics.top_intents[:5]:
            print(f"{stat.intent}: {stat.count} veces ({stat.percentage:.1f}%)")

        # Intents con baja confianza
        for stat in metrics.low_confidence:
            print(f"{stat.intent}: conf={stat.avg_confidence:.2f}")
    """

    def __init__(self, low_confidence_threshold: float = 0.6) -> None:
        """
        Args:
            low_confidence_threshold: Umbral de confianza baja (default: 0.6).
                Intents con confianza promedio por debajo de este valor
                se reportan en low_confidence.
        """
        self._threshold = low_confidence_threshold

    # ── API pública ──────────────────────────────────────────

    def calculate(
        self,
        messages:     List[Any],
        period_label: str = "",
    ) -> IntentMetrics:
        """
        Calcula métricas completas de intents.

        Args:
            messages:     Lista de objetos Message.
            period_label: Etiqueta del período analizado.

        Returns:
            IntentMetrics con todas las métricas calculadas.
        """
        metrics = IntentMetrics(
            total_messages=len(messages),
            period_label=period_label,
        )

        if not messages:
            return metrics

        # Acumuladores por intent
        intent_counts:      Counter              = Counter()
        intent_confidences: Dict[str, List[float]] = defaultdict(list)

        for msg in messages:
            intent, confidence = self._extract_intent(msg)
            if intent:
                intent_counts[intent] += 1
                if confidence is not None:
                    intent_confidences[intent].append(confidence)

        metrics.messages_with_intent = sum(intent_counts.values())
        metrics.unique_intents       = len(intent_counts)

        if metrics.messages_with_intent == 0:
            return metrics

        # Construir IntentStat por intent
        stats: List[IntentStat] = []
        all_confidences: List[float] = []

        for intent, count in intent_counts.items():
            confs = intent_confidences.get(intent, [])
            avg_conf = round(sum(confs) / len(confs), 4) if confs else 0.0
            min_conf = min(confs) if confs else 0.0
            max_conf = max(confs) if confs else 0.0

            pct = round(
                (count / metrics.messages_with_intent) * 100, 2
            )

            stat = IntentStat(
                intent         = intent,
                count          = count,
                percentage     = pct,
                avg_confidence = avg_conf,
                min_confidence = min_conf,
                max_confidence = max_conf,
            )
            stats.append(stat)
            all_confidences.extend(confs)

        # Ordenar por frecuencia descendente
        stats.sort(key=lambda s: s.count, reverse=True)

        metrics.top_intents  = stats
        metrics.distribution = {s.intent: s.percentage for s in stats}

        # Confianza global
        if all_confidences:
            metrics.avg_confidence_global = round(
                sum(all_confidences) / len(all_confidences), 4
            )

        # Intents con baja confianza
        metrics.low_confidence = [
            s for s in stats
            if s.avg_confidence < self._threshold and s.avg_confidence > 0
        ]

        return metrics

    def top_intents(
        self,
        messages: List[Any],
        n:        int = 5,
    ) -> List[IntentStat]:
        """
        Retorna los N intents más frecuentes.

        Args:
            messages: Lista de mensajes.
            n:        Número de intents a retornar.

        Returns:
            Lista de IntentStat ordenada por frecuencia desc.
        """
        metrics = self.calculate(messages)
        return metrics.top_intents[:n]

    def low_confidence_intents(
        self,
        messages:  List[Any],
        threshold: Optional[float] = None,
    ) -> List[IntentStat]:
        """
        Retorna intents con confianza por debajo del umbral.

        Args:
            messages:  Lista de mensajes.
            threshold: Umbral personalizado (usa el del constructor si None).
        """
        if threshold is not None:
            original = self._threshold
            self._threshold = threshold
            result = self.calculate(messages).low_confidence
            self._threshold = original
            return result
        return self.calculate(messages).low_confidence

    def distribution(self, messages: List[Any]) -> Dict[str, float]:
        """
        Distribución porcentual de intents.

        Returns:
            Dict {intent: porcentaje}
        """
        return self.calculate(messages).distribution

    def coverage_rate(self, messages: List[Any]) -> float:
        """
        % de mensajes con intent detectado.

        Returns:
            Porcentaje (0.0 - 100.0)
        """
        return self.calculate(messages).coverage_rate

    def by_day(self, messages: List[Any]) -> List[Dict[str, Any]]:
        """
        Agrupa métricas de intents por día.

        Returns:
            Lista de dicts {date, top_intent, unique_intents, coverage}
        """
        return self._group_by_period(messages, "day")

    def by_month(self, messages: List[Any]) -> List[Dict[str, Any]]:
        """Agrupa métricas de intents por mes."""
        return self._group_by_period(messages, "month")

    # ── Agrupación por período ───────────────────────────────

    def _group_by_period(
        self,
        messages: List[Any],
        period:   str,
    ) -> List[Dict[str, Any]]:
        """Agrupa mensajes por período y calcula métricas."""
        groups: Dict[str, List[Any]] = defaultdict(list)

        for msg in messages:
            created_at = self._get_created_at(msg)
            if not created_at:
                continue

            if period == "day":
                key = created_at.strftime("%Y-%m-%d")
            elif period == "month":
                key = created_at.strftime("%Y-%m")
            else:
                key = created_at.strftime("%Y-%m-%d")

            groups[key].append(msg)

        result = []
        for period_key in sorted(groups.keys()):
            m = self.calculate(groups[period_key], period_label=period_key)
            top = m.top_intents[0].intent if m.top_intents else None
            result.append({
                "period":         period_key,
                "top_intent":     top,
                "unique_intents": m.unique_intents,
                "coverage":       m.coverage_rate,
                "avg_confidence": m.avg_confidence_global,
            })

        return result

    # ── Helpers ──────────────────────────────────────────────

    def _extract_intent(
        self,
        msg: Any,
    ) -> Tuple[Optional[str], Optional[float]]:
        """
        Extrae intent y confidence de un mensaje.

        Busca en:
          1. msg.metadata["intent"] / msg.metadata["confidence"]
          2. msg.intent / msg.confidence (atributos directos)
          3. msg.strategy_used como intent (fallback)

        Returns:
            Tupla (intent, confidence) — ambos pueden ser None.
        """
        intent     = None
        confidence = None

        # 1. Desde metadata dict
        metadata = getattr(msg, "metadata", None)
        if isinstance(metadata, dict):
            intent     = metadata.get("intent")
            confidence = metadata.get("confidence")

        # 2. Atributos directos
        if not intent:
            intent = getattr(msg, "intent", None)
        if confidence is None:
            confidence = getattr(msg, "confidence", None)

        # 3. Fallback: strategy_used como intent
        if not intent:
            intent = getattr(msg, "strategy_used", None)

        # Normalizar
        if intent:
            intent = str(intent).strip().lower()
            if not intent or intent in ("none", "null", "unknown"):
                intent = None

        if confidence is not None:
            try:
                confidence = float(confidence)
                # Asegurarse que esté en rango 0-1
                confidence = max(0.0, min(1.0, confidence))
            except (ValueError, TypeError):
                confidence = None

        return intent, confidence

    def _get_created_at(self, msg: Any) -> Optional[datetime]:
        """Fecha de creación del mensaje."""
        return getattr(msg, "created_at", None)