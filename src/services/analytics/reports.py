# -*- coding: utf-8 -*-
"""
reports.py - Generador de Reportes
====================================
Genera reportes semanales y mensuales en Markdown/HTML
a partir de AggregatedMetrics.

Reportes disponibles:
    - Reporte semanal  (Markdown)
    - Reporte mensual  (Markdown)
    - Resumen ejecutivo (Markdown)
    - Reporte HTML     (con estilos)
    - Detección de problemas

Uso:
    generator = ReportGenerator()
    md  = generator.weekly_report(metrics)
    html = generator.to_html(md)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.services.analytics.aggregator import AggregatedMetrics


# ── Value Objects ────────────────────────────────────────────


@dataclass
class ReportSection:
    """Sección individual de un reporte."""

    title: str
    content: str
    level: int = 2  # nivel de heading (1-3)

    def to_markdown(self) -> str:
        heading = "#" * self.level
        return f"{heading} {self.title}\n\n{self.content}\n"


@dataclass
class Report:
    """
    Reporte completo generado.

    Attributes:
        title:       Título del reporte
        period:      Período cubierto
        tenant_id:   Tenant al que pertenece
        report_type: "weekly" | "monthly" | "executive"
        sections:    Secciones del reporte
        problems:    Problemas detectados
        generated_at: Fecha de generación
    """

    title: str = ""
    period: str = ""
    tenant_id: str = ""
    report_type: str = "weekly"
    sections: List[ReportSection] = field(default_factory=list)
    problems: List[str] = field(default_factory=list)
    generated_at: str = ""

    def to_markdown(self) -> str:
        """Genera el reporte completo en Markdown."""
        lines = [
            f"# {self.title}",
            f"",
            f"**Período:** {self.period}  ",
            f"**Tenant:** {self.tenant_id}  ",
            f"**Generado:** {self.generated_at}",
            f"",
            "---",
            "",
        ]

        for section in self.sections:
            lines.append(section.to_markdown())

        if self.problems:
            lines.append("## ⚠️ Problemas Detectados\n")
            for problem in self.problems:
                lines.append(f"- {problem}")
            lines.append("")

        return "\n".join(lines)

    def to_html(self) -> str:
        """Genera el reporte en HTML con estilos básicos."""
        md = self.to_markdown()
        return _md_to_html(md, self.title)

    def __repr__(self) -> str:
        return (
            f"Report(type='{self.report_type}', "
            f"period='{self.period}', "
            f"sections={len(self.sections)})"
        )


# ── Generador principal ──────────────────────────────────────


class ReportGenerator:
    """
    Genera reportes de analytics para clientes y administradores.

    Uso:
        generator = ReportGenerator()

        # Reporte semanal
        report = generator.weekly_report(weekly_metrics)
        print(report.to_markdown())

        # Reporte mensual
        report = generator.monthly_report(monthly_metrics, daily_list)

        # Solo resumen ejecutivo
        summary = generator.executive_summary(metrics)

        # Detectar problemas
        problems = generator.detect_problems(metrics)
    """

    # Umbrales para detección de problemas
    THRESHOLDS = {
        "min_completion_rate": 60.0,  # % mínimo de conversaciones completadas
        "max_abandonment_rate": 40.0,  # % máximo de abandono
        "max_avg_response_ms": 3000.0,  # ms máximo de respuesta
        "min_success_rate": 90.0,  # % mínimo de requests exitosos
        "min_intent_coverage": 70.0,  # % mínimo de mensajes con intent
        "min_confidence": 0.65,  # confianza mínima promedio
    }

    # ── API pública ──────────────────────────────────────────

    def weekly_report(
        self,
        metrics: AggregatedMetrics,
        daily_list: Optional[List[AggregatedMetrics]] = None,
    ) -> Report:
        """
        Genera reporte semanal completo.

        Args:
            metrics:    Métricas semanales agregadas.
            daily_list: Lista de métricas diarias (opcional, para tendencias).

        Returns:
            Report con secciones de conversaciones, intents, productos y performance.
        """
        report = Report(
            title=f"Reporte Semanal — {metrics.period}",
            period=metrics.period,
            tenant_id=metrics.tenant_id,
            report_type="weekly",
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            problems=self.detect_problems(metrics),
        )

        report.sections = [
            self._section_resumen(metrics),
            self._section_conversaciones(metrics),
            self._section_intents(metrics),
            self._section_productos(metrics),
            self._section_performance(metrics),
        ]

        if daily_list:
            report.sections.append(self._section_tendencias(daily_list))

        return report

    def monthly_report(
        self,
        metrics: AggregatedMetrics,
        weekly_list: Optional[List[AggregatedMetrics]] = None,
    ) -> Report:
        """
        Genera reporte mensual completo.

        Args:
            metrics:     Métricas mensuales agregadas.
            weekly_list: Lista de métricas semanales (opcional).

        Returns:
            Report mensual con comparativas.
        """
        report = Report(
            title=f"Reporte Mensual — {metrics.period}",
            period=metrics.period,
            tenant_id=metrics.tenant_id,
            report_type="monthly",
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            problems=self.detect_problems(metrics),
        )

        report.sections = [
            self._section_resumen(metrics),
            self._section_conversaciones(metrics),
            self._section_intents(metrics),
            self._section_productos(metrics),
            self._section_performance(metrics),
        ]

        if weekly_list:
            report.sections.append(self._section_tendencias(weekly_list))

        return report

    def executive_summary(
        self,
        metrics: AggregatedMetrics,
    ) -> str:
        """
        Genera un resumen ejecutivo breve en Markdown.

        Args:
            metrics: Métricas del período.

        Returns:
            String Markdown con resumen de 5-8 líneas.
        """
        problems = self.detect_problems(metrics)
        status = (
            "✅ Sin problemas críticos"
            if not problems
            else f"⚠️ {len(problems)} problema(s) detectado(s)"
        )

        lines = [
            f"## Resumen Ejecutivo — {metrics.period}",
            "",
            f"| Métrica | Valor |",
            f"|---------|-------|",
            f"| Conversaciones | {metrics.total_conversations} |",
            f"| Tasa de completación | {metrics.completion_rate:.1f}% |",
            f"| Revenue | ${metrics.total_revenue:,.0f} COP |",
            f"| Tasa de éxito | {metrics.success_rate:.1f}% |",
            f"| Tiempo respuesta promedio | {metrics.avg_response_ms:.0f}ms |",
            f"| Top producto | {metrics.top_product or 'N/A'} |",
            "",
            f"**Estado:** {status}",
        ]

        if problems:
            lines.append("")
            lines.append("**Problemas:**")
            for p in problems:
                lines.append(f"- {p}")

        return "\n".join(lines)

    def detect_problems(
        self,
        metrics: AggregatedMetrics,
    ) -> List[str]:
        """
        Detecta problemas en las métricas y retorna lista de alertas.

        Returns:
            Lista de strings describiendo cada problema encontrado.
            Lista vacía si todo está bien.
        """
        problems = []
        t = self.THRESHOLDS

        if (
            metrics.total_conversations > 0
            and metrics.completion_rate < t["min_completion_rate"]
        ):
            problems.append(
                f"Tasa de completación baja: {metrics.completion_rate:.1f}% "
                f"(mínimo esperado: {t['min_completion_rate']:.0f}%)"
            )

        if (
            metrics.total_conversations > 0
            and (100 - metrics.completion_rate) > t["max_abandonment_rate"]
        ):
            problems.append(
                f"Alta tasa de abandono: " f"{100 - metrics.completion_rate:.1f}%"
            )

        if (
            metrics.avg_response_ms > 0
            and metrics.avg_response_ms > t["max_avg_response_ms"]
        ):
            problems.append(
                f"Tiempo de respuesta alto: {metrics.avg_response_ms:.0f}ms "
                f"(máximo: {t['max_avg_response_ms']:.0f}ms)"
            )

        if metrics.total_requests > 0 and metrics.success_rate < t["min_success_rate"]:
            problems.append(
                f"Tasa de éxito baja: {metrics.success_rate:.1f}% "
                f"(mínimo: {t['min_success_rate']:.0f}%)"
            )

        if (
            metrics.intent_coverage > 0
            and metrics.intent_coverage < t["min_intent_coverage"]
        ):
            problems.append(
                f"Cobertura de intents baja: {metrics.intent_coverage:.1f}% "
                f"(mínimo: {t['min_intent_coverage']:.0f}%)"
            )

        if metrics.avg_confidence > 0 and metrics.avg_confidence < t["min_confidence"]:
            problems.append(
                f"Confianza promedio baja: {metrics.avg_confidence:.2f} "
                f"(mínimo: {t['min_confidence']:.2f})"
            )

        return problems

    def to_html(self, markdown_or_report) -> str:
        """
        Convierte Markdown o Report a HTML.

        Args:
            markdown_or_report: String Markdown o objeto Report.

        Returns:
            String HTML completo.
        """
        if isinstance(markdown_or_report, Report):
            return markdown_or_report.to_html()
        return _md_to_html(str(markdown_or_report))

    # ── Secciones ────────────────────────────────────────────

    def _section_resumen(self, m: AggregatedMetrics) -> ReportSection:
        content = (
            f"| Métrica | Valor |\n"
            f"|---------|-------|\n"
            f"| Total conversaciones | {m.total_conversations} |\n"
            f"| Completadas | {m.completed_conv} ({m.completion_rate:.1f}%) |\n"
            f"| Abandonadas | {m.abandoned_conv} |\n"
            f"| Revenue total | ${m.total_revenue:,.0f} COP |\n"
            f"| Requests exitosos | {m.success_rate:.1f}% |\n"
            f"| Tiempo respuesta promedio | {m.avg_response_ms:.0f}ms |\n"
        )
        return ReportSection("📊 Resumen del Período", content, level=2)

    def _section_conversaciones(self, m: AggregatedMetrics) -> ReportSection:
        content = (
            f"- **Total:** {m.total_conversations} conversaciones\n"
            f"- **Completadas:** {m.completed_conv} ({m.completion_rate:.1f}%)\n"
            f"- **Abandonadas:** {m.abandoned_conv}\n"
            f"- **Promedio de mensajes:** {m.avg_messages:.1f} por conversación\n"
            f"- **Duración promedio:** {m.avg_duration_min:.1f} minutos\n"
        )
        return ReportSection("💬 Conversaciones", content, level=2)

    def _section_intents(self, m: AggregatedMetrics) -> ReportSection:
        top = m.top_intent or "N/A"
        content = (
            f"- **Intents únicos detectados:** {m.unique_intents}\n"
            f"- **Intent más frecuente:** {top}\n"
            f"- **Cobertura:** {m.intent_coverage:.1f}% de mensajes con intent\n"
            f"- **Confianza promedio:** {m.avg_confidence:.2f}\n"
        )
        return ReportSection("🎯 Intents del Agente", content, level=2)

    def _section_productos(self, m: AggregatedMetrics) -> ReportSection:
        top = m.top_product or "N/A"
        content = (
            f"- **Total consultas de productos:** {m.total_views}\n"
            f"- **Total ventas:** {m.total_sales} unidades\n"
            f"- **Revenue:** ${m.total_revenue:,.0f} COP\n"
            f"- **Tasa de conversión:** {m.conversion_rate:.1f}%\n"
            f"- **Producto más consultado:** {top}\n"
        )
        return ReportSection("🛒 Productos y Ventas", content, level=2)

    def _section_performance(self, m: AggregatedMetrics) -> ReportSection:
        content = (
            f"- **Total requests:** {m.total_requests}\n"
            f"- **Tasa de éxito:** {m.success_rate:.1f}%\n"
            f"- **Tiempo de respuesta promedio:** {m.avg_response_ms:.0f}ms\n"
            f"- **Total errores:** {m.total_errors}\n"
            f"- **Uptime estimado:** {m.success_rate:.1f}%\n"
        )
        return ReportSection("⚡ Performance", content, level=2)

    def _section_tendencias(
        self,
        period_list: List[AggregatedMetrics],
    ) -> ReportSection:
        """Genera tabla de tendencias por período."""
        lines = [
            "| Período | Conversaciones | Revenue | Éxito% | Resp.ms |",
            "|---------|---------------|---------|--------|---------|",
        ]
        for m in period_list:
            lines.append(
                f"| {m.period} "
                f"| {m.total_conversations} "
                f"| ${m.total_revenue:,.0f} "
                f"| {m.success_rate:.1f}% "
                f"| {m.avg_response_ms:.0f}ms |"
            )
        return ReportSection("📈 Tendencias", "\n".join(lines), level=2)


# ── Conversión Markdown → HTML ────────────────────────────────


def _md_to_html(markdown: str, title: str = "Reporte EstructuraAI") -> str:
    """
    Convierte Markdown básico a HTML con estilos.
    Soporta: headings, bold, listas, tablas, separadores.
    """
    css = """
    <style>
      body { font-family: Arial, sans-serif; max-width: 900px;
             margin: 40px auto; color: #333; line-height: 1.6; }
      h1 { color: #1F3864; border-bottom: 3px solid #2E75B6; padding-bottom: 10px; }
      h2 { color: #2E75B6; margin-top: 30px; }
      h3 { color: #444; }
      table { border-collapse: collapse; width: 100%; margin: 16px 0; }
      th { background: #2E75B6; color: white; padding: 10px 14px; text-align: left; }
      td { padding: 8px 14px; border: 1px solid #ddd; }
      tr:nth-child(even) { background: #f5f9ff; }
      ul { padding-left: 20px; }
      li { margin: 4px 0; }
      hr { border: none; border-top: 2px solid #2E75B6; margin: 24px 0; }
      strong { color: #1F3864; }
      .warning { background: #FFF3CD; border-left: 4px solid #FFC107;
                 padding: 12px 16px; margin: 16px 0; border-radius: 4px; }
    </style>
    """

    lines = markdown.split("\n")
    output = []
    in_table = False
    in_list = False

    for line in lines:
        # Headings
        if line.startswith("### "):
            if in_list:
                output.append("</ul>")
                in_list = False
            output.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            if in_list:
                output.append("</ul>")
                in_list = False
            output.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            if in_list:
                output.append("</ul>")
                in_list = False
            output.append(f"<h1>{line[2:]}</h1>")
        # Tabla
        elif line.startswith("|"):
            if not in_table:
                output.append("<table>")
                in_table = True
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(
                set(c.replace("-", "").replace(":", "").strip()) == set()
                or c.replace("-", "").replace(":", "").strip() == ""
                for c in cells
            ):
                continue  # separador de tabla
            if not any("<th>" in o for o in output[-5:]):
                tag = "th"
            else:
                tag = "td"
            row = "".join(f"<{tag}>{_inline(c)}</{tag}>" for c in cells)
            output.append(f"<tr>{row}</tr>")
        else:
            if in_table:
                output.append("</table>")
                in_table = False
            # Lista
            if line.startswith("- "):
                if not in_list:
                    output.append("<ul>")
                    in_list = True
                output.append(f"<li>{_inline(line[2:])}</li>")
            else:
                if in_list:
                    output.append("</ul>")
                    in_list = False
                # Separador
                if line.strip() == "---":
                    output.append("<hr>")
                elif line.strip() == "":
                    output.append("")
                else:
                    output.append(f"<p>{_inline(line)}</p>")

    if in_table:
        output.append("</table>")
    if in_list:
        output.append("</ul>")

    body = "\n".join(output)
    return (
        f"<!DOCTYPE html><html lang='es'><head>"
        f"<meta charset='UTF-8'><title>{title}</title>{css}</head>"
        f"<body>{body}</body></html>"
    )


def _inline(text: str) -> str:
    """Procesa formato inline: **bold**, *italic*."""
    import re

    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    return text
