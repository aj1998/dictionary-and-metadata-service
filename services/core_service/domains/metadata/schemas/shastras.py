from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from .common import AnuyogaSummary, AuthorSummary, LangText, Pagination, _coerce_lang_text


class ShastraStats(BaseModel):
    total_gathas: int
    total_teekas: int


class ShastraResponse(BaseModel):
    id: uuid.UUID
    natural_key: str
    title: list[LangText]
    author: AuthorSummary | None = None
    anuyogas: list[AnuyogaSummary] = []
    source_url: str | None = None
    description: list[LangText] | None = None
    stats: ShastraStats
    created_at: datetime
    updated_at: datetime
    # Either a scalar offset (legacy) or a list of [up_to_published_page, offset]
    # pairs, applied in ascending order of threshold.
    pdf_page_offset: int | list[list[int]] = 0
    pustak_offsets: dict[str, int | list[list[int]]] | None = None

    @field_validator("title", mode="before")
    @classmethod
    def _coerce_title(cls, v: object) -> list[dict]:
        return _coerce_lang_text(v)

    @field_validator("description", mode="before")
    @classmethod
    def _coerce_desc(cls, v: object) -> list[dict] | None:
        if v is None:
            return None
        return _coerce_lang_text(v)


class ShastraSummaryResponse(BaseModel):
    id: uuid.UUID
    natural_key: str
    title: list[LangText]
    author: AuthorSummary | None = None
    anuyogas: list[AnuyogaSummary] = []
    similarity: float | None = None

    @field_validator("title", mode="before")
    @classmethod
    def _coerce_title(cls, v: object) -> list[dict]:
        return _coerce_lang_text(v)


class ShastraListResponse(BaseModel):
    items: list[ShastraSummaryResponse]
    pagination: Pagination


class ShastraCreate(BaseModel):
    natural_key: str
    title: list[LangText]
    author_id: uuid.UUID
    source_url: str | None = None
    description: list[LangText] | None = None
    anuyoga_ids: list[uuid.UUID] = []


class ShastraUpdate(BaseModel):
    title: list[LangText] | None = None
    author_id: uuid.UUID | None = None
    source_url: str | None = None
    description: list[LangText] | None = None
    anuyoga_ids: list[uuid.UUID] | None = None
