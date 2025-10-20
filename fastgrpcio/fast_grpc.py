import logging
from collections.abc import Callable
from concurrent import futures
from typing import Any, Generator

import grpc
from grpc_reflection.v1alpha import reflection

from .exceptions import FastGRPCError, FastGRPCMiddlewareError
from .grpc_compiler import GRPCCompiler
from .middlewares import BaseMiddleware, LoggingMiddleware

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S", level=logging.INFO)
logger = logging.getLogger(__name__)


class FastGRPCRouter:
    def __init__(
        self,
        app_name: str = "FastGRPCApp",
        app_package_name: str = "fast_grpc_app",
    ):
        self.app_name = app_name
        self.app_package_name = app_package_name
        self._functions: dict[str, Callable[..., Any]] = {}

    def register_as(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            if name in self._functions.keys():
                raise ValueError(f"Function with name '{name}' is already registered.")
            if func in self._functions.values():
                raise ValueError(f"Function '{func.__name__}' is already registered.")

            self._functions[name] = func
            return func

        return decorator


class FastGRPC:
    def __init__(
        self,
        app_name: str = "FastGRPCApp",
        app_package_name: str = "fast_grpc_app",
        port: int = 50051,
        worker_count: int = 10,
    ):
        self.app_name = app_name
        self.app_package_name = app_package_name
        self.port = port
        self.worker_count = worker_count

        self._functions: dict[str, Callable[..., Any]] = {}
        self._middlewares: list[BaseMiddleware] = [LoggingMiddleware()]
        self._routers: list[FastGRPCRouter] = []

    def register_as(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            if name in self._functions.keys():
                raise ValueError(f"Function with name '{name}' is already registered.")
            if func in self._functions.values():
                raise ValueError(f"Function '{func.__name__}' is already registered.")

            self._functions[name] = func
            return func

        return decorator

    def add_middleware(self, middleware: BaseMiddleware) -> None:
        if issubclass(type(middleware), BaseMiddleware):
            self._middlewares.append(middleware)
            return
        raise FastGRPCMiddlewareError(f"Middleware should be instance of {BaseMiddleware.__name__}")

    def include_router(self, router: FastGRPCRouter) -> None:
        if issubclass(type(router), FastGRPCRouter):
            self._routers.append(router)
            return
        raise FastGRPCError("Router should be instance of FastGRPCRouter")

    def _compile(self, funcs: dict[str, Callable[..., Any]]) -> tuple[dict[str, Callable[..., Any]], str, GRPCCompiler]:
        compiler = GRPCCompiler(
            app_name=self.app_name,
            app_package_name=self.app_package_name,
            middlewares=self._middlewares,
        )
        handlers, service_name = compiler.compile(funcs)
        return handlers, service_name, compiler

    def _compile_routers(self) -> Generator[tuple[dict[str, Callable[..., Any]], str], None, None]:
        for router in self._routers:
            compiler = GRPCCompiler(
                app_name=router.app_name,
                app_package_name=router.app_package_name,
                middlewares=self._middlewares,
            )
            handlers, service_name = compiler.compile(router._functions)
            yield handlers, service_name

    async def serve(self) -> Any:
        logger.info("Starting gRPC server...")
        server = grpc.aio.server(futures.ThreadPoolExecutor(self.worker_count))
        service_names = [
            reflection.SERVICE_NAME,
        ]
        try:
            handlers, service, compiler = self._compile(self._functions)
            generic_handler = grpc.method_handlers_generic_handler(service, handlers)
            service_names.append(service)
            server.add_generic_rpc_handlers((generic_handler,))
        except Exception:
            raise
        try:
            for router_handlers, route_service in self._compile_routers():
                generic_handler = grpc.method_handlers_generic_handler(route_service, router_handlers)
                service_names.append(route_service)
                server.add_generic_rpc_handlers((generic_handler,))
        except Exception:
            raise

        server.add_insecure_port(f"[::]:{self.port}")
        reflection.enable_server_reflection(service_names, server)
        await server.start()
        logger.info(f"Server started at [::]:{self.port}")
        await server.wait_for_termination()
