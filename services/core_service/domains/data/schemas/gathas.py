from __future__ import annotations

import uuid

from pydantic import BaseModel, field_validator

from .common import LangText, Pagination, ShastraRef


def _coerce(v: object) -> list[dict]:
    if v is None:
        return []
    if isinstance(v, dict):
        return [v]
    return list(v)  # type: ignore[arg-type]


class GathaSummary(BaseModel):
    id: uuid.UUID
    natural_key: str
    gatha_number: str
    shastra: ShastraRef
    adhikaar: list[LangText] = []
    heading: list[LangText] = []

    @field_validator("adhikaar", "heading", mode="before")
    @classmethod
    def _coerce_lt(cls, v: object) -> list[dict]:
        return _coerce(v)


class GathaListResponse(BaseModel):
    pagination: Pagination
    items: list[GathaSummary]


class GathaDetail(BaseModel):
    id: uuid.UUID
    natural_key: str
    gatha_number: str
    shastra: ShastraRef
    adhikaar: list[LangText] = []
    heading: list[LangText] = []
    prakrit: dict | None = None
    sanskrit: dict | None = None
    hindi_chhand: list[dict] = []
    word_meanings: dict | None = None
    teeka_mapping: list[dict] | None = None
    teeka_sanskrit: list[dict] | None = None
    teeka_hindi: list[dict] | None = None
    teeka_bhaavarth: list[dict] | None = None

    @field_validator("adhikaar", "heading", mode="before")
    @classmethod
    def _coerce_lt(cls, v: object) -> list[dict]:
        return _coerce(v)
