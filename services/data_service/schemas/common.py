from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, field_validator


def _coerce_lang_text(v: object) -> list[dict]:
    if v is None:
        return []
    if isinstance(v, dict):
        return [v]
    return list(v)  # type: ignore[arg-type]


class LangText(BaseModel):
    lang: str
    script: str
    text: str


class Pagination(BaseModel):
    total: int
    limit: int
    offset: int


class ErrorDetail(BaseModel):
    code: Literal["not_found", "validation_error", "conflict", "unauthorized", "internal"]
    message: str
    details: dict | None = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


class AuthorSummary(BaseModel):
    natural_key: str
    display_name: list[LangText]

    @field_validator("display_name", mode="before")
    @classmethod
    def _coerce(cls, v: object) -> list[dict]:
        return _coerce_lang_text(v)


class ShastraRef(BaseModel):
    natural_key: str
    title: list[LangText]

    @field_validator("title", mode="before")
    @classmethod
    def _coerce(cls, v: object) -> list[dict]:
        return _coerce_lang_text(v)


class TeekaRef(BaseModel):
    natural_key: str
    shastra: ShastraRef
    teekakar: AuthorSummary | None = None


class KeywordRef(BaseModel):
    id: uuid.UUID
    natural_key: str
    display_text: str
