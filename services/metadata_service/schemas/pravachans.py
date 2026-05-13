from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from .common import AuthorSummary, LangText, Pagination, ShastraSummary, _coerce_lang_text


class PravachanResponse(BaseModel):
    id: uuid.UUID
    natural_key: str
    title: list[LangText]
    shastra: ShastraSummary | None = None
    speaker: AuthorSummary | None = None
    publisher: list[LangText] | None = None
    translator: list[LangText] | None = None
    editor: list[LangText] | None = None
    public_url: str | None = None
    publisher_url: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("title", mode="before")
    @classmethod
    def _coerce_title(cls, v: object) -> list[dict]:
        return _coerce_lang_text(v)

    @field_validator("publisher", "translator", "editor", mode="before")
    @classmethod
    def _coerce_nullable(cls, v: object) -> list[dict] | None:
        if v is None:
            return None
        return _coerce_lang_text(v)


class PravachanListResponse(BaseModel):
    items: list[PravachanResponse]
    pagination: Pagination


class PravachanCreate(BaseModel):
    natural_key: str
    title: list[LangText]
    shastra_id: uuid.UUID | None = None
    speaker_id: uuid.UUID | None = None
    publisher: list[LangText] | None = None
    translator: list[LangText] | None = None
    editor: list[LangText] | None = None
    public_url: str | None = None
    publisher_url: str | None = None


class PravachanUpdate(BaseModel):
    title: list[LangText] | None = None
    shastra_id: uuid.UUID | None = None
    speaker_id: uuid.UUID | None = None
    publisher: list[LangText] | None = None
    translator: list[LangText] | None = None
    editor: list[LangText] | None = None
    public_url: str | None = None
    publisher_url: str | None = None
