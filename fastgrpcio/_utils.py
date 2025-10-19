import grpc
from google.protobuf.any_pb2 import Any
from google.rpc import error_details_pb2, status_pb2
from grpc_status import rpc_status
from pydantic_core import ValidationError


def pydantic_error_to_grpc(e: ValidationError) -> grpc.Status:
    bad_request = error_details_pb2.BadRequest()

    for err in e.errors():
        field_path = ".".join(str(p) for p in err["loc"])
        violation = bad_request.field_violations.add()
        violation.field = field_path
        violation.description = err["msg"]

    detail = Any()
    detail.Pack(bad_request)

    status_proto = status_pb2.Status(
        code=grpc.StatusCode.INVALID_ARGUMENT.value[0],
        message="Invalid input data",
        details=[detail],
    )

    grpc_status_obj = rpc_status.to_status(status_proto)
    return grpc_status_obj
