from __future__ import annotations

import unicodedata
from typing import Any, Literal, Optional

from pydantic import BaseModel, field_validator


def _nfc(v: str) -> str:
    return unicodedata.normalize("NFC", v)


class LangText(BaseModel):
    lang: str
    script: str
    text: str

    @field_validator("text", mode="before")
    @classmethod
    def nfc_normalize(cls, v: str) -> str:
        return _nfc(v)


# ---------------------------------------------------------------------------
# Block types used inside keyword_definitions and topic_extracts
# ---------------------------------------------------------------------------

class Block(BaseModel):
    kind: Literal["reference", "sanskrit", "prakrit", "hindi", "see_also"]
    ref_text: Optional[str] = None
    text: Optional[list[LangText]] = None
    target_keyword: Optional[str] = None
    target_url: Optional[str] = None


class Subsection(BaseModel):
    subsection_index: int
    heading: list[LangText] = []
    is_topic_seed: bool = False
    topic_natural_key: Optional[str] = None
    blocks: list[Block] = []


class PageSection(BaseModel):
    section_index: int
    section_kind: Literal["siddhantkosh", "puraankosh", "misc"]
    heading: list[LangText] = []
    subsections: list[Subsection] = []


# ---------------------------------------------------------------------------
# Collection document schemas
# ---------------------------------------------------------------------------

class GathaPrakrit(BaseModel):
    natural_key: str
    shastra_natural_key: str
    gatha_natural_key: str
    gatha_number: str
    text: list[LangText]
    is_kalash: bool = False
    raw_html_fragment: Optional[str] = None
    ingestion_run_id: Optional[str] = None


class GathaSanskrit(BaseModel):
    natural_key: str
    shastra_natural_key: str
    gatha_natural_key: str
    gatha_number: str
    text: list[LangText]
    raw_html_fragment: Optional[str] = None
    ingestion_run_id: Optional[str] = None


class GathaHindiChhand(BaseModel):
    natural_key: str
    gatha_natural_key: str
    chhand_index: int
    chhand_type: str
    translator: list[LangText] = []
    text: list[LangText]
    ingestion_run_id: Optional[str] = None


class WordMeaningEntry(BaseModel):
    source_word: list[LangText]
    meanings: list[LangText]
    position: int


class GathaWordMeanings(BaseModel):
    natural_key: str
    gatha_natural_key: str
    source_language: str
    entries: list[WordMeaningEntry]
    ingestion_run_id: Optional[str] = None


class TaggedTerm(BaseModel):
    source_word: str
    meaning: str


class TeekaGathaMapping(BaseModel):
    natural_key: str
    teeka_natural_key: str
    gatha_natural_key: str
    anvayartha: list[LangText]
    tagged_terms: list[TaggedTerm] = []
    raw_html_fragment: Optional[str] = None
    ingestion_run_id: Optional[str] = None


class KeywordDefinition(BaseModel):
    natural_key: str
    keyword_id: str
    source_url: str
    page_sections: list[PageSection] = []
    redirect_aliases: list[str] = []
    ingestion_run_id: Optional[str] = None


class TopicExtract(BaseModel):
    natural_key: str
    topic_id: str
    source: str
    source_url: str
    heading: list[LangText]
    blocks: list[Block] = []
    extracted_keyword_natural_keys: list[str] = []
    ingestion_run_id: Optional[str] = None


class RawHtmlSnapshot(BaseModel):
    natural_key: str
    source: str
    source_url: str
    ingestion_run_id: Optional[str] = None
    html: str
    content_hash: str


class OcrPage(BaseModel):
    natural_key: str
    shastra_natural_key: str
    gatha_natural_key: str
    page: int
    image_path: str
    ocr_engine: str
    ocr_text: list[LangText] = []
    tables: list[Any] = []
    review_status: Literal["raw", "reviewed", "corrected"] = "raw"
