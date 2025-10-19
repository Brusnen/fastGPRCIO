import asyncio
from typing import AsyncIterator


from fastGRPC.context import GRPCContext
from fastGRPC import FastGRPC
from fastGRPC.schemas import BaseGRPCSchema

class ResponseSchema(BaseGRPCSchema):
    response: str | None

class RequestSchema(BaseGRPCSchema):
    request: str

app = FastGRPC(
    app_name="HelloApp",
    app_package_name="test_app"
)

@app.register_as("unary_unary")
async def unary_unary(data: RequestSchema, context: GRPCContext) -> ResponseSchema:
    return ResponseSchema(response=f"Hello, {data.request}!")


@app.register_as("client_streaming")
async def client_streaming(
    data: AsyncIterator[RequestSchema], context: GRPCContext) -> ResponseSchema:

    requests: list[str] = []
    async for item in data:
        requests.append(item.request or "Unknown")

    joined = ", ".join(requests)
    return ResponseSchema(response=joined)


@app.register_as("server_streaming")
async def server_streaming(data: RequestSchema, context: GRPCContext) -> AsyncIterator[ResponseSchema]:
    for i in range(2):
        yield ResponseSchema(response=f"Goodbye count {i+1}")


@app.register_as("bidi_streaming")
async def bidi_streaming(data: AsyncIterator[RequestSchema], context: GRPCContext) -> AsyncIterator[ResponseSchema]:

    async for item in data:
        yield ResponseSchema(response=f"Echo: {item.request}")

asyncio.run(app.serve())