from __future__ import annotations

import unicodedata
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


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

BlockKind = Literal[
    "sanskrit_text", "sanskrit_gatha",
    "prakrit_text",  "prakrit_gatha",
    "hindi_text",    "hindi_gatha",
    "table", "see_also",
]


class ResolvedField(BaseModel):
    field: str
    value: int | str


class BlockRef(BaseModel):
    text: str
    raw_html: Optional[str] = None
    resolved_fields: list[ResolvedField] = Field(default_factory=list)
    shastra_name: Optional[str] = None
    teeka_name: str = ""
    inline_reference: bool = False


class Block(BaseModel):
    kind: BlockKind
    text_devanagari: Optional[str] = None
    hindi_translation: Optional[str] = None
    references: list[BlockRef] = Field(default_factory=list)
    # table
    raw_html: Optional[str] = None
    # see_also
    target_keyword: Optional[str] = None
    target_url: Optional[str] = None


class Definition(BaseModel):
    definition_index: int
    blocks: list[Block] = Field(default_factory=list)


class PageSection(BaseModel):
    section_index: int
    section_kind: Literal["siddhantkosh", "puraankosh", "misc"]
    heading: list[LangText] = []
    definitions: list[Definition] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 1 richer keyword/topic models
# ---------------------------------------------------------------------------

class DefinitionItem(BaseModel):
    definition_index: int
    blocks: list[dict]  # opaque dict matching parser Block


class SubsectionTreeNode(BaseModel):
    natural_key: str
    topic_path: Optional[str] = None
    heading: list[LangText]
    is_leaf: bool
    is_synthetic: bool
    children: list["SubsectionTreeNode"] = []


SubsectionTreeNode.model_rebuild()


class IndexRelationItem(BaseModel):
    label_text: Optional[str] = None
    target_keyword: Optional[str] = None
    target_topic_path: Optional[str] = None
    is_self: bool = False
    target_exists: bool = True
    source_topic_path: Optional[str] = None


class KeywordPageSection(BaseModel):
    section_index: int
    section_kind: str
    h2_text: Optional[str] = None
    definitions: list[DefinitionItem] = []
    subsection_tree: list[SubsectionTreeNode] = []
    index_relations: list[IndexRelationItem] = []
    extra_blocks: list[dict] = []


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
    full_anyavaarth: Optional[str] = None
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
    full_anyavaarth: Optional[str] = None
    is_related: list[str] = []
    raw_html_fragment: Optional[str] = None
    ingestion_run_id: Optional[str] = None


class KeywordDefinition(BaseModel):
    natural_key: str
    keyword_id: Optional[str] = None
    source_url: str
    page_sections: list[KeywordPageSection] = []
    redirect_aliases: list[str] = []
    ingestion_run_id: Optional[str] = None
    parser_version: Optional[str] = None


class TopicExtract(BaseModel):
    natural_key: str
    topic_id: Optional[str] = None
    source: str
    source_url: str
    heading: list[LangText]
    blocks: list[Block] = []
    extracted_keyword_natural_keys: list[str] = []
    ingestion_run_id: Optional[str] = None
    topic_path: Optional[str] = None
    parent_natural_key: Optional[str] = None
    parent_keyword_natural_key: Optional[str] = None
    is_leaf: bool = True
    is_synthetic: bool = False
    parser_version: Optional[str] = None


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


class GathaTeekaSanskrit(BaseModel):
    natural_key: str
    gatha_teeka_natural_key: str
    teeka_natural_key: str
    gatha_number: str
    text: list[LangText]
    ingestion_run_id: Optional[str] = None


class GathaTeekaHindi(BaseModel):
    natural_key: str
    gatha_teeka_natural_key: str
    teeka_natural_key: str
    gatha_number: str
    text: list[LangText]
    ingestion_run_id: Optional[str] = None


class GathaTeekaBhaavarth(BaseModel):
    natural_key: str
    gatha_teeka_bhaavarth_natural_key: str
    publication_natural_key: str
    gatha_teeka_natural_key: str
    publisher_id: str
    gatha_number: str
    text: list[LangText]
    ingestion_run_id: Optional[str] = None


class KalashSanskrit(BaseModel):
    natural_key: str
    kalash_natural_key: str
    teeka_natural_key: str
    kalash_number: str
    text: list[LangText]
    ingestion_run_id: Optional[str] = None


class KalashHindi(BaseModel):
    natural_key: str
    kalash_natural_key: str
    teeka_natural_key: str
    kalash_number: str
    text: list[LangText]
    ingestion_run_id: Optional[str] = None


class KalashBhaavarth(BaseModel):
    natural_key: str
    kalash_bhaavarth_natural_key: str
    publication_natural_key: str
    kalash_natural_key: str
    publisher_id: str
    kalash_number: str
    text: list[LangText]
    ingestion_run_id: Optional[str] = None


class KalashWMEntry(BaseModel):
    source_word: str
    meaning: str
    position: int


class KalashWordMeanings(BaseModel):
    natural_key: str
    kalash_natural_key: str
    teeka_natural_key: str
    kalash_number: str
    entries: list[KalashWMEntry]
    ingestion_run_id: Optional[str] = None


class BhaavarthShortFontOccurrence(BaseModel):
    start_offset: int
    end_offset: int


class BhaavarthShortFontEntry(BaseModel):
    marker_number: int
    marker_devanagari: str
    anchor_text: str
    meaning: str
    is_definition: bool
    occurrences: list[BhaavarthShortFontOccurrence]


class BhaavarthShortFontDoc(BaseModel):
    natural_key: str
    bhaavarth_natural_key: str
    publication_natural_key: str
    gatha_natural_key: str
    gatha_number: str
    entries: list[BhaavarthShortFontEntry]
    ingestion_run_id: str | None = None


class KalashBhaavarthShortFontDoc(BaseModel):
    natural_key: str
    kalash_natural_key: str
    teeka_natural_key: str
    kalash_number: str
    entries: list[BhaavarthShortFontEntry]
    ingestion_run_id: str | None = None


class TableDoc(BaseModel):
    natural_key: str
    table_id: Optional[str] = None
    source: str
    parent_natural_key: str
    parent_kind: str
    table_type: str = "general"
    seq: int
    source_url: Optional[str] = None
    caption: list[LangText] = []
    raw_html: str
    cells: list[list[str]] = []
    # 3-D list: rows × cols × list of resolved Reference dicts per cell.
    # Empty list for tables with no GRef spans inside cells.
    cell_refs: list[list[list[dict]]] = []
    header_rows: int = 0
    mentioned_keyword_natural_keys: list[str] = []
    mentioned_topic_natural_keys: list[str] = []
    plaintext: Optional[str] = None
    ingestion_run_id: Optional[str] = None
    parser_version: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
