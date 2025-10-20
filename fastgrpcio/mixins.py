import asyncio
import logging
from typing import Any, AsyncIterator, Callable, Literal

import fast_depends
import grpc
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message
from grpc._cython.cygrpc import _ServicerContext
from pydantic import ValidationError

from fastgrpcio._utils import pydantic_error_to_grpc
from fastgrpcio.context import GRPCContext
from fastgrpcio.middlewares import BaseMiddleware
from fastgrpcio.schemas import BaseGRPCSchema

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S", level=logging.INFO)
logger = logging.getLogger(__name__)


class CreateHandlersMixins:
    _middlewares: list[BaseMiddleware]

    def _apply_middlewares(
        self,
        handler: Callable[..., Any],
        user_func: Callable[..., Any],
        request_model: type[BaseGRPCSchema],
        response_class: type[BaseGRPCSchema],
        unary_type: Literal["Unary", "ServerStreaming", "ClientStreaming", "BidiStreaming"],
    ) -> Any:
        if unary_type in ("Unary"):

            async def _apply_unary(request: Any, context: grpc.aio.ServicerContext) -> Any:
                async def call_next(req: Any, ctx: grpc.aio.ServicerContext) -> Any:
                    return await handler(req, ctx)

                for mw in reversed(self._middlewares):
                    prev_next = call_next

                    async def wrapper(
                        req: Any,
                        ctx: grpc.aio.ServicerContext,
                        mw: BaseMiddleware = mw,
                        nxt: Callable[..., Any] = prev_next,
                    ) -> Any:
                        return await mw.handle_unary(
                            request=req,
                            context=ctx,
                            call_next=nxt,
                            user_func=user_func,
                            request_model=request_model,
                            response_class=response_class,
                            handler=handler,
                            unary_type=unary_type,
                        )

                    call_next = wrapper

                return await call_next(request, context)

            return _apply_unary

        elif unary_type in ("ServerStreaming", "BidiStreaming"):

            async def _apply_server_stream(request: Any, context: grpc.aio.ServicerContext) -> AsyncIterator[Any]:
                async def call_next(req: Any, ctx: grpc.aio.ServicerContext) -> AsyncIterator[Any]:
                    async for resp in handler(req, ctx):
                        yield resp

                for mw in reversed(self._middlewares):
                    prev_next = call_next

                    async def wrapper(
                        req: Any,
                        ctx: grpc.aio.ServicerContext,
                        mw: BaseMiddleware = mw,
                        nxt: Callable[..., Any] = prev_next,
                    ) -> AsyncIterator[Any]:
                        async for resp in mw.handle_stream(
                            request=req,
                            context=ctx,
                            call_next=nxt,
                            user_func=user_func,
                            request_model=request_model,
                            response_class=response_class,
                            handler=handler,
                            unary_type=unary_type,
                        ):
                            yield resp

                    call_next = wrapper

                async for resp in call_next(request, context):
                    yield resp

            return _apply_server_stream

        elif unary_type in ("ClientStreaming"):

            async def _apply_client_stream(request: AsyncIterator[Any], context: grpc.aio.ServicerContext) -> Any:
                async def call_next(req_stream: AsyncIterator[Any], ctx: grpc.aio.ServicerContext) -> Any:
                    return await handler(req_stream, ctx)

                for mw in reversed(self._middlewares):
                    prev_next = call_next

                    async def wrapper(
                        req_stream: AsyncIterator[Any],
                        ctx: grpc.aio.ServicerContext,
                        mw: BaseMiddleware = mw,
                        nxt: Callable[..., Any] = prev_next,
                    ) -> Any:
                        return await mw.handle_client_stream(
                            request=req_stream,
                            context=ctx,
                            call_next=nxt,
                            user_func=user_func,
                            request_model=request_model,
                            response_class=response_class,
                            handler=handler,
                            unary_type=unary_type,
                        )

                    call_next = wrapper

                return await call_next(request, context)

            return _apply_client_stream

    def _make_unary_handler(
        self,
        user_func: Callable[..., Any],
        request_model: type[BaseGRPCSchema],
        response_class: type[BaseGRPCSchema],
    ) -> Callable[..., Any]:
        async def handler(request_proto: Message, context: _ServicerContext) -> Any:
            request_dict: dict[str, Any] = MessageToDict(request_proto)
            try:
                pydantic_request = request_model.model_validate(request_dict)
            except ValidationError as e:
                grpc_status_obj = pydantic_error_to_grpc(e)
                await context.abort_with_status(grpc_status_obj)
                return

            injected = fast_depends.inject(user_func)

            grpc_context = GRPCContext(context)
            result = (
                await injected(pydantic_request, context=grpc_context)
                if asyncio.iscoroutinefunction(injected)
                else injected(pydantic_request, context=grpc_context)
            )

            if isinstance(result, response_class):
                return result

            return response_class(**result.model_dump())

        handler = self._apply_middlewares(handler, user_func, request_model, response_class, unary_type="Unary")
        return handler

    def _make_server_stream_handler(
        self,
        user_func: Callable[..., Any],
        request_model: type[BaseGRPCSchema],
        response_class: type[BaseGRPCSchema],
    ) -> Callable[..., Any]:
        async def handler(request_proto: Message, context: _ServicerContext) -> AsyncIterator[Any]:
            request_dict: dict[str, Any] = MessageToDict(request_proto)
            try:
                pydantic_request = request_model.model_validate(request_dict)
            except ValidationError as e:
                grpc_status_obj = pydantic_error_to_grpc(e)
                await context.abort_with_status(grpc_status_obj)
                return

            injected = fast_depends.inject(user_func)
            grpc_context = GRPCContext(context)
            result = injected(pydantic_request, context=grpc_context)
            if asyncio.iscoroutine(result):
                result = await result

            async for item in result:
                yield response_class(**item.model_dump())

        handler = self._apply_middlewares(
            handler, user_func, request_model, response_class, unary_type="ServerStreaming"
        )
        return handler

    def _make_client_stream_handler(
        self,
        user_func: Callable[..., Any],
        request_model: type[BaseGRPCSchema],
        response_class: type[BaseGRPCSchema],
    ) -> Callable[..., Any]:
        async def handler(request_iterator: AsyncIterator[Message], context: _ServicerContext) -> Any:
            async def pydantic_request_gen() -> AsyncIterator[Any]:
                async for msg in request_iterator:
                    msg_dict: dict[str, Any] = MessageToDict(msg)
                    try:
                        yield request_model.model_validate(msg_dict)
                    except ValidationError as e:
                        grpc_status_obj = pydantic_error_to_grpc(e)
                        await context.abort_with_status(grpc_status_obj)
                        return

            injected = fast_depends.inject(user_func)
            grpc_context = GRPCContext(context)
            result = (
                await injected(pydantic_request_gen(), context=grpc_context)
                if asyncio.iscoroutinefunction(user_func)
                else injected(pydantic_request_gen(), context=grpc_context)
            )

            if isinstance(result, response_class):
                return result
            return response_class(**result.model_dump())

        handler = self._apply_middlewares(
            handler, user_func, request_model, response_class, unary_type="ClientStreaming"
        )
        return handler

    def _make_bidi_stream_handler(
        self,
        user_func: Callable[..., Any],
        request_model: type[BaseGRPCSchema],
        response_class: type[BaseGRPCSchema],
    ) -> Callable[..., Any]:
        async def handler(request_iterator: AsyncIterator[Message], context: _ServicerContext) -> AsyncIterator[Any]:
            async def pydantic_request_gen() -> AsyncIterator[Any]:
                async for msg in request_iterator:
                    msg_dict: dict[str, Any] = MessageToDict(msg)
                    try:
                        yield request_model.model_validate(msg_dict)
                    except ValidationError as e:
                        grpc_status_obj = pydantic_error_to_grpc(e)
                        await context.abort_with_status(grpc_status_obj)
                        return

            injected = fast_depends.inject(user_func)
            grpc_context = GRPCContext(context)

            result = injected(pydantic_request_gen(), context=grpc_context)
            if asyncio.iscoroutine(result):
                result = await result

            async for resp in result:
                yield response_class(**resp.model_dump())

        handler = self._apply_middlewares(handler, user_func, request_model, response_class, unary_type="BidiStreaming")
        return handler
