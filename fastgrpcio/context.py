from typing import Annotated

import grpc
from grpc._cython.cygrpc import _ServicerContext
from grpc.aio._typing import MetadataType
from pydantic import SkipValidation


class Context:
    def __init__(self, grpc_context: _ServicerContext) -> None:
        self.grpc_context = grpc_context

    @property
    def meta(self) -> dict[str, str]:
        return {key: value for key, value in self.grpc_context.invocation_metadata()}

    async def abort(self, code: grpc.StatusCode, details: str = "", trailing_metadata: MetadataType = ()) -> None:
        await self.grpc_context.abort(code, details, trailing_metadata)


GRPCContext = Annotated[Context, SkipValidation()]
