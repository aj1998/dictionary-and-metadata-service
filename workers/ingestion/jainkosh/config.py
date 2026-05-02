"""Pydantic models for jainkosh.yaml parser config + loader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import yaml
import jsonschema
from pydantic import BaseModel, ConfigDict, Field

_SCHEMA_PATH = Path(__file__).parents[3] / "parser_configs" / "_schemas" / "jainkosh.schema.json"
_DEFAULT_CONFIG_PATH = Path(__file__).parents[3] / "parser_configs" / "jainkosh.yaml"


class NormalizationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nfc: bool = True
    strip_zwj: bool = True
    strip_zwnj: bool = True
    collapse_whitespace: bool = True
    br_to_newline: bool = True


class SectionKindEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    kind: str


class SectionsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selector: str
    h2_headline_selector: str
    kinds: list[SectionKindEntry]
    default_kind: str


class DefinitionBoundaryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    boundary: str


class DefinitionsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    siddhantkosh: DefinitionBoundaryConfig
    puraankosh: DefinitionBoundaryConfig


class IndexConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled_for: list[str]
    outer_list_selector: str
    inner_anchor_ignore_selector: str
    see_also_list_selector: str
    see_also_text_pattern: str
    self_link_class: str


class ReferenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selector: str
    strip_inner_anchors: bool


class TranslationMarkerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prefix: str
    source_kinds: list[str]
    hindi_kinds: list[str]


class NestedSpanConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flatten: bool
    outer_kinds: list[str]


class TableConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selector: str
    store_raw_html: bool
    attach_to: str


class NavigationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    drop: bool
    prev_text: str
    next_text: str
    containing_tag: str


class EmphasisConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bold_to_markdown: bool
    italic_to_markdown: bool


class HeadingVariant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    selector: str
    id_from: str
    heading_text: str
    regex: Optional[str] = None


class HeadingsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    variants: list[HeadingVariant]


class SlugConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preserve_devanagari: bool
    strip_chars: str
    whitespace_to: str
    collapse_dashes: bool
    strip_v4_numeric_prefix: bool


class BulletStripConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prefixes: list[str]
    trailing_punct: list[str]


class JainkoshConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str
    parser_rules_version: str
    normalization: NormalizationConfig
    sections: SectionsConfig
    definitions: DefinitionsConfig
    index: IndexConfig
    block_classes: dict[str, str]
    reference: ReferenceConfig
    translation_marker: TranslationMarkerConfig
    nested_span: NestedSpanConfig
    table: TableConfig
    navigation: NavigationConfig
    emphasis: EmphasisConfig
    headings: HeadingsConfig
    slug: SlugConfig
    bullet_strip: BulletStripConfig
    blocks_to_drop_when_empty: list[str]

    def section_kind_for(self, headline_id: str) -> str:
        for entry in self.sections.kinds:
            if entry.id == headline_id:
                return entry.kind
        return self.sections.default_kind


def load_config(path: Path | str | None = None, *, validate_schema: bool = True) -> JainkoshConfig:
    """Load and validate the jainkosh.yaml config file."""
    config_path = Path(path) if path else _DEFAULT_CONFIG_PATH
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if validate_schema:
        with open(_SCHEMA_PATH, encoding="utf-8") as f:
            schema = json.load(f)
        try:
            jsonschema.validate(raw, schema)
        except jsonschema.ValidationError as exc:
            raise ValueError(f"Config schema validation failed: {exc.message}") from exc

    return JainkoshConfig.model_validate(raw)
