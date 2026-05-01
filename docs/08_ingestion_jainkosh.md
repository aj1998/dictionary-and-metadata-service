# 08 — Ingestion: JainKosh

Scrapes `jainkosh.org/wiki/Jain_dictionary` → per-letter category pages → per-keyword pages, parses each into a `keyword_definitions` Mongo doc + (optionally) child `topic_extracts` docs, lands them in the **review queue** for admin approval, then upserts on approval.

## Source structure (observed from samples)

- Dictionary index: `https://www.jainkosh.org/wiki/Jain_dictionary` — links to per-letter Category pages (अ, आ, क …).
- Category page (e.g. `https://www.jainkosh.org/wiki/Category:%E0%A4%85`) — alphabetical list of keywords.
- Keyword page (e.g. `https://www.jainkosh.org/wiki/%E0%A4%86%E0%A4%A4%E0%A5%8D%E0%A4%AE%E0%A4%BE`) — MediaWiki-rendered article. Within `<div class="mw-parser-output">`:
  - `<h2><span class="mw-headline" id="...">सिद्धांतकोष से</span></h2>` — top-level section.
  - `<h2><span class="mw-headline" id="...">पुराणकोष से</span></h2>` — second top-level section.
  - Within each section, **bold paragraphs** like `<p class="HindiText"><b>2. आत्मा के बहिरात्मादि 3 भेद</b></p>` mark **subsections** (these become **topic seeds**).
  - Reference markers: `<span class="GRef">धवला पुस्तक 13/5,5,50/282/9</span>`.
  - Body blocks: `<p class="SanskritText">…</p>`, `<p class="PrakritText">…</p>`, `<p class="HindiText">…</p>`.
  - "देखें" links: `<p class="HindiText">• <X> - देखें <a href="/wiki/Y" …>Y</a></p>` — these mine into `keyword_aliases` of `Y`.
  - Adjacent-page nav: `<a href="/wiki/...">पूर्व पृष्ठ</a>`, `<a href="/wiki/...">अगला पृष्ठ</a>`.

## Parser config (`parser_configs/jainkosh.yaml`)

```yaml
version: 1.0.0
source: jainkosh
seed_url: "https://www.jainkosh.org/wiki/Jain_dictionary"
allowed_hosts: ["www.jainkosh.org", "jainkosh.org"]
rate_limit:
  requests_per_second: 1
  concurrent: 1
fetch:
  user_agent: "JainKBBot/1.0 (+contact)"
  timeout_seconds: 30
  retries: 3
  backoff_seconds: [2, 5, 15]
storage:
  raw_html_dir: "data/raw/jainkosh/{run_ts}"
  mongo_store_raw_html: false  # disabled by default; use disk
selectors:
  letter_links: "a[href^='/wiki/Category:']"
  keyword_links_in_category: "div.mw-category a"
  page_main: "div.mw-parser-output"
  section_h2: "h2 > span.mw-headline"
  subsection_bold_in_p: "p.HindiText > b"   # numbered headings like '2. आत्मा के बहिरात्मादि 3 भेद'
  reference_span: "span.GRef"
  see_also_link_in_p: "p.HindiText a[href^='/wiki/']"
parsing:
  block_classes:
    SanskritText: sanskrit
    PrakritText: prakrit
    HindiText: hindi
  topic_subsection_pattern: '^\s*\d+\.\s+(?P<heading>.+?)\s*$'   # extract heading from bold text
  strip_zwj: true
  strip_zwnj: true
post_process:
  derive_topic_natural_key: "jainkosh:{keyword}:{slug(heading)}"
  alias_extraction:
    from_see_also: true
    from_redirects_via_api: true   # use ?action=raw&redirect=no via API to fetch redirect targets
review:
  auto_approve: false   # always queue for human review in v1
```

## Job structure

```
workers/ingestion/jainkosh/
├── orchestrator.py     # Celery entry point, drives fetch → parse → queue
├── fetch.py            # rate-limited httpx client, snapshot writer
├── parse_index.py      # dictionary_index → letters → keyword URLs
├── parse_keyword.py    # one keyword page → KeywordExtract
├── alias_mining.py     # 'देखें' links + redirect API
├── models.py           # Pydantic intermediate types
└── tests/
    ├── fixtures/
    │   ├── आत्मा.html
    │   └── पर्याय.html
    └── test_parse_keyword.py
```

## Pipeline

```
Celery task: jainkosh.ingest_letter(run_id, letter='अ', config_path=...)
  1. Load parser config, register parser_config row, create ingestion_run row (status=running)
  2. Resolve letter category URL → list keyword URLs
  3. For each keyword URL (rate-limited):
       a. Fetch HTML → write to {raw_html_dir}/{slug}.html, sha256 hash recorded
       b. Parse → KeywordExtract Pydantic model
       c. Mine aliases (see_also, redirect API)
       d. Build proposed payload (postgres + mongo + graph fragments)
       e. Insert into ingestion_review_queue with diff vs existing
  4. Update iterator_state {"last_letter": "अ", "last_keyword": "..."}, stats
  5. On finish, set ingestion_run.status = success | partial
  6. Notify admin UI (websocket / SSE / polled status)

On admin approve (one or many at once):
  apply_approved_keyword_payload(...)
    BEGIN
      pg.upsert_keyword(...)  -> keyword_id
      mongo.upsert_keyword_definition(natural_key=keyword.natural_key, doc=...)
      pg.upsert_keyword_aliases(...)
      for topic_seed in payload.topic_seeds:
          pg.upsert_topic(...)              -> topic_id
          mongo.upsert_topic_extract(natural_key=topic.natural_key, doc=...)
      neo4j.sync_keyword(...)
      neo4j.sync_topics(...)
    COMMIT
  set review_queue.status = approved
```

## `KeywordExtract` (intermediate Pydantic)

```python
class Block(BaseModel):
    kind: Literal["sanskrit", "prakrit", "hindi", "reference", "see_also"]
    text: list[Multilingual] | None = None
    ref_text: str | None = None
    target_keyword: str | None = None
    target_url: str | None = None

class Subsection(BaseModel):
    subsection_index: int
    heading: list[Multilingual]
    is_topic_seed: bool
    topic_natural_key: str | None      # 'jainkosh:आत्मा:बहिरात्मादि-3-भेद'
    blocks: list[Block]

class PageSection(BaseModel):
    section_index: int
    section_kind: Literal["siddhantkosh", "puraankosh", "misc"]
    heading: list[Multilingual]
    subsections: list[Subsection]

class KeywordExtract(BaseModel):
    natural_key: str                  # NFC keyword text
    source_url: str
    page_sections: list[PageSection]
    redirect_aliases: list[str]
```

## Parser pseudocode

```python
def parse_keyword_html(html: str, url: str, config: JainkoshConfig) -> KeywordExtract:
    tree = HTMLParser(html)
    main = tree.css_first(config.selectors.page_main)
    keyword = nfc(extract_keyword_from_url(url))
    page_sections = []
    section_index = 0

    for h2 in main.css(config.selectors.section_h2):
        section_kind = classify_section(h2.text())  # by id 'सिद्धांतकोष_से' etc.
        section = PageSection(section_index=section_index,
                              section_kind=section_kind,
                              heading=[ml_hi(h2.text())],
                              subsections=[])
        section_index += 1

        # walk siblings until next h2
        cur_subsection = None
        sub_idx = 0
        for sibling in walk_siblings_until(h2.parent, "h2"):
            tag = sibling.tag
            cls = sibling.attributes.get("class", "")

            if tag == "p" and is_subsection_heading(sibling, config):
                heading_text = extract_bold_heading(sibling, config.parsing.topic_subsection_pattern)
                sub_idx += 1
                cur_subsection = Subsection(
                    subsection_index=sub_idx,
                    heading=[ml_hi(heading_text)],
                    is_topic_seed=True,
                    topic_natural_key=f"jainkosh:{keyword}:{slug(heading_text)}",
                    blocks=[],
                )
                section.subsections.append(cur_subsection)
                continue

            if cur_subsection is None:
                # synthetic subsection 0 captures pre-heading content
                cur_subsection = Subsection(
                    subsection_index=0, heading=[ml_hi("intro")], is_topic_seed=False,
                    topic_natural_key=None, blocks=[]
                )
                section.subsections.append(cur_subsection)

            if tag == "p":
                if "GRef" in extract_inner_classes(sibling):
                    cur_subsection.blocks.append(
                        Block(kind="reference", ref_text=clean(sibling.text()))
                    )
                elif cls == "SanskritText":
                    cur_subsection.blocks.append(
                        Block(kind="sanskrit",
                              text=[Multilingual(lang="san", script="Deva", text=clean(sibling.text()))])
                    )
                elif cls == "PrakritText":
                    cur_subsection.blocks.append(
                        Block(kind="prakrit",
                              text=[Multilingual(lang="pra", script="Deva", text=clean(sibling.text()))])
                    )
                elif cls == "HindiText":
                    if has_see_also(sibling):
                        for link in see_also_links(sibling):
                            cur_subsection.blocks.append(
                                Block(kind="see_also",
                                      target_keyword=nfc(link.text), target_url=link.href)
                            )
                    else:
                        cur_subsection.blocks.append(
                            Block(kind="hindi",
                                  text=[Multilingual(lang="hin", script="Deva", text=clean(sibling.text()))])
                        )

        page_sections.append(section)

    redirect_aliases = mine_redirect_aliases(keyword, config)   # API call

    return KeywordExtract(
        natural_key=keyword,
        source_url=url,
        page_sections=page_sections,
        redirect_aliases=redirect_aliases,
    )
```

`slug(heading)` — lowercase ASCII-fold-where-applicable + replace whitespace with `-`. For Devanagari headings, we keep Devanagari letters but replace spaces with `-` and strip punctuation. Example: `आत्मा के बहिरात्मादि 3 भेद` → `आत्मा-के-बहिरात्मादि-3-भेद`. The full topic natural_key prepends `jainkosh:आत्मा:` (parent keyword) for global uniqueness.

## Alias mining

Two sources, both contribute to `keyword_aliases`:

1. **`देखें` links**: any `<p class="HindiText">• <text> - देखें <a href="/wiki/Y">Y</a></p>` produces `text → Y` alias.
2. **MediaWiki redirects**: query `https://www.jainkosh.org/w/api.php?action=query&list=backlinks&blfilterredir=redirects&bltitle=<keyword>&format=json` — each backlink with `redirect=true` is an alias of the current keyword.

## Storage of raw HTML

```
data/raw/jainkosh/2026-05-01T12:00:00Z/
├── _index.json                # {run_id, started_at, scraped_count, ...}
├── अ/
│   ├── आत्मा.html
│   └── ...
└── आ/
```

## Running it

```bash
# CLI for manual triggers (admin UI also calls this)
python -m workers.ingestion.jainkosh.orchestrator \
  --config parser_configs/jainkosh.yaml \
  --letter अ \
  --triggered-by admin@example.com
```

## Definition of Done

- [ ] `parser_configs/jainkosh.yaml` validated against a JSON-schema in `parser_configs/_schemas/jainkosh.schema.json`.
- [ ] Parser passes golden tests on `sample_html_jainkosh_pages/आत्मा.html` and `पर्याय.html` — emitted `KeywordExtract` matches `tests/golden/आत्मा.json`.
- [ ] Re-running the orchestrator twice with identical inputs produces zero net DB changes after second approval (idempotent).
- [ ] Rate-limit honored (single-threaded sleep-based throttle).
- [ ] All scraped HTML written to `data/raw/jainkosh/<run_ts>/`.
- [ ] Admin can list, approve, reject items from `ingestion_review_queue` (see `13_admin_ui.md`).
- [ ] Aliases mined from at least one keyword in the test fixture.
