import asyncio
from typing import AsyncIterator

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from fastgrpcio import FastGRPC, FastGRPCRouter
from fastgrpcio.calls import GRPCClient
from fastgrpcio.context import GRPCContext
from fastgrpcio.schemas import BaseGRPCSchema
from fastgrpcio.tracing.middleware import TracingMiddleware


class ResponseSchema(BaseGRPCSchema):
    response: str | None


class RequestSchema(BaseGRPCSchema):
    request: str


app = FastGRPC(app_name="HelloApp", app_package_name="test_app")

resource = Resource.create({"service.name": "HelloApp"})
provider = TracerProvider(resource=resource)
trace.set_tracer_provider(provider)

jaeger_exporter = OTLPSpanExporter(
        endpoint="http://localhost:4317",
        insecure=True,
    )


span_processor = BatchSpanProcessor(jaeger_exporter)
provider.add_span_processor(span_processor)

app.add_middleware(TracingMiddleware(tracer_provider=provider))

@app.register_as("unary_unary")
async def unary_unary(data: RequestSchema, context: GRPCContext) -> ResponseSchema:
    async with GRPCClient("localhost:50052") as client:
        await client.unary_unary(
            service_name="test_app.SecondApp",
            method_name="unary_unary",
            body={"request": "Alexey"},
            metadata=context.meta
        )
    return ResponseSchema(response=f"Hello, {data.request}!")


@app.register_as("client_streaming")
async def client_streaming(data: AsyncIterator[RequestSchema], context: GRPCContext) -> ResponseSchema:
    requests: list[str] = []
    async for item in data:
        requests.append(item.request or "Unknown")

    joined = ", ".join(requests)
    return ResponseSchema(response=joined)


@app.register_as("server_streaming")
async def server_streaming(data: RequestSchema, context: GRPCContext) -> AsyncIterator[ResponseSchema]:
    for i in range(2):
        yield ResponseSchema(response=f"Goodbye count {i + 1}")


@app.register_as("bidi_streaming")
async def bidi_streaming(data: AsyncIterator[RequestSchema], context: GRPCContext) -> AsyncIterator[ResponseSchema]:
    async for item in data:
        yield ResponseSchema(response=f"Echo: {item.request}")


router = FastGRPCRouter(
    app_name="RouterApp",
    app_package_name="router_app",
)


@router.register_as("unary_unary2")
async def unary_unary2(data: RequestSchema, context: GRPCContext) -> ResponseSchema:
    return ResponseSchema(response=f"logic1, {data.request}!")


app.include_router(router)
asyncio.run(app.serve())
