---
title: First Steps
---

# First Steps

Let’s build a minimal gRPC service with one unary RPC.

1) Define your request/response schemas using Pydantic models (inherit `BaseGRPCSchema`).

```python
from fastgrpcio.schemas import BaseGRPCSchema

class Request(BaseGRPCSchema):
    name: str

class Response(BaseGRPCSchema):
    message: str | None
```

2) Create an app and register a function using `@app.register_as("<rpc_name>")`.

```python
import asyncio
from fastgrpcio.fast_grpc import FastGRPC
from fastgrpcio.context import GRPCContext

app = FastGRPC(app_name="HelloApp", app_package_name="hello_app")

@app.register_as("say_hello")
async def say_hello(data: Request, context: GRPCContext) -> Response:
    return Response(message=f"Hello, {data.name}!")

asyncio.run(app.serve())
```

3) Run the server. It listens on `0.0.0.0:50051` by default and exposes a compiled gRPC service with reflection enabled.

You can now use `grpcurl` or any gRPC client to discover and call your service. Reflection makes the service discoverable without a `.proto` file.

