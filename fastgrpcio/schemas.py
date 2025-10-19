from collections.abc import Generator
from typing import Any, get_args, get_origin

from pydantic import BaseModel, ConfigDict


class BaseGRPCSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    @classmethod
    def iterate_by_model_fields(
        cls,
        model: type[BaseModel] | None = None,
    ) -> Generator[tuple[str, Any, bool], None, None]:
        model = model or cls
        for name, field in model.model_fields.items():
            anno = field.annotation

            origin = get_origin(anno)
            args = get_args(anno)

            is_repeated = origin in (list, list)

            base_types = tuple(t for t in args if t is not type(None))
            if not base_types:
                base_type: Any = anno
            elif len(base_types) == 1:
                base_type = base_types[0]
            else:
                base_type = base_types

            yield name, base_type, is_repeated
