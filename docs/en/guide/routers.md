---
title: Routers
---

# Routers

Group related RPCs with `FastGRPCRouter` and include them into the main app. Each router compiles into its own gRPC service with its own `app_name` and `app_package_name`.

```python
from fastgrpcio.fast_grpc import FastGRPCRouter

router = FastGRPCRouter(app_name="RouterApp", app_package_name="router_app")

@router.register_as("unary_unary2")
async def logic(data: Request, context: GRPCContext) -> Response:
    return Response(message=f"Router logic for {data.name}")

app.include_router(router)
```

Result: your server exposes multiple compiled services (one for the main app, one per router). Reflection lists them all.

