from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, field_validator


class KeywordResolveBatchRequest(BaseModel):
    tokens: list[str]
    fuzzy_top_k: int = 5
    min_similarity: float = 0.35
    include_definitions: bool = True
    definitions_per_keyword: int = 0  # 0 = all
    language: str = "hi"

    @field_validator("tokens")
    @classmethod
    def tokens_not_empty(cls, v: list[str]) -> list[str]:
        if len(v) == 0:
            raise ValueError("tokens must not be empty")
        return v


class DefinitionBlock(BaseModel):
    source_natural_key: str
    block_index: int
    text_hi: str


class Suggestion(BaseModel):
    keyword_natural_key: str
    similarity: float


class Resolution(BaseModel):
    input_token: str
    match_kind: Literal["exact", "alias", "suffix_strip", "none"]
    keyword_natural_key: Optional[str] = None
    keyword_id: Optional[str] = None
    definitions: Optional[list[DefinitionBlock]] = None
    suggestions: Optional[list[Suggestion]] = None


class KeywordResolveBatchResponse(BaseModel):
    resolutions: list[Resolution]
    tool_trace_id: str
