"""Block stream parsing: converts DOM elements into Block objects."""

from __future__ import annotations

import re
import re as _re
from typing import Optional, Iterator

from selectolax.parser import Node

from .config import JainkoshConfig
from .models import Block, Reference
from .normalize import normalize_text, nfc
from .refs import extract_refs_from_node, is_leading_reference_node, strip_refs_from_text
from .see_also import (
    find_see_also_candidates_in_element,
    find_see_alsos_in_element,
    strip_dekhen_redlink_substring,
    strip_paren_dekhen,
)
from .selectors import block_class_kind, is_gref_node, node_outer_html
from .tables import extract_table_block


def _render_inline(node: Node, config: JainkoshConfig) -> str:
    """Render a node's inline content, converting <br> to \\n and emphasis to markdown."""
    html = node.html or ""
    # br → newline
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    # Bold/strong → markdown
    if config.emphasis.bold_to_markdown:
        html = re.sub(r"<strong>([^<]*)</strong>", r"**\1**", html)
        html = re.sub(r"<b>([^<]*)</b>", r"**\1**", html)
    # Italic/em → markdown
    if config.emphasis.italic_to_markdown:
        html = re.sub(r"<em>([^<]*)</em>", r"*\1*", html)
        html = re.sub(r"<i>([^<]*)</i>", r"*\1*", html)
    # Strip remaining HTML tags
    text = re.sub(r"<[^>]+>", "", html)
    # Normalize per-line
    lines = text.split("\n")
    lines = [normalize_text(line) for line in lines]
    result = "\n".join(lines).strip()
    result = re.sub(r"\n{2,}", "\n", result)
    return result


def make_block(node: Node, config: JainkoshConfig, *, current_keyword: str = "") -> Optional[Block]:
    """Convert a single DOM element into a Block, or None if it should be dropped."""
    tag = node.tag
    if not tag or tag in ("-text", "#text", "script", "style"):
        return None

    if tag == "table":
        return extract_table_block(node, config)

    kind = block_class_kind(node, config)

    if kind is None:
        # Unknown block - emit warning-worthy but not crash
        return None

    # Get text content with inline rendering
    text = _render_inline(node, config)

    if not text:
        # Drop empty blocks
        return None

    # Extract trailing GRef spans (inline references)
    refs = extract_refs_from_node(node, config)

    # Check for see_also links
    see_alsos = find_see_alsos_in_element(
        node, config, current_keyword=current_keyword, as_index_relation=False
    )

    if config.redlink.prose_strip.enabled:
        for sa in see_alsos:
            if isinstance(sa, Block) and sa.target_exists is False:
                text = strip_dekhen_redlink_substring(
                    text=text,
                    anchor_text=sa.target_keyword or "",
                    triggers=config.index.see_also_triggers,
                    connector_re=config.redlink.prose_strip.connector_re,
                )

    text = strip_refs_from_text(text, refs, config)
    text = strip_paren_dekhen(text, config)
    if not text.strip():
        return None

    block = Block(
        kind=kind,
        text_devanagari=text,
        references=refs,
    )

    return block, see_alsos  # type: ignore[return-value]


def _strip_eq_prefix(text: str) -> str:
    """Remove the leading '=' translation marker and trim."""
    if text.startswith("="):
        text = text[1:].lstrip()
    return text


def _is_translation_block(block: Block, config: JainkoshConfig) -> bool:
    return (
        block.kind in config.translation_marker.hindi_kinds
        and block.text_devanagari is not None
        and block.text_devanagari.lstrip().startswith(config.translation_marker.prefix)
    )


def _is_row_style_element(el: Node, config: JainkoshConfig) -> bool:
    """Return True if element is a row-style bullet entry (• label - देखें target).

    Row-style entries should NOT contribute prose or see_also to the parent block
    stream; their see_also belongs in the corresponding child label-seed subsection.
    """
    raw_text = el.text(strip=True) or ""
    # Must start with a bullet (not '-', which is too general)
    bullet_chars = [b for b in config.label_to_topic.bullet_prefixes if b != "-"]
    if not any(raw_text.startswith(b) for b in bullet_chars):
        return False
    # Must contain a dash-trigger pattern (checked BEFORE any stripping)
    triggers_alt = "|".join(
        re.escape(t) for t in sorted(config.index.see_also_triggers, key=len, reverse=True)
    )
    dash_trigger_re = re.compile(r"[\-–]\s*(?:" + triggers_alt + r")")
    if not dash_trigger_re.search(raw_text):
        return False
    # Must have at least one see_also anchor
    candidates = find_see_also_candidates_in_element(el, config)
    return bool(candidates)


def parse_block_stream(
    elements: list[Node],
    config: JainkoshConfig,
    *,
    current_keyword: str = "",
) -> list[Block]:
    """Parse a list of DOM elements into a block stream, handling translation markers."""
    out: list[Block] = []
    pending_refs: list[Reference] = []
    last_block: Optional[Block] = None
    prev_element: Optional[Node] = None

    for el in flatten_for_blocks(elements, config, current_keyword=current_keyword):
        tag = el.tag if hasattr(el, 'tag') else None
        if not tag:
            continue

        if tag in ("-text", "#text", "script", "style"):
            continue

        if tag == "table":
            tblock = extract_table_block(el, config)
            tblock.references.extend(pending_refs)
            pending_refs.clear()
            out.append(tblock)
            last_block = tblock
            continue

        if is_leading_reference_node(el, config):
            pending_refs.extend(extract_refs_from_node(el, config))
            continue

        if _is_row_style_element(el, config):
            prev_element = el
            continue

        # Check sibling_eq marker before splitting so synthetic nodes don't break context
        saw_sibling_eq = _has_eq_text_marker_between(prev_element, el, config)

        # Only split when not in a translation-absorption context (preserves sibling_eq)
        if config.reference_splitting.enabled and not saw_sibling_eq:
            sub_els = split_element_at_inline_refs(el, config)
        else:
            sub_els = [el]

        for sub_el in sub_els:
            result = make_block(sub_el, config, current_keyword=current_keyword)
            if result is None:
                continue

            if isinstance(result, tuple):
                block, see_alsos = result
            else:
                block = result
                see_alsos = []

            if (
                saw_sibling_eq
                and last_block is not None
                and last_block.kind in config.translation_marker.source_kinds
                and block.kind in config.translation_marker.hindi_kinds
            ):
                last_block.hindi_translation = strip_paren_dekhen(
                    strip_refs_from_text(block.text_devanagari or "", block.references, config),
                    config,
                )
                if config.translation_marker.reference_ordering == "leading_then_inline":
                    last_block.references = list(last_block.references) + list(pending_refs) + list(block.references)
                else:
                    last_block.references = list(last_block.references) + list(block.references) + list(pending_refs)
                pending_refs.clear()
                # Translation absorbed; only applies once per original el
                saw_sibling_eq = False
            else:
                last_block, pending_refs, out = _emit(
                    block, last_block, pending_refs, out, config
                )

            for sa in see_alsos:
                if isinstance(sa, Block):
                    out.append(sa)

        prev_element = el

    # Trailing refs attach to last block
    if pending_refs and last_block is not None:
        last_block.references = list(last_block.references) + list(pending_refs)

    return _drop_see_also_only(out, config)


def _drop_see_also_only(blocks: list[Block], config: JainkoshConfig) -> list[Block]:
    if not config.see_also_only_block.enabled:
        return blocks
    pattern = re.compile(config.see_also_only_block.match_re)
    out: list[Block] = []
    pending_see_also: list[Block] = []
    for b in blocks:
        if b.kind == "see_also":
            pending_see_also.append(b)
            continue
        if (
            b.kind in config.see_also_only_block.prose_kinds
            and not b.hindi_translation
            and pattern.match(b.text_devanagari or "")
        ):
            for sa in pending_see_also:
                out.append(sa)
            pending_see_also = []
            continue
        for sa in pending_see_also:
            out.append(sa)
        pending_see_also = []
        out.append(b)
    for sa in pending_see_also:
        out.append(sa)
    return out


def _emit(
    block: Block,
    last_block: Optional[Block],
    pending_refs: list[Reference],
    out: list[Block],
    config: JainkoshConfig,
) -> tuple[Optional[Block], list[Reference], list[Block]]:
    """Emit a block, handling translation-marker absorption."""
    if _is_translation_block(block, config):
        if last_block is not None and last_block.kind in config.translation_marker.source_kinds:
            last_block.hindi_translation = strip_paren_dekhen(
                _strip_eq_prefix(block.text_devanagari or ""),
                config,
            )
            if config.translation_marker.reference_ordering == "leading_then_inline":
                last_block.references = list(last_block.references) + list(pending_refs) + list(block.references)
            else:
                last_block.references = list(last_block.references) + list(block.references) + list(pending_refs)
            pending_refs.clear()
            return last_block, pending_refs, out
        # Orphan translation
        block.is_orphan_translation = True
        block.text_devanagari = strip_paren_dekhen(
            _strip_eq_prefix(block.text_devanagari or ""),
            config,
        )

    block.references = list(pending_refs) + list(block.references)
    pending_refs.clear()
    out.append(block)
    return out[-1], pending_refs, out


def _has_eq_text_marker_between(
    previous: Optional[Node],
    current: Node,
    config: JainkoshConfig,
) -> bool:
    if not config.translation_marker.sibling_marker_enabled:
        return False
    if previous is None:
        return False
    prev_parent = previous.parent
    cur_parent = current.parent
    if prev_parent is None or cur_parent is None or not _same_node(prev_parent, cur_parent):
        return False
    text_parts: list[str] = []
    marker_found = False
    node = previous.next
    while node is not None and not _same_node(node, current):
        if (node.tag or "") not in ("-text", "#text"):
            return False
        txt = node.text(strip=False) or ""
        if txt.strip():
            text_parts.append(txt)
            marker_found = True
        node = node.next
    if node is None or not marker_found:
        return False
    joined = "".join(text_parts)
    return re.match(config.translation_marker.sibling_marker_text_node_re, joined) is not None


def _same_node(left: Node, right: Node) -> bool:
    if left is right:
        return True
    return (
        (left.tag or "") == (right.tag or "")
        and (left.html or "") == (right.html or "")
        and dict(left.attributes) == dict(right.attributes)
    )


def has_nested_block(node: Node, config: JainkoshConfig) -> bool:
    """Check if a node contains nested block-class elements."""
    # Use css("*") for deep traversal (iter() only returns direct children)
    for child in node.css("*"):
        if child == node:
            continue
        tag = child.tag or ""
        if tag in ("-text", "#text"):
            continue
        if block_class_kind(child, config) is not None:
            return True
    return False


def _split_at_inline_grefs(inner_html: str) -> list[str]:
    """
    Tokenise inner_html into text + GRef tokens.
    Start a new segment whenever non-trivial text follows accumulated GRefs.
    Returns a list of HTML strings (one per output block).
    """
    gref_re = _re.compile(
        r'<span\b[^>]*\bclass=["\']GRef["\'][^>]*>.*?</span>',
        _re.DOTALL,
    )

    tokens: list[tuple[str, str]] = []
    pos = 0
    for m in gref_re.finditer(inner_html):
        if m.start() > pos:
            tokens.append(("text", inner_html[pos:m.start()]))
        tokens.append(("gref", m.group(0)))
        pos = m.end()
    if pos < len(inner_html):
        tokens.append(("text", inner_html[pos:]))

    segments: list[str] = []
    current_html = ""
    pending_grefs: list[str] = []

    for kind, fragment in tokens:
        if kind == "text":
            prose = _re.sub(r"<[^>]+>", "", fragment).strip()
            # Only split when actual word characters (not just dandas/punctuation) follow a GRef
            if _re.search(r"\w", prose) and pending_grefs:
                segments.append(current_html + "".join(pending_grefs))
                current_html = fragment
                pending_grefs = []
            else:
                current_html += fragment
        else:
            pending_grefs.append(fragment)

    current_html += "".join(pending_grefs)
    if _re.sub(r"<[^>]+>", "", current_html).strip():
        segments.append(current_html)

    return segments


def split_element_at_inline_refs(
    el: Node,
    config: "JainkoshConfig",
) -> list[Node]:
    """
    If `el` is a text-block element of an applicable kind and has inline GRefs
    with prose after them, split into multiple synthetic nodes.
    Returns [el] unchanged when no split is needed or the feature is disabled.
    """
    from selectolax.parser import HTMLParser

    if not config.reference_splitting.enabled:
        return [el]

    kind = block_class_kind(el, config)
    if kind not in config.reference_splitting.applicable_block_kinds:
        return [el]

    html = el.html or ""
    start = html.find(">")
    end = html.rfind("<")
    if start < 0 or end <= start:
        return [el]
    inner = html[start + 1:end]

    segments = _split_at_inline_grefs(inner)
    if len(segments) <= 1:
        return [el]

    tag = el.tag or "p"
    cls = (el.attributes or {}).get("class", "HindiText")

    result: list[Node] = []
    for seg_html in segments:
        synthetic = f'<{tag} class="{cls}">{seg_html}</{tag}>'
        tree = HTMLParser(synthetic)
        node = tree.css_first(f"{tag}.{cls.split()[0]}")
        if node is not None:
            result.append(node)
    return result if result else [el]


def flatten_for_blocks(
    elements: list[Node],
    config: JainkoshConfig,
    *,
    current_keyword: str = "",
) -> list[Node]:
    """Flatten nested spans into a sequential list of blocks."""
    if not config.nested_span.flatten:
        return elements

    result = []
    for el in elements:
        kind = block_class_kind(el, config)
        if kind in config.nested_span.outer_kinds and has_nested_block(el, config):
            result.extend(_explode_nested_span(el, config))
        else:
            result.append(el)
    return result


def _explode_nested_span(span: Node, config: JainkoshConfig) -> list[Node]:
    """Flatten a nested-span element into a list of child blocks."""
    from selectolax.parser import HTMLParser

    results = []

    # 1. Collect GRefs that appear before the first nested block child
    #    and the direct text of the outer span
    outer_kind = block_class_kind(span, config)

    # Build the outer span's "direct text" from leading text nodes + leading GRefs
    # Strategy: iterate children; emit outer text/GRefs as synthetic nodes until
    # we hit a nested block, then switch to iterating children normally
    leading_text_parts = []
    leading_refs = []
    reached_nested = False

    span_html = span.html or ""
    inner_html = _get_inner_html(span)

    # Parse children
    children = list(span.iter(include_text=False))
    children = [c for c in children if c != span]

    # Find the first nested block child index
    first_nested_idx = -1
    for i, child in enumerate(children):
        kind = block_class_kind(child, config)
        if kind is not None and kind != outer_kind:
            first_nested_idx = i
            break
        if is_gref_node(child, config):
            continue
        # Check if child itself contains a nested block
        if kind == outer_kind and has_nested_block(child, config):
            first_nested_idx = i
            break

    # Collect the direct text from the outer span (not inside nested elements)
    # We do this by looking at text nodes that are direct children of span
    direct_text = _direct_text_of(span)
    if direct_text.strip():
        # Make a synthetic node for the outer span's direct text
        results.append(_make_synthetic_block(direct_text, outer_kind, config))

    # Now iterate direct children of the span (iter() gives direct children in selectolax)
    for child in span.iter(include_text=False):
        child_kind = block_class_kind(child, config)
        if is_gref_node(child, config):
            results.append(child)
        elif child_kind is not None:
            if child_kind in config.nested_span.outer_kinds and has_nested_block(child, config):
                results.extend(_explode_nested_span(child, config))
            else:
                results.append(child)
        else:
            # Unknown/other element - skip
            pass

    return results if results else [span]


def _direct_text_of(node: Node) -> str:
    """Get text nodes that are direct children of node (not inside nested elements)."""
    node_html = node.html or ""
    # Find the tag and strip outer tag
    inner = _get_inner_html(node)
    if not inner:
        return ""

    import re
    # Remove all child element content (keep only top-level text nodes)
    # This is approximate - remove any complete tags and their content
    depth = 0
    text_parts = []
    i = 0
    while i < len(inner):
        if inner[i] == "<":
            # Find end of tag
            end = inner.find(">", i)
            if end < 0:
                break
            tag_content = inner[i+1:end]
            if tag_content.startswith("/"):
                depth -= 1
            elif not tag_content.endswith("/"):
                depth += 1
            i = end + 1
        else:
            if depth == 0:
                text_parts.append(inner[i])
            i += 1

    raw = "".join(text_parts)
    # Also decode HTML entities
    raw = raw.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return normalize_text(raw)


def _get_inner_html(node: Node) -> str:
    """Get inner HTML of a node (content between opening and closing tags)."""
    html = node.html or ""
    # Find the first > (end of opening tag)
    start = html.find(">")
    if start < 0:
        return ""
    # Find the last < (start of closing tag)
    end = html.rfind("<")
    if end <= start:
        return ""
    return html[start+1:end]


def _make_synthetic_block(text: str, kind: str, config: JainkoshConfig) -> Node:
    """Create a synthetic HTML node wrapping text as a specific block kind."""
    from selectolax.parser import HTMLParser
    # Find the CSS class corresponding to this kind
    css_class = None
    for cls_name, k in config.block_classes.items():
        if k == kind:
            css_class = cls_name
            break
    if css_class is None:
        css_class = "HindiText"
    html = f'<p class="{css_class}">{text}</p>'
    tree = HTMLParser(html)
    return tree.css_first(f"p.{css_class}")
