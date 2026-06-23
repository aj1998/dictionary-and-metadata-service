"""Config loader for the nikkyjain (nj) parser."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal, Optional

import yaml
from pydantic import BaseModel, Field

_NJ_CONFIG_DIR = Path(__file__).parents[3] / "parser_configs" / "nj"


class NJAdhikaar(BaseModel):
    number: int
    name_hi: str


class AuthorConfig(BaseModel):
    natural_key: str
    display_name_hi: str
    kind: str


class TeekaConfig(BaseModel):
    natural_key: str
    teekakar_natural_key: str
    teekakar_display_name_hi: str
    publication_natural_key: str
    publisher_id: str
    role: Literal["primary", "secondary"]


class ShastraConfig(BaseModel):
    natural_key: str
    title_hi: str
    author: AuthorConfig
    teekas: list[TeekaConfig] = Field(default_factory=list)
    adhikaars: list[NJAdhikaar] = Field(default_factory=list)

    @property
    def primary_teeka(self) -> Optional[TeekaConfig]:
        for t in self.teekas:
            if t.role == "primary":
                return t
        return None

    @property
    def secondary_teekas(self) -> list[TeekaConfig]:
        return [t for t in self.teekas if t.role == "secondary"]


class InputConfig(BaseModel):
    html_dir: str
    my_item_js: str = "myItem.js"
    encoding: str = "utf-8"
    skip_files: list[str] = Field(default_factory=list)

    @property
    def resolved_html_dir(self) -> Path:
        nj_path = os.environ.get("NIKKYJAIN_LOCAL_PATH", "")
        resolved = self.html_dir.replace("{NIKKYJAIN_LOCAL_PATH}", nj_path)
        return Path(resolved)


class SelectorsConfig(BaseModel):
    primary_teeka_select: str = "select#select-native-0"
    secondary_teeka_select: Optional[str] = None
    gatha_title_div: str = "div.title[id^='gatha-']"
    gatha_heading_link: str = "div.title > span > a"
    gatha_prakrit: Optional[str] = "div.gatha"
    gatha_sanskrit: Optional[str] = "div.gathaS"
    gatha_hindi_chhand_body: str = "div.gadya"
    anyavartha_para: str = "div.paragraph"
    anyavartha_marker: str = "अन्वयार्थ"
    teeka0_div: str = "div#teeka0"
    teeka1_div: str = "div#teeka1"
    steeka0_div: str = "div.steeka#steeka0"
    steeka1_div: str = "div.steeka#steeka1"
    primary_teeka_label: str = ""
    secondary_teeka_label: Optional[str] = None
    kalash_type_marker_color: str = "DarkSlateGray"
    kalash_word_meaning_color: str = "maroon"
    gatha_word_meaning_color: str = "darkRed"
    teeka_separator: str = "hr.type_7"


class ParsingConfig(BaseModel):
    strip_zwj: bool = False
    notes_teeka_index: Optional[int] = None


class NJConfig(BaseModel):
    version: str
    source: str = "nj"
    shastra: ShastraConfig
    input: InputConfig
    selectors: SelectorsConfig
    parsing: ParsingConfig = Field(default_factory=ParsingConfig)


def load_config(path: Path | str) -> NJConfig:
    """Load and validate a nj parser config YAML file."""
    config_path = Path(path)
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return NJConfig.model_validate(raw)


def load_config_for_shastra(shastra_natural_key: str) -> NJConfig:
    """Load config from parser_configs/nj/{shastra_natural_key}.yaml."""
    path = _NJ_CONFIG_DIR / f"{shastra_natural_key}.yaml"
    return load_config(path)
