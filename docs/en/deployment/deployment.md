---
title: Deployment
---

# Deployment

FastGRPC runs on `grpc.aio.server` and is production-ready behind standard process managers and load balancers.

Checklist:

- Choose a stable port and bind to `0.0.0.0` inside containers.
- Use multiple workers via the thread pool size (`worker_count`) if needed.
- Put a reverse proxy or L4 load balancer in front when scaling horizontally.
- Enable tracing and metrics with OpenTelemetry if observability matters.

Example Dockerfile snippet:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir fastgrpcio
CMD ["python", "-m", "your_package.server"]
```

Health checks

- Consider adding a lightweight unary RPC for readiness/liveness.
- Alternatively, expose a simple HTTP sidecar if your environment requires HTTP health checks.

