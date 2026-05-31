from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from .common import LangText, Pagination, TeekaSummary, _coerce_lang_text


class PublicationResponse(BaseModel):
    id: uuid.UUID
    natural_key: str
    teeka: TeekaSummary | None = None
    publisher_id: str
    publisher: list[LangText] | None = None
    public_url: str | None = None
    publisher_url: str | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("publisher", mode="before")
    @classmethod
    def _coerce(cls, v: object) -> list[dict] | None:
        if v is None:
            return None
        return _coerce_lang_text(v)


class PublicationListResponse(BaseModel):
    items: list[PublicationResponse]
    pagination: Pagination


class PublicationCreate(BaseModel):
    natural_key: str
    teeka_id: uuid.UUID
    publisher_id: str
    publisher: list[LangText] | None = None
    public_url: str | None = None
    publisher_url: str | None = None


class PublicationUpdate(BaseModel):
    teeka_id: uuid.UUID | None = None
    publisher_id: str | None = None
    publisher: list[LangText] | None = None
    public_url: str | None = None
    publisher_url: str | None = None
