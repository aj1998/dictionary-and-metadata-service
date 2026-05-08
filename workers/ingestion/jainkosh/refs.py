"""GRef extraction utilities."""

from __future__ import annotations

import re

from selectolax.parser import Node

from .config import JainkoshConfig
from .models import Reference, SectionKind
from .normalize import normalize_text
from .selectors import is_gref_node


def extract_ref_text(node: Node, config: JainkoshConfig) -> str:
    """Extract text from a GRef node, stripping inner anchors if configured."""
    if config.reference.strip_inner_anchors:
        # Remove any <a href> tags, keeping their text
        html = node.html or ""
        html = re.sub(r"<a[^>]*>", "", html)
        html = re.sub(r"</a>", "", html)
        from selectolax.parser import HTMLParser
        text = HTMLParser(html).text(strip=True) or ""
    else:
        text = node.text(strip=True) or ""
    return normalize_text(text)


def _split_gref_text(text: str, config: JainkoshConfig) -> list[str]:
    """Split a GRef text string at '); (' boundaries when configured."""
    if not config.reference.semicolon_split.enabled:
        return [text]
    parts = re.split(config.reference.semicolon_split.split_re, text)
    return [p.strip() for p in parts if p.strip()]


def extract_refs_from_node(
    node: Node,
    config: JainkoshConfig,
    *,
    inline: bool = False,
    section_kind: SectionKind = "siddhantkosh",
) -> list[Reference]:
    """Extract all GRef spans from a node, splitting at semicolons when configured.

    14A.1: section_kind="puraankosh" skips resolution entirely.
    14A.4: each text part may expand into multiple References (range/list fields).
    """
    refs = []
    for gref in node.css("span.GRef"):
        full_text = extract_ref_text(gref, config)
        if not full_text:
            continue
        parts = _split_gref_text(full_text, config)
        for part in parts:
            resolutions = _resolve_reference(part, config, section_kind=section_kind)
            inline_ref_value = inline if config.reference.annotate_inline_position else False
            for resolution in resolutions:
                refs.append(Reference(text=part, inline_reference=inline_ref_value, **resolution))
    return refs


def _resolve_reference(
    text: str,
    config: JainkoshConfig,
    *,
    section_kind: SectionKind = "siddhantkosh",
) -> list[dict]:
    # 14A.1: puraankosh sections skip structured resolution
    if (
        section_kind == "puraankosh"
        or config.reference.parse_strategy == "text_only"
        or config.shastra_registry is None
    ):
        return [{}]

    from .parse_reference import parse_reference_text
    results = parse_reference_text(text, config.shastra_registry, config.reference)
    return [
        {
            "needs_manual_match": r.needs_manual_match,
            "is_teeka": r.is_teeka,
            "teeka_name": r.teeka_name,
            "shastra_name": r.shastra_name,
            "match_method": r.match_method,
            "resolved_fields": r.resolved_fields,
        }
        for r in results
    ]


def is_leading_reference_node(node: Node, config: JainkoshConfig) -> bool:
    """Return True if this node is a leading reference (only GRefs as meaningful content)."""
    if is_gref_node(node, config):
        return True
    if node.tag != "p":
        return False
    # Check if the p contains only GRef spans (and whitespace/punctuation text)
    # Use direct children via iter() - they are direct children of p
    meaningful_children = []
    for child in node.iter(include_text=False):
        # iter() returns direct children only in selectolax
        tag = child.tag
        if not tag or tag in ("-text", "#text"):
            continue
        cls = child.attributes.get("class", "") or ""
        if "GRef" in cls.split():
            meaningful_children.append(("gref", child))
        else:
            meaningful_children.append(("other", child))

    if not meaningful_children:
        # Only text nodes - check if it's empty or punctuation
        text = normalize_text(node.text(strip=True) or "")
        return not text

    # Must have at least one gref and no "other" elements
    has_gref = any(kind == "gref" for kind, _ in meaningful_children)
    has_other = any(kind == "other" for kind, _ in meaningful_children)

    if has_other:
        return False

    # Also check: the direct text (not from children) should be trivial
    # Use a quick heuristic: strip all GRef text and see if what's left is trivial
    full_text = normalize_text(node.text(strip=True) or "")
    gref_texts = []
    for kind, child in meaningful_children:
        if kind == "gref":
            gref_texts.append(normalize_text(child.text(strip=True) or ""))

    remaining = full_text
    for gt in gref_texts:
        remaining = remaining.replace(gt, "", 1)
    remaining = re.sub(r"[,;\s]+", "", remaining)
    return not remaining


def strip_refs_from_text(text: str, refs: list[Reference], config: JainkoshConfig) -> str:
    """Remove inline reference text snippets from prose according to parser config."""
    if not config.ref_strip.enabled:
        return text
    out = text
    for ref in refs:
        if ref.text:
            out = out.replace(ref.text, " ")
    if config.ref_strip.collapse_orphan_parens:
        out = re.sub(r"\(\s*\)", "", out)
    if config.ref_strip.collapse_orphan_brackets:
        out = re.sub(r"\[\s*\]", "", out)
    if config.ref_strip.collapse_double_spaces:
        out = re.sub(r"[ \t]{2,}", " ", out)
        out = re.sub(r"\s*\n\s*", "\n", out)
    trim_chars = config.ref_strip.trim_trailing_chars
    if trim_chars:
        out = re.sub(r"^[" + re.escape(trim_chars) + r"]+", "", out)
    out = re.sub(r"[ \t]+([।॥;,])", r"\1", out)
    return out.strip()
