# -*- coding: utf-8 -*-
"""
test_reports.py - Tests del ReportGenerator (Tarea 8)
======================================================
Ejecutar: pytest tests/analytics/test_reports.py -v
"""

import pytest
from src.services.analytics.aggregator import AggregatedMetrics
from src.services.analytics.reports import (
    ReportGenerator,
    ReportSection,
    Report,
)


# ── Helpers ───────────────────────────────────────────────────


def make_metrics(
    period: str = "2024-01-15",
    tenant_id: str = "tenant_a",
    total_conversations: int = 100,
    completed_conv: int = 75,
    abandoned_conv: int = 25,
    completion_rate: float = 75.0,
    avg_messages: float = 6.0,
    avg_duration_min: float = 15.0,
    top_intent: str = "greeting",
    unique_intents: int = 5,
    intent_coverage: float = 85.0,
    avg_confidence: float = 0.82,
    total_views: int = 200,
    total_sales: int = 40,
    total_revenue: float = 7_200_000.0,
    conversion_rate: float = 20.0,
    top_product: str = "Camara Domo",
    total_requests: int = 500,
    success_rate: float = 95.0,
    avg_response_ms: float = 800.0,
    total_errors: int = 25,
) -> AggregatedMetrics:
    return AggregatedMetrics(
        period=period,
        tenant_id=tenant_id,
        total_conversations=total_conversations,
        completed_conv=completed_conv,
        abandoned_conv=abandoned_conv,
        completion_rate=completion_rate,
        avg_messages=avg_messages,
        avg_duration_min=avg_duration_min,
        top_intent=top_intent,
        unique_intents=unique_intents,
        intent_coverage=intent_coverage,
        avg_confidence=avg_confidence,
        total_views=total_views,
        total_sales=total_sales,
        total_revenue=total_revenue,
        conversion_rate=conversion_rate,
        top_product=top_product,
        total_requests=total_requests,
        success_rate=success_rate,
        avg_response_ms=avg_response_ms,
        total_errors=total_errors,
    )


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def generator() -> ReportGenerator:
    return ReportGenerator()


@pytest.fixture
def metrics() -> AggregatedMetrics:
    return make_metrics()


@pytest.fixture
def metrics_problemas() -> AggregatedMetrics:
    """Métricas con problemas para probar detect_problems."""
    return make_metrics(
        completion_rate=40.0,  # bajo
        success_rate=70.0,  # bajo
        avg_response_ms=5000.0,  # alto
        intent_coverage=50.0,  # bajo
        avg_confidence=0.45,  # bajo
    )


# ── Tests: ReportSection ──────────────────────────────────────


class TestReportSection:

    def test_to_markdown_contiene_titulo(self):
        s = ReportSection("Mi Sección", "contenido", level=2)
        md = s.to_markdown()
        assert "## Mi Sección" in md

    def test_to_markdown_contiene_contenido(self):
        s = ReportSection("Título", "Este es el contenido")
        md = s.to_markdown()
        assert "Este es el contenido" in md

    def test_nivel_heading(self):
        s3 = ReportSection("Sub", "txt", level=3)
        assert s3.to_markdown().startswith("###")


# ── Tests: Report ─────────────────────────────────────────────


class TestReport:

    def test_to_markdown_contiene_titulo(self):
        r = Report(title="Mi Reporte", period="2024-01", generated_at="hoy")
        md = r.to_markdown()
        assert "# Mi Reporte" in md

    def test_to_markdown_contiene_periodo(self):
        r = Report(title="R", period="2024-W01", generated_at="hoy")
        md = r.to_markdown()
        assert "2024-W01" in md

    def test_to_markdown_con_secciones(self):
        r = Report(title="R", period="p", generated_at="hoy")
        r.sections.append(ReportSection("Sección 1", "contenido"))
        md = r.to_markdown()
        assert "Sección 1" in md

    def test_to_markdown_con_problemas(self):
        r = Report(
            title="R",
            period="p",
            generated_at="hoy",
            problems=["Problema 1", "Problema 2"],
        )
        md = r.to_markdown()
        assert "Problema 1" in md
        assert "Problema 2" in md

    def test_to_html_retorna_html(self):
        r = Report(title="R", period="p", generated_at="hoy")
        html = r.to_html()
        assert "<!DOCTYPE html>" in html
        assert "<html" in html

    def test_repr_contiene_type(self):
        r = Report(report_type="weekly", period="2024-W01")
        assert "weekly" in repr(r)


# ── Tests: weekly_report ──────────────────────────────────────


class TestWeeklyReport:

    def test_retorna_report(self, generator, metrics):
        result = generator.weekly_report(metrics)
        assert isinstance(result, Report)

    def test_type_es_weekly(self, generator, metrics):
        result = generator.weekly_report(metrics)
        assert result.report_type == "weekly"

    def test_tiene_secciones(self, generator, metrics):
        result = generator.weekly_report(metrics)
        assert len(result.sections) >= 5

    def test_titulo_contiene_periodo(self, generator, metrics):
        result = generator.weekly_report(metrics)
        assert metrics.period in result.title

    def test_markdown_contiene_conversaciones(self, generator, metrics):
        result = generator.weekly_report(metrics)
        md = result.to_markdown()
        assert "Conversaciones" in md

    def test_markdown_contiene_revenue(self, generator, metrics):
        result = generator.weekly_report(metrics)
        md = result.to_markdown()
        assert "Revenue" in md or "revenue" in md.lower()

    def test_con_daily_list_agrega_tendencias(self, generator, metrics):
        daily = [make_metrics(period=f"2024-01-0{i}") for i in range(1, 4)]
        result = generator.weekly_report(metrics, daily_list=daily)
        titulos = [s.title for s in result.sections]
        assert any("Tendencia" in t for t in titulos)


# ── Tests: monthly_report ─────────────────────────────────────


class TestMonthlyReport:

    def test_retorna_report(self, generator, metrics):
        result = generator.monthly_report(metrics)
        assert isinstance(result, Report)

    def test_type_es_monthly(self, generator, metrics):
        result = generator.monthly_report(metrics)
        assert result.report_type == "monthly"

    def test_tiene_secciones(self, generator, metrics):
        result = generator.monthly_report(metrics)
        assert len(result.sections) >= 5


# ── Tests: executive_summary ──────────────────────────────────


class TestExecutiveSummary:

    def test_retorna_string(self, generator, metrics):
        result = generator.executive_summary(metrics)
        assert isinstance(result, str)

    def test_contiene_conversaciones(self, generator, metrics):
        result = generator.executive_summary(metrics)
        assert "100" in result  # total_conversations

    def test_contiene_revenue(self, generator, metrics):
        result = generator.executive_summary(metrics)
        assert "7" in result  # revenue 7.200.000

    def test_sin_problemas_estado_ok(self, generator, metrics):
        result = generator.executive_summary(metrics)
        assert "Sin problemas" in result

    def test_con_problemas_lista_problemas(self, generator, metrics_problemas):
        result = generator.executive_summary(metrics_problemas)
        assert "problema" in result.lower()


# ── Tests: detect_problems ────────────────────────────────────


class TestDetectProblems:

    def test_sin_problemas_lista_vacia(self, generator, metrics):
        problems = generator.detect_problems(metrics)
        assert problems == []

    def test_completion_rate_bajo(self, generator):
        m = make_metrics(completion_rate=40.0, total_conversations=50)
        problems = generator.detect_problems(m)
        assert any("completación" in p for p in problems)

    def test_success_rate_bajo(self, generator):
        m = make_metrics(success_rate=70.0, total_requests=100)
        problems = generator.detect_problems(m)
        assert any("éxito" in p for p in problems)

    def test_response_ms_alto(self, generator):
        m = make_metrics(avg_response_ms=5000.0, total_requests=100)
        problems = generator.detect_problems(m)
        assert any("respuesta" in p for p in problems)

    def test_intent_coverage_bajo(self, generator):
        m = make_metrics(intent_coverage=50.0)
        problems = generator.detect_problems(m)
        assert any("intent" in p.lower() for p in problems)

    def test_confianza_baja(self, generator):
        m = make_metrics(avg_confidence=0.40)
        problems = generator.detect_problems(m)
        assert any("confianza" in p.lower() for p in problems)

    def test_multiples_problemas(self, generator, metrics_problemas):
        problems = generator.detect_problems(metrics_problemas)
        assert len(problems) >= 3


# ── Tests: to_html ────────────────────────────────────────────


class TestToHtml:

    def test_html_valido(self, generator, metrics):
        report = generator.weekly_report(metrics)
        html = generator.to_html(report)
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_html_contiene_titulo(self, generator, metrics):
        report = generator.weekly_report(metrics)
        html = generator.to_html(report)
        assert metrics.period in html

    def test_html_desde_markdown_string(self, generator):
        md = "# Título\n\n## Sección\n\n- Item 1\n- Item 2"
        html = generator.to_html(md)
        assert "<h1>" in html
        assert "<h2>" in html
        assert "<li>" in html

    def test_html_tablas(self, generator):
        md = "| Col1 | Col2 |\n|------|------|\n| A | B |"
        html = generator.to_html(md)
        assert "<table>" in html
        assert "<td>" in html
