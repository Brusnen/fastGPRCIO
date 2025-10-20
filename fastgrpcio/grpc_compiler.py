import logging
from typing import Any, AsyncIterator, Callable, get_args, get_origin, get_type_hints

import grpc
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory
from google.protobuf.descriptor_pb2 import ServiceDescriptorProto
from google.protobuf.message_factory import GetMessageClass

from .middlewares import BaseMiddleware
from .mixins import CreateHandlersMixins
from .schemas import BaseGRPCSchema

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S", level=logging.INFO)
logger = logging.getLogger(__name__)


PYTHON_TO_PROTO_TYPE: dict[type[Any], int] = {
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


class GRPCCompiler(CreateHandlersMixins):
    def __init__(
        self,
        app_name: str,
        app_package_name: str,
        middlewares: list[BaseMiddleware],
    ):
        self.file_proto = descriptor_pb2.FileDescriptorProto()
        self.file_proto.name = f"{app_package_name}.proto"
        self.service_name = app_name
        self.file_proto.package = app_package_name
        self._middlewares = middlewares

        self.pool = descriptor_pool.Default()
        self.factory = message_factory.MessageFactory(self.pool)
        self.method_handlers: dict[str, Callable[..., Any]] = {}
        self.generated_messages: set[str] = set()

    def _extract_pydantic_models(
        self, func: Callable[..., Any]
    ) -> tuple[type[BaseGRPCSchema], type[BaseGRPCSchema], bool, bool]:
        hints: dict[str, Any] = get_type_hints(func)

        request_model: type[BaseGRPCSchema] | None = None
        response_model: type[BaseGRPCSchema] | None = None

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
            raise ValueError(f"Function {func.__name__} must have both request and response Pydantic models")

        return request_model, response_model, client_stream, server_stream

    def _create_message(self, model: type[BaseGRPCSchema]) -> None:
        if model.__name__ in self.generated_messages:
            return

        message_proto = self.file_proto.message_type.add()
        message_proto.name = model.__name__
        self.generated_messages.add(model.__name__)

        field_number = 1
        for field_name, field_type, is_repeated in model.iterate_by_model_fields():
            grpc_field = message_proto.field.add()
            grpc_field.name = field_name
            grpc_field.number = field_number
            field_number += 1

            if is_repeated:
                grpc_field.label = PYTHON_TO_LABEL_TYPE["repeated"]
            else:
                grpc_field.label = PYTHON_TO_LABEL_TYPE["optional"]

            try:
                grpc_field.type = PYTHON_TO_PROTO_TYPE[field_type]
            except KeyError as err:
                if isinstance(field_type, type) and issubclass(field_type, BaseGRPCSchema):
                    self._create_message(field_type)

                    grpc_field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
                    grpc_field.type_name = f".{self.file_proto.package}.{field_type.__name__}"
                else:
                    origin = get_origin(field_type)
                    args = get_args(field_type)

                    if origin is list and args:
                        inner_type = args[0]
                        if isinstance(inner_type, type) and issubclass(inner_type, BaseGRPCSchema):
                            self._create_message(inner_type)
                            grpc_field.type = descriptor_pb2.FieldDescriptorProto.TYPE_MESSAGE
                            grpc_field.type_name = f".{self.file_proto.package}.{inner_type.__name__}"
                            grpc_field.label = PYTHON_TO_LABEL_TYPE["repeated"]
                            continue
                        elif inner_type in PYTHON_TO_PROTO_TYPE:
                            grpc_field.type = PYTHON_TO_PROTO_TYPE[inner_type]
                            grpc_field.label = PYTHON_TO_LABEL_TYPE["repeated"]
                            continue

                    raise TypeError(
                        f"Unknown or unsupported field type: {field_name} ({field_type}) in model {model.__name__}"
                    ) from err

    def _create_service(self) -> ServiceDescriptorProto:
        service = self.file_proto.service.add()
        service.name = self.service_name
        return service

    def _add_rpc(
        self,
        service: ServiceDescriptorProto,
        func_name: str,
        request_model: type[BaseGRPCSchema],
        response_model: type[BaseGRPCSchema],
        client_stream: bool,
        server_stream: bool,
    ) -> tuple[str, str]:
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
        user_func: Callable[..., Any],
        request_model: type[BaseGRPCSchema],
        response_class: type[BaseGRPCSchema],
        client_stream: bool = False,
        server_stream: bool = False,
    ) -> Callable[..., Any]:
        if not client_stream and not server_stream:
            return self._make_unary_handler(user_func, request_model, response_class)
        if not client_stream and server_stream:
            return self._make_server_stream_handler(user_func, request_model, response_class)
        if client_stream and not server_stream:
            return self._make_client_stream_handler(user_func, request_model, response_class)
        if client_stream and server_stream:
            return self._make_bidi_stream_handler(user_func, request_model, response_class)

        raise ValueError(f"Failed to determine RPC type for {user_func.__name__}")

    def compile(self, funcs: dict[str, Callable[..., Any]]) -> tuple[dict[str, Callable[..., Any]], str]:
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
                logger.info("Registered gRPC method: %s", func_name)

            self.method_handlers[func_name] = grpc_handler

        full_service_name = f"{self.file_proto.package}.{self.service_name}"

        return self.method_handlers, full_service_name
