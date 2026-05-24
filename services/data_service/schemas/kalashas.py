from __future__ import annotations

import uuid

from pydantic import BaseModel

from .common import AuthorSummary, Pagination, ShastraRef


class TeekaInfo(BaseModel):
    natural_key: str
    shastra: ShastraRef
    teekakar: AuthorSummary | None = None


class TeekaInfoDetail(BaseModel):
    id: uuid.UUID
    natural_key: str
    shastra: ShastraRef
    teekakar: AuthorSummary | None = None


class KalashSummary(BaseModel):
    id: uuid.UUID
    natural_key: str
    kalash_number: str
    teeka: TeekaInfo


class KalashListResponse(BaseModel):
    pagination: Pagination
    items: list[KalashSummary]


class KalashDetail(BaseModel):
    id: uuid.UUID
    natural_key: str
    kalash_number: str
    teeka: TeekaInfoDetail
    sanskrit: dict | None = None
    hindi: dict | None = None
    bhaavarth: list[dict] = []


class KalashWMEntryResponse(BaseModel):
    source_word: str
    meaning: str
    position: int


class KalashWordMeaningsResponse(BaseModel):
    kalash_id: uuid.UUID
    kalash_natural_key: str
    teeka_natural_key: str
    kalash_number: str
    entries: list[KalashWMEntryResponse]
