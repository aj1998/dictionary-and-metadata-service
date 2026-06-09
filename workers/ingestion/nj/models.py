"""Pydantic extract models for the nikkyjain (nj) parser."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ShortFontAnchor(BaseModel):
    start_offset: int   # char index in the cleaned bhaavarth Markdown (post strip)
    end_offset: int     # exclusive


class ShortFontEntry(BaseModel):
    marker_number: int                  # 1, 2, 3, … (Devanagari digits normalised to ASCII)
    marker_devanagari: str              # "१", "२", … (kept for display)
    anchor_text: str                    # term the marker was attached to in the body
    meaning: str                        # RHS of "= " in shortFont line; or full text for bare lines
    is_definition: bool                 # True if line had "= " separator; False for narrative footnote
    occurrences: list[ShortFontAnchor]  # zero or more body anchor positions


class GathaWordMeaningEntry(BaseModel):
    source_word: str       # prakrit/sanskrit key, brackets stripped
    meaning: str           # hindi meaning
    position: int          # 1-based position in anyavartha


class AnyavarthaItem(BaseModel):
    full_anyavaarth: str                        # complete Hindi anyavartha text
    tagged_terms: list[GathaWordMeaningEntry]   # per-word breakdown


class GathaHindiChhand(BaseModel):
    chhand_index: int   # 1-based
    chhand_type: str    # "harigeet" default for body chhands
    text_hi: str


class KalashSanskritEntry(BaseModel):
    local_kalash_index: int    # 1-based within this page
    global_kalash_index: int   # sequential across all pages in sorted file order
    chhand_type: str           # "अनुष्टुभ्", "मालिनी", "रोला" etc.
    text_san: str
    verse_number: Optional[str] = None  # canonical kalash # from trailing ॥N॥ in source


class KalashHindiEntry(BaseModel):
    local_kalash_index: int
    global_kalash_index: int
    chhand_type: str           # from <span class=notes>(कलश-XXX)</span>
    text_hi: str
    verse_number: Optional[str] = None  # canonical kalash # from trailing ॥N॥ in source
    shortfont: list[ShortFontEntry] = Field(default_factory=list)


class KalashWMEntry(BaseModel):
    source_word: str    # text inside [<font color=maroon>...]
    meaning: str        # Hindi meaning text following the key


class PrimaryTeeka(BaseModel):
    """Primary teeka with kalashes (e.g. अमृतचंद्राचार्य)."""
    kalash_san: list[KalashSanskritEntry] = Field(default_factory=list)
    gatha_teeka_san: Optional[str] = None            # Sanskrit prose "अथ सूत्रावतार..."
    kalash_hindi: list[KalashHindiEntry] = Field(default_factory=list)
    kalash_word_meanings: dict[int, list[KalashWMEntry]] = Field(default_factory=dict)
    gatha_teeka_bhaavarth_md: Optional[str] = None   # Markdown with inline HTML for colors
    gatha_teeka_bhaavarth_shortfont: list[ShortFontEntry] = Field(default_factory=list)


class SecondaryTeeka(BaseModel):
    """Secondary teeka without kalashes (e.g. जयसेनाचार्य)."""
    gatha_teeka_san: Optional[str] = None
    gatha_teeka_bhaavarth_md: Optional[str] = None
    gatha_teeka_bhaavarth_shortfont: list[ShortFontEntry] = Field(default_factory=list)


class GathaExtract(BaseModel):
    # Identity
    shastra_natural_key: str
    gatha_number: str                      # from primary index: "001", "009-010"
    page_html_id: str                      # from div.title id (debug only)
    html_filename: str
    adhikaar_hi: Optional[str] = None      # optgroup label from myItem.js
    adhikaar_number: Optional[int] = None  # optgroup ordinal from myItem.js (1-based)
    heading_hi: Optional[str] = None       # option text from myItem.js
    is_combined_page: bool = False
    related_gatha_numbers: list[str] = Field(default_factory=list)

    # Gatha content
    prakrit_text: Optional[str] = None
    sanskrit_text: Optional[str] = None
    hindi_chhands: list[GathaHindiChhand] = Field(default_factory=list)
    anyavartha: Optional[AnyavarthaItem] = None

    # Teekas
    primary_teeka: Optional[PrimaryTeeka] = None
    secondary_teeka: Optional[SecondaryTeeka] = None


class KalashExtract(BaseModel):
    """Secondary-teeka standalone kalash pages (not in the primary index)."""
    shastra_natural_key: str
    kalash_number: str                           # html filename number e.g. "011"
    html_filename: str
    heading_hi: Optional[str] = None
    preceding_primary_gatha_number: Optional[str] = None

    prakrit_text: Optional[str] = None
    anyavartha: Optional[AnyavarthaItem] = None
    secondary_teeka: Optional[SecondaryTeeka] = None


class ShastraParseResult(BaseModel):
    shastra_natural_key: str
    gathas: list[GathaExtract]
    secondary_kalashes: list[KalashExtract]
    total_html_files_processed: int
    warnings: list[str] = Field(default_factory=list)
    parser_version: str
    parsed_at: datetime
