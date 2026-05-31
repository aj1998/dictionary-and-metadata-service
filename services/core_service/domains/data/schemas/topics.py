from __future__ import annotations

import uuid

from pydantic import BaseModel, field_validator

from .common import KeywordRef, LangText, Pagination


def _coerce(v: object) -> list[dict]:
    if v is None:
        return []
    if isinstance(v, dict):
        return [v]
    return list(v)  # type: ignore[arg-type]


class TopicParentRef(BaseModel):
    id: uuid.UUID
    natural_key: str
    display_text: list[LangText]

    @field_validator("display_text", mode="before")
    @classmethod
    def _coerce_dt(cls, v: object) -> list[dict]:
        return _coerce(v)


class TopicSummary(BaseModel):
    id: uuid.UUID
    natural_key: str
    display_text: list[LangText]
    source: str
    is_leaf: bool
    topic_path: str | None = None
    parent_keyword: KeywordRef | None = None

    @field_validator("display_text", mode="before")
    @classmethod
    def _coerce_dt(cls, v: object) -> list[dict]:
        return _coerce(v)


class TopicListResponse(BaseModel):
    pagination: Pagination
    items: list[TopicSummary]


class TopicDetail(BaseModel):
    id: uuid.UUID
    natural_key: str
    display_text: list[LangText]
    source: str
    is_leaf: bool
    is_synthetic: bool
    topic_path: str | None = None
    parent_keyword: KeywordRef | None = None
    parent_topic: TopicParentRef | None = None
    extracts: list[dict] = []

    @field_validator("display_text", mode="before")
    @classmethod
    def _coerce_dt(cls, v: object) -> list[dict]:
        return _coerce(v)
