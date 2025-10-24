---
title: Error Handling
---

# Error Handling

Validation errors

- Request messages are converted to Pydantic models. If validation fails, FastGRPC converts the error to a gRPC status and aborts the call with structured details.

Manual errors

- Use `context.abort(StatusCode, details)` to end a call with a specific status.

Examples:

```python
from pydantic import BaseModel, Field
import grpc

class Request(BaseGRPCSchema):
    limit: int = Field(ge=1, le=100)

@app.register_as("bounded")
async def bounded(data: Request, context: GRPCContext) -> Response:
    return Response(message=f"limit={data.limit}")

@app.register_as("forbidden")
async def forbidden(_: Request, context: GRPCContext) -> Response:
    await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Not allowed")
```

