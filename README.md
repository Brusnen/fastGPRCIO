# FastGRPC

Lightweight framework for building gRPC services with a FastAPI-like developer experience.

FastGRPC compiles Python async callables into a generic gRPC service at runtime, supports unary and streaming handlers, dependency injection, and gRPC reflection for easy discovery and testing.

## Features
- Register async Python callables as gRPC RPCs with a decorator.
- Support for unary, client-streaming, server-streaming and bidirectional streaming handlers.
- Simple dependency injection via Depends(...) (similar to FastAPI).
- Automatic compilation of request/response schemas into dynamic gRPC handlers.
- gRPC reflection support for easier testing and tooling integration.

## Quickstart
1. Install dependencies (example using uv and pip):
   ```bash
   pip install fastgrpcio
   ```
   
   ```bash
   uv add fastgrpcio
   ```

2. Define schemas and a context for your RPCs (see `fastGRPC/schemas.py` and `fastGRPC/context.py`).

3. Create an app, register handlers and run the server.:
    - Define schemas:
   ```python
    class ResponseSchema(BaseGRPCSchema):
        response: str | None
    
    class RequestSchema(BaseGRPCSchema):
        request: str
    ```
   - Define the app

     ```python
     from fastgrpcio.fast_grpc import FastGRPC
     app = FastGRPC(app_name="HelloApp", app_package_name="test_app")
     ```

Register handlers using the decorator:

  ```python
  # unary unary handler example
   @app.register_as("unary_unary")
   async def unary_unary(data: RequestSchema, context: GRPCContext) -> ResponseSchema:
       return ResponseSchema(response=f"Hello, {data.request or "Unknown"}!")
   ```
     
```python
   # client streaming handler example
@app.register_as("client-streaming")
async def client_streaming(
    data: AsyncIterator[RequestSchema], context: GRPCContext) -> ResponseSchema:

    requests: list[str] = []
    async for item in data:
        requests.append(item.request or "Unknown")

    joined = ", ".join(requests)
    return ResponseSchema(response=joined)
 ```
     
```python
     # server streaming handler example
    @app.register_as("server_streaming")
    async def server_streaming(data: RequestSchema, context: GRPCContext) -> AsyncIterator[ResponseSchema]:
        for i in range(2):
            yield ResponseSchema(response=f"Goodbye count {i+1}")
 ```

```python
# bidirectional streaming handler example
@app.register_as("bidi_streaming")
async def bidi_streaming(data: AsyncIterator[RequestSchema], context: GRPCContext) -> AsyncIterator[ResponseSchema]:

    async for item in data:
        yield ResponseSchema(response=f"Echo: {item.request}")
```


   - Start the server:

     ```python
     asyncio.run(app.serve())
     ```

## Handler types supported
- Unary: single request -> single response
- Client streaming: async iterator request -> single response
- Server streaming: request -> async iterator responses
- Bidirectional streaming: async iterator request -> async iterator responses

## Dependencies
FastGRPC integrates a simple Depends(...) mechanism (see examples) to inject values into handler signatures. Use synchronous functions or callables that return values needed by handlers.

## Reflection and discovery
gRPC reflection is enabled by default so tools like Evans, grpcurl, and Protobuf-backed clients can discover the compiled service and RPC definitions at runtime.

