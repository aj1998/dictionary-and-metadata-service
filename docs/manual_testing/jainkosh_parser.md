# JainKosh Parser — Manual Testing Guide

Covers the parser-only stage: `workers/ingestion/jainkosh/`. No HTTP or DB writes.

## Prerequisites

```bash
pip install selectolax PyYAML jsonschema pydantic
```

## 1. Parse a single page

```bash
# Parse आत्मा and write envelope JSON to a file
python -m workers.ingestion.jainkosh.cli parse \
    samples/sample_html_jainkosh_pages/आत्मा.html \
    --out /tmp/atma_out.json \
    --frozen-time 2026-05-02T00:00:00Z

cat /tmp/atma_out.json | python -m json.tool | head -60
```

Expected output summary:
- `keyword_parse_result.keyword == "आत्मा"`
- 2 `page_sections`: `siddhantkosh`, `puraankosh`
- `warnings` is empty `[]`

## 2. Parse all three sample pages

```bash
for kw in आत्मा द्रव्य पर्याय; do
    python -m workers.ingestion.jainkosh.cli parse \
        "samples/sample_html_jainkosh_pages/${kw}.html" \
        --validate-only
    echo "✓ ${kw}"
done
```

## 3. Verify parse statistics via Python

```python
import sys
sys.path.insert(0, 'workers')
from ingestion.jainkosh.config import load_config
from ingestion.jainkosh.parse_keyword import parse_keyword_html

config = load_config()

pages = [
    ('samples/sample_html_jainkosh_pages/आत्मा.html', 'https://jainkosh.org/wiki/आत्मा'),
    ('samples/sample_html_jainkosh_pages/द्रव्य.html', 'https://jainkosh.org/wiki/द्रव्य'),
    ('samples/sample_html_jainkosh_pages/पर्याय.html', 'https://jainkosh.org/wiki/पर्याय'),
]

for fname, url in pages:
    with open(fname, encoding='utf-8') as f:
        html = f.read()
    result = parse_keyword_html(html, url, config)
    def count_subs(subs):
        t = len(subs)
        for s in subs: t += count_subs(s.children)
        return t
    for sec in result.page_sections:
        total = count_subs(sec.subsections)
        print(f'{result.keyword} [{sec.section_kind}]: defs={len(sec.definitions)}, idx={len(sec.index_relations)}, subs={total}')
    print(f'  warnings: {result.warnings}')
```

Expected output:
```
आत्मा [siddhantkosh]: defs=4, idx=0, subs=3
आत्मा [puraankosh]: defs=2, idx=0, subs=0
  warnings: []
द्रव्य [siddhantkosh]: defs=1, idx=21, subs=58
द्रव्य [puraankosh]: defs=1, idx=0, subs=0
  warnings: []
पर्याय [siddhantkosh]: defs=1, idx=0, subs=43
पर्याय [puraankosh]: defs=2, idx=0, subs=0
  warnings: []
```

## 4. Inspect subsection tree

```python
import sys
sys.path.insert(0, 'workers')
from ingestion.jainkosh.config import load_config
from ingestion.jainkosh.parse_keyword import parse_keyword_html

config = load_config()
with open('samples/sample_html_jainkosh_pages/पर्याय.html', encoding='utf-8') as f:
    html = f.read()
result = parse_keyword_html(html, 'https://jainkosh.org/wiki/पर्याय', config)

def print_tree(subs, indent=0):
    for s in subs:
        print(f'{"  " * indent}[{s.topic_path}] {s.heading_text[:50]}')
        print_tree(s.children, indent + 1)

for sec in result.page_sections:
    if sec.section_kind == 'siddhantkosh':
        print_tree(sec.subsections)
```

## 5. Inspect the envelope

```bash
python -m workers.ingestion.jainkosh.cli parse \
    samples/sample_html_jainkosh_pages/द्रव्य.html \
    --out /tmp/dravya.json

# Show Neo4j edges summary
python -c "
import json
with open('/tmp/dravya.json') as f: d = json.load(f)
edges = d['would_write']['neo4j']['edges']
from collections import Counter
c = Counter(e['type'] for e in edges)
print(c)
"
```

## 6. Run the full test suite

```bash
python -m pytest workers/ingestion/jainkosh/tests/ -v
```

All 95 tests should pass.

## 7. Sanity checks by page

| Page | Sections | SiddhantKosh defs | SiddhantKosh index_relations | Total subsections |
|------|----------|-------------------|------------------------------|-------------------|
| आत्मा | 2 | 4 | 0 | 3 |
| द्रव्य | 2 | 1 | 21 | 58 |
| पर्याय | 2 | 1 | 0 | 43 |

Known quirks:
- **आत्मा**: First subsection is `topic_path == "2"` — there is no `<b>1. …</b>` heading in the source HTML. The parser correctly does NOT synthesise a missing root.
- **द्रव्य**: Has one section-level table between subsections 3 and 4 (`extra_blocks[0].kind == "table"`).
- **पर्याय**: Subsections go 3 levels deep (`1.1.1`, `1.1.2`, …). V1 headings (`<strong id="N">`) are nested inside `<li class="HindiText">` elements — the DFS walker correctly recurses into block-class `<li>` elements that contain heading children.
