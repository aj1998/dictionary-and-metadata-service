"""Extract <span class=shortFont> glossary entries + anchor offsets from bhaavarth nodes."""

from __future__ import annotations

import copy
import logging
import re
import unicodedata

from bs4 import BeautifulSoup, NavigableString, Tag

from .html_to_markdown import node_to_markdown
from .models import ShortFontAnchor, ShortFontEntry

logger = logging.getLogger(__name__)

_DEV_DIGIT_MAP: dict[str, int] = {
    "०": 0, "१": 1, "२": 2, "३": 3, "४": 4,
    "५": 5, "६": 6, "७": 7, "८": 8, "९": 9,
}
_ASCII_TO_DEV = str.maketrans("0123456789", "०१२३४५६७८९")
# Contiguous Devanagari + hyphen token (anchor candidate)
_DEV_TOKEN_RE = re.compile(r"[ऀ-ॿ\-]+")
# Leading dash variants (ASCII hyphen, en-dash, em-dash) + surrounding space that
# some glossary lines prefix to the headword, e.g. "<sup>3</sup> – आग्रह = …".
_LEADING_DASH_RE = re.compile(r"^[\s\-–—]+")


def _dev_to_int(text: str) -> int | None:
    """Marker text → unique int key. Devanagari/ASCII digits map to positive ints;
    asterisk runs (`*`, `**`, ...) map to negative ints (-1, -2, ...) so they get
    a distinct slot without colliding with numeric markers."""
    text = text.strip()
    if not text:
        return None
    if set(text) == {"*"}:
        return -len(text)
    result = 0
    for ch in text:
        if ch in _DEV_DIGIT_MAP:
            result = result * 10 + _DEV_DIGIT_MAP[ch]
        elif ch.isdigit():
            result = result * 10 + int(ch)
        else:
            return None
    return result


def _int_to_dev(n: int) -> str:
    if n < 0:
        return "*" * (-n)
    return str(n).translate(_ASCII_TO_DEV)


def _clean(text: str) -> str:
    return unicodedata.normalize("NFC", text.replace("﻿", "").replace("‍", "")).strip()


def _is_shortfont_span(node: NavigableString | Tag) -> bool:
    if not isinstance(node, Tag) or node.name != "span":
        return False
    classes = [c.lower() for c in (node.get("class") or [])]
    return "shortfont" in classes


def _find_and_remove_shortfont(wrapper: Tag) -> Tag | None:
    """Find the shortFont span anywhere in wrapper, extract it, and return it."""
    found = wrapper.find(lambda t: isinstance(t, Tag) and _is_shortfont_span(t))
    if found:
        found.extract()
        return found  # type: ignore[return-value]
    return None


def _parse_glossary_lines(sf_node: Tag) -> list[tuple[int, str, str, bool]]:
    """Parse shortFont block into (marker_number, anchor_text, meaning, is_definition) tuples.

    Splits by `<sup>` markers found anywhere in the block (document order) rather
    than by top-level `<br>` lines. Source HTML is frequently malformed — an
    unclosed `<span class=notes>` in one glossary line nests every following
    marker inside it, so `<br>`-based line grouping silently drops them (and their
    `<sup>` numbers leak into the preceding entry's text). Walking from each
    `<sup>` to the next and collecting the text in between is robust to that
    nesting because `find_all`/`next_elements` traverse the whole tree.
    """
    sups = sf_node.find_all("sup")

    results: list[tuple[int, str, str, bool]] = []
    for idx, sup in enumerate(sups):
        marker_num = _dev_to_int(_clean(sup.get_text()))
        if marker_num is None:
            continue

        next_sup = sups[idx + 1] if idx + 1 < len(sups) else None

        # Collect all text between this <sup> and the next one (document order),
        # regardless of how deeply it is nested by malformed/unclosed tags.
        text_parts: list[str] = []
        for elem in sup.next_elements:
            if elem is next_sup:
                break
            if isinstance(elem, NavigableString):
                # `next_elements` yields the <sup>'s own digit child first; skip
                # anything still inside this marker so the number doesn't leak in.
                if sup in elem.parents:
                    continue
                text_parts.append(str(elem))

        full_text = _clean("".join(text_parts)).rstrip("।").strip()
        if not full_text:
            continue

        if "=" in full_text:
            eq_idx = full_text.index("=")
            # Strip a leading dash ("– आग्रह = …") so the headword matches the body word.
            anchor_text = _clean(_LEADING_DASH_RE.sub("", _clean(full_text[:eq_idx])))
            meaning = _clean(full_text[eq_idx + 1:])
            results.append((marker_num, anchor_text, meaning, True))
        else:
            results.append((marker_num, "", full_text, False))

    return results


def _get_following_token(sup: Tag) -> str:
    """Return the contiguous Devanagari/hyphen token immediately following a <sup>."""
    nxt = sup.next_sibling
    if isinstance(nxt, NavigableString):
        text = str(nxt)
    elif isinstance(nxt, Tag):
        text = nxt.get_text()
    else:
        return ""
    # Strip leading whitespace before matching
    m = _DEV_TOKEN_RE.match(text.lstrip())
    return m.group(0) if m else ""


def extract_shortfont(
    nodes: list[NavigableString | Tag],
    warnings: list[str] | None = None,
    *,
    source_ref: str = "",
) -> tuple[str, list[ShortFontEntry]]:
    """Extract shortFont glossary from a list of bhaavarth nodes.

    Returns (cleaned_md, entries) where cleaned_md has sup digits and the
    shortFont block stripped, and entries carry per-marker meanings + offsets.

    `source_ref` (e.g. an HTML filename + gatha number) is prefixed onto every
    warning so they can be traced back to the source page during manual debugging.
    """
    if warnings is None:
        warnings = []
    ref = f"[{source_ref}] " if source_ref else ""

    # Wrap nodes in a shared parent BEFORE deep-copying so sibling relationships
    # (used by `_get_following_token`) survive the copy. Deep-copying each node
    # individually would detach them and break `.next_sibling`.
    wrapper = BeautifulSoup("<div></div>", "html.parser").div
    assert wrapper is not None
    for n in nodes:
        wrapper.append(copy.deepcopy(n))

    # 1. Locate and detach the shortFont span
    sf_span = _find_and_remove_shortfont(wrapper)

    # 2. Parse glossary
    glossary: dict[int, ShortFontEntry] = {}
    if sf_span is not None:
        for marker_num, anchor_text, meaning, is_def in _parse_glossary_lines(sf_span):
            glossary[marker_num] = ShortFontEntry(
                marker_number=marker_num,
                marker_devanagari=_int_to_dev(marker_num),
                anchor_text=anchor_text,
                meaning=meaning,
                is_definition=is_def,
                occurrences=[],
            )

    # 3. Walk body (before sup removal) to collect ordered anchor candidates.
    # `find_all("sup")` on the wrapper covers both top-level and nested sups.
    body_anchors: list[tuple[int, str]] = []
    for sup in wrapper.find_all("sup"):
        marker_num = _dev_to_int(_clean(sup.get_text()))
        if marker_num is None:
            continue
        body_anchors.append((marker_num, _get_following_token(sup)))

    # 4. Emit warnings for body/glossary mismatches
    glossary_markers = set(glossary.keys())
    body_markers = {mn for mn, _ in body_anchors}

    for mn in sorted(body_markers - glossary_markers):
        msg = f"{ref}shortfont_missing_glossary: marker {mn}"
        warnings.append(msg)
        logger.warning(msg)

    for mn in sorted(glossary_markers - body_markers):
        msg = f"{ref}shortfont_orphan_glossary: marker {mn}"
        warnings.append(msg)
        logger.warning(msg)

    # 5. Strip all <sup> nodes
    for sup in wrapper.find_all("sup"):
        sup.decompose()

    # 6. Build cleaned Markdown. Render the whole wrapper as a single tree so
    # inline siblings (NavigableString / span / font) stay on one line.
    # `<br>` already maps to `\n` inside `node_to_markdown`; consecutive `<br>`s
    # become a `\n\n` paragraph break.
    raw_md = node_to_markdown(wrapper)
    # Trim whitespace on each line and collapse 3+ newlines to 2 (paragraph break).
    lines = [ln.rstrip() for ln in raw_md.split("\n")]
    cleaned_md = "\n".join(lines)
    while "\n\n\n" in cleaned_md:
        cleaned_md = cleaned_md.replace("\n\n\n", "\n\n")
    # Break inline `**[word]**` (shabdaarth header) onto its own line so the UI
    # bhaavarth-segments parser detects each `[word] meaning` block. Source HTML
    # for some teekas (e.g. jayasenacharya samaysar) emits multiple
    # `<b>[word]</b> meaning … <b>[word]</b> meaning …` inline within one
    # paragraph; without a newline before each `**[`, only the first is parsed.
    cleaned_md = re.sub(r"(?<!\n)[ \t]*(\*\*\[)", r"\n\1", cleaned_md)
    # Ensure the meaning that follows `**[word]**` ends the line: cut after the
    # next danda (।) so the *next* `**[` starts cleanly even if no source break.
    # (Skip — we only need the leading newline; the trailing newline before the
    # next `**[` already comes from the same rule on the next match.)
    cleaned_md = unicodedata.normalize("NFC", cleaned_md).strip()

    # 7. Resolve each marker's effective anchor, then compute offsets (cursor-based).
    # First body following-token per marker (the word the <sup> annotates).
    body_candidate_by_marker: dict[int, str] = {}
    for marker_num, body_candidate in body_anchors:
        if body_candidate and marker_num not in body_candidate_by_marker:
            body_candidate_by_marker[marker_num] = body_candidate

    for entry in glossary.values():
        bc = body_candidate_by_marker.get(entry.marker_number)
        # Bare footnotes: anchor comes from the body token.
        if not entry.is_definition and not entry.anchor_text and bc:
            entry.anchor_text = bc
        # Definition headwords are sometimes a lemma that differs from the inflected
        # body word (e.g. असहायगुणवाला vs body असहायगुणात्मक). When the headword is not
        # present verbatim, fall back to the annotated body word so the offset can be
        # located and the round-trip invariant (cleaned_md[s:e] == anchor_text) holds.
        if entry.anchor_text and entry.anchor_text not in cleaned_md and bc and bc in cleaned_md:
            entry.anchor_text = bc

    cursor = 0
    for marker_num, body_candidate in body_anchors:
        entry = glossary.get(marker_num)
        if entry is None:
            continue

        anchor_text = entry.anchor_text
        if not anchor_text:
            logger.debug("shortfont: skipping offset for marker %d (no anchor_text)", marker_num)
            continue

        start = cleaned_md.find(anchor_text, cursor)
        if start == -1:
            # Anchor exists but lies *before* the cursor: glossary headwords are
            # sometimes longer compounds than the body word, so an earlier marker's
            # match can advance the cursor past a later marker's (earlier) body word.
            # Retry from the start, but skip a hit that merely re-points at an offset
            # already recorded for this entry (the collapsed duplicate-marker case,
            # where one body word serves several same-numbered footnotes).
            retry = cleaned_md.find(anchor_text)
            if retry != -1 and not any(o.start_offset == retry for o in entry.occurrences):
                start = retry
        if start == -1:
            msg = f"{ref}shortfont_anchor_not_found: marker {marker_num}, anchor={anchor_text!r}"
            warnings.append(msg)
            logger.warning(msg)
            continue
        end = start + len(anchor_text)
        entry.occurrences.append(ShortFontAnchor(start_offset=start, end_offset=end))
        cursor = max(cursor, end)

    entries = list(glossary.values())
    return cleaned_md, entries
