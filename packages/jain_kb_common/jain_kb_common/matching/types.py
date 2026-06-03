from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BlockKind = Literal[
    "prakrit_gatha",
    "prakrit_text",
    "sanskrit_gatha",
    "sanskrit_text",
    "hindi_text",
    "hindi_gatha",
    "see_also",
    "table",
]


@dataclass
class MatchResult:
    matched: bool
    method: Literal["exact_normalized", "shingle_fuzzy", "none"]
    score: float                   # 0.0–1.0; 1.0 for exact
    char_start: int | None         # offset into ORIGINAL NFC target_text
    char_end: int | None           # exclusive
    normalized_source: str
    normalized_target: str
