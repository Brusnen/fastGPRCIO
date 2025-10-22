from __future__ import annotations

from typing import Any, AsyncIterator, Awaitable, Callable, Literal
import grpc
from google.protobuf.message import Message
from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import INVALID_SPAN, Span

from fastgrpcio.context import ContextWrapper
from fastgrpcio.middlewares import BaseMiddleware
from fastgrpcio.schemas import BaseGRPCSchema


class TracingMiddleware(BaseMiddleware):

    def __init__(self, tracer_provider: TracerProvider) -> None:
        self.tracer_provider = tracer_provider

    def _start_root_if_needed(self, ctx: trace.Context, tracer: trace.Tracer) -> tuple[trace.Context, dict[str, str]]:
        current_span: Span = trace.get_current_span(context=ctx)
        metadata: dict[str, str] = {}

        if current_span.get_span_context() == INVALID_SPAN.get_span_context():
            with tracer.start_as_current_span("RootTrace") as root_span:
                root_ctx = trace.set_span_in_context(root_span)
                inject(metadata, context=root_ctx)
                return root_ctx, metadata
        return ctx, metadata

    @staticmethod
    def _set_rpc_attributes(
        span: Span,
        func_name: str,
        app_name: str,
        app_package_name: str,
    ) -> None:
        span.set_attribute("rpc.method", func_name)
        span.set_attribute("rpc.service", app_name)
        span.set_attribute("rpc.package", app_package_name)

    async def handle_unary(
        self,
        request: Message,
        context: ContextWrapper,
        call_next: Callable[[Any, ContextWrapper], Awaitable[Any]],
        user_func: Callable[..., Any],
        request_model: type[BaseGRPCSchema],
        response_class: type[BaseGRPCSchema],
        handler: Callable[..., Any],
        unary_type: Literal["Unary", "ServerStreaming", "ClientStreaming", "BidiStreaming"],
        app_name: str = "",
        app_package_name: str = "",
        func_name: str = "",
    ) -> Any:
        carrier: dict[str, str] = dict(context._context.invocation_metadata())
        ctx = extract(carrier)
        tracer = self.tracer_provider.get_tracer(__name__)
        ctx, _ = self._start_root_if_needed(ctx, tracer)

        with tracer.start_as_current_span(f"{app_package_name}/{app_name}/{func_name}", context=ctx) as span:
            self._set_rpc_attributes(span, func_name, app_name, app_package_name)
            inject(context._trace_ctx, context=trace.set_span_in_context(span))
            return await call_next(request, context)

    async def handle_client_stream(
        self,
        request: AsyncIterator[Message],
        context: ContextWrapper,
        call_next: Callable[[AsyncIterator[Any], ContextWrapper], Awaitable[Any]],
        user_func: Callable[..., Any],
        request_model: type[BaseGRPCSchema],
        response_class: type[BaseGRPCSchema],
        handler: Callable[..., Any],
        unary_type: Literal["Unary", "ServerStreaming", "ClientStreaming", "BidiStreaming"],
        app_name: str = "",
        app_package_name: str = "",
        func_name: str = "",
    ) -> Any:
        carrier = dict(context._context.invocation_metadata())
        ctx = extract(carrier)
        tracer = self.tracer_provider.get_tracer(__name__)
        ctx, _ = self._start_root_if_needed(ctx, tracer)

        with tracer.start_as_current_span(f"{app_package_name}/{app_name}/{func_name}", context=ctx) as span:
            self._set_rpc_attributes(span, func_name, app_name, app_package_name)
            inject(context._trace_ctx, context=trace.set_span_in_context(span))

            async def wrapped_stream() -> AsyncIterator[Any]:
                async for msg in request:
                    yield msg

            return await call_next(wrapped_stream(), context)

    async def handle_stream(
        self,
        request: Message,
        context: ContextWrapper,
        call_next: Callable[[Any, ContextWrapper], AsyncIterator[Message]],
        user_func: Callable[..., Any],
        request_model: type[BaseGRPCSchema],
        response_class: type[BaseGRPCSchema],
        handler: Callable[..., Any],
        unary_type: Literal["Unary", "ServerStreaming", "ClientStreaming", "BidiStreaming"],
        app_name: str = "",
        app_package_name: str = "",
        func_name: str = "",
    ) -> AsyncIterator[Message]:
        carrier = dict(context._context.invocation_metadata())
        ctx = extract(carrier)
        tracer = self.tracer_provider.get_tracer(__name__)
        ctx, _ = self._start_root_if_needed(ctx, tracer)

        with tracer.start_as_current_span(f"{app_package_name}/{app_name}/{func_name}", context=ctx) as span:
            self._set_rpc_attributes(span, func_name, app_name, app_package_name)
            inject(context._trace_ctx, context=trace.set_span_in_context(span))

            async for response in call_next(request, context):
                yield response
