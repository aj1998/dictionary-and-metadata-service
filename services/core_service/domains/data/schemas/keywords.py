from __future__ import annotations

import uuid

from pydantic import BaseModel

from .common import LangText, Pagination


class AliasSummary(BaseModel):
    id: uuid.UUID
    alias_text: str
    source: str


class KeywordSummary(BaseModel):
    id: uuid.UUID
    natural_key: str
    display_text: str
    source_url: str | None = None


class KeywordListResponse(BaseModel):
    pagination: Pagination
    items: list[KeywordSummary]


class LetterCount(BaseModel):
    letter: str
    count: int


class KeywordDetail(BaseModel):
    id: uuid.UUID
    natural_key: str
    display_text: str
    source_url: str | None = None
    aliases: list[AliasSummary] = []
    definition: dict | None = None


class KeywordUpdate(BaseModel):
    display_text: str | None = None
    source_url: str | None = None

    model_config = {"extra": "forbid"}
