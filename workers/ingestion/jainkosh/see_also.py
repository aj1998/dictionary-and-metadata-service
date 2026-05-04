"""देखें (see_also) extraction utilities."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import unquote, urlparse, parse_qs

from selectolax.parser import Node

from .config import JainkoshConfig
from .models import Block, IndexRelation
from .normalize import nfc, normalize_text


def _build_see_also_re(config: JainkoshConfig) -> re.Pattern:
    return re.compile(config.index.see_also_text_pattern)


def is_redlink_anchor(a: Node, config: JainkoshConfig) -> bool:
    if not config.redlink.enabled:
        return False
    href = a.attributes.get("href", "") or ""
    if config.redlink.href_marker_substring in href:
        return True
    cls = (a.attributes.get("class", "") or "").split()
    if config.redlink.anchor_class in cls:
        title = a.attributes.get("title", "") or ""
        if re.match(config.redlink.title_marker_re, title):
            return True
    return False


def parse_anchor(a: Node, config: JainkoshConfig, *, current_keyword: str = "") -> dict:
    """Parse an <a> anchor into a see_also/IndexRelation field dict."""
    href = a.attributes.get("href", "") or ""
    cls = a.attributes.get("class", "") or ""

    if is_redlink_anchor(a, config):
        # Extract title from query string
        parsed_url = urlparse(href)
        qs = parse_qs(parsed_url.query)
        title = qs.get("title", [None])[0]
        if title:
            title = nfc(unquote(title)).replace("_", " ")
        else:
            title = normalize_text(a.text(strip=True) or "")
        return dict(
            target_keyword=title,
            target_topic_path=None,
            target_url=href,
            is_self=False,
            target_exists=False,
        )

    if config.index.self_link_class in cls.split():
        frag = href.lstrip("#")
        return dict(
            target_keyword=current_keyword or None,
            target_topic_path=frag or None,
            target_url=href,
            is_self=True,
            target_exists=True,
        )

    if href.startswith("/wiki/"):
        path_part = href[len("/wiki/"):]
        path, _, frag = path_part.partition("#")
        keyword = nfc(unquote(path, encoding="utf-8")).replace("_", " ")
        return dict(
            target_keyword=keyword,
            target_topic_path=frag or None,
            target_url=href,
            is_self=False,
            target_exists=True,
        )

    # Fallback
    return dict(
        target_keyword=None,
        target_topic_path=None,
        target_url=href,
        is_self=False,
        target_exists=True,
    )


def find_see_alsos_in_element(
    el: Node,
    config: JainkoshConfig,
    *,
    current_keyword: str = "",
    source_topic_path: Optional[str] = None,
    as_index_relation: bool = False,
) -> list[Block | IndexRelation]:
    """Find देखें links in an element. Returns Block or IndexRelation depending on context."""
    see_also_re = _build_see_also_re(config)
    nth_tracking = config.index.anchor_dedup.nth_occurrence_tracking
    anchor_occurrence_count: dict[tuple[str, str], int] = {}
    results = []

    for a in el.css("a"):
        a_html = a.html or ""
        parent_html_prefix = (a.parent.html or "")[:100] if a.parent else ""
        count_key = (parent_html_prefix, a_html)

        nth = 0
        if nth_tracking:
            nth = anchor_occurrence_count.get(count_key, 0)
            anchor_occurrence_count[count_key] = nth + 1

        prev_text = _preceding_inline_text(a, max_chars=config.index.see_also_window_chars, nth_occurrence=nth)
        if not see_also_re.search(prev_text):
            continue

        parsed = parse_anchor(a, config, current_keyword=current_keyword)
        label_text = _extract_label_before_anchor(a, nth_occurrence=nth)

        if as_index_relation:
            results.append(IndexRelation(
                label_text=label_text,
                source_topic_path=source_topic_path,
                **parsed,
            ))
        else:
            results.append(Block(
                kind="see_also",
                **{k: v for k, v in parsed.items()},
            ))

    return results


def find_see_also_candidates_in_element(
    el: Node,
    config: JainkoshConfig,
    *,
    current_keyword: str = "",
) -> list[dict]:
    see_also_re = _build_see_also_re(config)
    nth_tracking = config.index.anchor_dedup.nth_occurrence_tracking
    anchor_occurrence_count: dict[tuple[str, str], int] = {}
    results: list[dict] = []

    for a in el.css("a"):
        a_html = a.html or ""
        parent_html_prefix = (a.parent.html or "")[:100] if a.parent else ""
        count_key = (parent_html_prefix, a_html)

        nth = 0
        if nth_tracking:
            nth = anchor_occurrence_count.get(count_key, 0)
            anchor_occurrence_count[count_key] = nth + 1

        prev_text = _preceding_inline_text(a, max_chars=config.index.see_also_window_chars, nth_occurrence=nth)
        if not see_also_re.search(prev_text):
            continue
        parsed = parse_anchor(a, config, current_keyword=current_keyword)
        results.append({
            "label_text": _extract_label_before_anchor(a, nth_occurrence=nth),
            **parsed,
        })
    return results


def _preceding_inline_text(a: Node, max_chars: int = 40, nth_occurrence: int = 0) -> str:
    """Walk up ancestors concatenating text before <a> until max_chars is reached."""
    pieces: list[str] = []
    cur = a
    is_first_level = True
    while cur.parent is not None and sum(len(p) for p in pieces) < max_chars:
        parent = cur.parent
        parent_html = parent.html or ""
        cur_html = cur.html or ""

        if is_first_level and nth_occurrence > 0:
            idx = -1
            for _ in range(nth_occurrence + 1):
                new_idx = parent_html.find(cur_html, idx + 1)
                if new_idx < 0:
                    idx = parent_html.find(cur_html)
                    break
                idx = new_idx
        else:
            idx = parent_html.find(cur_html) if cur_html else -1

        is_first_level = False

        if idx > 0:
            before = parent_html[:idx]
            pieces.append(re.sub(r"<[^>]+>", "", before))
        cur = parent
    text = "".join(reversed(pieces))
    return text[-max_chars:] if len(text) > max_chars else text


def _extract_label_before_anchor(a: Node, nth_occurrence: int = 0) -> str:
    """Extract the label text immediately before the देखें trigger in the parent element."""
    parent = a.parent
    if parent is None:
        return ""
    parent_html = parent.html or ""
    a_html = a.html or ""

    # Find the nth_occurrence-th match of a_html in parent_html
    idx = -1
    for _ in range(nth_occurrence + 1):
        new_idx = parent_html.find(a_html, idx + 1)
        if new_idx < 0:
            idx = parent_html.find(a_html)
            break
        idx = new_idx

    if idx < 0:
        return ""
    before_html = parent_html[:idx]
    # Split on the rightmost separator to isolate the current item's text
    best_pos = -1
    best_sep_len = 0
    for sep in ("</a>", "<br/>", "<br >", "<br>", "</li>"):
        pos = before_html.rfind(sep)
        if pos > best_pos:
            best_pos = pos
            best_sep_len = len(sep)
    if best_pos >= 0:
        before_html = before_html[best_pos + best_sep_len:]
    label = re.sub(r"<[^>]+>", "", before_html)
    label = re.sub(r"[(–\-।\s]*(?:विशेष\s+)?देखें\s*$", "", label).strip()
    return normalize_text(label)


def strip_dekhen_redlink_substring(
    text: str,
    anchor_text: str,
    triggers: list[str],
    connector_re: str,
) -> str:
    if not text or not anchor_text:
        return text
    triggers_alt = "|".join(
        re.escape(t) for t in sorted(triggers, key=len, reverse=True)
    )
    connector = connector_re.rstrip("$")
    pattern = (
        r"(?P<connector>" + connector + r")"
        r"(?P<trigger>" + triggers_alt + r")"
        r"\s*" + re.escape(anchor_text) + r"\s*"
    )
    stripped = re.sub(pattern, "", text, count=1)
    return stripped.rstrip(" -–\t")


def strip_paren_dekhen(text: str, config: JainkoshConfig) -> str:
    if not text or not config.paren_dekhen_strip.enabled:
        return text
    triggers = config.index.see_also_triggers
    out = text
    for opn, cls in config.paren_dekhen_strip.bracket_pairs:
        if config.paren_dekhen_strip.trigger_required_inside:
            triggers_alt = "|".join(
                re.escape(t) for t in sorted(triggers, key=len, reverse=True)
            )
            pattern = re.compile(
                re.escape(opn) + r"[^" + re.escape(opn + cls) + r"]*?"
                + r"(?:" + triggers_alt + r")"
                + r"[^" + re.escape(opn + cls) + r"]*?" + re.escape(cls),
                flags=re.DOTALL,
            )
        else:
            pattern = re.compile(
                re.escape(opn) + r"[^" + re.escape(opn + cls) + r"]*?" + re.escape(cls),
                flags=re.DOTALL,
            )
        out = pattern.sub("", out)
    if config.paren_dekhen_strip.collapse_double_punct:
        out = re.sub(r"[ \t]{2,}", " ", out)
        out = re.sub(r"([।॥])\s*\n\s*([।॥])", r"\1\2", out)
        out = re.sub(r"\n[ \t]*\n", "\n", out)
    return out.strip()


def extract_label_before_trigger(text: str, config: JainkoshConfig) -> str:
    triggers = sorted(config.index.see_also_triggers, key=len, reverse=True)
    for trigger in triggers:
        idx = text.rfind(trigger)
        if idx <= 0:
            continue
        label = text[:idx]
        if config.label_to_topic.trim_to_clause:
            boundary_chars = config.label_to_topic.clause_boundary_chars
            last = -1
            for ch in boundary_chars:
                last = max(last, label.rfind(ch))
            if last >= 0:
                label = label[last + 1:]
        for bullet in config.label_to_topic.bullet_prefixes:
            label = label.lstrip(bullet)
        label = re.sub(r"[\-–]\s*$", "", label)
        label = label.strip(config.label_to_topic.label_trim_chars + " \t\n")
        return normalize_text(label)
    return ""
