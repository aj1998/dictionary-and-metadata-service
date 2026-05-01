# 02 — Postgres Data Model

Authoritative for: metadata, IDs, parser configs, ingestion runs, candidate topics, audit logs, sync state.

## Conventions

- All primary keys are UUIDv4 (`id UUID PRIMARY KEY DEFAULT gen_random_uuid()`).
- All ingested entities have `natural_key TEXT NOT NULL UNIQUE` for idempotent upsert on re-scrape.
- All tables have `created_at TIMESTAMPTZ DEFAULT now()` and `updated_at TIMESTAMPTZ DEFAULT now()`. A trigger updates `updated_at` on every row write (see `migrations/0001_setup.sql`).
- Multilingual text fields use `JSONB` arrays with shape `[{lang, script, text}]`.
- Foreign references to non-Postgres systems (Mongo doc IDs, cataloguesearch chunk IDs) use plain `TEXT`, no FK.
- Use `pg_trgm` extension for fuzzy keyword search.

## Extensions

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;     -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pg_trgm;      -- fuzzy match
CREATE EXTENSION IF NOT EXISTS btree_gin;
```

## Enums

```sql
CREATE TYPE author_kind AS ENUM ('acharya', 'gyaani', 'scholar', 'unknown');

CREATE TYPE anuyoga_kind AS ENUM (
  'prathmanuyoga',     -- प्रथमानुयोग
  'karananuyoga',      -- करणानुयोग
  'charananuyoga',     -- चरणानुयोग
  'dravyanuyoga'       -- द्रव्यानुयोग
);

CREATE TYPE ingestion_source AS ENUM (
  'jainkosh',
  'nj', -- nikkyjain
  'vyakaran_vishleshan',
  'cataloguesearch',
  'cataloguesearch-chat' -- enrichment
);

CREATE TYPE ingestion_run_status AS ENUM (
  'pending', 'running', 'success', 'partial', 'failed', 'cancelled'
);

CREATE TYPE candidate_status AS ENUM ('pending', 'approved', 'rejected', 'merged');
```

## Core metadata tables

### `authors`

```sql
CREATE TABLE authors (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  natural_key  TEXT NOT NULL UNIQUE,            -- e.g. 'kundkundacharya'
  display_name JSONB NOT NULL,                  -- [{lang, script, text}]
  kind         author_kind NOT NULL,
  bio          JSONB,                           -- [{lang, script, text}]
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### `shastras`

```sql
CREATE TABLE shastras (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  natural_key  TEXT NOT NULL UNIQUE,            -- e.g. 'pravachansaar'
  title        JSONB NOT NULL,                  -- multilingual
  author_id    UUID NOT NULL REFERENCES authors(id) ON DELETE RESTRICT,
  source_url   TEXT,                            -- canonical source
  description  JSONB,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_shastras_author ON shastras(author_id);
```

### `anuyogas` (lookup, seeded)

```sql
CREATE TABLE anuyogas (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind         anuyoga_kind NOT NULL UNIQUE,
  display_name JSONB NOT NULL,
  description  JSONB
);
-- Seed all four kinds in 0002_seed.sql
```

### `shastra_anuyogas` (link)

```sql
CREATE TABLE shastra_anuyogas (
  shastra_id  UUID NOT NULL REFERENCES shastras(id) ON DELETE CASCADE,
  anuyoga_id  UUID NOT NULL REFERENCES anuyogas(id) ON DELETE RESTRICT,
  PRIMARY KEY (shastra_id, anuyoga_id)
);
```

### `book_anuyogas` (link)

```sql
CREATE TABLE book_anuyogas (
  book_id     UUID NOT NULL REFERENCES books(id) ON DELETE CASCADE,
  anuyoga_id  UUID NOT NULL REFERENCES anuyogas(id) ON DELETE RESTRICT,
  PRIMARY KEY (book_id, anuyoga_id)
);
```

### `teekas`

A Teeka is a commentary on a Shastra by another Gyaani. A shastra will have atleast one entry in teeka table even if we don't have teekakar details

```sql
CREATE TABLE teekas (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  natural_key                 TEXT NOT NULL UNIQUE,    -- e.g. 'pravachansaar:amritchandra'
  shastra_id                  UUID NOT NULL REFERENCES shastras(id) ON DELETE CASCADE,
  teekakar_id                 UUID REFERENCES authors(id)
  publisher                   JSONB,                   -- multilingual
  translator                  JSONB,
  editor                      JSONB,
  cataloguesearch_shastra_id  TEXT,                    -- foreign ref into cataloguesearch
  public_url                  TEXT,
  publisher_url               TEXT,
  created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_teekas_shastra ON teekas(shastra_id);
CREATE INDEX idx_teekas_teekakar ON teekas(teekakar_id);
```

### `books`

```sql
CREATE TABLE books (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  natural_key   TEXT NOT NULL UNIQUE,
  title         JSONB NOT NULL,
  shastra_id    UUID REFERENCES shastras(id) ON DELETE SET NULL,    -- optional
  publisher     JSONB,
  translator    JSONB,
  editor        JSONB,
  public_url    TEXT,
  publisher_url TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_books_shastra ON books(shastra_id);
```

### `pravachans`

```sql
CREATE TABLE pravachans (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  natural_key   TEXT NOT NULL UNIQUE,
  title         JSONB NOT NULL,
  shastra_id    UUID REFERENCES shastras(id) ON DELETE SET NULL,
  speaker_id    UUID REFERENCES authors(id),
  publisher     JSONB,
  translator    JSONB,
  editor        JSONB,
  public_url    TEXT,
  publisher_url TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

## Dictionary index tables

These hold the *index rows* for keywords/topics/gathas. Long-form text lives in Mongo and is referenced via `mongo_doc_ids`.

### `keywords`

```sql
CREATE TABLE keywords (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  natural_key     TEXT NOT NULL UNIQUE,    -- NFC-normalized Devanagari, e.g. 'आत्मा'
  display_text    TEXT NOT NULL,           -- NFC normalized; same as natural_key for now
  source_url      TEXT,                    -- jainkosh URL
  definition_doc_ids JSONB NOT NULL DEFAULT '[]'::jsonb,  -- [<mongo_id>, ...]
  graph_node_id   TEXT,                    -- Neo4j node natural_key (= this.natural_key)
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- pg_trgm index for fuzzy admin lookup (NOT used in v1 query path)
CREATE INDEX idx_keywords_text_trgm ON keywords USING gin (display_text gin_trgm_ops);
```

### `keyword_aliases`

Synonyms / variant spellings. Mined from JainKosh redirects + admin-curated.

```sql
CREATE TABLE keyword_aliases (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  alias_text   TEXT NOT NULL,              -- NFC normalized
  keyword_id   UUID NOT NULL REFERENCES keywords(id) ON DELETE CASCADE,
  source       TEXT NOT NULL,              -- 'jainkosh_redirect' | 'admin' | 'manual_seed'
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (alias_text)
);

CREATE INDEX idx_keyword_aliases_keyword ON keyword_aliases(keyword_id);
CREATE INDEX idx_keyword_aliases_alias_trgm ON keyword_aliases USING gin (alias_text gin_trgm_ops);
```

### `gathas`

```sql
CREATE TABLE gathas (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  natural_key              TEXT NOT NULL UNIQUE,        -- e.g. 'pravachansaar:039'
  shastra_id               UUID NOT NULL REFERENCES shastras(id) ON DELETE CASCADE,
  gatha_number             TEXT NOT NULL,               -- '039' or '004-005' for ranges
  adhikaar                 JSONB,                       -- chapter title (multilingual)
  heading                  JSONB,                       -- title under which gatha sits, used as a topic seed
  prakrit_doc_id           TEXT,                        -- mongo id
  sanskrit_doc_id          TEXT,
  hindi_chhand_doc_ids     JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [mongo_id, ...] (multiple harigeets allowed)
  prakrit_word_meanings_doc_id  TEXT,
  sanskrit_word_meanings_doc_id TEXT,
  teeka_mapping_doc_ids    JSONB NOT NULL DEFAULT '[]'::jsonb,   -- one per teeka
  keyword_ids              JSONB NOT NULL DEFAULT '[]'::jsonb,   -- [uuid, ...]
  topic_ids                JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_gathas_shastra ON gathas(shastra_id);
CREATE INDEX idx_gathas_keyword_ids ON gathas USING gin (keyword_ids jsonb_path_ops);
CREATE INDEX idx_gathas_topic_ids ON gathas USING gin (topic_ids jsonb_path_ops);
```

### `topics`

```sql
CREATE TABLE topics (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  natural_key     TEXT NOT NULL UNIQUE,         -- e.g. 'jainkosh:आत्मा:बहिरात्मादि-3-भेद'
  display_text    JSONB NOT NULL,               -- multilingual heading
  source          ingestion_source NOT NULL,
  parent_keyword_id UUID REFERENCES keywords(id) ON DELETE SET NULL,  -- topic was extracted from this keyword's page
  extract_doc_ids JSONB NOT NULL DEFAULT '[]'::jsonb,                 -- [mongo_id, ...]
  graph_node_id   TEXT,                         -- Neo4j node natural_key (= this.natural_key)
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_topics_parent_keyword ON topics(parent_keyword_id);
```

### `topic_mentions` (where a topic is cited)

```sql
CREATE TABLE topic_mentions (
  id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  topic_id                    UUID NOT NULL REFERENCES topics(id) ON DELETE CASCADE,

  -- atleast one of the following groupings should be non-null:
  teeka_id                    UUID REFERENCES teekas(id),
  gatha_id                    UUID REFERENCES gathas(id),
  book_id                     UUID REFERENCES books(id),
  pravachan_id                UUID REFERENCES pravachans(id),

  page                        INT,
  -- foreign references (no FK):
  cataloguesearch_chunk_id    TEXT,         -- preferred when the source is in cataloguesearch
  mongo_doc_id                TEXT,         -- when the source is in our Mongo

  created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),

  CHECK (
    (teeka_id IS NOT NULL)::int +
    (gatha_id IS NOT NULL)::int +
    (book_id IS NOT NULL)::int +
    (pravachan_id IS NOT NULL)::int = 1
  )
);

CREATE INDEX idx_topic_mentions_topic ON topic_mentions(topic_id);
CREATE INDEX idx_topic_mentions_chunk ON topic_mentions(cataloguesearch_chunk_id);
```

## Ingestion / operations tables

### `parser_configs` (registry — files live in `parser_configs/`)

```sql
CREATE TABLE parser_configs (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source       ingestion_source NOT NULL,
  config_path  TEXT NOT NULL,                -- relative path under parser_configs/
  version      TEXT NOT NULL,                -- semver of the config
  checksum     TEXT NOT NULL,                -- sha256 of file content at registration time
  active       BOOLEAN NOT NULL DEFAULT true,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (source, config_path, version)
);
```

### `ingestion_runs`

```sql
CREATE TABLE ingestion_runs (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source            ingestion_source NOT NULL,
  parser_config_id  UUID REFERENCES parser_configs(id),
  triggered_by      TEXT NOT NULL,                  -- admin user / 'cron'
  status            ingestion_run_status NOT NULL DEFAULT 'pending',
  started_at        TIMESTAMPTZ,
  finished_at       TIMESTAMPTZ,
  iterator_state    JSONB NOT NULL DEFAULT '{}'::jsonb,   -- e.g. {"last_letter": "क", "last_keyword": "कर्म"}
  raw_html_dir      TEXT,                           -- absolute path on disk
  stats             JSONB NOT NULL DEFAULT '{}'::jsonb,   -- {pages_scraped, entities_upserted, errors}
  error_log         TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_ingestion_runs_source_status ON ingestion_runs(source, status);
```

### `ingestion_review_queue`

Each parsed entity awaits admin approval before it's promoted to public-visible.

```sql
CREATE TABLE ingestion_review_queue (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ingestion_run_id  UUID NOT NULL REFERENCES ingestion_runs(id) ON DELETE CASCADE,
  entity_type       TEXT NOT NULL,             -- 'letter' | 'keyword' | 'topic' | 'gatha' | 'shastra' | 'teeka'
  entity_natural_key TEXT NOT NULL,
  proposed_payload  JSONB NOT NULL,            -- the would-be row (postgres + mongo + graph fragments)
  diff_against_existing JSONB,                 -- nullable, computed if entity already exists
  status            candidate_status NOT NULL DEFAULT 'pending',
  reviewed_by       TEXT,
  reviewed_at       TIMESTAMPTZ,
  reject_reason     TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_review_queue_status ON ingestion_review_queue(status);
CREATE INDEX idx_review_queue_run ON ingestion_review_queue(ingestion_run_id);
```

### `topic_candidates` (from cataloguesearch-chat)

Pulled nightly by `chat_candidate_puller`. Admins approve → become real topics.

```sql
CREATE TABLE topic_candidates (
  id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_chat_id           TEXT NOT NULL UNIQUE,        -- ID from cataloguesearch-chat DB; idempotent
  proposed_topic_text      JSONB NOT NULL,              -- multilingual
  associated_keyword_texts JSONB NOT NULL,              -- [str, ...] (NFC normalized)
  user_query               TEXT,
  llm_explanation          TEXT,
  cataloguesearch_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  status                   candidate_status NOT NULL DEFAULT 'pending',
  merged_into_topic_id     UUID REFERENCES topics(id),
  reviewed_by              TEXT,
  reviewed_at              TIMESTAMPTZ,
  reject_reason            TEXT,
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_topic_candidates_status ON topic_candidates(status);
```

### `chat_puller_state`

```sql
CREATE TABLE chat_puller_state (
  id                  INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),  -- single row
  last_pulled_at      TIMESTAMPTZ,
  last_source_id      TEXT,
  last_run_status     TEXT,
  last_error          TEXT
);
```

### `query_logs` (audit + future quality metrics)

```sql
CREATE TABLE query_logs (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_text          TEXT NOT NULL,
  normalized_tokens   JSONB NOT NULL,
  matched_keyword_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
  topic_ids_returned  JSONB NOT NULL DEFAULT '[]'::jsonb,
  num_results         INT NOT NULL DEFAULT 0,
  latency_ms          INT,
  caller              TEXT,                -- 'cataloguesearch-chat' | 'public-ui' | 'admin'
  created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_query_logs_created ON query_logs(created_at DESC);
```

## Migration plan (Alembic)

```
migrations/
├── 0001_setup.sql              extensions, enums, updated_at trigger
├── 0002_seed_anuyogas.sql      insert four anuyoga rows
├── 0003_authors_shastras.py    authors, shastras, link tables
├── 0004_teekas_books_pravachans.py
├── 0005_keywords_aliases.py
├── 0006_gathas_topics_mentions.py
├── 0007_ingestion_ops.py       parser_configs, ingestion_runs, review_queue
├── 0008_chat_enrichment.py     topic_candidates, chat_puller_state
└── 0009_query_logs.py
```

## SQLAlchemy model layout

```
packages/jain_kb_common/db/postgres/
├── __init__.py        # async engine + session factory from env
├── base.py            # DeclarativeBase, TimestampMixin
├── enums.py
├── authors.py
├── shastras.py
├── anuyogas.py
├── teekas.py
├── books.py
├── pravachans.py
├── keywords.py
├── gathas.py
├── topics.py
├── ingestion.py       # parser_configs, ingestion_runs, review_queue
├── enrichment.py      # topic_candidates, chat_puller_state
└── query_logs.py
```

## Sample upsert pattern (idempotent re-scrape)

```python
# packages/jain_kb_common/db/postgres/upserts.py
async def upsert_keyword(session, *, natural_key: str, display_text: str,
                          source_url: str, definition_doc_ids: list[str]) -> uuid.UUID:
    stmt = pg_insert(Keyword).values(
        natural_key=natural_key,
        display_text=display_text,
        source_url=source_url,
        definition_doc_ids=definition_doc_ids,
    ).on_conflict_do_update(
        index_elements=[Keyword.natural_key],
        set_={
            "display_text": display_text,
            "source_url": source_url,
            "definition_doc_ids": definition_doc_ids,
            "updated_at": func.now(),
        },
    ).returning(Keyword.id)
    res = await session.execute(stmt)
    return res.scalar_one()
```

## Definition of Done

- [ ] All tables, enums, indexes created via Alembic migrations.
- [ ] `0002_seed_anuyogas.sql` populates four anuyoga rows with multilingual labels.
- [ ] All SQLAlchemy models pass `mypy --strict` and round-trip a sample fixture.
- [ ] `upsert_*` functions exist for keywords, topics, gathas, shastras, teekas, books, pravachans.
- [ ] `pytest tests/db/test_idempotent_upsert.py` proves running ingestion twice produces identical row count and overwrites fields.
