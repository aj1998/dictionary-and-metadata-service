"""Parse primary teeka (div#teeka0) into structured kalash + bhaavarth fields."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from bs4 import NavigableString, Tag

from .config import NJConfig
from .html_to_markdown import node_to_markdown
from .models import KalashHindiEntry, KalashSanskritEntry, KalashWMEntry, PrimaryTeeka

_KALASH_RE = re.compile(r"\(कलश-([^)]+)\)")


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return unicodedata.normalize("NFC", text.replace("\ufeff", "")).strip()


def _clean_preserve_newlines(text: str | None) -> str:
    if not text:
        return ""
    normalized = unicodedata.normalize("NFC", text.replace("\ufeff", ""))
    lines = [ln.strip() for ln in normalized.splitlines()]
    return "\n".join([ln for ln in lines if ln]).strip()


def _get_text(node: NavigableString | Tag) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    if isinstance(node, Tag):
        return node.get_text(" ", strip=False)
    return ""


def _is_kalash_type_marker(node: NavigableString | Tag, color: str) -> bool:
    if isinstance(node, NavigableString):
        return False
    font = node if node.name == "font" else node.find("font")
    if not font:
        return False
    node_color = (font.get("color") or "").strip().lower()
    if node_color != color.lower():
        return False
    return bool(_KALASH_RE.search(_clean(font.get_text())))


def _extract_chhand_type(node: NavigableString | Tag) -> str:
    text = _clean(_get_text(node))
    m = _KALASH_RE.search(text)
    return _clean(m.group(1)) if m else ""


def _is_kalash_gadya(node: NavigableString | Tag) -> bool:
    return isinstance(node, Tag) and node.name == "b" and node.find("div", class_="gadya") is not None


def _is_kalash_word_meaning(node: NavigableString | Tag, color: str) -> bool:
    if not isinstance(node, Tag) or node.name != "b":
        return False
    font = node.find("font")
    return bool(font and (font.get("color") or "").strip().lower() == color.lower())


def _nodes_before_hr(parent: Tag, hr_selector: str) -> list[NavigableString | Tag]:
    out: list[NavigableString | Tag] = []
    hr = parent.select_one(hr_selector)
    for node in parent.children:
        if hr and node is hr:
            break
        out.append(node)
    return out


def _first_gadya_with_kalash_markers(parent: Tag, marker_color: str) -> Tag | None:
    for gadya in parent.select("div.gadya"):
        for f in gadya.find_all("font"):
            color = (f.get("color") or "").strip().lower()
            if color == marker_color.lower() and _KALASH_RE.search(_clean(f.get_text())):
                return gadya
    return None


def _parse_sanskrit_kalashes_from_gadya(
    gadya: Tag,
    marker_color: str,
    global_kalash_start: int,
) -> list[KalashSanskritEntry]:
    entries: list[KalashSanskritEntry] = []
    current_type: str | None = None
    current_parts: list[str] = []

    def flush() -> None:
        nonlocal current_type, current_parts
        if current_type and current_parts:
            text = _clean_preserve_newlines("".join(current_parts))
            if text:
                idx = len(entries) + 1
                entries.append(
                    KalashSanskritEntry(
                        local_kalash_index=idx,
                        global_kalash_index=global_kalash_start + idx - 1,
                        chhand_type=current_type,
                        text_san=text,
                    )
                )
        current_type = None
        current_parts = []

    for node in gadya.children:
        if _is_kalash_type_marker(node, marker_color):
            flush()
            current_type = _extract_chhand_type(node) or "unknown"
            continue
        if isinstance(node, Tag) and node.name == "br":
            if current_type and current_parts and not current_parts[-1].endswith("\n"):
                current_parts.append("\n")
            continue
        text = _clean(_get_text(node))
        if current_type and text:
            if current_parts and not current_parts[-1].endswith("\n"):
                current_parts.append(" ")
            current_parts.append(text)
    flush()
    return entries


def _parse_sanskrit_kalashes_from_nodes(
    nodes: list[NavigableString | Tag],
    marker_color: str,
    global_kalash_start: int,
) -> tuple[list[KalashSanskritEntry], str | None]:
    entries: list[KalashSanskritEntry] = []
    prose_parts: list[str] = []
    current_type: str | None = None
    current_parts: list[str] = []

    def flush() -> None:
        nonlocal current_type, current_parts
        if current_type and current_parts:
            text = _clean(" ".join(current_parts))
            if text:
                idx = len(entries) + 1
                entries.append(
                    KalashSanskritEntry(
                        local_kalash_index=idx,
                        global_kalash_index=global_kalash_start + idx - 1,
                        chhand_type=current_type,
                        text_san=text,
                    )
                )
        current_type = None
        current_parts = []

    for node in nodes:
        if _is_kalash_type_marker(node, marker_color):
            flush()
            current_type = _extract_chhand_type(node) or "unknown"
            continue
        text = _clean(_get_text(node))
        if not text:
            continue
        if current_type:
            current_parts.append(text)
        else:
            prose_parts.append(text)
    flush()
    prose = _clean("\n".join(prose_parts)) or None
    return entries, prose


def _gatha_teeka_sanskrit_from_steeka(steeka0: Tag, kalash_gadya: Tag | None, hr_selector: str) -> str | None:
    nodes = _nodes_before_hr(steeka0, hr_selector)
    parts: list[str] = []
    for n in nodes:
        if kalash_gadya is not None and isinstance(n, Tag) and n.find(kalash_gadya.name) is not None:
            # Skip the block that carries Sanskrit kalash verses.
            if n.find(lambda t: isinstance(t, Tag) and t is kalash_gadya):
                continue
        t = _clean(_get_text(n))
        if t:
            parts.append(t)
    text = _clean("\n".join(parts))
    return text or None


def _nodes_after_element(parent: Tag, element: Tag | None) -> list[NavigableString | Tag]:
    nodes = list(parent.children)
    if element is None:
        return nodes
    for i, node in enumerate(nodes):
        if node is element:
            return nodes[i + 1 :]
    return nodes


def _extract_chhand_from_notes_span(node: Tag) -> str:
    notes = node.find("span", class_="notes")
    if not notes:
        return ""
    m = _KALASH_RE.search(_clean(notes.get_text()))
    return _clean(m.group(1)) if m else ""


def _clean_gadya_text(node: Tag) -> str:
    gadya = node.find("div", class_="gadya")
    if not gadya:
        return ""
    text = gadya.get_text(" ", strip=False)
    for notes in gadya.select("span.notes"):
        notes_text = notes.get_text(" ", strip=False)
        if notes_text:
            text = text.replace(notes_text, " ")
    return _clean(text)


def _parse_kalash_wm(node: Tag, trailing_text: str = "") -> KalashWMEntry:
    font = node.find("font")
    source_word = _clean(font.get_text()).strip("[]").strip() if font else ""

    meaning_parts: list[str] = []
    if font and font.parent:
        for sib in font.next_siblings:
            if isinstance(sib, NavigableString):
                meaning_parts.append(str(sib))
            elif isinstance(sib, Tag):
                meaning_parts.append(sib.get_text(" ", strip=False))
    else:
        meaning_parts.append(node.get_text(" ", strip=False))

    combined_meaning = "".join(meaning_parts)
    if trailing_text:
        combined_meaning = f"{combined_meaning} {trailing_text}"

    return KalashWMEntry(source_word=source_word, meaning=_clean(combined_meaning.replace("]", "", 1)))


def parse_primary_teeka(
    teeka0_div: Tag,
    cfg: NJConfig,
    global_kalash_start: int,
) -> tuple[PrimaryTeeka, int]:
    """Parse div#teeka0 for primary teeka data; return (parsed, kalash_delta)."""
    steeka0 = teeka0_div.select_one(cfg.selectors.steeka0_div)
    kalash_san_entries: list[KalashSanskritEntry] = []
    gatha_teeka_san: str | None = None
    if steeka0:
        kalash_gadya = _first_gadya_with_kalash_markers(steeka0, cfg.selectors.kalash_type_marker_color)
        if kalash_gadya is not None:
            kalash_san_entries = _parse_sanskrit_kalashes_from_gadya(
                kalash_gadya,
                cfg.selectors.kalash_type_marker_color,
                global_kalash_start,
            )
            gatha_teeka_san = _gatha_teeka_sanskrit_from_steeka(steeka0, kalash_gadya, cfg.selectors.teeka_separator)
        else:
            nodes = _nodes_before_hr(steeka0, cfg.selectors.teeka_separator)
            kalash_san_entries, gatha_teeka_san = _parse_sanskrit_kalashes_from_nodes(
                nodes,
                cfg.selectors.kalash_type_marker_color,
                global_kalash_start,
            )

    nodes_after = _nodes_after_element(teeka0_div, steeka0)

    # Strip the primary label node from markdown/hindi parsing.
    if nodes_after and isinstance(nodes_after[0], Tag):
        maybe_label = nodes_after[0].find("font") if nodes_after[0].name == "b" else None
        if maybe_label and (maybe_label.get("color") or "").strip().lower() == "darkgreen":
            nodes_after = nodes_after[1:]

    hindi_counter = 0
    kalash_hindi_entries: list[KalashHindiEntry] = []
    kalash_wm_entries: dict[int, list[KalashWMEntry]] = defaultdict(list)
    bhaavarth_parts: list[str] = []

    i = 0
    while i < len(nodes_after):
        node = nodes_after[i]
        if _is_kalash_gadya(node):
            hindi_counter += 1
            kalash_hindi_entries.append(
                KalashHindiEntry(
                    local_kalash_index=hindi_counter,
                    global_kalash_index=global_kalash_start + hindi_counter - 1,
                    chhand_type=_extract_chhand_from_notes_span(node) or "unknown",
                    text_hi=_clean_gadya_text(node),
                )
            )
            i += 1
            continue
        if _is_kalash_word_meaning(node, cfg.selectors.kalash_word_meaning_color):
            trailing_parts: list[str] = []
            j = i + 1
            br_streak = 0
            saw_content = False
            while j < len(nodes_after):
                nxt = nodes_after[j]
                if _is_kalash_gadya(nxt) or _is_kalash_word_meaning(nxt, cfg.selectors.kalash_word_meaning_color):
                    break
                if isinstance(nxt, NavigableString):
                    txt = str(nxt)
                    if txt.strip():
                        trailing_parts.append(txt)
                        saw_content = True
                        br_streak = 0
                    else:
                        trailing_parts.append(txt)
                    j += 1
                    continue
                if isinstance(nxt, Tag) and nxt.name == "br":
                    br_streak += 1
                    trailing_parts.append("\n")
                    j += 1
                    # Two consecutive line breaks indicate end of this meaning block.
                    if saw_content and br_streak >= 2:
                        break
                    continue
                if isinstance(nxt, Tag) and nxt.name in {"span", "font", "i", "em", "u", "strong", "small"}:
                    inline_text = nxt.get_text(" ", strip=False)
                    if inline_text.strip():
                        trailing_parts.append(inline_text)
                        saw_content = True
                    br_streak = 0
                    j += 1
                    continue
                break
            kalash_wm_entries[hindi_counter].append(_parse_kalash_wm(node, trailing_text=_clean("".join(trailing_parts))))
            i = j
            continue
        md = node_to_markdown(node).strip()
        if md:
            bhaavarth_parts.append(md)
        i += 1

    result = PrimaryTeeka(
        kalash_san=kalash_san_entries,
        gatha_teeka_san=gatha_teeka_san,
        kalash_hindi=kalash_hindi_entries,
        kalash_word_meanings=dict(kalash_wm_entries),
        gatha_teeka_bhaavarth_md=_clean("\n".join(bhaavarth_parts)) or None,
    )

    return result, len(kalash_san_entries)
