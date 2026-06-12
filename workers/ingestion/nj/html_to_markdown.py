"""Convert BeautifulSoup nodes to Markdown strings for bhaavarth content."""

from __future__ import annotations

from bs4 import NavigableString, Tag

# Colors used as teekakar label decorators — strip these, don't wrap in color spans.
# Note: the top-level darkgreen teekakar label (e.g. <b><font color=darkgreen>अमृतचंद्राचार्य</font></b>)
# is already removed from nodes_after by parse_primary_teeka/parse_secondary_teeka,
# so darkgreen surviving here belongs to in-flow content (e.g. (हरिगीत) translation
# verses on pages like samaysaar 014.html) and should be preserved as a color span.
_STRIP_COLORS = {"red"}


def node_to_markdown(node: NavigableString | Tag, *, _depth: int = 0) -> str:
    """Recursively convert a BS4 node to a Markdown string."""
    if isinstance(node, NavigableString):
        return str(node)

    if not isinstance(node, Tag):
        return ""

    tag = node.name
    if not tag:
        return ""

    if tag in ("script", "style", "head"):
        return ""

    if tag == "br":
        return "\n"

    if tag == "hr":
        return "\n---\n"

    # Recursively convert children
    children_md = "".join(
        node_to_markdown(ch, _depth=_depth + 1) for ch in node.children
    )

    if tag == "b":
        # <b> containing a <div class="gadya"> is a Hindi chhand/translation
        # verse wrapper. The source styles div.gadya green via CSS (no inline
        # color attribute), so wrap children in an explicit color span so the
        # green formatting survives into the rendered bhaavarth markdown.
        gadya = node.find("div", class_="gadya")
        if gadya:
            # Hindi chhand/translation verse block. Source styles div.gadya
            # green via CSS (no inline color). Emit a self-contained block
            # with internal <br> separators so the verse lines stay tightly
            # spaced — teekaMarkdownToHtml splits paragraphs on `\n\n+`, so a
            # single-line HTML fragment renders as one <p> with all verse
            # lines joined by <br>.
            lines = [ln.strip() for ln in children_md.split("\n") if ln.strip()]
            inner = "<br>".join(lines)
            return f'<div class="nj-gadya" style="color:darkgreen">{inner}</div>'
        if node.find("div"):
            return children_md
        inner = children_md.strip()
        return f"**{inner}**" if inner else children_md

    if tag == "i":
        inner = children_md.strip()
        return f"*{inner}*" if inner else children_md

    if tag == "font":
        color = (node.get("color") or "").strip()
        if color.lower() in _STRIP_COLORS:
            return ""
        if color:
            return f'<span style="color:{color}">{children_md}</span>'
        return children_md

    if tag == "span":
        classes = node.get("class") or []
        if isinstance(classes, str):
            classes = classes.split()
        if "notes" in classes:
            inner = children_md.strip()
            return f"*({inner})*"
        if "comment" in classes:
            inner = children_md.strip()
            return f"*({inner})*"
        return children_md

    if tag == "ul":
        items: list[str] = []
        for ch in node.children:
            if isinstance(ch, Tag) and ch.name == "li":
                item_md = "".join(
                    node_to_markdown(c, _depth=_depth + 1) for c in ch.children
                ).strip()
                items.append(f"- {item_md}")
        return "\n".join(items) + "\n" if items else children_md

    if tag == "li":
        return f"- {children_md.strip()}\n"

    if tag == "a":
        classes = node.get("class") or []
        if isinstance(classes, str):
            classes = classes.split()
        if "nj-table-link" in classes:
            nk = node.get("data-table-nk", "")
            return f"[तालिका देखें](table://{nk})"
        return children_md

    # Block-level and generic tags: pass through children
    return children_md
