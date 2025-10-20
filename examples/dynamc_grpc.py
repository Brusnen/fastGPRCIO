import asyncio
from typing import Any

import grpc
from fast_depends import inject
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.message_factory import GetMessageClass
from grpc_reflection.v1alpha import reflection, reflection_pb2_grpc, reflection_pb2
from google.protobuf.json_format import ParseDict, MessageToDict
from opentelemetry import trace
from opentelemetry.propagate import extract
from opentelemetry.trace import INVALID_SPAN


async def grpc_request(
    target: str,
    service_name: str,
    method_name: str,
    body: dict[str, Any],
    *,
    metadata: list[tuple[str, str]] | None = None,
    timeout: float | None = 10,
    use_tls: bool = False,
) -> dict[str, Any]:
    if use_tls:
        creds = grpc.ssl_channel_credentials()
        channel = grpc.aio.secure_channel(target, creds)
    else:
        channel = grpc.aio.insecure_channel(target)

    stub = reflection_pb2_grpc.ServerReflectionStub(channel)

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
    method_desc = service_desc.FindMethodByName(method_name)

    request_cls = GetMessageClass(pool.FindMessageTypeByName(method_desc.input_type.full_name))
    response_cls = GetMessageClass(pool.FindMessageTypeByName(method_desc.output_type.full_name))

    request_msg = request_cls()
    ParseDict(body, request_msg)

    method = f"/{service_name}/{method_name}"

    ctx = extract(dict(metadata))
    current_span = trace.get_current_span(context=ctx)
    tracer = trace.get_tracer(__name__)
    if current_span.get_span_context() == INVALID_SPAN.get_span_context():
        metadata = {}
        with tracer.start_as_current_span("RootTrace") as span:
            ctx = trace.set_span_in_context(span)
            metadata: dict[str, str] = {}
            inject(metadata, context=ctx)

    unary_call = channel.unary_unary(
        method,
        request_serializer=request_msg.SerializeToString,
        response_deserializer=response_cls.FromString,
    )

    with tracer.start_as_current_span(f"request {method_name}", context=ctx):
        response = await unary_call(request_msg, metadata=metadata, timeout=timeout)
    with tracer.start_as_current_span(f"response {method_name}", context=ctx):
        await asyncio.sleep(1)
        result = MessageToDict(response, preserving_proto_field_name=True)
        await channel.close()
        return result
