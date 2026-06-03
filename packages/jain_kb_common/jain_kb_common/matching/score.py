from __future__ import annotations

import os

from .types import BlockKind

DEFAULT_THRESHOLD: float = 0.80

KIND_THRESHOLDS: dict[str, float] = {
    "prakrit_gatha": 0.90,
    "sanskrit_gatha": 0.90,
    "hindi_gatha": 0.85,
    "prakrit_text": 0.80,
    "sanskrit_text": 0.80,
    "hindi_text": 0.80,
}

_ENV_PREFIX = "MATCHER_THRESHOLD_"


def threshold_for(kind: BlockKind) -> float:
    """Return the match threshold for *kind*, with env-var override support."""
    env_key = _ENV_PREFIX + kind.upper()
    env_val = os.environ.get(env_key)
    if env_val is not None:
        return float(env_val)
    return KIND_THRESHOLDS.get(kind, DEFAULT_THRESHOLD)


def jaccard(a: set, b: set) -> float:
    """Jaccard similarity of two sets. Empty ∩ empty → 1.0."""
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union)
