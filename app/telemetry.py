"""OpenTelemetry SDK bootstrap for AgentGuard."""

import logging

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.config import settings

logger = logging.getLogger(__name__)

_initialized = False


def init_telemetry(app=None) -> None:
    """Bootstrap the OTel SDK. Idempotent — safe to call multiple times."""
    global _initialized
    if _initialized or not settings.otel_enabled:
        return

    exporter = OTLPSpanExporter(endpoint=settings.otel_endpoint)
    processor = BatchSpanProcessor(exporter)

    provider = trace.get_tracer_provider()
    if hasattr(provider, "add_span_processor"):
        # Langfuse v4 SDK (or another component) already set a TracerProvider at
        # import time. Bolt our OTLP exporter onto it so spans fan-out to both
        # Langfuse and the otel-collector → Jaeger pipeline.
        provider.add_span_processor(processor)
    else:
        resource = Resource.create({SERVICE_NAME: "agentguard"})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

    HTTPXClientInstrumentor().instrument()
    if app is not None:
        FastAPIInstrumentor.instrument_app(app)

    _initialized = True
    logger.info("OTel tracing initialised → %s", settings.otel_endpoint)


def get_otel_trace_id() -> str | None:
    """Return the active OTel trace ID as a 32-char hex string, or None."""
    ctx = trace.get_current_span().get_span_context()
    return format(ctx.trace_id, "032x") if ctx.is_valid else None
