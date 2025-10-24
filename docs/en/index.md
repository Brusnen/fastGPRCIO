---
title: FastGRPC
---

# FastGRPC

Build gRPC services with a friendly, FastAPI-like developer experience.

FastGRPC lets you write standard Python async callables annotated with Pydantic models and turns them into a full gRPC service at runtime. It supports unary and all streaming patterns, dependency injection, middlewares, server reflection, routers, and optional OpenTelemetry tracing.

What you get:

- Simple decorator-based RPC registration
- Unary and streaming handlers (client, server, bidirectional)
- Pydantic models as request/response schemas
- Dependency injection via `fast_depends`
- Middlewares (logging included; tracing optional)
- gRPC server reflection enabled by default
- A lightweight dynamic client powered by reflection

Continue with the Tutorial to get a service running in minutes.

Quick links:

- Tutorial — Installation, First Steps, Handlers & Schemas, Streaming
- User Guide — Dependencies, Routers, Middlewares, Context, Errors, Reflection
- Observability — OpenTelemetry tracing
- Client — Call your services from Python dynamically
- Deployment — Run in production
- Examples — Copy-paste ready snippets

