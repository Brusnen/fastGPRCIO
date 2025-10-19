import asyncio
from typing import Dict, Callable, Type, Tuple, Any, get_origin, AsyncIterator, get_args
from typing import get_type_hints

import grpc
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.json_format import MessageToDict
from google.protobuf.message_factory import GetMessageClass
import logging
import fast_depends
from grpc._cython.cygrpc import _ServicerContext

from .context import GRPCContext
from .schemas import BaseGRPCSchema


logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


PYTHON_TO_PROTO_TYPE: dict[Type[Any], int] = {
    int: descriptor_pb2.FieldDescriptorProto.TYPE_INT64,
    float: descriptor_pb2.FieldDescriptorProto.TYPE_DOUBLE,
    bool: descriptor_pb2.FieldDescriptorProto.TYPE_BOOL,
    str: descriptor_pb2.FieldDescriptorProto.TYPE_STRING,
    bytes: descriptor_pb2.FieldDescriptorProto.TYPE_BYTES,
}

PYTHON_TO_LABEL_TYPE: dict[str, int] = {
    "optional": descriptor_pb2.FieldDescriptorProto.LABEL_OPTIONAL,
    "repeated": descriptor_pb2.FieldDescriptorProto.LABEL_REPEATED,
    "default": descriptor_pb2.FieldDescriptorProto.LABEL_REQUIRED,
}


class GRPCCompiler:

    def __init__(self, app_name: str, app_package_name: str):
        self.file_proto.name = f"{app_package_name}.proto"
        self.service_name = app_name
        self.file_proto.package = app_package_name

    file_proto = descriptor_pb2.FileDescriptorProto()
    pool = descriptor_pool.Default()
    factory = message_factory.MessageFactory(pool)
    method_handlers = {}
    generated_messages: set[str] = set()

    def _extract_pydantic_models(
        self, func: Callable[..., Any]
    ) -> Tuple[Type[BaseGRPCSchema], Type[BaseGRPCSchema], bool, bool]:
        hints: Dict[str, Any] = get_type_hints(func)

        request_model: Type[BaseGRPCSchema] | None = None
        response_model: Type[BaseGRPCSchema] | None = None

        client_stream = False
        server_stream = False

        for key, val in hints.items():
            origin = get_origin(val)

            if key == "return":
                if origin is get_origin(AsyncIterator):
                    inner = get_args(val)[0]
                    if isinstance(inner, type) and issubclass(inner, BaseGRPCSchema):
                        response_model = inner
                        server_stream = True
                        continue
                elif isinstance(val, type) and issubclass(val, BaseGRPCSchema):
                    response_model = val
                    continue
                raise ValueError(f"Function {func.__name__}: invalid return type annotation")

            if origin is get_origin(AsyncIterator):
                inner = get_args(val)[0]
                if isinstance(inner, type) and issubclass(inner, BaseGRPCSchema):
                    request_model = inner
                    client_stream = True
                    continue
            elif isinstance(val, type) and issubclass(val, BaseGRPCSchema):
                request_model = val
                continue

        if not request_model or not response_model:
            raise ValueError(
                f"Function {func.__name__} must have both request and response Pydantic models"
            )

        return request_model, response_model, client_stream, server_stream

    def _create_message(self, request_model: Type[BaseGRPCSchema]):
        if request_model.__name__ in self.generated_messages:
            return
        message_request = self.file_proto.message_type.add()
        message_request.name = request_model.__name__
        self.generated_messages.add(request_model.__name__)

        field_number = 1
        for field_name, field_type, optional, is_repeated in request_model.iterate_by_model_fields():
            grpc_field = message_request.field.add()
            grpc_field.name = field_name
            grpc_field.number = field_number
            field_number += 1

            if optional:
                label = PYTHON_TO_LABEL_TYPE["optional"]
            elif is_repeated:
                label = PYTHON_TO_LABEL_TYPE["repeated"]
            else:
                label = PYTHON_TO_LABEL_TYPE["default"]
            grpc_field.label = label

            try:
                grpc_field.type = PYTHON_TO_PROTO_TYPE[field_type]
            except KeyError:
                if isinstance(field_type, type) and issubclass(field_type, BaseGRPCSchema):
                    nested_message = self.file_proto.message_type.add()
                    nested_message.name = field_type.__name__

                    nested_field_number = 1
                    for sub_field_name, sub_field_type, sub_optional, sub_repeated in field_type.iterate_by_model_fields():
                        sub_field = nested_message.field.add()
                        sub_field.name = sub_field_name
                        sub_field.number = nested_field_number
                        nested_field_number += 1

                        if sub_optional:
                            sub_label = PYTHON_TO_LABEL_TYPE["optional"]
                        elif is_repeated is list:
                            sub_label = PYTHON_TO_LABEL_TYPE["repeated"]
                        else:
                            sub_label = PYTHON_TO_LABEL_TYPE["default"]
                        sub_field.label = sub_label

                        try:
                            sub_field.type = PYTHON_TO_PROTO_TYPE[sub_field_type]
                        except KeyError:
                            raise Exception(
                                f"Unknown nested field type: {sub_field_name} ({sub_field_type})"
                            )

                    grpc_field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
                    grpc_field.type_name = f".{self.file_proto.package}.{field_type.__name__}"
                else:
                    raise Exception("Unknown field type:", field_name, field_type)

    def _create_service(self):
        service = self.file_proto.service.add()
        service.name = self.service_name

        return service

    def _add_rpc(
        self,
        service,
        func_name: str,
        request_model: Type[BaseGRPCSchema],
        response_model: Type[BaseGRPCSchema],
        client_stream: bool,
        server_stream: bool,
    ):
        rpc = service.method.add()
        rpc.name = func_name
        rpc.input_type = f"{self.file_proto.package}.{request_model.__name__}"
        rpc.output_type = f"{self.file_proto.package}.{response_model.__name__}"
        if client_stream:
            rpc.client_streaming = True
        if server_stream:
            rpc.server_streaming = True
        return rpc.input_type, rpc.output_type

    def _make_handler(
        self,
        user_func: Callable,
        request_model: type[BaseGRPCSchema],
        response_class: type[BaseGRPCSchema],
        client_stream: bool = False,
        server_stream: bool = False,
    ) -> Callable[..., Any]:

        if not client_stream and not server_stream:
            async def handler(request_proto: Any, context: _ServicerContext) -> Any:
                logger.info("[Unary] %s - Received request", user_func.__name__)

                request_dict: dict[str, Any] = MessageToDict(request_proto)
                pydantic_request = request_model.model_validate(request_dict)
                injected = fast_depends.inject(user_func)

                grpc_context = GRPCContext(context)
                result = await injected(pydantic_request, context=grpc_context) \
                    if asyncio.iscoroutinefunction(injected) \
                    else injected(pydantic_request, context=grpc_context)

                if isinstance(result, response_class):
                    return result

                logger.info("[Unary] %s - Processed response", user_func.__name__)
                return response_class(**result.model_dump())

            return handler

        if not client_stream and server_stream:
            async def handler(request_proto: Any, context: _ServicerContext) -> AsyncIterator[Any]:
                logger.info("[Server streaming] %s - Received request", user_func.__name__)

                request_dict: dict[str, Any] = MessageToDict(request_proto)
                pydantic_request = request_model.model_validate(request_dict)
                injected = fast_depends.inject(user_func)
                grpc_context = GRPCContext(context)
                result = injected(pydantic_request, context=grpc_context)
                if asyncio.iscoroutine(result):
                    result = await result

                async for item in result:
                    yield response_class(**item.model_dump())
                logger.info("[Server streaming] %s - Processed response", user_func.__name__)

            return handler

        if client_stream and not server_stream:
            async def handler(request_iterator: AsyncIterator[Any], context: _ServicerContext) -> Any:
                logger.info("[Client streaming] %s - Received request", user_func.__name__)

                async def pydantic_request_gen() -> AsyncIterator[Any]:
                    async for msg in request_iterator:
                        msg_dict: dict[str, Any] = MessageToDict(msg)
                        yield request_model.model_validate(msg_dict)
                injected = fast_depends.inject(user_func)
                grpc_context = GRPCContext(context)
                result = await injected(pydantic_request_gen(), context=grpc_context) \
                    if asyncio.iscoroutinefunction(user_func) \
                    else injected(pydantic_request_gen(), context=grpc_context)

                if isinstance(result, response_class):
                    return result
                logger.info(f"[Client streaming] %s - Processed response", user_func.__name__)
                return response_class(**result.model_dump())

            return handler

        if client_stream and server_stream:
            async def handler(request_iterator: AsyncIterator[Any], context: _ServicerContext) -> AsyncIterator[Any]:
                logger.info(f"[Bidi streaming] %s - Received request", user_func.__name__)

                async def pydantic_request_gen() -> AsyncIterator[Any]:
                    async for msg in request_iterator:
                        msg_dict: dict[str, Any] = MessageToDict(msg)
                        yield request_model.model_validate(msg_dict)
                injected = fast_depends.inject(user_func)
                grpc_context = GRPCContext(context)

                result = injected(pydantic_request_gen(), context=grpc_context)
                if asyncio.iscoroutine(result):
                    result = await result

                async for resp in result:
                    yield response_class(**resp.model_dump())
                logger.info(f"[Bidi streaming] %s - Processed response", user_func.__name__)

            return handler

        raise ValueError(f"Failed to determine RPC type for {user_func.__name__}")

    def compile(self, funcs: Dict[str, Callable]):
        service = self._create_service()

        for func_name, func in funcs.items():
            request_model, response_model, client_stream, server_stream = self._extract_pydantic_models(func)
            self._create_message(request_model)
            self._create_message(response_model)
            self._add_rpc(service, func_name, request_model, response_model, client_stream, server_stream)

        self.pool.Add(self.file_proto)

        for func_name, func in funcs.items():
            request_model, response_model, client_stream, server_stream = self._extract_pydantic_models(func)
            request_message = f"{self.file_proto.package}.{request_model.__name__}"
            response_message = f"{self.file_proto.package}.{response_model.__name__}"

            request_class = GetMessageClass(self.pool.FindMessageTypeByName(request_message))
            response_class = GetMessageClass(self.pool.FindMessageTypeByName(response_message))

            handler = self._make_handler(func, request_model, response_class, client_stream, server_stream)

            if client_stream and server_stream:
                grpc_handler = grpc.stream_stream_rpc_method_handler(
                    handler,
                    request_deserializer=request_class.FromString,
                    response_serializer=response_class.SerializeToString,
                )
                logger.info("Registered gRPC bidirectional streaming method: %s", func_name)
            elif client_stream:
                grpc_handler = grpc.stream_unary_rpc_method_handler(
                    handler,
                    request_deserializer=request_class.FromString,
                    response_serializer=response_class.SerializeToString,
                )
                logger.info("Registered gRPC client streaming method: %s", func_name)
            elif server_stream:
                grpc_handler = grpc.unary_stream_rpc_method_handler(
                    handler,
                    request_deserializer=request_class.FromString,
                    response_serializer=response_class.SerializeToString,
                )
                logger.info("Registered gRPC server streaming method: %s", func_name)
            else:
                grpc_handler = grpc.unary_unary_rpc_method_handler(
                    handler,
                    request_deserializer=request_class.FromString,
                    response_serializer=response_class.SerializeToString,
                )
                logger.info("Registered gRPC method: %s",func_name)

            self.method_handlers[func_name] = grpc_handler

        full_service_name = f"{self.file_proto.package}.{self.service_name}"

        return self.method_handlers, full_service_name
