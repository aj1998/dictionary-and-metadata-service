# 08 — Ingestion: JainKosh

Scrapes `jainkosh.org/wiki/Jain_dictionary` → per-letter category pages → per-keyword pages, parses each into a `keyword_definitions` Mongo doc + (optionally) child `topic_extracts` docs, lands them in the **review queue** for admin approval, then upserts on approval.

## Parsing rules and parser implementation

The HTML→JSON parsing rules and the parser implementation spec are
maintained in dedicated documents:

- **Parsing rules** (DOM patterns, heading variants, definitions, references, `देखें` extraction, tables, nav): [`jainkosh/parsing_rules.md`](./jainkosh/parsing_rules.md)
- **Parser implementation spec** (file layout, Pydantic models, YAML config, algorithms, tests, CLI): [`jainkosh/parser_spec.md`](./jainkosh/parser_spec.md)
- **Schema additions** (Postgres `topics` columns, Mongo collection shapes, Neo4j properties): [`jainkosh/schema_updates.md`](./jainkosh/schema_updates.md)

The remainder of *this* document covers only the orchestration pieces
that wrap the parser: source discovery, fetching, rate-limiting,
snapshot writing, alias mining, the review queue, and apply-on-approve
upserts. **Anything that contradicts the rules in
[`jainkosh/parsing_rules.md`](./jainkosh/parsing_rules.md) — that
file wins.**

## Source discovery

- Dictionary index: `https://www.jainkosh.org/wiki/Jain_dictionary` — links to per-letter Category pages (अ, आ, क …).
- Category page (e.g. `https://www.jainkosh.org/wiki/Category:आ`) — alphabetical list of keywords.
- Keyword page (e.g. `https://www.jainkosh.org/wiki/आत्मा`) — MediaWiki-rendered article; parsed by the rules in `jainkosh/parsing_rules.md`.

## Parser config (`parser_configs/jainkosh.yaml`)

The parser-rules portion (heading variants, block classes, references,
`देखें` patterns, etc.) is defined in
[`jainkosh/parser_spec.md`](./jainkosh/parser_spec.md) §3. The
orchestrator-only portion (fetch, rate limit, storage, alias mining
toggles, review) lives in the same YAML file:

```yaml
# Orchestrator-level keys (this doc):
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
  mongo_store_raw_html: false
discovery_selectors:
  letter_links: "a[href^='/wiki/Category:']"
  keyword_links_in_category: "div.mw-category a"
alias_extraction:
  from_see_also: true
  from_redirects_via_api: true
review:
  auto_approve: false

# Parser-rules portion: see jainkosh/parser_spec.md §3 for the full schema
# (sections, block_classes, headings.variants[V1..V4], translation_marker,
#  nested_span, table, navigation, emphasis, slug, etc.).
```

## Job structure

```
workers/ingestion/jainkosh/
├── orchestrator.py     # Celery entry point, drives fetch → parse → queue
├── fetch.py            # rate-limited httpx client, snapshot writer
├── discover.py         # dictionary_index → letters → keyword URLs
├── parse_keyword.py    # one keyword page → KeywordParseResult (see jainkosh/parser_spec.md)
├── alias_mining.py     # 'देखें' links + redirect API
├── envelope.py         # would_write fragment builder
├── models.py           # Pydantic intermediate types (defined in jainkosh/parser_spec.md §4)
├── cli.py              # standalone parser CLI (see jainkosh/parser_spec.md §7)
└── tests/              # see jainkosh/parser_spec.md §8
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

## Intermediate Pydantic types

The complete `KeywordParseResult`, `WouldWriteEnvelope`,
`Block`/`Subsection`/`PageSection`/`Definition`/`IndexRelation` models
live in [`jainkosh/parser_spec.md`](./jainkosh/parser_spec.md) §4.
The orchestrator consumes a `WouldWriteEnvelope` and is responsible
for (a) writing the snapshot HTML to disk, (b) appending mined
aliases, and (c) inserting the envelope into `ingestion_review_queue`
as the proposed payload.

## Parser

The parser is implemented per [`jainkosh/parser_spec.md`](./jainkosh/parser_spec.md). Orchestrator code calls:

```python
from workers.ingestion.jainkosh.parse_keyword import parse_keyword_html
from workers.ingestion.jainkosh.envelope import build_envelope

result = parse_keyword_html(html_bytes.decode("utf-8"), source_url, config)
envelope = build_envelope(result)
# envelope.would_write is what gets queued for review.
```

Slug rules and natural-key formats (e.g.
`आत्मा-के-बहिरात्मादि-3-भेद`, `आत्मा:आत्मा-के-बहिरात्मादि-3-भेद`)
are documented in
[`jainkosh/parsing_rules.md`](./jainkosh/parsing_rules.md) §5.4.

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

The Definition of Done for the parser-only stage lives in
[`jainkosh/parser_spec.md`](./jainkosh/parser_spec.md) §10. The
orchestrator-stage Definition of Done is below; it depends on
parser-stage being green.

- [ ] Parser-stage Definition of Done complete (per `jainkosh/parser_spec.md` §10).
- [ ] Schema updates applied (per `jainkosh/schema_updates.md` §7).
- [ ] `parser_configs/jainkosh.yaml` validated against `parser_configs/_schemas/jainkosh.schema.json`.
- [ ] Re-running the orchestrator twice with identical inputs produces zero net DB changes after second approval (idempotent).
- [ ] Rate-limit honored (single-threaded sleep-based throttle).
- [ ] All scraped HTML written to `data/raw/jainkosh/<run_ts>/`.
- [ ] Admin can list, approve, reject items from `ingestion_review_queue` (see `13_admin_ui.md`).
- [ ] Aliases mined from at least one keyword in the test fixture.
