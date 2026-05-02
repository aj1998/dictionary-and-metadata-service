"""Pydantic models for jainkosh parser output."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Multilingual(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lang: str
    script: str
    text: str


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    raw_html: Optional[str] = None


BlockKind = Literal[
    "sanskrit_text", "sanskrit_gatha",
    "prakrit_text",  "prakrit_gatha",
    "hindi_text",    "hindi_gatha",
    "table", "see_also",
]


class Block(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: BlockKind

    text_devanagari: Optional[str] = None
    hindi_translation: Optional[str] = None
    references: list[Reference] = Field(default_factory=list)
    is_orphan_translation: bool = False

    # table
    raw_html: Optional[str] = None

    # see_also
    target_keyword: Optional[str] = None
    target_topic_path: Optional[str] = None
    target_url: Optional[str] = None
    is_self: bool = False
    target_exists: bool = True


class Definition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition_index: int
    blocks: list[Block]
    raw_html: Optional[str] = None


class Subsection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic_path: str
    heading_text: str
    heading_path: list[str]
    natural_key: str
    parent_natural_key: Optional[str] = None
    is_leaf: bool
    is_synthetic: bool = False
    blocks: list[Block]
    children: list["Subsection"]


Subsection.model_rebuild()


class IndexRelation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label_text: str
    target_keyword: Optional[str] = None
    target_topic_path: Optional[str] = None
    target_url: str
    is_self: bool = False
    target_exists: bool = True
    source_topic_path: Optional[str] = None


SectionKind = Literal["siddhantkosh", "puraankosh", "misc"]


class PageSection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    section_kind: SectionKind
    section_index: int
    h2_text: str
    definitions: list[Definition]
    index_relations: list[IndexRelation]
    subsections: list[Subsection]
    extra_blocks: list[Block] = Field(default_factory=list)


class Nav(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prev: Optional[str] = None
    next: Optional[str] = None


class ParserWarning(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
    where: Optional[str] = None


class KeywordParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keyword: str
    source_url: str
    page_sections: list[PageSection]
    nav: Nav
    parser_version: str
    parsed_at: datetime
    warnings: list[ParserWarning] = Field(default_factory=list)


class WouldWriteEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keyword_parse_result: KeywordParseResult
    would_write: dict
