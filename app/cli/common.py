"""Shared helpers used by CLI commands."""

from contextlib import contextmanager

from opentelemetry import trace

from app.core.tracing import get_langfuse_client

_tracer = trace.get_tracer("agentguard.cli")


@contextmanager
def cli_span(name: str, **attrs):
    """Wrap a CLI operation in an OTel span so it appears in Zipkin."""
    with _tracer.start_as_current_span(name) as span:
        for k, v in attrs.items():
            span.set_attribute(k, str(v))
        yield span


def flush() -> None:
    """Flush buffered Langfuse spans before the process exits."""
    get_langfuse_client().flush()
