"""Pydantic models for jainkosh.yaml parser config + loader."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal, Optional

import yaml
import jsonschema
from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    self_link_class: str

    see_also_triggers: list[str] = Field(default_factory=lambda: ["देखें"])
    see_also_window_chars: int = 40
    see_also_leading_punct_re: str = r'[(–\-।\s]*'

    # deprecated: auto-derived from see_also_triggers if absent
    see_also_text_pattern: Optional[str] = None

    @model_validator(mode="after")
    def _build_pattern(self) -> "IndexConfig":
        if not self.see_also_text_pattern:
            triggers = "|".join(
                re.escape(t)
                for t in sorted(self.see_also_triggers, key=len, reverse=True)
            )
            self.see_also_text_pattern = (
                f"(?:{self.see_also_leading_punct_re})(?:{triggers})\\s*$"
            )
        return self


class ReferenceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selector: str
    strip_inner_anchors: bool
    parse_strategy: Literal["text_only", "structured", "text_plus_structured"] = "text_only"


class TranslationMarkerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prefix: str
    source_kinds: list[str]
    hindi_kinds: list[str]
    sibling_marker_enabled: bool = True
    sibling_marker_text_node_re: str = r"^\s*=\s*$"
    reference_ordering: Literal["leading_then_inline", "document_order"] = "leading_then_inline"


class RefStripConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    collapse_double_spaces: bool = True
    collapse_orphan_parens: bool = True
    collapse_orphan_brackets: bool = True
    trim_trailing_chars: str = " ।॥;,"


class NestedSpanConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flatten: bool
    outer_kinds: list[str]


class TableConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selector: str
    store_raw_html: bool
    extraction_strategy: Literal["raw_html_only", "raw_html_plus_rows"] = "raw_html_only"
    attach_to: Literal["current_subsection", "section_root"] = "current_subsection"
    fallback_when_no_subsection: Literal["section_root"] = "section_root"


class RedlinkProseStripConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    connector_re: str = r"\s*[\-–]\s*$"


class RedlinkConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    anchor_class: str = "new"
    title_marker_re: str = r"^.+\(page does not exist\)\s*$"
    href_marker_substring: str = "redlink=1"
    prose_strip: RedlinkProseStripConfig = Field(default_factory=RedlinkProseStripConfig)


class LabelToTopicConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    emit_for_redlink: bool = True
    emit_for_wiki_link: bool = True
    emit_for_self_link: bool = True
    bullet_prefixes: list[str] = Field(default_factory=lambda: ["•", "·", "*", "-"])
    label_trim_chars: str = " \t।॥"
    attach_to: Literal["current_subsection", "section_root"] = "current_subsection"
    is_synthetic: bool = True
    is_leaf: bool = True
    source_marker: str = "label_seed"


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
    ref_strip: RefStripConfig = Field(default_factory=RefStripConfig)
    translation_marker: TranslationMarkerConfig
    nested_span: NestedSpanConfig
    table: TableConfig
    redlink: RedlinkConfig = Field(default_factory=RedlinkConfig)
    label_to_topic: LabelToTopicConfig = Field(default_factory=LabelToTopicConfig)
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
