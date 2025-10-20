import logging
from typing import Any, AsyncIterator, Awaitable, Callable, Literal

import grpc
from google.protobuf.message import Message

from fastgrpcio.schemas import BaseGRPCSchema

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S", level=logging.INFO)
logger = logging.getLogger(__name__)


class BaseMiddleware:
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
    ) -> Any:
        response = await call_next(request, context)
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
    ) -> AsyncIterator[Message]:
        async for resp in call_next(request, context):
            yield resp

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
    ) -> Any:
        async def wrapped_stream() -> AsyncIterator[Any]:
            async for msg in request:
                yield msg

        response = await call_next(wrapped_stream(), context)
        return response


class LoggingMiddleware(BaseMiddleware):
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
    ) -> Any:
        logger.info(f"[{unary_type}] - {user_func.__name__} - Received request")
        response = await call_next(request, context)
        logger.info(f"[{unary_type}] - {user_func.__name__} - Processed response")
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
    ) -> Any:
        logger.info(f"[{unary_type}] - {user_func.__name__} - Started streaming")
        async for resp in call_next(request, context):
            logger.info(f"[{unary_type}] - {user_func.__name__} - Streamed response chunk")
            yield resp
        logger.info(f"[{unary_type}] - {user_func.__name__} - Completed streaming")

    async def handle_client_stream(
        self,
        request: AsyncIterator[Message],
        context: grpc.aio.ServicerContext,
        call_next: Callable[[AsyncIterator[Any], grpc.aio.ServicerContext], Awaitable[Any]],
        user_func: Callable[..., Any],
        request_model: type[BaseGRPCSchema],
        response_class: type[BaseGRPCSchema],
        handler: Callable[..., Any],
        unary_type: Literal["Unary", "ServerStreaming", "ClientStreaming", "BidiStreaming"],
    ) -> Any:
        async def wrapped_stream() -> AsyncIterator[Any]:
            async for msg in request:
                logger.info(f"[{unary_type}] - {user_func.__name__} - Recieved client message")
                yield msg

        logger.info(f"[{unary_type}] - {user_func.__name__} - Started receiving client stream")
        response = await call_next(wrapped_stream(), context)
        logger.info(f"[{unary_type}] - {user_func.__name__} - Client stream completed")
        return response
