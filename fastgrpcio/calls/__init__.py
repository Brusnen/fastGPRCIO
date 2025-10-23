from __future__ import annotations

import asyncio
import grpc
from typing import Any, AsyncIterator, Type, Callable

from google.protobuf import descriptor_pb2, descriptor_pool
from google.protobuf.message_factory import GetMessageClass
from google.protobuf.json_format import ParseDict, MessageToDict
from grpc_reflection.v1alpha import reflection_pb2, reflection_pb2_grpc

try:
    from opentelemetry import trace
    from opentelemetry.propagate import extract, inject
    from opentelemetry.trace import INVALID_SPAN
    _OTEL_ENABLED = True
except ImportError:
    _OTEL_ENABLED = False

    class DummyTracer:
        def start_as_current_span(self, name: str, context: Any = None):
            class DummySpan:
                def __enter__(self): return None
                def __exit__(self, *a): return False
            return DummySpan()

    class DummyTrace:
        @staticmethod
        def get_tracer(name: str) -> DummyTracer: return DummyTracer()

    class DummyPropagate:
        @staticmethod
        def extract(carrier: dict[str, str]) -> Any: return None
        @staticmethod
        def inject(carrier: dict[str, str], context: Any = None) -> None: return None

    trace = DummyTrace()
    extract = DummyPropagate.extract
    inject = DummyPropagate.inject
    INVALID_SPAN = object()


class GRPCClient:
    def __init__(
        self,
        target: str,
        use_tls: bool = False,
        *,
        max_retries: int = 3,
        retry_backoff: float = 0.5,
        retry_exceptions: tuple[type[BaseException], ...] = (
            grpc.aio.AioRpcError,
            ConnectionError,
            TimeoutError,
        ),
    ) -> None:
        self.target = target
        self.use_tls = use_tls
        self.channel: grpc.aio.Channel | None = None
        self.tracer = trace.get_tracer(__name__)
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.retry_exceptions = retry_exceptions

    async def __aenter__(self) -> GRPCClient:
        creds = grpc.ssl_channel_credentials() if self.use_tls else None
        self.channel = (
            grpc.aio.secure_channel(self.target, creds)
            if creds else grpc.aio.insecure_channel(self.target)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.channel:
            await self.channel.close()

    async def _get_service_descriptor(
        self,
        service_name: str,
    ) -> tuple[Any, descriptor_pool.DescriptorPool]:
        if not self.channel:
            raise RuntimeError("Channel is not initialized")

        stub = reflection_pb2_grpc.ServerReflectionStub(self.channel)

        list_req = reflection_pb2.ServerReflectionRequest(list_services="")
        call = stub.ServerReflectionInfo()
        await call.write(list_req)
        await call.done_writing()
        list_response = await call.read()

        services = [s.name for s in list_response.list_services_response.service]
        if service_name not in services:
            raise ValueError(f"Service '{service_name}' not found. Found: {services}")

        file_req = reflection_pb2.ServerReflectionRequest(file_containing_symbol=service_name)
        call = stub.ServerReflectionInfo()
        await call.write(file_req)
        await call.done_writing()
        file_response = await call.read()

        file_proto = file_response.file_descriptor_response.file_descriptor_proto[0]
        file_desc_proto = descriptor_pb2.FileDescriptorProto.FromString(file_proto)

        pool = descriptor_pool.DescriptorPool()
        pool.Add(file_desc_proto)
        service_desc = pool.FindServiceByName(service_name)

        return service_desc, pool

    def _create_messages(
        self,
        pool: descriptor_pool.DescriptorPool,
        method_desc: Any,
    ) -> tuple[Type, Type]:
        request_cls = GetMessageClass(pool.FindMessageTypeByName(method_desc.input_type.full_name))
        response_cls = GetMessageClass(pool.FindMessageTypeByName(method_desc.output_type.full_name))
        return request_cls, response_cls

    async def _prepare_tracing_context(
        self,
        metadata: dict[str, str] | None = None,
    ) -> tuple[dict[str, str], Any]:
        if not _OTEL_ENABLED:
            return dict(metadata or []), None

        ctx = extract(dict(metadata or []))
        current_span = trace.get_current_span(context=ctx)
        try:
            invalid_ctx = INVALID_SPAN.get_span_context()
        except AttributeError:
            invalid_ctx = None

        if hasattr(current_span, "get_span_context") and current_span.get_span_context() == invalid_ctx:
            metadata_dict: dict[str, str] = {}
            with self.tracer.start_as_current_span("RootTrace") as span:
                ctx = trace.set_span_in_context(span)
                inject(metadata_dict, context=ctx)
            return metadata_dict, ctx

        metadata_dict = dict(metadata or [])
        inject(metadata_dict, context=ctx)
        return metadata_dict, ctx

    async def _retry_call(self, func: Callable[[], Any]) -> Any:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return await func()
            except self.retry_exceptions as exc:
                last_exc = exc
                if attempt == self.max_retries:
                    raise
                delay = self.retry_backoff * (2 ** (attempt - 1))
                await asyncio.sleep(delay)
        if last_exc:
            raise last_exc


    async def unary_unary(
        self,
        service_name: str,
        method_name: str,
        body: dict[str, Any],
        *,
        metadata: list[tuple[str, str]] | None = None,
        timeout: float | None = 10,
    ) -> dict[str, Any]:
        if not self.channel:
            raise RuntimeError("Channel is not initialized")

        service_desc, pool = await self._get_service_descriptor(service_name)
        method_desc = service_desc.FindMethodByName(method_name)
        request_cls, response_cls = self._create_messages(pool, method_desc)
        request_msg = request_cls()
        ParseDict(body, request_msg)

        metadata_dict, ctx = await self._prepare_tracing_context(metadata)
        method_path = f"/{service_name}/{method_name}"

        call = self.channel.unary_unary(
            method_path,
            request_serializer=request_msg.SerializeToString,
            response_deserializer=response_cls.FromString,
        )

        async def do_call() -> dict[str, Any]:
            with self.tracer.start_as_current_span(f"grpc.unary_unary.{method_name}", context=ctx):
                response = await call(request_msg, metadata=metadata_dict.items(), timeout=timeout)
                return MessageToDict(response, preserving_proto_field_name=True)

        return await self._retry_call(do_call)

    async def unary_stream(
        self,
        service_name: str,
        method_name: str,
        body: dict[str, Any],
        *,
        metadata: list[tuple[str, str]] | None = None,
        timeout: float | None = 10,
    ) -> AsyncIterator[dict[str, Any]]:
        if not self.channel:
            raise RuntimeError("Channel is not initialized")

        service_desc, pool = await self._get_service_descriptor(service_name)
        method_desc = service_desc.FindMethodByName(method_name)
        request_cls, response_cls = self._create_messages(pool, method_desc)
        request_msg = request_cls()
        ParseDict(body, request_msg)

        metadata_dict, ctx = await self._prepare_tracing_context(metadata)
        method_path = f"/{service_name}/{method_name}"

        call = self.channel.unary_stream(
            method_path,
            request_serializer=request_msg.SerializeToString,
            response_deserializer=response_cls.FromString,
        )

        async def stream_call() -> AsyncIterator[dict[str, Any]]:
            with self.tracer.start_as_current_span(f"grpc.unary_stream.{method_name}", context=ctx):
                async for response in call(request_msg, metadata=metadata_dict.items(), timeout=timeout):
                    yield MessageToDict(response, preserving_proto_field_name=True)

        for attempt in range(1, self.max_retries + 1):
            try:
                async for item in stream_call():
                    yield item
                break
            except self.retry_exceptions as exc:
                if attempt == self.max_retries:
                    raise
                await asyncio.sleep(self.retry_backoff * (2 ** (attempt - 1)))

    async def stream_unary(
        self,
        service_name: str,
        method_name: str,
        body_stream: AsyncIterator[dict[str, Any]],
        *,
        metadata: list[tuple[str, str]] | None = None,
        timeout: float | None = 10,
    ) -> dict[str, Any]:
        if not self.channel:
            raise RuntimeError("Channel is not initialized")

        service_desc, pool = await self._get_service_descriptor(service_name)
        method_desc = service_desc.FindMethodByName(method_name)
        request_cls, response_cls = self._create_messages(pool, method_desc)

        async def req_iter() -> AsyncIterator[Any]:
            async for item in body_stream:
                msg = request_cls()
                ParseDict(item, msg)
                yield msg

        metadata_dict, ctx = await self._prepare_tracing_context(metadata)
        method_path = f"/{service_name}/{method_name}"

        call = self.channel.stream_unary(
            method_path,
            request_serializer=lambda m: m.SerializeToString(),
            response_deserializer=response_cls.FromString,
        )

        async def do_call() -> dict[str, Any]:
            with self.tracer.start_as_current_span(f"grpc.stream_unary.{method_name}", context=ctx):
                response = await call(req_iter(), metadata=metadata_dict.items(), timeout=timeout)
                return MessageToDict(response, preserving_proto_field_name=True)

        return await self._retry_call(do_call)

    async def stream_stream(
        self,
        service_name: str,
        method_name: str,
        body_stream: AsyncIterator[dict[str, Any]],
        *,
        metadata: list[tuple[str, str]] | None = None,
        timeout: float | None = 10,
    ) -> AsyncIterator[dict[str, Any]]:
        if not self.channel:
            raise RuntimeError("Channel is not initialized")

        service_desc, pool = await self._get_service_descriptor(service_name)
        method_desc = service_desc.FindMethodByName(method_name)
        request_cls, response_cls = self._create_messages(pool, method_desc)

        async def req_iter() -> AsyncIterator[Any]:
            async for item in body_stream:
                msg = request_cls()
                ParseDict(item, msg)
                yield msg

        metadata_dict, ctx = await self._prepare_tracing_context(metadata)
        method_path = f"/{service_name}/{method_name}"

        call = self.channel.stream_stream(
            method_path,
            request_serializer=lambda m: m.SerializeToString(),
            response_deserializer=response_cls.FromString,
        )

        for attempt in range(1, self.max_retries + 1):
            try:
                with self.tracer.start_as_current_span(f"grpc.stream_stream.{method_name}", context=ctx):
                    async for response in call(req_iter(), metadata=metadata_dict.items(), timeout=timeout):
                        yield MessageToDict(response, preserving_proto_field_name=True)
                break
            except self.retry_exceptions:
                if attempt == self.max_retries:
                    raise
                await asyncio.sleep(self.retry_backoff * (2 ** (attempt - 1)))
