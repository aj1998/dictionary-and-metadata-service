"""Page-level parser for NJ shastra HTML files."""

from __future__ import annotations

import dataclasses
import logging
import re
import unicodedata
from pathlib import Path

logger = logging.getLogger(__name__)

from bs4 import BeautifulSoup, NavigableString, Tag

from .config import NJConfig
from .models import (
    AnyavarthaItem,
    GathaExtract,
    GathaHindiChhand,
    GathaWordMeaningEntry,
    KalashExtract,
)
from .parse_myitem import GathaIndexEntry
from .parse_primary_teeka import parse_primary_teeka
from .parse_secondary_teeka import parse_secondary_teeka

_TRAILING_VERSE_RE = re.compile(r"\s*(?:॥\s*[\d०-९]+\s*॥|\|\|\s*[\d०-९]+\s*\|\||॥|\|\|)\s*$")
_DEV_DIGIT_MAP = str.maketrans("०१२३४५६७८९", "0123456789")

_ANY_VERSE_MARKER_RE = re.compile(r"\s*(?:॥\s*[\d०-९]+\s*॥|\|\|\s*[\d०-९]+\s*\|\||॥|\|\|)\s*")
_PAREN_NUM_RE = re.compile(r"\s*\(\s*[\d०-९]+\s*\)\s*")
_DEV_DIGITS = str.maketrans("0123456789", "०१२३४५६७८९")


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return unicodedata.normalize("NFC", text.replace("\ufeff", "")).strip()


def _clean_preserve_newlines(text: str | None) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", text.replace("\ufeff", ""))
    # Preserve explicit line boundaries while trimming each line and dropping blank lines.
    lines = [ln.strip() for ln in normalized.splitlines()]
    return "\n".join([ln for ln in lines if ln]).strip()


def _strip_trailing_verse_no(text: str | None) -> str | None:
    if not text:
        return None
    return _clean(_TRAILING_VERSE_RE.sub("", text))


def _text_after_font_parent(font_parent: Tag) -> str:
    parts: list[str] = []
    for sib in font_parent.next_siblings:
        if isinstance(sib, Tag) and sib.name == "b":
            break
        if isinstance(sib, NavigableString):
            parts.append(str(sib))
        elif isinstance(sib, Tag):
            parts.append(sib.get_text(" ", strip=False))
    return "".join(parts)


def _parse_anyavartha(div: Tag, cfg: NJConfig) -> AnyavarthaItem:
    tagged_terms: list[GathaWordMeaningEntry] = []
    position = 1
    target_color = cfg.selectors.gatha_word_meaning_color.lower()

    for font in div.find_all("font"):
        color = (font.get("color") or "").strip().lower()
        if color != target_color:
            continue
        key_text = _clean(font.get_text()).strip("[]").strip()
        meaning = _clean(_text_after_font_parent(font.parent if font.parent else font))
        tagged_terms.append(
            GathaWordMeaningEntry(source_word=key_text, meaning=meaning, position=position)
        )
        position += 1

    full_div = BeautifulSoup(str(div), "lxml").find("div")
    if full_div:
        # Collect targets before decomposing — decompose() destroys children too,
        # which corrupts attrs on sibling nodes still in the find_all result list.
        target_fonts = [
            f for f in full_div.find_all("font")
            if (f.get("color") or "").strip().lower() == target_color
        ]
        for font in target_fonts:
            font.decompose()
        full_text = _clean(full_div.get_text(" ", strip=False))
    else:
        full_text = _clean(div.get_text(" ", strip=False))
    full_anyavaarth = re.sub(r"^अन्वयार्थ\s*:\s*", "", full_text).strip()
    full_anyavaarth = re.sub(r"\s+", " ", full_anyavaarth).strip()

    return AnyavarthaItem(full_anyavaarth=full_anyavaarth, tagged_terms=tagged_terms)


def _parse_page_html_id(soup: BeautifulSoup, cfg: NJConfig) -> str:
    title_div = soup.select_one(cfg.selectors.gatha_title_div)
    if not title_div:
        return ""
    gid = title_div.get("id") or ""
    return gid.replace("gatha-", "")


_VERSE_END_MARKER_RE = re.compile(r"(?:॥\s*[\d०-९]+\s*॥|\|\|\s*[\d०-९]+\s*\|\||॥|\|\|)")

# Mid-verse `<span class=comment>(N)</span>` marker — authoritative primary gatha number when present.
_COMMENT_NUM_RE = re.compile(r"\(\s*([\d०-९]+)\s*\)")


def _extract_primary_comment_number(soup: BeautifulSoup, cfg: NJConfig) -> str | None:
    if not cfg.selectors.gatha_prakrit:
        return None
    gatha_div = soup.select_one(cfg.selectors.gatha_prakrit)
    if not gatha_div:
        return None
    for span in gatha_div.find_all("span", class_="comment"):
        m = _COMMENT_NUM_RE.search(span.get_text())
        if m:
            return m.group(1).translate(_DEV_DIGIT_MAP)
    return None


def _expand_gatha_numbers(gatha_number: str) -> list[str]:
    """Expand a hyphenated gatha_number into the list of individual gatha numbers.

    Two-part hyphenated values are treated as inclusive ranges (e.g. "098-100"
    → ["098", "099", "100"]), preserving the leading-zero width of the start
    value. Three-or-more-part values are treated as explicit lists (e.g.
    "020-021-022" → ["020", "021", "022"]). Non-numeric or malformed values
    fall back to a literal split.
    """
    if "-" not in gatha_number:
        return [gatha_number]
    parts = gatha_number.split("-")
    if len(parts) == 2:
        try:
            start, end = int(parts[0]), int(parts[1])
        except ValueError:
            return parts
        if end < start:
            return parts
        width = len(parts[0])
        return [str(n).zfill(width) for n in range(start, end + 1)]
    return parts


def _split_combined_text_by_markers(text: str | None, gatha_numbers: list[str]) -> list[str] | None:
    """Split combined text into N chunks using the first N-1 verse-end markers found in order.

    Any ॥M॥ or ||M|| (regardless of M's value) is treated as a verse-end marker.
    The (N) notation is a mid-verse line label, NOT a split point — it is stripped
    afterwards by _clean_gatha_chunk().
    Markers are NOT included in the returned chunks.
    """
    if not text or len(gatha_numbers) < 2:
        return None

    n_splits = len(gatha_numbers) - 1
    chunks: list[str] = []
    cursor = 0
    for _ in range(n_splits):
        m = _VERSE_END_MARKER_RE.search(text, cursor)
        if not m:
            return None
        chunk = _clean(text[cursor : m.start()])
        if not chunk:
            return None
        chunks.append(chunk)
        cursor = m.end()

    last = _clean(text[cursor:])
    if not last:
        return None
    chunks.append(last)

    return chunks if len(chunks) == len(gatha_numbers) else None


def _clean_gatha_chunk(text: str, all_gatha_numbers: list[str]) -> str:
    """Strip residual gatha-number markers from a split chunk.

    Removes:
    - (N) and (N-deva) where N is any gatha number on the combined page
    - Any remaining ॥M॥ / ||M|| verse-end markers

    Replaces removed markers with newlines so adjacent content lines are not merged.
    """
    for n in all_gatha_numbers:
        try:
            num = int(n)
        except ValueError:
            continue
        n_ascii = str(num)
        n_deva = n_ascii.translate(_DEV_DIGITS)
        text = re.sub(
            rf"\s*\(\s*(?:{re.escape(n_ascii)}|{re.escape(n_deva)})\s*\)\s*",
            "\n",
            text,
        )
    text = _ANY_VERSE_MARKER_RE.sub("\n", text)
    return _clean_preserve_newlines(text)


def _parse_body_fields(
    soup: BeautifulSoup,
    cfg: NJConfig,
) -> tuple[str | None, str | None, list[GathaHindiChhand], AnyavarthaItem | None, list[str]]:
    def _clean_verse_text(raw: str) -> str:
        text = _clean_preserve_newlines(raw)
        text = _PAREN_NUM_RE.sub("\n", text)
        text = _TRAILING_VERSE_RE.sub("", text)
        return _clean_preserve_newlines(text)

    gatha_div = soup.select_one(cfg.selectors.gatha_prakrit) if cfg.selectors.gatha_prakrit else None
    raw_prakrit = gatha_div.get_text("\n", strip=False) if gatha_div else None
    # Capture ALL ॥N॥ / ||N|| markers in source order, BEFORE _clean_verse_text strips
    # the trailing one. For single-gatha pages there is one; for combined pages (e.g.
    # 112-113.html → gatha_number "105-106") there is one per included gatha.
    prakrit_verse_markers: list[str] = []
    if raw_prakrit:
        normalized = unicodedata.normalize("NFC", raw_prakrit)
        prakrit_verse_markers = [
            m.group(1).translate(_DEV_DIGIT_MAP)
            for m in re.finditer(r"(?:॥|\|\|)\s*([\d०-९]+)\s*(?:॥|\|\|)", normalized)
        ]
    prakrit_text = _clean_verse_text(raw_prakrit) if raw_prakrit is not None else None
    prakrit_text = prakrit_text or None  # keep None if empty string

    gatha_s_div = soup.select_one(cfg.selectors.gatha_sanskrit) if cfg.selectors.gatha_sanskrit else None
    sanskrit_text = _clean_verse_text(gatha_s_div.get_text("\n", strip=False)) if gatha_s_div else None
    sanskrit_text = sanskrit_text or None

    body_gadyas = [
        d
        for d in soup.select(cfg.selectors.gatha_hindi_chhand_body)
        if not d.find_parent("table") and not d.find_parent("div", id=re.compile(r"^teeka"))
    ]
    hindi_chhands = [
        GathaHindiChhand(
            chhand_index=i + 1,
            chhand_type="harigeet",
            text_hi=_clean_verse_text(d.get_text("\n", strip=False)),
        )
        for i, d in enumerate(body_gadyas)
    ]

    para_div = next(
        (
            d
            for d in soup.select(cfg.selectors.anyavartha_para)
            if cfg.selectors.anyavartha_marker in d.get_text()
            and not d.find_parent("div", id=re.compile(r"^teeka"))
        ),
        None,
    )
    anyavartha = _parse_anyavartha(para_div, cfg) if para_div else None

    return prakrit_text, sanskrit_text, hindi_chhands, anyavartha, prakrit_verse_markers


def _teeka0_label_role(teeka0_div: Tag | None, cfg: NJConfig) -> str | None:
    """Classify the darkgreen label at the top of div#teeka0.

    Returns "primary" when it matches `primary_teeka_label`, "secondary" when it
    matches `secondary_teeka_label`, and None when there is no darkgreen label.
    A label that matches neither is treated as None and surfaced as a warning
    (genuine config drift). Some gathas (e.g. पंचास्तिकाय gatha 24) have **no**
    primary teeka at all — the secondary teeka (जयसेनाचार्य / तात्पर्यवृत्ति) sits
    in teeka0 with no teeka1 — so "secondary" is an expected, non-warning outcome.
    """
    if teeka0_div is None:
        return None
    label = teeka0_div.select_one("font[color='darkgreen'], font[color='DarkGreen']")
    if not label:
        return None
    label_text = _clean(label.get_text())
    if cfg.selectors.primary_teeka_label in label_text:
        return "primary"
    secondary_label = cfg.selectors.secondary_teeka_label
    if secondary_label and secondary_label in label_text:
        return "secondary"
    # Config drift guard: teeka0 with a darkgreen label exists, but it matches
    # neither the primary nor the secondary configured label. The teeka payload
    # is skipped in this case, so surface it loudly to the ingestion logs.
    logger.warning(
        "nj.teeka0_label.unrecognized shastra=%s primary_label=%r secondary_label=%r "
        "html_label=%r — teeka skipped for this page; update teeka labels in the shastra YAML",
        cfg.shastra.natural_key,
        cfg.selectors.primary_teeka_label,
        secondary_label,
        label_text,
    )
    return None


def _is_primary_page(teeka0_div: Tag | None, cfg: NJConfig) -> bool:
    return _teeka0_label_role(teeka0_div, cfg) == "primary"


def parse_primary_page(
    soup: BeautifulSoup,
    idx_entry: GathaIndexEntry,
    cfg: NJConfig,
    global_kalash_start: int,
) -> tuple[list[GathaExtract], int]:
    """Parse a primary-gatha page; returns (expanded_gathas, kalash_delta)."""
    # `<span class=comment>(N)</span>` inside `<div class=gatha>` is the authoritative
    # primary gatha number for single-gatha pages — overrides myItem.js when present.
    # Combined pages (e.g. "030-031") carry only one comment value matching the start
    # of the range; skip the override there and trust myItem.js.
    comment_num = _extract_primary_comment_number(soup, cfg)
    if comment_num and "-" not in idx_entry.gatha_number:
        width = len(idx_entry.gatha_number)
        normalized = comment_num.zfill(width) if comment_num.isdigit() else comment_num
        if normalized != idx_entry.gatha_number:
            idx_entry = dataclasses.replace(idx_entry, gatha_number=normalized)

    prakrit_text, sanskrit_text, hindi_chhands, anyavartha, prakrit_verse_markers = _parse_body_fields(soup, cfg)
    # Single-gatha page → first marker is canonical; combined pages override per-chunk below.
    prakrit_verse_marker = prakrit_verse_markers[0] if prakrit_verse_markers else None

    teeka0_div = soup.select_one(cfg.selectors.teeka0_div)
    teeka1_div = soup.select_one(cfg.selectors.teeka1_div)
    teeka0_role = _teeka0_label_role(teeka0_div, cfg)
    source_ref = f"{cfg.shastra.natural_key}/{idx_entry.html_filename} गाथा {idx_entry.gatha_number}"

    primary_teeka = None
    kalash_delta = 0
    if teeka0_role == "primary":
        primary_cfg = cfg.shastra.primary_teeka
        primary_pub_nk = primary_cfg.publication_natural_key if primary_cfg else ""
        try:
            norm_gatha = str(int(idx_entry.gatha_number))
        except ValueError:
            norm_gatha = idx_entry.gatha_number
        primary_bhaavarth_nk = (
            f"{primary_pub_nk}:गाथा:टीका:भावार्थ:{norm_gatha}"
            if primary_pub_nk else None
        )
        primary_teeka, kalash_delta = parse_primary_teeka(
            teeka0_div, cfg, global_kalash_start,
            parent_bhaavarth_nk=primary_bhaavarth_nk,
            source_ref=source_ref,
        )

    secondary_cfg = cfg.shastra.secondary_teekas[0] if cfg.shastra.secondary_teekas else None
    try:
        norm_gatha_sec = str(int(idx_entry.gatha_number))
    except ValueError:
        norm_gatha_sec = idx_entry.gatha_number
    secondary_bhaavarth_nk = (
        f"{secondary_cfg.publication_natural_key}:गाथा:टीका:भावार्थ:{norm_gatha_sec}"
        if secondary_cfg else None
    )
    if isinstance(teeka1_div, Tag):
        secondary_teeka = parse_secondary_teeka(
            teeka1_div, cfg, parent_bhaavarth_nk=secondary_bhaavarth_nk,
            source_ref=source_ref,
        )
    elif teeka0_role == "secondary" and isinstance(teeka0_div, Tag):
        # No primary teeka for this gatha and no div#teeka1: the secondary teeka
        # (e.g. जयसेनाचार्य / तात्पर्यवृत्ति) lives in div#teeka0. Parse it as the
        # secondary teeka so its content is not silently dropped (पंचास्तिकाय gatha 24).
        logger.info(
            "nj.secondary_teeka_in_teeka0 shastra=%s gatha=%s — parsing teeka0 as secondary teeka",
            cfg.shastra.natural_key,
            idx_entry.gatha_number,
        )
        secondary_teeka = parse_secondary_teeka(
            teeka0_div, cfg, parent_bhaavarth_nk=secondary_bhaavarth_nk,
            source_ref=source_ref,
        )
    else:
        secondary_teeka = None

    base = GathaExtract(
        shastra_natural_key=cfg.shastra.natural_key,
        gatha_number=idx_entry.gatha_number,
        page_html_id=_parse_page_html_id(soup, cfg),
        html_filename=idx_entry.html_filename,
        adhikaar_hi=idx_entry.adhikaar_hi,
        adhikaar_number=idx_entry.adhikaar_number,
        heading_hi=idx_entry.heading_hi,
        prakrit_text=prakrit_text,
        sanskrit_text=sanskrit_text,
        hindi_chhands=hindi_chhands,
        anyavartha=anyavartha,
        primary_teeka=primary_teeka,
        secondary_teeka=secondary_teeka,
        prakrit_verse_marker=prakrit_verse_marker,
    )

    if "-" in idx_entry.gatha_number:
        parts = _expand_gatha_numbers(idx_entry.gatha_number)
        # For combined pages, the raw prakrit text carries one ॥M॥ marker per included
        # gatha (e.g. 112-113.html → markers ॥112॥, ॥113॥ for canonical 105, 106).
        # Use the markers list captured from raw text — `base.prakrit_text` has its
        # trailing marker stripped, so scanning it would miss the last gatha's marker.
        per_chunk_markers: list[str | None] = [None] * len(parts)
        for i in range(min(len(parts), len(prakrit_verse_markers))):
            per_chunk_markers[i] = prakrit_verse_markers[i]
        raw_prakrit_parts = _split_combined_text_by_markers(base.prakrit_text, parts)
        prakrit_parts = (
            [_clean_gatha_chunk(p, parts) for p in raw_prakrit_parts]
            if raw_prakrit_parts
            else None
        )
        raw_sanskrit_parts = _split_combined_text_by_markers(base.sanskrit_text, parts)
        sanskrit_parts = (
            [_clean_gatha_chunk(p, parts) for p in raw_sanskrit_parts]
            if raw_sanskrit_parts
            else None
        )
        hindi_chhand_parts: list[list[GathaHindiChhand]] = []
        for i in range(len(parts)):
            split_chhands: list[GathaHindiChhand] = []
            for ch in base.hindi_chhands:
                raw_split = _split_combined_text_by_markers(ch.text_hi, parts)
                cleaned_split = (
                    [_clean_gatha_chunk(t, parts) for t in raw_split] if raw_split else None
                )
                split_chhands.append(
                    ch.model_copy(
                        update={"text_hi": cleaned_split[i] if cleaned_split else ch.text_hi}
                    )
                )
            hindi_chhand_parts.append(split_chhands)
        return (
            [
                base.model_copy(
                    update={
                        "gatha_number": num,
                        "prakrit_text": prakrit_parts[i] if prakrit_parts else base.prakrit_text,
                        "sanskrit_text": sanskrit_parts[i] if sanskrit_parts else base.sanskrit_text,
                        "hindi_chhands": hindi_chhand_parts[i],
                        "is_combined_page": True,
                        "related_gatha_numbers": [p for p in parts if p != num],
                        "prakrit_verse_marker": per_chunk_markers[i],
                    }
                )
                for i, num in enumerate(parts)
            ],
            kalash_delta,
        )

    return [base], kalash_delta


def parse_secondary_kalash_page(
    soup: BeautifulSoup,
    filename: str,
    preceding_gatha: str | None,
    cfg: NJConfig,
    secondary_entry: "GathaIndexEntry | None" = None,
) -> list[KalashExtract]:
    """Parse a page that is only in the secondary teeka index.

    Returns one KalashExtract per individual gatha number when the secondary
    index encodes a multi-gatha range (e.g. "131-133" → 3 entries with split
    prakrit verses). Falls back to a single entry when the gatha_number is
    a single number or expansion/splitting fails.
    """
    prakrit_text, _sanskrit_text, _hindi_chhands, anyavartha, _prakrit_verse_markers = _parse_body_fields(soup, cfg)

    teeka0_div = soup.select_one(cfg.selectors.teeka0_div)

    raw_gatha_number = (
        secondary_entry.gatha_number if secondary_entry else Path(filename).stem.split("-")[0]
    )

    kalash_sec_cfg = cfg.shastra.secondary_teekas[0] if cfg.shastra.secondary_teekas else None
    try:
        norm_kalash = str(int(raw_gatha_number))
    except ValueError:
        norm_kalash = raw_gatha_number
    kalash_bhaavarth_nk = (
        f"{kalash_sec_cfg.publication_natural_key}:कलश:भावार्थ:{norm_kalash}"
        if kalash_sec_cfg else None
    )
    secondary_teeka = (
        parse_secondary_teeka(
            teeka0_div, cfg, parent_bhaavarth_nk=kalash_bhaavarth_nk,
            source_ref=f"{cfg.shastra.natural_key}/{filename} कलश {raw_gatha_number}",
        )
        if isinstance(teeka0_div, Tag) else None
    )

    heading = None
    title_link = soup.select_one(cfg.selectors.gatha_heading_link)
    if isinstance(title_link, Tag):
        heading = _clean(title_link.get_text()) or None

    parts = _expand_gatha_numbers(raw_gatha_number)

    base = KalashExtract(
        shastra_natural_key=cfg.shastra.natural_key,
        kalash_number=raw_gatha_number,
        html_filename=filename,
        heading_hi=heading,
        preceding_primary_gatha_number=preceding_gatha,
        prakrit_text=prakrit_text,
        anyavartha=anyavartha,
        secondary_teeka=secondary_teeka,
    )

    if len(parts) <= 1:
        return [base]

    raw_prakrit_parts = _split_combined_text_by_markers(prakrit_text, parts)
    prakrit_parts = (
        [_clean_gatha_chunk(c, parts) for c in raw_prakrit_parts] if raw_prakrit_parts else None
    )

    return [
        base.model_copy(
            update={
                "kalash_number": num,
                "prakrit_text": prakrit_parts[i] if prakrit_parts else prakrit_text,
            }
        )
        for i, num in enumerate(parts)
    ]
