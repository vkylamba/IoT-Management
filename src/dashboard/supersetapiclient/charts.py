"""Charts."""
from dataclasses import dataclass

from .base import (
    Object, ObjectFactories, json_field, default_string
)


@dataclass
class Chart(Object):
    JSON_FIELDS = [
        "params",
        "query_context"
    ]

    id: int
    description: default_string()
    slice_name: default_string()
    datasource_id: int = None
    datasource_type: str = default_string
    viz_type: str = ""
    params: dict = json_field()
    query_context: dict = json_field()


class Charts(ObjectFactories):
    endpoint = "/chart/"
    base_object = Chart
