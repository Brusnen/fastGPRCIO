---
title: Middlewares
---

# Middlewares

Middlewares let you run logic before/after handlers. FastGRPC ships with a `LoggingMiddleware` by default and supports custom middlewares by subclassing `BaseMiddleware`.

Key hooks:

- `handle_unary(...)` for unary RPCs
- `handle_stream(...)` for server/bidi streaming
- `handle_client_stream(...)` for client streaming

Add a middleware:

```python
from fastgrpcio.middlewares import BaseMiddleware

class MyMiddleware(BaseMiddleware):
    async def handle_unary(self, request, context, call_next, user_func, request_model, response_class, handler, unary_type, **kw):
        # pre
        resp = await call_next(request, context)
        # post
        return resp

app.add_middleware(MyMiddleware())
```

Middlewares run in registration order and wrap the execution chain.

