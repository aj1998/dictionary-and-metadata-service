# Phase 2 — Fetch, discover, alias-mine, queue

**Goal**: drive the parser end-to-end from a live or replayed JainKosh
source: discover keyword URLs, fetch HTML rate-limited, write snapshots,
parse, mine aliases, and insert proposed payloads into
`ingestion_review_queue`. **Stops at queue-with-pending** — no apply.

When this phase is done, running

```bash
python -m workers.ingestion.jainkosh.orchestrator \
  --config parser_configs/jainkosh.yaml \
  --letter अ --triggered-by admin@example.com
```

(Phase 3 wires the actual `__main__` — Phase 2 ships the underlying
Celery task callable + a thin runner) yields:

- `data/raw/jainkosh/<run_ts>/अ/<keyword>.html` per keyword on disk.
- `_index.json` with run metadata.
- One `ingestion_runs` row in status `success` (or `partial` on errors).
- One `ingestion_review_queue` row per keyword, status `pending`,
  with `proposed_payload = WouldWriteEnvelope.dict()` and
  `entity_natural_key = <keyword>`.

---

## 2.1 Modules

All under `workers/ingestion/jainkosh/`:

| File | Purpose |
|---|---|
| `fetch.py` | Rate-limited httpx client with retry/backoff; `fetch_html(url) -> bytes`. |
| `discover.py` | `list_letter_urls(seed) -> list[str]`, `list_keyword_urls(letter_url) -> list[str]`. |
| `snapshot.py` | `write_snapshot(html_bytes, run_dir, letter, slug) -> Path`; appends to `_index.json`. |
| `alias_mining.py` | `mine_aliases(keyword: str, parsed: KeywordParseResult, http_client) -> list[Alias]`. |
| `orchestrator.py` | Celery task `jainkosh_ingest_letter(run_id, letter, config_path)`; plain Python entry `run_letter(...)` for CLI. |
| `queue.py` | `insert_review_queue_row(session, run_id, envelope, diff_against_existing)` helper. |

---

## 2.2 `fetch.py`

```python
class JainKoshFetcher:
    def __init__(self, config: ParserConfig):
        self.client = httpx.AsyncClient(
            headers={"User-Agent": config.fetch.user_agent},
            timeout=config.fetch.timeout_seconds,
            follow_redirects=True,
        )
        self._last_request_at: float = 0.0
        self.min_interval = 1.0 / config.rate_limit.requests_per_second

    async def fetch_html(self, url: str) -> tuple[bytes, str]:
        """Returns (html_bytes, sha256). Throttled, retried with backoff."""
```

Rules:

- Single-threaded throttle: `await asyncio.sleep(max(0, min_interval - (now - last)))`
  before each request. `concurrent: 1` per the YAML — do NOT parallelize.
- Reject hosts not in `config.allowed_hosts`.
- On `429`, `5xx`, or network errors: retry per `config.fetch.retries`
  with `config.fetch.backoff_seconds` (sleep before retry).
- Compute `sha256(html_bytes)` and return alongside.
- Caller is responsible for closing the client (`async with` or
  `await fetcher.aclose()`).

---

## 2.3 `discover.py`

```python
async def list_letter_urls(seed_url: str, fetcher) -> list[tuple[str, str]]:
    """Returns [(letter, category_url), ...]. Selects per
    config.discovery_selectors.letter_links."""

async def list_keyword_urls(category_url: str, fetcher) -> list[str]:
    """All anchor hrefs matching config.discovery_selectors.keyword_links_in_category.
    Returns absolute URLs."""
```

Use `selectolax` (already a parser dep). Resolve relative URLs against
the category URL. Keep ordering stable (alphabetical = HTML order).

---

## 2.4 `snapshot.py`

```python
def write_snapshot(html_bytes: bytes, run_dir: Path, letter: str, slug: str) -> Path:
    """Writes {run_dir}/{letter}/{slug}.html. Returns path. Updates
    {run_dir}/_index.json with {url, slug, sha256, fetched_at, bytes}."""
```

`_index.json` is a JSON array; load → append → atomic-rename write.
Dir-create on first call. `slug` is `topic_keys.slug(keyword)` so it is
filesystem-safe.

---

## 2.5 `alias_mining.py`

Two sources per `08_ingestion_jainkosh.md` §"Alias mining":

```python
async def mine_aliases(
    keyword: str,
    parsed: KeywordParseResult,
    fetcher: JainKoshFetcher,
) -> list[dict]:
    """
    Returns [{"alias": str, "source": "see_also"|"redirect"}, ...].
    """
```

1. **`देखें` aliases**: scan `parsed.see_also_targets` (the parser already
   exposes these — verify by reading `models.py`; if the field is named
   differently, adapt). Each target keyword whose `is_self=False` and
   that points at the same keyword's redirect set is an alias.
   *Not synthetic-topic seeds* — those are separate Topic entities.
2. **MediaWiki redirects**: GET
   `https://www.jainkosh.org/w/api.php?action=query&list=backlinks&blfilterredir=redirects&bltitle=<keyword>&format=json`,
   parse JSON, take every `query.backlinks[].title`. Throttle through
   `fetcher`.

Dedupe within the list. Skip silently on API error (log a warning into
the run's `error_log`).

---

## 2.6 Orchestrator pipeline

`orchestrator.py::run_letter(...)` (sync wrapper around an async
implementation):

```python
async def run_letter_async(
    *,
    config_path: str,
    letter: str,
    triggered_by: str,
    pg_session_factory,
    run_id: uuid.UUID | None = None,
) -> uuid.UUID:
    config = load_jainkosh_config(config_path)
    parser_config_id = await register_parser_config(pg_session_factory, config_path, config)
    run_id = run_id or uuid.uuid4()
    run_dir = Path(config.storage.raw_html_dir.format(run_ts=now_iso()))
    run_dir.mkdir(parents=True, exist_ok=True)

    async with pg_session_factory() as s:
        await create_ingestion_run(s, id=run_id, source="jainkosh",
            parser_config_id=parser_config_id, triggered_by=triggered_by,
            raw_html_dir=str(run_dir), status="running")
        await s.commit()

    fetcher = JainKoshFetcher(config)
    try:
        async with fetcher:
            letter_urls = dict(await list_letter_urls(config.seed_url, fetcher))
            cat_url = letter_urls[letter]
            keyword_urls = await list_keyword_urls(cat_url, fetcher)

            stats = {"keyword_count": 0, "errors": 0}
            for kw_url in keyword_urls:
                try:
                    keyword = decode_keyword_from_url(kw_url)
                    html_bytes, sha = await fetcher.fetch_html(kw_url)
                    snap_path = write_snapshot(html_bytes, run_dir, letter, slug(keyword))

                    parsed = parse_keyword_html(html_bytes.decode("utf-8"), kw_url, config)
                    aliases = await mine_aliases(keyword, parsed, fetcher)
                    envelope = build_envelope(parsed)
                    inject_aliases(envelope, aliases)
                    inject_run_metadata(envelope, run_id=run_id,
                        snapshot_path=snap_path, sha256=sha)

                    async with pg_session_factory() as s:
                        await insert_review_queue_row(
                            s, run_id=run_id, envelope=envelope,
                            entity_type="keyword",
                            entity_natural_key=keyword,
                            diff_against_existing=await compute_diff(s, keyword, envelope),
                        )
                        await update_iterator_state(s, run_id, {"last_letter": letter, "last_keyword": keyword})
                        await s.commit()
                    stats["keyword_count"] += 1
                except Exception as e:
                    stats["errors"] += 1
                    await append_error_log(pg_session_factory, run_id, kw_url, e)
    finally:
        final_status = "success" if stats["errors"] == 0 else "partial"
        async with pg_session_factory() as s:
            await finish_ingestion_run(s, run_id, status=final_status, stats=stats)
            await s.commit()

    return run_id
```

Helpers needed (put them in `queue.py` / `orchestrator.py`):

- `register_parser_config(session, path, config_obj)` — upsert into
  `parser_configs` keyed by `(source, config_path, version)` with a
  `checksum` of the YAML bytes.
- `create_ingestion_run` / `finish_ingestion_run` /
  `update_iterator_state` / `append_error_log` — small
  SQLAlchemy helpers around `IngestionRun`.
- `compute_diff(session, keyword, envelope)` — best-effort, may be
  `None` for v1 (Phase 3 can refine). If a `keyword` row already exists,
  populate `{"existed": true}` else `None`.
- `inject_aliases(envelope, aliases)` — appends to
  `envelope["would_write"]["postgres"]["keyword_aliases"]`. Defines a
  shape if absent: `[{"keyword_natural_key": kw, "alias": …, "source": …}]`.
- `inject_run_metadata` — adds `ingestion_run_id`, `snapshot_path`,
  `sha256`, `fetched_at` to the envelope's mongo `keyword_definitions`
  doc and to a new `would_write.mongo.raw_html_snapshots[0]` entry.

---

## 2.7 Celery wiring

`workers/ingestion/jainkosh/orchestrator.py`:

```python
from celery import shared_task

@shared_task(name="jainkosh.ingest_letter")
def ingest_letter(run_id: str | None, letter: str, config_path: str, triggered_by: str) -> str:
    return str(asyncio.run(run_letter_async(
        config_path=config_path, letter=letter,
        triggered_by=triggered_by,
        pg_session_factory=get_pg_session_factory(),
        run_id=uuid.UUID(run_id) if run_id else None,
    )))
```

A bare `celery` app config can live in `workers/celery_app.py` if not
already present; broker URL from env (`CELERY_BROKER_URL`, default
`redis://localhost:6379/0`). Phase 2 does not need to actually run a
worker process in CI — local imports + a direct call to `run_letter_async`
suffice for tests.

---

## 2.8 Tests

`tests/ingestion/test_orchestrator.py`:

1. `test_fetcher_rate_limit` — monkeypatch `time.monotonic`/`asyncio.sleep`,
   request 3 URLs at `requests_per_second=2`, assert ≥ 1.0s elapsed.
2. `test_discover_letter_urls` — feed the seed page HTML from a fixture
   (`tests/fixtures/jainkosh/seed.html`); assert at least one
   `(letter, url)` pair returned.
3. `test_alias_mining_see_also` — mock `fetcher.fetch_html` and the
   API endpoint with `respx`; assert dedup + correct sources.
4. `test_run_letter_inserts_queue_rows` — monkeypatch `fetch_html` to
   return saved HTML from `samples/sample_html_jainkosh_pages/`,
   monkeypatch the discover functions to return a 1-keyword list, run
   `run_letter_async` once. Assert:
     - `ingestion_runs` row exists, status `success`, raw_html_dir set;
     - exactly 1 `ingestion_review_queue` row, status `pending`;
     - `proposed_payload` parses back into a `WouldWriteEnvelope`;
     - `data/raw/jainkosh/<ts>/<letter>/<slug>.html` exists with the
       expected sha256.
5. `test_run_letter_partial_on_error` — make 1 of 2 keywords throw;
   assert run status `partial`, queue has 1 row, `error_log` set.

Fixtures: stash a tiny seed/category HTML under
`tests/fixtures/jainkosh/`. Use existing parser samples for keyword HTML.

---

## 2.9 Definition of Done — Phase 2

- [ ] `fetch.py` enforces single-threaded rate limit + retries; tests pass.
- [ ] `discover.py` parses both seed and category pages.
- [ ] `snapshot.py` writes HTML + appends `_index.json` correctly.
- [ ] `alias_mining.py` returns deduped aliases from both sources.
- [ ] `run_letter_async` produces an `ingestion_runs` row plus one
      `ingestion_review_queue` row per keyword, with the parser-
      produced envelope as `proposed_payload`.
- [ ] Iterator state and stats are updated after each keyword.
- [ ] Error in one keyword does not abort the letter; final status is
      `partial` with `error_log` populated.
- [ ] All Phase-2 tests above pass.
- [ ] The orchestrator can be imported via Celery (`@shared_task`
      decorator resolves) — no need to actually run a worker in CI.
