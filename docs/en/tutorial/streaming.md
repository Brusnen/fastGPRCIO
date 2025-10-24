---
title: Streaming
---

# Streaming

FastGRPC supports all gRPC streaming patterns by inspecting function annotations.

- Client streaming: accept `AsyncIterator[RequestModel]`, return a single `ResponseModel`.
- Server streaming: accept a single `RequestModel`, yield `ResponseModel` instances.
- Bidirectional streaming: accept and yield `AsyncIterator`.

Examples:

Client streaming:

```python
from typing import AsyncIterator

@app.register_as("client_streaming")
async def client_streaming(data: AsyncIterator[Request], context: GRPCContext) -> Response:
    values: list[str] = []
    async for item in data:
        values.append(item.name)
    return Response(message=", ".join(values))
```

Server streaming:

```python
@app.register_as("server_streaming")
async def server_streaming(data: Request, context: GRPCContext) -> AsyncIterator[Response]:
    for i in range(3):
        yield Response(message=f"Tick {i}")
```

Bidirectional streaming:

```python
@app.register_as("bidi_streaming")
async def bidi_streaming(data: AsyncIterator[Request], context: GRPCContext) -> AsyncIterator[Response]:
    async for item in data:
        yield Response(message=f"Echo: {item.name}")
```

