# 21 — Finetune Dataset Export Spec

Scope context: [`scope/06_advanced_rag_and_finetuning.md`](../../scope/06_advanced_rag_and_finetuning.md) (pipeline diagram, model families).
Related: [`design/02_data_model_postgres.md`](../data_model/02_data_model_postgres.md), [`design/03_data_model_mongo.md`](../data_model/03_data_model_mongo.md), [`design/04_data_model_graph.md`](../data_model/04_data_model_graph.md), [`design/scope/15_multilingual_keyword_storage_spec.md`](./15_multilingual_keyword_storage_spec.md).

Build a deterministic exporter that snapshots Postgres + Mongo + Neo4j into versioned JSONL training datasets, uploads them to an S3-compatible store, and records a metadata row per snapshot. Consumed by spec 22 (training) and spec 24 (eval).

## Phase A — exporter orchestrator + formatters

### Files

```
workers/finetune/
├── __init__.py
├── dataset_export.py             Orchestrator (CLI + Celery task)
├── snapshot.py                   sha256 + S3 upload + PG metadata write
├── s3_client.py                  boto3 S3 wrapper (endpoint_url, bucket from env)
├── formatters/
│   ├── __init__.py
│   ├── base.py                   Formatter ABC: name(), iter_rows(session), schema_doc()
│   ├── graph_cypher.py           {question, cypher} from synth generator (calls spec 25 module)
│   ├── jainism_main.py           {instruction, input, output} from gathas + bhaavarths
│   ├── sa_pr.py                  {src_lang, tgt_lang, src, tgt} from chhaaya + word-meanings
│   ├── kn_gu.py                  Same shape as sa_pr; reads keyword_translations (spec 15)
│   └── research_domains.py       {domain, instruction, input, output} from categorisation tags
└── tests/
    ├── conftest.py
    ├── test_orchestrator.py
    ├── test_graph_cypher_formatter.py
    ├── test_jainism_main_formatter.py
    ├── test_sa_pr_formatter.py
    ├── test_kn_gu_formatter.py
    ├── test_research_domains_formatter.py
    └── test_snapshot_versioning.py
```

CLI entry: `python -m workers.finetune.dataset_export --task <name> [--task ...] --out s3://jinvani-finetune-datasets/`.
Celery task: `workers.finetune.tasks.run_dataset_export(task_names: list[str], triggered_by: str)`.

### Orchestrator contract

```python
# workers/finetune/dataset_export.py
TASKS: dict[str, type[BaseFormatter]] = {
    "graph_cypher": GraphCypherFormatter,
    "jainism_main": JainismMainFormatter,
    "sa_pr": SaPrFormatter,
    "kn_gu": KnGuFormatter,
    "research_domains": ResearchDomainsFormatter,
}

async def run_export(task_names: list[str], *, triggered_by: str,
                     source_run_id: uuid.UUID | None = None) -> list[FinetuneDataset]:
    out: list[FinetuneDataset] = []
    for name in task_names:
        fmt = TASKS[name](pg=pg, mongo=mongo, neo4j=neo4j)
        local = tmp_jsonl_path(name)
        row_count = await write_jsonl(local, fmt.iter_rows())
        sha = sha256_of_file(local)
        version = f"{date.today():%Y%m%d}-{sha[:8]}"
        s3_uri = upload_s3(local, key=f"{name}/{version}.jsonl")
        ds = await insert_finetune_dataset(
            pg, name=name, version=version, s3_uri=s3_uri,
            row_count=row_count, sha256=sha,
            schema_doc_url=f"docs/design/scope/21_finetune_dataset_export_spec.md#{name}",
            source_run_id=source_run_id, created_by=triggered_by,
        )
        out.append(ds)
    return out
```

### Per-task JSONL schemas

#### `graph_cypher` (one row per question)

```json
{"question": "Which gathas mention आत्मा and बंध?",
 "cypher": "MATCH (g:Gatha)-[:MENTIONS_TOPIC]->(t:Topic)<-[:HAS_TOPIC]-(k:Keyword) WHERE k.natural_key IN ['आत्मा','बंध'] WITH g, count(DISTINCT k) AS o WHERE o = 2 RETURN g.natural_key LIMIT 50",
 "seed_kind": "keyword_resolve|topic_traverse|alias_resolve|counter_lookup",
 "seed_node_ids": ["आत्मा", "बंध"]}
```

Rows are produced by `workers.finetune.synth.graph_cypher` (defined in spec 25). The formatter just reads from that generator; it does not duplicate the logic.

#### `jainism_main` (instruction-tuning row)

```json
{"instruction": "Translate the following Prakrit gatha into Hindi and explain its meaning.",
 "input": "<prakrit text from gatha_prakrit>",
 "output": "<concatenation of gatha_hindi_chhand[0].text + first teeka_mapping bhaavarth>",
 "meta": {"gatha_natural_key": "pravachansaar:039",
          "shastra_natural_key": "pravachansaar",
          "anuyoga": "dravyanuyoga",
          "approved_only": true}}
```

Only emit rows where the gatha has been approved (`ingestion_review_queue.status='approved'` for its row, OR the gatha pre-dates the review queue). Multiple instruction templates per gatha (translate, explain, list-keywords) — driven by `jainism_main.templates` dict in the formatter.

#### `sa_pr` (translation pair)

```json
{"src_lang": "pra", "tgt_lang": "san",
 "src": "णेव हि संजाया", "tgt": "नैव हि संजाताः",
 "source": "gatha_word_meanings|chhaaya_full|jainkosh_phrase",
 "confidence": 1.0}
```

Sources (concatenated, deduped on `(src_lang, src, tgt_lang)`):
- For each `gathas` row: `(gatha_prakrit.text, gatha_sanskrit.text)` as a single long-form pair.
- For each `gatha_word_meanings` row with `source_language='pra'`: per-entry word pairs.
- For Hindi↔Sanskrit: pull JainKosh keyword definitions whose Mongo extract has both `hin` and `san` text blocks.

#### `kn_gu` (multilingual keyword translations)

```json
{"src_lang": "hin", "tgt_lang": "kan",
 "src": "आत्मा", "tgt": "ಆತ್ಮ",
 "source": "keyword_translations",
 "confidence": <PG row confidence>}
```

Reads `keyword_translations` and `topic_translations` (spec 15). Only `status='approved'`.

#### `research_domains` (one row per gatha × domain tag)

```json
{"domain": "maths|sciences|philosophy|astronomy|ethics",
 "instruction": "Explain the following Jain text from a <domain> perspective.",
 "input": "<gatha hindi text>",
 "output": "<bhaavarth + categorisation_pipeline annotation>",
 "meta": {"gatha_natural_key": "...", "categorisation_confidence": 0.87}}
```

Reads from `gatha_research_categories` table (spec 13). Min confidence 0.6.

### Common JSONL writer

- One JSON object per line, UTF-8, no BOM, `ensure_ascii=False`.
- Stable ordering: rows sorted by `natural_key` ascending — required so re-export with the same input produces an identical sha256.
- Empty / missing fields collapsed (no `null` outputs unless the schema explicitly allows).

## Phase B — versioning + S3 + Postgres registry

### Postgres schema (migration `0040_finetune_datasets.py`)

```sql
CREATE TYPE finetune_task AS ENUM (
  'graph_cypher','jainism_main','sa_pr','kn_gu','research_domains'
);

CREATE TABLE finetune_datasets (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name            finetune_task NOT NULL,
  version         TEXT NOT NULL,                       -- 'YYYYMMDD-<sha8>'
  s3_uri          TEXT NOT NULL,                       -- s3://jinvani-finetune-datasets/<name>/<version>.jsonl
  row_count       INT NOT NULL,
  schema_doc_url  TEXT NOT NULL,                       -- in-repo path
  sha256          TEXT NOT NULL,                       -- hex
  source_run_id   UUID REFERENCES ingestion_runs(id) ON DELETE SET NULL,
  created_by      TEXT NOT NULL,                       -- admin email or 'cron'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (name, version)
);

CREATE INDEX idx_finetune_datasets_name ON finetune_datasets(name, created_at DESC);
```

`source_run_id` is FK-shaped per `ingestion_runs` (see `02_data_model_postgres.md`); `ON DELETE SET NULL` keeps the dataset row even if the run is purged.

### S3 layout

```
s3://jinvani-finetune-datasets/
├── graph_cypher/20260521-9a3f8b21.jsonl
├── jainism_main/20260521-1c4e09aa.jsonl
├── sa_pr/20260521-7b22ff10.jsonl
├── kn_gu/20260521-441a02de.jsonl
└── research_domains/20260521-d09c8821.jsonl
```

Env config:
- `FINETUNE_S3_ENDPOINT_URL` (e.g. AWS or Cloudflare R2 endpoint)
- `FINETUNE_S3_BUCKET=jinvani-finetune-datasets`
- `FINETUNE_S3_REGION`
- `FINETUNE_S3_ACCESS_KEY` / `FINETUNE_S3_SECRET_KEY`
- `FINETUNE_S3_KMS_KEY_ID` (optional SSE)

Lifecycle: never delete. Old versions are training history. Glacier transition after 365 days is fine to suggest in `deployment.md` but is not required here.

### Pydantic contracts

```python
# packages/jain_kb_common/schemas/finetune.py
class FinetuneDatasetOut(BaseModel):
    id: UUID
    name: Literal['graph_cypher','jainism_main','sa_pr','kn_gu','research_domains']
    version: str
    s3_uri: str
    row_count: int
    sha256: str
    source_run_id: UUID | None
    created_by: str
    created_at: datetime

class ExportRequest(BaseModel):
    tasks: list[Literal['graph_cypher','jainism_main','sa_pr','kn_gu','research_domains']]
    source_run_id: UUID | None = None
```

### Admin endpoint

`POST /admin/finetune/datasets/export` on `metadata-service` — body is `ExportRequest`, returns 202 + list of new `FinetuneDatasetOut`. Requires `require_role('admin')` from spec 01. Behind the scenes enqueues the Celery task; returns the row stub immediately (status='pending') and the row is updated after the upload completes. (For simpler v1, run synchronously and return 200 with the final rows — feature-flag via `FINETUNE_EXPORT_ASYNC` env.)

## Tests (TDD — write these first)

1. `test_orchestrator.py`: stub formatter yields 3 rows → JSONL has 3 lines → PG row inserted with `row_count=3`, `sha256` matches recomputed sha.
2. `test_snapshot_versioning.py`: same input twice → identical sha256 and identical S3 key; PG insert idempotent on `(name, version)` (second call returns existing row).
3. `test_graph_cypher_formatter.py`: with a tiny Neo4j fixture (2 keywords, 1 topic, 1 gatha), the synth generator stub emits ≥1 row per seed_kind and each row's `cypher` parses (`neo4j.run` with `EXPLAIN`).
4. `test_jainism_main_formatter.py`: gatha with prakrit + chhand + one teeka_mapping → 3 instruction templates emitted; gatha lacking chhand → translate template skipped.
5. `test_sa_pr_formatter.py`: word-meaning fixture → per-entry pairs emitted; dedup across collections proven (same `(src,tgt,src_lang,tgt_lang)` not double-emitted).
6. `test_kn_gu_formatter.py`: only `status='approved'` rows from `keyword_translations` emitted; pending/rejected ignored.
7. `test_research_domains_formatter.py`: confidence < 0.6 filtered out.
8. `test_export_rbac.py`: non-admin caller → 403.
9. `test_export_async_flag.py`: with `FINETUNE_EXPORT_ASYNC=1`, endpoint returns 202 with stub row; with `=0`, returns 200 with complete row.

Use a moto-backed S3 in tests (`moto.mock_s3`) — no real bucket calls.

## Manual verification

```bash
# Set env
export FINETUNE_S3_ENDPOINT_URL=http://localhost:9000  # minio
export FINETUNE_S3_BUCKET=jinvani-finetune-datasets
export FINETUNE_S3_ACCESS_KEY=... FINETUNE_S3_SECRET_KEY=...

# Run one task
python -m workers.finetune.dataset_export --task sa_pr

# Check PG row
psql -c "SELECT name, version, row_count, sha256 FROM finetune_datasets ORDER BY created_at DESC LIMIT 5;"

# Pull and inspect
aws s3 --endpoint-url $FINETUNE_S3_ENDPOINT_URL cp \
  s3://jinvani-finetune-datasets/sa_pr/<version>.jsonl - | head -3

# Determinism
python -m workers.finetune.dataset_export --task sa_pr
# sha256 must match the previous run; PG row count for `sa_pr` should not double.
```

## Definition of done

- [ ] Migration `0040_finetune_datasets.py` applies cleanly; rollback drops the table + enum.
- [ ] All five formatters implemented; each has a passing unit test with fixtures under `tests/finetune/fixtures/`.
- [ ] Orchestrator writes JSONL with stable ordering proven by the determinism test.
- [ ] S3 upload + PG insert is one logical transaction (PG row rolled back on S3 failure; S3 object deleted on PG failure — best-effort, with a reconciler note).
- [ ] Admin endpoint reachable from admin UI with role enforcement.
- [ ] CLI runs end-to-end against a minio container.

## Implementation notes

_(to be filled in after merge)_
