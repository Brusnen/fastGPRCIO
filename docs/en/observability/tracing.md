---
title: Tracing
---

# Tracing

FastGRPC can propagate and export traces with OpenTelemetry using the `TracingMiddleware`.

Example with OTLP exporter (compatible with collectors like the OpenTelemetry Collector or Jaeger via OTLP):

```python
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

from fastgrpcio.tracing.middleware import TracingMiddleware

resource = Resource.create({"service.name": "HelloApp"})
provider = TracerProvider(resource=resource)
trace.set_tracer_provider(provider)

exporter = OTLPSpanExporter(endpoint="http://localhost:4317", insecure=True)
provider.add_span_processor(BatchSpanProcessor(exporter))

app.add_middleware(TracingMiddleware(tracer_provider=provider))
```

When calling other FastGRPC services from a handler (e.g., via the Python client), pass `context.meta` as metadata to propagate trace context.

