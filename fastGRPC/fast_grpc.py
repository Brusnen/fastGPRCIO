from concurrent import futures
from typing import Dict, Callable, Any

import grpc
from grpc_reflection.v1alpha import reflection

from .grpc_compiler import GRPCCompiler
import logging

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO
)
logger = logging.getLogger(__name__)



class FastGRPC:

    def __init__(self, app_name: str = "FastGRPCApp",
                 app_package_name: str = "fast_grpc_app",
                 port: int = 50051):
        self.app_name = app_name
        self.app_package_name = app_package_name
        self.port = port

    _functions: Dict[str, Callable[..., Any]] = {}

    @classmethod
    def register_as(cls, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            if name in cls._functions.keys():
                raise ValueError(f"Function with name '{name}' is already registered.")
            if func in cls._functions.values():
                raise ValueError(f"Function '{func.__name__}' is already registered.")

            cls._functions[name] = func
            return func

        return decorator


    def _compile(self, funcs: Dict[str, Callable]):
        compiler = GRPCCompiler(
            app_name=self.app_name,
            app_package_name=self.app_package_name,
        )
        handler, service_name = compiler.compile(funcs)
        return handler, service_name, compiler

    async def serve(self) -> Any:
        logger.info("Starting gRPC server...")
        server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=10))
        SERVICE_NAMES = [
            reflection.SERVICE_NAME,
        ]
        try:
            handlers, service, compiler = self._compile(self._functions)
            generic_handler = grpc.method_handlers_generic_handler(service, handlers)
            SERVICE_NAMES.append(service)
        except Exception:
            raise
        server.add_generic_rpc_handlers((generic_handler,))
        server.add_insecure_port(f'[::]:{self.port}')
        reflection.enable_server_reflection(SERVICE_NAMES, server)
        await server.start()
        logger.info(f"Server started at [::]:{self.port}")
        await server.wait_for_termination()


