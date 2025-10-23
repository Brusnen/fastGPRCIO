from typing import Annotated

import grpc
from grpc._cython.cygrpc import _ServicerContext
from grpc.aio._typing import MetadataType
from pydantic import SkipValidation


class ContextWrapper:
    def __init__(self, context: _ServicerContext, trace_ctx: dict[str, str] | None = None) -> None:
        if trace_ctx is None:
            trace_ctx = {}
        self._context = context
        self._trace_ctx = trace_ctx

    def __getattr__(self, name: str):
        return self._context


class Context:
    def __init__(self, grpc_context: ContextWrapper) -> None:
        self.grpc_context = grpc_context

    @property
    def meta(self) -> dict[str, str]:
        metadata = {key: value for key, value in self.grpc_context._context.invocation_metadata()}
        metadata.update(self.trace_context)
        return metadata

    async def abort(self, code: grpc.StatusCode, details: str = "", trailing_metadata: MetadataType = ()) -> None:
        await self.grpc_context._context.abort(code, details, trailing_metadata)

    @property
    def trace_context(self) -> dict[str, str]:
        return self.grpc_context._trace_ctx



GRPCContext = Annotated[Context, SkipValidation()]

