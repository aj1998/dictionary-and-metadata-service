"""Block stream parsing: converts DOM elements into Block objects."""

from __future__ import annotations

import re
import re as _re
from typing import Optional, Iterator

from selectolax.parser import Node

from .config import JainkoshConfig
from .models import Block, Reference, SectionKind
from .normalize import normalize_text, nfc
from .refs import extract_refs_from_node, is_leading_reference_node, strip_refs_from_text
from .see_also import (
    extract_label_before_trigger,
    find_see_also_candidates_in_element,
    find_see_alsos_in_element,
    strip_dekhen_redlink_substring,
    strip_paren_dekhen,
)
from .selectors import block_class_kind, is_gref_node, node_outer_html
from .tables import extract_table_block


def _decode_html_entities(text: str) -> str:
    """Decode common HTML entities that survive tag stripping."""
    text = text.replace("&nbsp;", " ").replace("&#160;", " ").replace("&#xA0;", " ")
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&apos;", "'")
    return text


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
    # Decode HTML entities (e.g. &nbsp; → space, &amp; → &)
    text = _decode_html_entities(text)
    # Normalize per-line
    lines = text.split("\n")
    lines = [normalize_text(line) for line in lines]
    result = "\n".join(lines).strip()
    result = re.sub(r"\n{2,}", "\n", result)
    return result


def make_block(
    node: Node,
    config: JainkoshConfig,
    *,
    current_keyword: str = "",
    section_kind: SectionKind = "siddhantkosh",
) -> Optional[Block]:
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
    refs = extract_refs_from_node(node, config, inline=True, section_kind=section_kind)

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

    pre_strip = text
    text = strip_refs_from_text(text, refs, config)
    text = strip_paren_dekhen(text, config)
    if not text.strip():
        if config.blocks.preserve_see_alsos_on_empty_text and see_alsos:
            return None, see_alsos   # type: ignore[return-value]
        return None

    block = Block(
        kind=kind,
        text_devanagari=text,
        references=refs,
    )
    block._pre_strip_text = pre_strip
    if config.blocks.is_bullet_point_for_li and tag == "li":
        block.is_bullet_point = True

    return block, see_alsos  # type: ignore[return-value]


def _strip_eq_prefix(text: str) -> str:
    """Remove the leading '=' translation marker and trim."""
    if text.startswith("="):
        text = text[1:].lstrip()
    return text


def _strip_dekhen_trigger_lines(text: str, config: JainkoshConfig) -> str:
    """Strip lines starting with a देखें trigger and the following parenthesised/punct line.

    Used to clean translation text that embeds a देखें link inline:
      'prose.\nदेखें X - 1.2\n(label text)।'  →  'prose.'
    """
    triggers = sorted(config.index.see_also_triggers, key=len, reverse=True)
    triggers_alt = "|".join(re.escape(t) for t in triggers)
    trigger_re = re.compile(r"^\s*(?:" + triggers_alt + r")\s")
    lines = text.split("\n")
    result: list[str] = []
    skip_next = False
    for line in lines:
        stripped = line.strip()
        if skip_next:
            # Skip parenthesised label line, empty line, or pure-punct line
            if (re.match(r'^[-–.\s]*\(', stripped)
                    or not stripped
                    or re.match(r'^[।॥,;.\s]+$', stripped)):
                skip_next = False
                continue
            skip_next = False
        if trigger_re.match(stripped):
            skip_next = True
            continue
        result.append(line)
    return "\n".join(result).strip()


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


def _is_after_dekhen_element(el: Node, config: JainkoshConfig) -> bool:
    """Return True if element matches the after-dekhen pattern: देखें <link> text_after.

    Condition: element's text starts with a देखें trigger (only leading whitespace allowed
    before it), and there is text containing Devanagari characters after the anchor.
    These elements are skipped in the normal block stream and converted to label-seed
    child topics instead.
    """
    if not config.label_to_topic.enabled:
        return False
    raw_text = normalize_text(el.text(strip=False) or "")
    # Element must begin with the देखें trigger — only whitespace/bullets allowed before it
    triggers_alt = "|".join(
        re.escape(t) for t in sorted(config.index.see_also_triggers, key=len, reverse=True)
    )
    start_re = re.compile(r"^\s*(?:" + triggers_alt + r")\s", re.DOTALL)
    if not start_re.match(raw_text):
        return False
    # Must have at least one anchor with Devanagari text after it
    candidates = find_see_also_candidates_in_element(el, config)
    return any(
        bool(re.search(r"[ऀ-ॿ]", c.get("after_anchor_text") or ""))
        for c in candidates
    )


def _is_br_dekhen_element(el: Node, config: JainkoshConfig) -> bool:
    """Return True if element has <br/>-separated देखें lines but does NOT start with देखें.

    Detects patterns like:
      <span>initial prose...<br/>देखें <a>link</a> (label text).<br/>देखें ...</span>
    where the initial prose means _is_after_dekhen_element would return False.
    """
    if not config.label_to_topic.enabled:
        return False
    el_html = el.html or ""
    if not re.search(r"<br\b", el_html, re.IGNORECASE):
        return False
    raw_text = normalize_text(el.text(strip=False) or "")
    triggers_alt = "|".join(
        re.escape(t) for t in sorted(config.index.see_also_triggers, key=len, reverse=True)
    )
    start_re = re.compile(r"^\s*(?:" + triggers_alt + r")\s", re.DOTALL)
    if start_re.match(raw_text):
        return False  # Already handled by _is_after_dekhen_element
    candidates = find_see_also_candidates_in_element(el, config)
    return any(
        bool(re.search(r"[ऀ-ॿ]", c.get("after_anchor_text") or ""))
        for c in candidates
    )


def parse_block_stream(
    elements: list[Node],
    config: JainkoshConfig,
    *,
    current_keyword: str = "",
    section_kind: SectionKind = "siddhantkosh",
) -> list[Block]:
    """Parse a list of DOM elements into a block stream, handling translation markers."""
    out: list[Block] = []
    pending_refs: list[Reference] = []
    last_block: Optional[Block] = None
    prev_element: Optional[Node] = None
    _carry_sibling_eq: bool = False
    _carry_sibling_eq_prefix: str = ""

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
            pending_refs.extend(extract_refs_from_node(el, config, inline=False, section_kind=section_kind))
            continue

        if _is_row_style_element(el, config):
            prev_element = el
            continue

        if _is_after_dekhen_element(el, config):
            prev_element = el
            continue

        # Check sibling_eq marker before splitting so synthetic nodes don't break context.
        # If a transparent wrapper (strong/b) was skipped in the previous iteration while
        # sibling_eq was active, carry the flag forward rather than recomputing from DOM.
        if _carry_sibling_eq:
            sibling_eq_prefix = _carry_sibling_eq_prefix
            saw_sibling_eq = True
            _carry_sibling_eq = False
            _carry_sibling_eq_prefix = ""
        else:
            sibling_eq_prefix = _get_eq_sibling_prefix(prev_element, el, config)
            saw_sibling_eq = sibling_eq_prefix is not None

        # Only split when not in a translation-absorption context (preserves sibling_eq)
        if config.reference_splitting.enabled and not saw_sibling_eq:
            sub_els = split_element_at_inline_refs(el, config)
        else:
            sub_els = [el]

        for sub_el in sub_els:
            result = make_block(sub_el, config, current_keyword=current_keyword, section_kind=section_kind)
            if result is None:
                # When a transparent inline wrapper (strong/b) sits directly after the "="
                # sibling marker and produces no block, carry the marker forward to the
                # next element and accumulate the wrapper's text into the prefix so it
                # becomes part of the translation (e.g. <strong><span HindiText>प्रश्न).
                if saw_sibling_eq and (sub_el.tag or "") in ("strong", "b"):
                    inner_text = normalize_text(sub_el.text() or "")
                    if inner_text and config.emphasis.bold_to_markdown:
                        inner_text = f"**{inner_text}**"
                    _carry_sibling_eq = True
                    _carry_sibling_eq_prefix = (sibling_eq_prefix or "") + inner_text
                continue

            if isinstance(result, tuple):
                block, see_alsos = result
                if block is None:
                    # text was fully stripped but see_alsos survived
                    for sa in see_alsos:
                        if isinstance(sa, Block):
                            out.append(sa)
                    continue
            else:
                block = result
                see_alsos = []

            if (
                saw_sibling_eq
                and last_block is not None
                and last_block.kind in config.translation_marker.source_kinds
                and block.kind in config.translation_marker.hindi_kinds
            ):
                translation_text = (sibling_eq_prefix or "") + (block.text_devanagari or "")
                tl = strip_paren_dekhen(
                    strip_refs_from_text(translation_text, block.references, config),
                    config,
                )
                tl = _strip_dekhen_trigger_lines(tl, config)
                last_block.hindi_translation = tl
                # Store pre-strip translation for inline-ref position detection in _do_split
                last_block._hindi_translation_pre_strip = (
                    (sibling_eq_prefix or "")
                    + (block._pre_strip_text or block.text_devanagari or "")
                )
                if config.translation_marker.reference_ordering == "leading_then_inline":
                    last_block.references = list(last_block.references) + list(pending_refs) + list(block.references)
                else:
                    last_block.references = list(last_block.references) + list(block.references) + list(pending_refs)
                pending_refs.clear()
                # Translation absorbed; only applies once per original el
                saw_sibling_eq = False
                sibling_eq_prefix = None
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

    return split_multi_verse_blocks(_drop_see_also_only(out, config), config)


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
            tl_text = _strip_eq_prefix(block.text_devanagari or "")
            tl_text = strip_paren_dekhen(tl_text, config)
            # Strip embedded देखें trigger lines (e.g. '\nदेखें X\n(label)।') from translation
            tl_text = _strip_dekhen_trigger_lines(tl_text, config)
            last_block.hindi_translation = tl_text
            # Store pre-strip translation for inline-ref position detection in _do_split
            last_block._hindi_translation_pre_strip = _strip_eq_prefix(
                block._pre_strip_text or block.text_devanagari or ""
            )
            if config.translation_marker.reference_ordering == "leading_then_inline":
                last_block.references = list(last_block.references) + list(pending_refs) + list(block.references)
            else:
                last_block.references = list(last_block.references) + list(block.references) + list(pending_refs)
            pending_refs.clear()
            return last_block, pending_refs, out
        # Orphan translation
        block.is_orphan_translation = True
        tl_text = _strip_eq_prefix(block.text_devanagari or "")
        tl_text = strip_paren_dekhen(tl_text, config)
        tl_text = _strip_dekhen_trigger_lines(tl_text, config)
        block.text_devanagari = tl_text

    block.references = list(pending_refs) + list(block.references)
    pending_refs.clear()
    out.append(block)
    return out[-1], pending_refs, out


def _get_eq_sibling_prefix(
    previous: Optional[Node],
    current: Node,
    config: JainkoshConfig,
) -> Optional[str]:
    """Return the text prefix after '=' if an eq-sibling marker exists between previous and current.

    Returns None if no marker found.
    Returns "" if marker is exactly '=' with no trailing text.
    Returns a non-empty string (e.g. "'") if the text node is "='" — the prefix should be
    prepended to the translation text.
    """
    if not config.translation_marker.sibling_marker_enabled:
        return None
    if previous is None:
        return None
    prev_parent = previous.parent
    cur_parent = current.parent
    if prev_parent is None or cur_parent is None or not _same_node(prev_parent, cur_parent):
        return None
    text_parts: list[str] = []
    marker_found = False
    node = previous.next
    while node is not None and not _same_node(node, current):
        if (node.tag or "") not in ("-text", "#text"):
            return None
        txt = node.text(strip=False) or ""
        if txt.strip():
            text_parts.append(txt)
            marker_found = True
        node = node.next
    if node is None or not marker_found:
        return None
    joined = "".join(text_parts)
    # Exact match (configured regex): = with no trailing content
    if re.match(config.translation_marker.sibling_marker_text_node_re, joined):
        return ""
    # Extended match: = optionally followed by a short prefix (e.g. "='")
    m = re.match(r'^\s*=\s*(?P<prefix>.+?)\s*$', joined)
    if m:
        return m.group("prefix")
    return None


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


def _is_block_span_container(el: Node, config: JainkoshConfig) -> bool:
    """Return True if el's direct element children are ALL GRef spans, block-classed
    elements, <br> tags, or transparent inline wrappers (<strong>/<b>) — i.e. it's a
    classless wrapper around block-level spans."""
    has_block = False
    for child in el.iter(include_text=False):
        if child is el:
            continue
        tag = child.tag or ""
        if tag in ("-text", "#text"):
            continue
        cls = child.attributes.get("class", "") or ""
        if "GRef" in cls.split() and tag == "span":
            continue
        if tag == "br":
            continue
        if tag in ("strong", "b"):
            # Transparent inline bold wrappers (e.g. <strong><span class="HindiText">)
            continue
        if block_class_kind(child, config) is not None:
            has_block = True
            continue
        return False
    return has_block


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
        elif kind is None and _is_block_span_container(el, config):
            # Classless container (e.g. bare <p>) whose direct children are only
            # GRef/block-class spans and <br>. Extract direct children so the
            # block stream sees them individually.
            children = [c for c in el.iter(include_text=False) if c != el]
            result.extend(children) if children else result.append(el)
        else:
            result.append(el)
    return result


def _explode_nested_span(span: Node, config: JainkoshConfig) -> list[Node]:
    """Flatten a nested-span element into a list of child blocks.

    When reattach is enabled, GRefs before the last <br/> boundary stay with the
    outer block and GRefs after that boundary are emitted before the first nested
    block so they attach to that nested block.
    """
    outer_kind = block_class_kind(span, config)
    if outer_kind is None:
        return [span]

    children = list(span.iter(include_text=False))
    children = [c for c in children if c != span]

    first_nested_idx = -1
    for i, child in enumerate(children):
        child_kind = block_class_kind(child, config)
        if child_kind is not None and child_kind != outer_kind:
            first_nested_idx = i
            break
        if child_kind == outer_kind and has_nested_block(child, config):
            first_nested_idx = i
            break

    if not config.blocks.nested_span_gref_reattach:
        return _explode_nested_span_legacy(span, config, outer_kind=outer_kind, children=children)

    if first_nested_idx < 0:
        direct_text = _direct_text_of(span)
        if direct_text.strip():
            return [_make_synthetic_block(direct_text, outer_kind, config)]
        return [span]

    pre_nested = children[:first_nested_idx]

    boundary_tags = {
        tag.lower()
        for tag in config.blocks.nested_span_gref_boundary_tags
    }
    last_boundary_idx = -1
    for i, child in enumerate(pre_nested):
        if (child.tag or "").lower() in boundary_tags:
            last_boundary_idx = i

    trailing_gref_indices = {
        i
        for i, child in enumerate(pre_nested)
        if is_gref_node(child, config) and (last_boundary_idx < 0 or i <= last_boundary_idx)
    }

    results: list[Node] = []
    outer_html_parts: list[str] = []
    direct_text = _direct_text_of(span)
    if direct_text.strip():
        outer_html_parts.append(direct_text)
    outer_html_parts.extend(
        child.html or ""
        for i, child in enumerate(pre_nested)
        if i in trailing_gref_indices and (child.html or "").strip()
    )

    if outer_html_parts:
        outer_html = " ".join(part.strip() for part in outer_html_parts if part.strip())
        if outer_html:
            results.append(_make_synthetic_block(outer_html, outer_kind, config))

    for i, child in enumerate(children):
        if i < first_nested_idx and i in trailing_gref_indices:
            continue
        child_kind = block_class_kind(child, config)
        if child_kind is not None and child_kind != outer_kind:
            if child_kind in config.nested_span.outer_kinds and has_nested_block(child, config):
                results.extend(_explode_nested_span(child, config))
            else:
                results.append(child)
        elif child_kind == outer_kind and has_nested_block(child, config):
            results.extend(_explode_nested_span(child, config))
        elif child_kind == outer_kind:
            results.append(child)
        elif is_gref_node(child, config):
            results.append(child)

    return results if results else [span]


def _explode_nested_span_legacy(
    span: Node,
    config: JainkoshConfig,
    *,
    outer_kind: str,
    children: list[Node],
) -> list[Node]:
    """Preserve the old nested-span flattening behavior behind the config flag."""
    results: list[Node] = []

    direct_text = _direct_text_of(span)
    if direct_text.strip():
        results.append(_make_synthetic_block(direct_text, outer_kind, config))

    for child in children:
        child_kind = block_class_kind(child, config)
        if is_gref_node(child, config):
            results.append(child)
        elif child_kind is not None:
            if child_kind in config.nested_span.outer_kinds and has_nested_block(child, config):
                results.extend(_explode_nested_span(child, config))
            else:
                results.append(child)

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


# ---------------------------------------------------------------------------
# Multi-verse block splitting (Issue: प्रवचनसार/19,96,98 style blocks)
# ---------------------------------------------------------------------------

def _find_verse_marker(text: str, n: int, pos: int) -> tuple[int, int]:
    """Find ।N। marker (with optional surrounding spaces) starting at pos.

    Returns (start, end) of the match or (-1, -1) if not found.
    """
    pattern = re.compile(r"।\s*" + str(n) + r"\s*।")
    m = pattern.search(text, pos)
    if m:
        return m.start(), m.end()
    return -1, -1


def _split_text_at_verse_markers(text: str, verse_numbers: list[int]) -> list[str]:
    """Split text at ।N। Devanagari verse-number markers (spaces around N allowed).

    Returns one segment per verse number. When a marker is absent the segment
    gets all text up to the next found marker (or all remaining for the last).
    """
    if not text or not verse_numbers:
        return [text] * len(verse_numbers) if verse_numbers else []

    segments: list[str] = []
    pos = 0

    for i, n in enumerate(verse_numbers[:-1]):
        _, end = _find_verse_marker(text, n, pos)
        if end != -1:
            segments.append(text[pos:end].strip())
            pos = end
        else:
            # Marker absent — give text up to the first available later marker
            found_later = False
            for next_n in verse_numbers[i + 1:]:
                _, next_end = _find_verse_marker(text, next_n, pos)
                if next_end != -1:
                    next_start, _ = _find_verse_marker(text, next_n, pos)
                    segments.append(text[pos:next_start].strip())
                    pos = next_start
                    found_later = True
                    break
            if not found_later:
                # No more markers — dump everything, pad with empty strings
                segments.append(text[pos:].strip())
                segments.extend([""] * (len(verse_numbers) - len(segments)))
                return segments

    # Last verse gets everything that remains
    segments.append(text[pos:].strip())
    return segments


def split_multi_verse_blocks(blocks: list[Block], config: JainkoshConfig) -> list[Block]:
    """Post-process block list: split each block whose non-inline references were
    all expanded from the same GRef text and carry distinct gatha values.

    Example:
        GRef "नयचक्र बृहद्/59-60" expands to refs [gatha=59, gatha=60].
        The PrakritText "...।59। ...।60।" is split into two blocks at ।59।.
    """
    result: list[Block] = []
    for block in blocks:
        result.extend(_try_split_multi_verse(block, config))
    return result


def _auto_detect_verse_numbers(text: str) -> list[int]:
    """Extract verse numbers from ।N। markers (with optional spaces) in text."""
    return sorted({int(m.group(1)) for m in re.finditer(r"।\s*(\d+)\s*।", text)})


def _nums_in_text_order(text: str, nums: list[int]) -> list[int]:
    """Return nums ordered by their first occurrence position in text."""
    positions = []
    for n in nums:
        start, _ = _find_verse_marker(text, n, 0)
        if start != -1:
            positions.append((start, n))
    return [n for _, n in sorted(positions)]


def _order_pairs_by_text_position(
    pairs: list[tuple],
    src_text: str,
) -> list[tuple]:
    """Order (ref, gatha_value) pairs by sequential marker appearance in src_text.

    Uses a greedy scan so duplicate values (e.g. [168, 15, 168]) are assigned
    to their respective sequential occurrence rather than all mapping to the first.
    """
    ordered: list[tuple] = []
    remaining = list(pairs)
    pos = 0
    while remaining:
        best_start = -1
        best_idx = -1
        best_end = pos
        for i, (_, v) in enumerate(remaining):
            start, end = _find_verse_marker(src_text, v, pos)
            if start != -1 and (best_start == -1 or start < best_start):
                best_start = start
                best_end = end
                best_idx = i
        if best_idx == -1:
            ordered.extend(remaining)
            break
        ordered.append(remaining.pop(best_idx))
        pos = best_end
    return ordered


def _try_split_multi_verse(block: Block, config: JainkoshConfig) -> list[Block]:
    """Try to split one block at verse markers. Returns [block] if not applicable."""
    if block.kind not in config.reference_splitting.applicable_block_kinds:
        return [block]

    non_inline = [r for r in block.references if not r.inline_reference]
    inline_refs = [r for r in block.references if r.inline_reference]

    gatha_field_names = set(config.reference.entity_keywords.gatha)

    def _gatha_value(r: Reference) -> Optional[int]:
        for rf in r.resolved_fields:
            if rf.field in gatha_field_names and isinstance(rf.value, int):
                return rf.value
        return None

    # --- Case A: multiple non-inline refs from same GRef text ---
    # Guard: only split when BOTH text_devanagari AND hindi_translation have
    # the required verse markers (same policy as Case B). Without a matching
    # translation the split produces stub blocks with no translation context.
    if len(non_inline) >= 2:
        ref_texts = {r.text for r in non_inline}
        if len(ref_texts) == 1:
            pairs = [(r, _gatha_value(r)) for r in non_inline]
            if not any(v is None for _, v in pairs):
                # Order refs by their marker's sequential position in src text
                # (not ascending numeric value) to handle cases like 168,15,168
                # where the GRef list order matches text order, not ascending order.
                src_for_order = block.text_devanagari or ""
                pairs = _order_pairs_by_text_position(pairs, src_for_order)  # type: ignore[arg-type]
                ordered_refs = [r for r, _ in pairs]
                ordered_nums = [v for _, v in pairs]  # type: ignore[misc]
                # Guard: all gatha values must appear as ।N। markers in the
                # source text. When a GRef lists e.g. 22,27,31 but the Prakrit
                # text only has markers 22, 26, 31 (verse numbering mismatch),
                # Case A must not run — it would create an empty third block.
                # Fall through to Case B which splits on common src+tl markers.
                src_nums_a = set(_auto_detect_verse_numbers(src_for_order))
                if not all(n in src_nums_a for n in ordered_nums):
                    pass  # fall through to Case B
                # Skip split when translation is present but contains NONE of the
                # verse markers (e.g. नयचक्र बृहद्/17-19 whose translation has no
                # ।17।/।18।/।19। markers — the translation covers the full range).
                elif (tl_text_a := block.hindi_translation) is not None:
                    tl_nums_a = _auto_detect_verse_numbers(tl_text_a)
                    if any(n in tl_nums_a for n in ordered_nums):
                        return _do_split(block, ordered_refs, ordered_nums, inline_refs)
                    # else: fall through (no verse markers in translation)
                else:
                    return _do_split(block, ordered_refs, ordered_nums, inline_refs)

    # --- Case C: equal-count independent-marker split ---
    # Applies when src and tl each have exactly N (≥ 2) verse markers with the
    # SAME count, even when their values differ (verse-numbering mismatch between
    # source language and translation).  The N unique non-inline refs (deduped by
    # gatha value, sorted ascending) are paired with the N verse pairs in order.
    #
    # Example: GRef 22,27,31 — Prakrit has markers [22,26,31], Hindi has [22,23,31].
    # Case A skips (27 absent from src).  Case C detects both have 3 markers,
    # splits src at [22,26,31] and tl at [22,23,31], producing 3 correctly-paired
    # blocks with refs ref22, ref27, ref31 respectively.
    src_text_c = block.text_devanagari or ""
    tl_text_c = block.hindi_translation or ""
    if src_text_c and tl_text_c:
        src_nums_c = _nums_in_text_order(src_text_c, list(set(_auto_detect_verse_numbers(src_text_c))))
        tl_nums_c = _nums_in_text_order(tl_text_c, list(set(_auto_detect_verse_numbers(tl_text_c))))
        if len(src_nums_c) >= 2 and len(src_nums_c) == len(tl_nums_c):
            # Dedup non_inline refs by gatha value, keeping first occurrence.
            # Sort ascending so they pair naturally with ascending src markers.
            seen_g: set[Optional[int]] = set()
            unique_refs_c: list[Reference] = []
            for r in non_inline:
                v = _gatha_value(r)
                if v not in seen_g:
                    seen_g.add(v)
                    unique_refs_c.append(r)
            unique_refs_c = sorted(unique_refs_c, key=lambda r: (_gatha_value(r) or 0))
            if len(unique_refs_c) == len(src_nums_c):
                return _do_split(
                    block, unique_refs_c, src_nums_c, inline_refs,
                    tl_nums=tl_nums_c,
                )

    # --- Case B: auto-detect from ।N। markers in text when both sides agree ---
    # Applies when: single-ref (matched or not), or no refs at all.
    # Only split if markers appear in BOTH text_devanagari AND hindi_translation.
    src_text = block.text_devanagari or ""
    tl_text = block.hindi_translation or ""
    if src_text and tl_text:
        src_nums = _auto_detect_verse_numbers(src_text)
        tl_nums = _auto_detect_verse_numbers(tl_text)
        # Intersect and order by position in src text (not ascending numeric value)
        # so that markers like ।168।...।15。 split in the correct order.
        common_nums = _nums_in_text_order(src_text, list(set(src_nums) & set(tl_nums)))
        if len(common_nums) >= 2:
            # Build one synthetic ref per split number from the first non-inline ref (if any)
            base_ref = non_inline[0] if non_inline else None
            split_refs: list[Optional[Reference]] = []
            for n in common_nums:
                if base_ref is not None:
                    # Clone ref with only this gatha value, preserving the
                    # existing gatha field name (e.g. "दोहक") if present.
                    from .models import ResolvedField
                    gatha_field_name = next(
                        (rf.field for rf in base_ref.resolved_fields if rf.field in gatha_field_names),
                        "गाथा",
                    )
                    new_resolved = [ResolvedField(field=rf.field, value=rf.value)
                                    for rf in base_ref.resolved_fields
                                    if rf.field not in gatha_field_names]
                    new_resolved.append(ResolvedField(field=gatha_field_name, value=n))
                    split_refs.append(Reference(
                        text=base_ref.text,
                        inline_reference=False,
                        needs_manual_match=base_ref.needs_manual_match,
                        is_teeka=base_ref.is_teeka,
                        teeka_name=base_ref.teeka_name,
                        shastra_name=base_ref.shastra_name,
                        match_method=base_ref.match_method,
                        resolved_fields=new_resolved,
                    ))
                else:
                    split_refs.append(None)
            return _do_split(block, split_refs, common_nums, inline_refs + non_inline[1:])

    return [block]


def _assign_inline_refs_to_segments(
    inline_refs: list[Reference],
    pre_strip_text: Optional[str],
    tl_split_nums: list[int],
    n_segments: int,
) -> dict[int, list[Reference]]:
    """Distribute inline refs to split segments based on their position in the
    pre-strip translation text relative to verse markers.

    A ref that appears immediately after ।N। belongs to the gatha-N segment —
    it is a footnote to that verse, not to the following verse.
    Falls back to placing all refs in the last segment when position cannot be
    determined (missing pre_strip_text or ref text not found).
    """
    result: dict[int, list[Reference]] = {i: [] for i in range(n_segments)}
    if not inline_refs:
        return result

    if not pre_strip_text or not tl_split_nums or len(tl_split_nums) < 2:
        result[n_segments - 1].extend(inline_refs)
        return result

    # End position of each tl verse marker in the pre-strip text.
    # -1 means the marker was not found.
    marker_ends: list[int] = []
    for n in tl_split_nums:
        _, end = _find_verse_marker(pre_strip_text, n, 0)
        marker_ends.append(end)

    for ref in inline_refs:
        pos = pre_strip_text.find(ref.text)
        if pos == -1:
            result[n_segments - 1].append(ref)
            continue
        # Assign to the segment corresponding to the most recently passed verse
        # marker: largest j where marker_ends[j] != -1 and marker_ends[j] <= pos.
        assigned = 0
        for j in range(n_segments):
            if marker_ends[j] != -1 and marker_ends[j] <= pos:
                assigned = j
            elif marker_ends[j] != -1:
                break
        result[assigned].append(ref)

    return result


def _do_split(
    block: Block,
    sorted_refs: list,
    sorted_nums: list[int],
    inline_refs: list[Reference],
    *,
    tl_nums: Optional[list[int]] = None,
) -> list[Block]:
    """Perform the actual text split and build new blocks.

    tl_nums: if provided, split the translation at these markers instead of
    sorted_nums (used by Case C when src and tl use different verse numbering).
    """
    src_segments = _split_text_at_verse_markers(block.text_devanagari or "", sorted_nums)
    _tl_split_nums = tl_nums if tl_nums is not None else sorted_nums
    tl_segments = (
        _split_text_at_verse_markers(block.hindi_translation, _tl_split_nums)
        if block.hindi_translation is not None
        else [None] * len(sorted_nums)
    )

    # Distribute inline refs by their position in the pre-strip translation text.
    inline_ref_map = _assign_inline_refs_to_segments(
        inline_refs,
        block._hindi_translation_pre_strip,
        _tl_split_nums,
        len(sorted_nums),
    )

    split_blocks: list[Block] = []
    for i, ref in enumerate(sorted_refs):
        tl = tl_segments[i] if tl_segments[i] else None
        refs_for_block = ([ref] if ref is not None else []) + inline_ref_map[i]
        b = Block(
            kind=block.kind,
            text_devanagari=src_segments[i] or None,
            hindi_translation=tl,
            references=refs_for_block,
            is_orphan_translation=block.is_orphan_translation,
            is_bullet_point=block.is_bullet_point,
        )
        split_blocks.append(b)

    return split_blocks
