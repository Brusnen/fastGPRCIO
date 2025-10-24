---
title: Examples
---

# Examples

Two end-to-end examples are provided in the repository under `examples/`.

Example 1 — end-to-end with tracing and a router (`examples/example.py`):

Highlights:

- Registers unary and streaming RPCs
- Configures OpenTelemetry tracer and OTLP exporter
- Uses the dynamic Python client from inside a handler
- Adds a separate router that compiles as another service

Example 2 — a second service (`examples/example2.py`):

- Runs on a different port
- Provides RPCs that can be called from the first service

Tip: run both to test inter-service calls and trace propagation. When calling from a handler, pass `context.meta` to forward incoming metadata and trace context to downstream services.

