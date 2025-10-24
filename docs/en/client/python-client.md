---
title: Python Client
---

# Python Client

FastGRPC includes a lightweight dynamic client that uses reflection—no generated stubs needed.

Basic unary call:

```python
from fastgrpcio.calls import GRPCClient

async with GRPCClient("localhost:50051") as client:
    resp = await client.unary_unary(
        service_name="hello_app.HelloApp",
        method_name="say_hello",
        body={"name": "World"},
        metadata={"authorization": "secret"},  # optional
    )
```

Notes:

- `service_name` is `<package>.<ServiceName>` as compiled (see your `app_package_name` and `app_name`).
- `method_name` is the name you used in `@app.register_as("...")`.
- For streaming, use `unary_stream`, `stream_unary`, and `stream_stream` helpers.

