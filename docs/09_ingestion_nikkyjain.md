# 09 — Ingestion: nikkyjain

Reads `nikkyjain.github.io` HTML files from a **local clone** (no scraping). Extracts shastra metadata + per-gatha Prakrit / Sanskrit / Hindi chhand / anvayartha. Outputs to Postgres `shastras`, `gathas`, and Mongo `gatha_*` + `teeka_gatha_mapping` collections.

## Source structure (observed)

`sample_html_granths/<shastra_slug>/html/index.html` is one big HTML file containing:

- Title block: `<div class="hdr1">प्रवचनसार</div>`, author `<font size=20>- कुन्दकुन्दाचार्य</font>`.
- Top-level adhikaar index: `table.adhikarIndex` with `<a href='#ad1'>...</a>`.
- Gatha index: `table.mainIndex` rows `<td><b>NNN)</b></td><td><a href="#gatha-NNN">heading</a></td>`.
- For each gatha — anchored by `<div class="title" id="gatha-NNN">...</div>`:
  - Prakrit gatha: `<div class="gatha">…</div>`. Trailing `(N)` and `॥N॥` mark numbering.
  - Hindi chhand: `<div class="gadya">…</div>` (one or more).
  - Anvayartha (teeka mapping): `<div class="paragraph"><b>अन्वयार्थ : </b>… <b><font color=darkRed>[term]</font></b> meaning …</div>`.
  - Optional alternate anvayartha: `<div class="paragraph">प्रकारांतर से अन्वयार्थ - …</div>`.
  - Optional footnotes: `<div class="paragraph"><span class="shortFont">…</span></div>`.

There is **no** Sanskrit chhaya in `pravachansaar` index.html samples. Where Sanskrit is present (other shastras), the parser config selector handles it.

## Parser config (`parser_configs/nikkyjain/pravachansaar.yaml`)

```yaml
version: 1.0.0
source: nikkyjain
shastra:
  natural_key: pravachansaar
  title_hi: प्रवचनसार
  author:
    natural_key: kundkundacharya
    display_name_hi: कुन्दकुन्दाचार्य
    kind: acharya
  default_teeka:
    natural_key: pravachansaar:hindi-chhand
    teekakar_natural_key: nikkyjain
    notes: "Default chhand-based hindi presentation by nikkyjain"
input:
  index_html_path: "{NIKKYJAIN_LOCAL_PATH}/path/to/pravachansaar/html/index.html"
  encoding: utf-8
selectors:
  shastra_title: "div.hdr1"
  author_name: "font[size='20']"
  adhikaar_index_table: "table.adhikarIndex"
  adhikaar_anchors: "table.adhikarIndex a[href^='#ad']"
  gatha_anchor: "div.title[id^='gatha-']"
  gatha_heading_link: "div.title > span > a"      # the visible heading
  gatha_block: "div.gatha"                         # Prakrit
  sanskrit_block: "div.sanskrit"                   # may be absent
  chhand_block: "div.gadya"
  paragraph_block: "div.paragraph"
parsing:
  gatha_id_prefix: "gatha-"
  gatha_natural_key_pattern: "{shastra}:{gatha_number}"   # gatha_number is the suffix after gatha-
  number_suffix_regex: '\(\s*(\d+)\s*\)'                  # matches '(38)'
  trailing_dandas_regex: '॥\s*(\d+)\s*॥'                  # matches '॥39॥'
  anvayartha_marker: 'अन्वयार्थ\s*:'
  alt_anvayartha_marker: 'प्रकारांतर से अन्वयार्थ'
  tagged_term_pattern:
    open: '\['
    close: '\]'
review:
  auto_approve: false
```

A separate config file per shastra under `parser_configs/nikkyjain/`. Shared selectors are loaded from `parser_configs/nikkyjain/_base.yaml` and merged.

## Job structure

```
workers/ingestion/nikkyjain/
├── orchestrator.py
├── parse_index.py        # adhikaar + gatha numbers
├── parse_gatha.py        # one gatha block → GathaExtract
├── tagged_terms.py       # parse [term] meaning interleaving in anvayartha
├── models.py             # GathaExtract, AnvayarthaEntry
└── tests/
    ├── fixtures/
    │   └── pravachansaar_index_partial.html
    └── test_parse_gatha.py
```

## Pipeline

```
Celery task: nikkyjain.ingest_shastra(run_id, shastra_slug='pravachansaar')
  1. Load shastra config, register parser_config row, create ingestion_run
  2. Read index.html from local path
  3. Upsert author + shastra rows directly into Postgres (low ambiguity)
  4. Build adhikaar map: {gatha_number → adhikaar_heading}
  5. Iterate over each gatha_anchor:
       a. Parse → GathaExtract
       b. Build proposed payload
       c. Insert into ingestion_review_queue
  6. Stats + finish

On admin approve:
  apply_approved_gatha_payload(...)
    BEGIN
      pg.upsert_gatha(...)                                  -> gatha_id
      mongo.upsert_gatha_prakrit(natural_key=..., doc=...)
      if has_sanskrit: mongo.upsert_gatha_sanskrit(...)
      for chhand in chhands: mongo.upsert_gatha_hindi_chhand(...)
      for tk in teeka_mappings:
          pg.upsert_teeka_if_missing(natural_key=tk.teeka_natural_key, ...)
          mongo.upsert_teeka_gatha_mapping(natural_key=tk.natural_key, doc=...)
      for kw in extracted_keywords:
          pg.attach_keyword_to_gatha(gatha_id, keyword_natural_key)
      for tp in heading_topics:
          pg.upsert_topic(natural_key=..., parent_keyword=None,
                          source='nikkyjain', display_text=heading)
          neo4j.sync_topic(...)
          neo4j.add_edge(Gatha → Topic, MENTIONS_TOPIC)
    COMMIT
```

## `GathaExtract` (intermediate Pydantic)

```python
class TaggedTerm(BaseModel):
    source_word: str            # text inside [...]
    meaning: str                # text after the closing ]

class AnvayarthaEntry(BaseModel):
    teeka_natural_key: str      # 'pravachansaar:hindi-chhand'
    raw_text_hi: str
    tagged_terms: list[TaggedTerm]
    is_alt: bool = False

class ChhandEntry(BaseModel):
    chhand_index: int
    chhand_type: str            # 'harigeet' default
    text_hi: str

class GathaExtract(BaseModel):
    natural_key: str            # 'pravachansaar:039'
    shastra_natural_key: str
    gatha_number: str           # '039' or '004-005'
    adhikaar_hi: str | None
    heading_hi: str | None
    prakrit_text: str | None
    sanskrit_text: str | None
    chhands: list[ChhandEntry]
    anvayarthas: list[AnvayarthaEntry]
    extracted_keyword_natural_keys: list[str]    # heuristic; admin may correct
```

## Parser pseudocode

```python
def parse_index(html: str, cfg: NikkyjainConfig) -> ShastraIndex:
    tree = HTMLParser(html)
    title = clean(tree.css_first(cfg.selectors.shastra_title).text())
    author = clean(tree.css_first(cfg.selectors.author_name).text()).lstrip("- ").strip()

    # adhikaar map: walk gatha_index rows, track current adhikaar by <h2 id='adN'>...</h2>
    adhikaar_map = {}
    current_adhikaar = None
    for row in tree.css("table.mainIndex > tr"):
        h2 = row.css_first("h2[id^='ad']")
        if h2:
            current_adhikaar = clean(h2.text())
            continue
        link = row.css_first("a[href^='#gatha-']")
        if link:
            gatha_id = link.attributes["href"][1:]   # 'gatha-039'
            gatha_number = gatha_id.removeprefix(cfg.parsing.gatha_id_prefix)
            adhikaar_map[gatha_number] = current_adhikaar
    return ShastraIndex(title=title, author=author, adhikaar_map=adhikaar_map)


def parse_gatha(anchor_div, cfg, shastra_natural_key, adhikaar_map) -> GathaExtract:
    gatha_id = anchor_div.attributes["id"]                          # 'gatha-039'
    gatha_number = gatha_id.removeprefix(cfg.parsing.gatha_id_prefix)
    natural_key = f"{shastra_natural_key}:{gatha_number}"

    heading_hi = clean(anchor_div.css_first("a").text())
    chhands, anvayarthas = [], []
    prakrit_text, sanskrit_text = None, None

    for sib in walk_siblings_until(anchor_div, "div.title"):
        cls = sib.attributes.get("class", "")
        if cls == "gatha":
            prakrit_text = strip_numbering(clean(sib.text()))
        elif cls == "sanskrit":
            sanskrit_text = strip_numbering(clean(sib.text()))
        elif cls == "gadya":
            chhands.append(ChhandEntry(
                chhand_index=len(chhands)+1,
                chhand_type="harigeet",
                text_hi=clean(sib.text()),
            ))
        elif cls == "paragraph":
            txt = sib.text()
            if cfg.parsing.alt_anvayartha_marker in txt:
                anvayarthas.append(parse_anvayartha(sib, is_alt=True, cfg=cfg))
            elif cfg.parsing.anvayartha_marker in txt:
                anvayarthas.append(parse_anvayartha(sib, is_alt=False, cfg=cfg))
            # else: footnote / shortFont — store as text in last anvayartha or skip

    return GathaExtract(
        natural_key=natural_key,
        shastra_natural_key=shastra_natural_key,
        gatha_number=gatha_number,
        adhikaar_hi=adhikaar_map.get(gatha_number),
        heading_hi=heading_hi,
        prakrit_text=prakrit_text,
        sanskrit_text=sanskrit_text,
        chhands=chhands,
        anvayarthas=anvayarthas,
        extracted_keyword_natural_keys=[],   # filled later by keyword detector
    )


def parse_anvayartha(div, is_alt, cfg) -> AnvayarthaEntry:
    raw = clean(div.text())
    tagged_terms = []
    # iterate <b><font color=darkRed>[term]</font></b> followed by sibling text
    for b in div.css("b font[color='darkRed']"):
        source_word = clean(b.text()).strip("[]")
        meaning = read_following_text_until_next_b(b)
        tagged_terms.append(TaggedTerm(source_word=source_word, meaning=meaning))
    return AnvayarthaEntry(
        teeka_natural_key=cfg.shastra.default_teeka.natural_key,
        raw_text_hi=raw,
        tagged_terms=tagged_terms,
        is_alt=is_alt,
    )
```

`strip_numbering` removes `(NN)` and `॥NN॥` while preserving line breaks.

## Keyword detection on a gatha

Initial heuristic, runs **after** approval (so admin sees clean extracts first):
1. Tokenize anvayartha Hindi text.
2. NFC normalize.
3. For each token, check `keywords.natural_key` and `keyword_aliases.alias_text` (Postgres `IN` query).
4. Attach matched keyword IDs to the gatha row.

This is a deliberate v1 heuristic. Better matching (e.g. multi-word keywords like "केवलज्ञान") follows in v2.

## Heading-based topic seeding

Each gatha heading (e.g. `भूत-भावि पर्यायों की असद्भूत--अविद्यमान संज्ञा है`) becomes a **topic** with:
- `natural_key`: `nikkyjain:{shastra}:{gatha_number}:{slug(heading)}`
- `source`: `nikkyjain`
- `parent_keyword_id`: NULL (no parent keyword for heading-derived topics)
- `display_text`: the heading
- `MENTIONS_TOPIC` edge from the gatha node.

This is per the user's note: "Add gatha headings (extracted from nikkyjain.github.io) as topics."

## Running it

```bash
python -m workers.ingestion.nikkyjain.orchestrator \
  --config parser_configs/nikkyjain/pravachansaar.yaml \
  --triggered-by admin@example.com
```

## Definition of Done

- [ ] `parse_index` correctly identifies title, author, and ≥ 270 gatha anchors in `pravachansaar/index.html`.
- [ ] `parse_gatha` produces a fixture-validated `GathaExtract` for gatha 039 (Prakrit text, 1 chhand, 1 anvayartha with ≥ 5 tagged terms).
- [ ] Adhikaar map associates gatha 039 with `ज्ञानतत्त्व-प्रज्ञापन-अधिकार`.
- [ ] Heading topic node created with `natural_key` matching the slug rule.
- [ ] Re-running ingestion is idempotent (same row count, fields overwritten).
- [ ] Default teeka row created once with `natural_key=pravachansaar:hindi-chhand`.
