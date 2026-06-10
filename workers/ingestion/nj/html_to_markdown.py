"""Convert BeautifulSoup nodes to Markdown strings for bhaavarth content."""

from __future__ import annotations

from bs4 import NavigableString, Tag

# Colors used as teekakar label decorators — strip these, don't wrap in color spans
_STRIP_COLORS = {"darkgreen", "red"}


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
        # <b> containing a <div> is a kalash gadya wrapper — don't bold it
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
