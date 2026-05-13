from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

from .common import LangText, Pagination, _coerce_lang_text


class AuthorResponse(BaseModel):
    id: uuid.UUID
    natural_key: str
    display_name: list[LangText]
    kind: str
    bio: list[LangText] | None = None
    created_at: datetime
    updated_at: datetime

    @field_validator("display_name", mode="before")
    @classmethod
    def _coerce_dn(cls, v: object) -> list[dict]:
        return _coerce_lang_text(v)

    @field_validator("bio", mode="before")
    @classmethod
    def _coerce_bio(cls, v: object) -> list[dict] | None:
        if v is None:
            return None
        return _coerce_lang_text(v)


class AuthorListResponse(BaseModel):
    items: list[AuthorResponse]
    pagination: Pagination


class AuthorCreate(BaseModel):
    natural_key: str
    display_name: list[LangText]
    kind: str
    bio: list[LangText] | None = None


class AuthorUpdate(BaseModel):
    display_name: list[LangText] | None = None
    kind: str | None = None
    bio: list[LangText] | None = None
