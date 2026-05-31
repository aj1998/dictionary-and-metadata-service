from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

MatchKind = Literal["exact", "alias", "suffix_strip", "none"]


class ResolveResponse(BaseModel):
    input: str
    matched_keyword_natural_key: str | None
    match_kind: MatchKind
