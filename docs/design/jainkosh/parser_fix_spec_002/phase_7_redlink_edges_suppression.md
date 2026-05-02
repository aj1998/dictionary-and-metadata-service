# Phase 7 — Suppress redlink Topic↔Keyword edges

## Problem

In `आत्मा.json`'s `would_write.neo4j.edges`:

```jsonc
{
  "type": "RELATED_TO",
  "from": { "label": "Topic", "key": "आत्मा:गुण-स्थानों-की-अपेक्षा-बहिरात्मा-आदि-भेद" },
  "to":   { "label": "Keyword", "key": "वह वह नाम" },
  "props": { "weight": 1.0, "source": "jainkosh" }
}
```

The target `वह वह नाम` is a redlink (the source HTML anchor has
`class="new"` + `?action=edit&redlink=1`, see fixture `द्रव्य.html` line 470).
We do not want to materialise edges to non-existent Keyword nodes — the
target node will never resolve, so the edge is permanently dangling.

Rule: if `target_exists=False`, skip the edge entirely. This applies to
edges derived from both `IndexRelation` and `Block(kind="see_also")`.
The `see_also` *block* itself is still kept (so the parser-level
intermediate output preserves the information), and the alias-mining
flow can still pick up the redlink target name. Only the
`would_write.neo4j.edges` materialisation is suppressed.

## Failing tests (write first)

`workers/ingestion/jainkosh/tests/unit/test_redlink_edge_suppression.py`:

```python
from pathlib import Path
from workers.ingestion.jainkosh.config import load_config
from workers.ingestion.jainkosh.envelope import build_envelope
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html


def _env(name):
    html = Path(__file__).parents[1].joinpath("fixtures", f"{name}.html").read_text(encoding="utf-8")
    res = parse_keyword_html(html, f"https://example.org/wiki/{name}", load_config())
    return build_envelope(res).would_write


def test_no_keyword_edge_to_redlink_target_dravya():
    edges = _env("द्रव्य")["neo4j"]["edges"]
    bad = [e for e in edges if e.get("to", {}).get("key") == "वह वह नाम"]
    assert bad == [], bad


def test_redlink_edge_absent_for_index_relations():
    edges = _env("द्रव्य")["neo4j"]["edges"]
    for e in edges:
        if e.get("type") == "RELATED_TO":
            assert e.get("props", {}).get("target_exists", True) is not False


def test_redlink_see_also_block_still_present():
    from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
    html = Path(__file__).parents[1].joinpath("fixtures", "द्रव्य.html").read_text(encoding="utf-8")
    res = parse_keyword_html(html, "https://example.org/wiki/द्रव्य", load_config())

    def _walk(s):
        for x in s:
            yield x
            yield from _walk(x.children)

    found = False
    for sec in res.page_sections:
        for sub in _walk(sec.subsections):
            for b in sub.blocks:
                if b.kind == "see_also" and b.target_exists is False:
                    found = True
    assert found, "redlink see_also block was lost — only the edge should be suppressed"
```

Run: must FAIL.

## Config additions

`parser_configs/jainkosh.yaml`:

```yaml
neo4j:
  redlink_edges: "never"   # "always" | "never" | "only_if_topic"
```

`only_if_topic` allows edges to redlink **Topic** targets but not
redlink **Keyword** targets — included for completeness; default
`never`.

`config.py`:

```python
class Neo4jEnvelopeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    redlink_edges: Literal["always", "never", "only_if_topic"] = "never"


class JainkoshConfig(BaseModel):
    ...
    neo4j: Neo4jEnvelopeConfig = Field(default_factory=Neo4jEnvelopeConfig)
```

## Implementation

### 7.1 Filter in `envelope.py`

Both `_see_also_edge` and `_index_relation_edge` already know
`target_exists` — for `_see_also_edge` it's on the `block.target_exists`
field, for `_index_relation_edge` it's on `rel.target_exists`. Add a
helper:

```python
def _redlink_edge_allowed(target_exists: bool, to_node: dict, config) -> bool:
    if target_exists:
        return True
    mode = config.neo4j.redlink_edges
    if mode == "always":
        return True
    if mode == "never":
        return False
    if mode == "only_if_topic":
        return to_node.get("label") == "Topic"
    return False
```

Then in `_see_also_edge`, after computing `to_node` and `edge_type`,
check:

```python
if not _redlink_edge_allowed(block.target_exists, to_node, config):
    return {}
```

Same in `_index_relation_edge`:

```python
if not _redlink_edge_allowed(rel.target_exists, to_node, config):
    return {}
```

Thread `config` through both functions. `build_neo4j_fragment` already
has `result` so add `config: JainkoshConfig` to the `build_envelope` →
`build_neo4j_fragment` chain. (Currently `build_envelope` does not
receive config — it loads no YAML. Add a `config` parameter to
`build_envelope` and to all three `build_*_fragment` helpers, defaulting
to `load_config()` if the caller passes nothing. Update CLI to pass
config explicitly.)

### 7.2 Document

`docs/design/jainkosh/parsing_rules.md` §6.14 (NEW) — *Redlink edge
suppression in Neo4j fragment*.

## Definition of Done

- [ ] All three tests in `test_redlink_edge_suppression.py` pass.
- [ ] In `द्रव्य.json` regenerated golden, no edge has
      `to.key == "वह वह नाम"` (or any other redlink keyword target).
- [ ] `Subsection.blocks` for the source topic still contains the
      `see_also` block with `target_exists=false` — only the *edge*
      is gone.
- [ ] No regression on `mongo:topic_extracts` data — see-also block
      data still ships.
- [ ] No regression in fix-spec-001 phases.
