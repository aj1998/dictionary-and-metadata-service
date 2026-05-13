from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from .common import AuthorSummary, LangText, Pagination, ShastraSummary, _coerce_lang_text


class TeekaStats(BaseModel):
    total_publications: int


class TeekaResponse(BaseModel):
    id: uuid.UUID
    natural_key: str
    shastra: ShastraSummary | None = None
    teekakar: AuthorSummary | None = None
    publisher: list[LangText] | None = None
    translator: list[LangText] | None = None
    editor: list[LangText] | None = None
    cataloguesearch_shastra_id: str | None = None
    public_url: str | None = None
    publisher_url: str | None = None
    stats: TeekaStats
    created_at: datetime
    updated_at: datetime

    @field_validator("publisher", "translator", "editor", mode="before")
    @classmethod
    def _coerce(cls, v: object) -> list[dict] | None:
        if v is None:
            return None
        return _coerce_lang_text(v)


class TeekaSummaryResponse(BaseModel):
    id: uuid.UUID
    natural_key: str
    shastra: ShastraSummary | None = None
    teekakar: AuthorSummary | None = None

    @field_validator("shastra", mode="before")
    @classmethod
    def _coerce_shastra(cls, v: object) -> object:
        return v

    @field_validator("teekakar", mode="before")
    @classmethod
    def _coerce_teekakar(cls, v: object) -> object:
        return v


class TeekaListResponse(BaseModel):
    items: list[TeekaSummaryResponse]
    pagination: Pagination


class TeekaCreate(BaseModel):
    natural_key: str
    shastra_id: uuid.UUID
    teekakar_id: uuid.UUID | None = None
    publisher: list[LangText] | None = None
    translator: list[LangText] | None = None
    editor: list[LangText] | None = None
    cataloguesearch_shastra_id: str | None = None
    public_url: str | None = None
    publisher_url: str | None = None


class TeekaUpdate(BaseModel):
    shastra_id: uuid.UUID | None = None
    teekakar_id: uuid.UUID | None = None
    publisher: list[LangText] | None = None
    translator: list[LangText] | None = None
    editor: list[LangText] | None = None
    cataloguesearch_shastra_id: str | None = None
    public_url: str | None = None
    publisher_url: str | None = None
