import asyncio
from typing import Callable, Any, Awaitable, Literal, AsyncIterator

import grpc
from google.protobuf.message import Message
from opentelemetry import trace
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import INVALID_SPAN

from fastgrpcio.context import ContextWrapper
from fastgrpcio.middlewares import BaseMiddleware
from fastgrpcio.schemas import BaseGRPCSchema


class TracingMiddleware(BaseMiddleware):

    def __init__(self, tracer_provider: TracerProvider) -> None:
        self.tracer_provider = tracer_provider
        GrpcInstrumentorServer().instrument()

    async def handle_unary(
        self,
        request: Message,
        context: grpc.aio.ServicerContext,
        call_next: Callable[[Any, grpc.aio.ServicerContext], Awaitable[Any]],
        user_func: Callable[..., Any],
        request_model: type[BaseGRPCSchema],
        response_class: type[BaseGRPCSchema],
        handler: Callable[..., Any],
        unary_type: Literal["Unary", "ServerStreaming", "ClientStreaming", "BidiStreaming"],
        app_name: str = "",
        app_package_name: str = "",
        func_name: str = ""
    ) -> Any:
        carrier = dict(context.invocation_metadata())
        ctx = extract(carrier)
        tracer = self.tracer_provider.get_tracer(__name__)
        current_span = trace.get_current_span(context=ctx)
        if current_span.get_span_context() == INVALID_SPAN.get_span_context():
            with tracer.start_as_current_span("RootTrace") as span:
                ctx = trace.set_span_in_context(span)
                metadata: dict[str, str] = {}

                inject(metadata, context=ctx)
                with tracer.start_as_current_span(f"{app_package_name}/{app_name}/{func_name}", context=ctx) as span:
                    span.set_attribute("rpc.method", func_name)
                    span.set_attribute("rpc.service", app_name)
                    span.set_attribute("rpc.package", app_package_name)
                    wrapped_context = ContextWrapper(context, trace_ctx=ctx)
                    await asyncio.sleep(1)

                    response = await call_next(request, wrapped_context)
                    return response
        else:
            with tracer.start_as_current_span(f"{app_package_name}/{app_name}/{func_name}", context=ctx) as span:
                span.set_attribute("rpc.method", func_name)
                span.set_attribute("rpc.service", app_name)
                span.set_attribute("rpc.package", app_package_name)
                wrapped_context = ContextWrapper(context, trace_ctx=ctx)
                response = await call_next(request, wrapped_context)
                return response

    async def handle_client_stream(
        self,
        request: AsyncIterator[Message],
        context: grpc.aio.ServicerContext,
        call_next: Callable[[Any, grpc.aio.ServicerContext], Awaitable[Any]],
        user_func: Callable[..., Any],
        request_model: type[BaseGRPCSchema],
        response_class: type[BaseGRPCSchema],
        handler: Callable[..., Any],
        unary_type: Literal["Unary", "ServerStreaming", "ClientStreaming", "BidiStreaming"],
        app_name: str = "",
        app_package_name: str = "",
        func_name: str = ""
    ) -> Any:
        ctx = extract(dict(context.invocation_metadata()))
        tracer = self.tracer_provider.get_tracer(__name__)
        with tracer.start_as_current_span(f"{app_package_name}/{app_name}/{func_name}", context=ctx) as span:
            span.set_attribute("rpc.method", func_name)
            span.set_attribute("rpc.service", app_name)
            span.set_attribute("rpc.package", app_package_name)
            async def wrapped_stream() -> AsyncIterator[Any]:
                async for msg in request:
                    yield msg

            response = await call_next(wrapped_stream(), context)
            return response

    async def handle_stream(
        self,
        request: Message,
        context: grpc.aio.ServicerContext,
        call_next: Callable[..., Any],
        user_func: Callable[..., Any],
        request_model: type[BaseGRPCSchema],
        response_class: type[BaseGRPCSchema],
        handler: Callable[..., Any],
        unary_type: Literal["Unary", "ServerStreaming", "ClientStreaming", "BidiStreaming"],
        app_name: str = "",
        app_package_name: str = "",
        func_name: str = ""
    ) -> AsyncIterator[Message]:
        ctx = extract(dict(context.invocation_metadata()))
        tracer = self.tracer_provider.get_tracer(__name__)
        with tracer.start_as_current_span(f"{app_package_name}/{app_name}/{func_name}", context=ctx) as span:
            span.set_attribute("rpc.method", func_name)
            span.set_attribute("rpc.service", app_name)
            span.set_attribute("rpc.package", app_package_name)

            async for resp in call_next(request, context):
                yield resp
