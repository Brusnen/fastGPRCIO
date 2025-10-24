---
title: Handlers & Schemas
---

# Handlers & Schemas

FastGRPC compiles your Python callables into gRPC RPCs by inspecting type annotations.

- Requests and responses must be Pydantic models inheriting `BaseGRPCSchema`.
- Function parameters and return types determine the RPC shape.

Example unary handler:

```python
from fastgrpcio.schemas import BaseGRPCSchema
from fastgrpcio.context import GRPCContext

class Request(BaseGRPCSchema):
    name: str

class Response(BaseGRPCSchema):
    message: str | None

@app.register_as("unary_unary")
async def unary_unary(data: Request, context: GRPCContext) -> Response:
    return Response(message=f"Hello, {data.name}")
```

Nested models and lists are supported:

```python
class Item(BaseGRPCSchema):
    id: int
    tags: list[str] | None = None

class ComplexRequest(BaseGRPCSchema):
    items: list[Item]

class ComplexResponse(BaseGRPCSchema):
    count: int
```

If a type is unsupported by Protobuf mapping, the compiler raises a clear error during startup.

