import os
from functools import lru_cache

import yaml

_EDGE_TYPES_YAML = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "..", "..", "..", "..", "..",
    "parser_configs", "_meta", "edge_types.yaml",
)

# Resolved absolute path based on package location
_PACKAGE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "..")
)
_EDGE_TYPES_PATH = os.path.join(_PACKAGE_ROOT, "parser_configs", "_meta", "edge_types.yaml")


class UnknownEdgeTypeError(ValueError):
    pass


@lru_cache(maxsize=1)
def _load_edge_types() -> frozenset[str]:
    path = _EDGE_TYPES_PATH
    if not os.path.exists(path):
        # Fallback: search upward from cwd
        cwd = os.getcwd()
        candidate = os.path.join(cwd, "parser_configs", "_meta", "edge_types.yaml")
        if os.path.exists(candidate):
            path = candidate
        else:
            raise FileNotFoundError(f"edge_types.yaml not found (tried {_EDGE_TYPES_PATH} and {candidate})")
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return frozenset(entry["name"] for entry in data["edge_types"])


def validate_edge_type(edge_type: str) -> None:
    known = _load_edge_types()
    if edge_type not in known:
        raise UnknownEdgeTypeError(
            f"Unknown edge type {edge_type!r}. Known types: {sorted(known)}"
        )
