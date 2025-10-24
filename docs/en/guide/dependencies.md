---
title: Dependencies
---

# Dependencies

FastGRPC integrates with `fast_depends` to provide a simple dependency injection mechanism.

Use standard callables and declare them in your handler signature via keyword arguments. The library injects them at runtime.

```python
import fast_depends

def config() -> dict:
    return {"greeting": "Hello"}

@app.register_as("unary_unary")
async def handler(data: Request, context: GRPCContext, cfg: dict = fast_depends.Depends(config)) -> Response:
    return Response(message=f"{cfg['greeting']}, {data.name}")
```

Notes:

- Dependencies can be sync or async.
- Values are resolved per-call.
- If validation fails on the request body, the framework returns a gRPC error with details.

