---
title: Context
---

# Context

Handlers receive a `GRPCContext` providing access to:

- `meta`: merged incoming metadata and trace context
- `abort(code, details, trailing_metadata)`: abort the call with a gRPC status

Example:

```python
from fastgrpcio.context import GRPCContext
import grpc

@app.register_as("needs_auth")
async def needs_auth(data: Request, context: GRPCContext) -> Response:
    if context.meta.get("authorization") != "secret":
        await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing or invalid token")
    return Response(message="ok")
```

