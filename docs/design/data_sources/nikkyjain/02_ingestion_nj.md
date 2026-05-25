# 02 — Ingestion: nikkyjain per-file HTML → DB

Maps `ShastraParseResult` (from `01_parser_nj.md`) into Postgres, MongoDB, and Neo4j.
Includes the apply script spec (`scripts/ingest_nj_apply.py`).

All patterns use `{shastra_nk}`, `{teeka_a_nk}`, `{teeka_j_nk}` as placeholders driven by
the parser config. No shastra identity is hard-coded in the ingestion layer.

---

## 1. Natural Key Conventions

**All label segments in natural keys use Hindi words** (matching JainKosh style where labels appear in Hindi, e.g. `समयसार:आत्मख्याति:गाथा:टीका:8`).

Label constants (defined in `envelope.py`):
- `गाथा` — gatha label segment (in gatha natural keys and Neo4j GathaTeeka keys)
- `कलश` — kalash label segment
- `टीका` — teeka content label segment (distinct from the teeka NK itself)
- `भावार्थ` — bhaavarth label segment
- `अध्याय` — chapter/adhyaay label segment

Variables used throughout:
- `{shastra_nk}` — from `cfg.shastra.natural_key` (e.g. `"समयसार"`)
- `{teeka_a_nk}` — primary teeka natural_key (e.g. `"समयसार:आत्मख्याति"`)
- `{teeka_j_nk}` — secondary teeka natural_key (e.g. `"समयसार:तात्पर्यवृत्ति"`)
- `{pub_a_nk}` — primary teeka publication (e.g. `"समयसार:आत्मख्याति:0"`) — uses numeric publisher id
- `{pub_j_nk}` — secondary teeka publication (e.g. `"समयसार:तात्पर्यवृत्ति:0"`)
- `{gatha_nk}` — `{shastra_nk}:गाथा:{gatha_number}` (e.g. `"समयसार:गाथा:1"`) — no leading zeros
- `{kalash_a_nk}` — `{teeka_a_nk}:कलश:{N}` (e.g. `"समयसार:आत्मख्याति:कलश:1"`)
- `{kalash_j_nk}` — `{teeka_j_nk}:कलश:{N}` (e.g. `"समयसार:तात्पर्यवृत्ति:कलश:11"`)

### Postgres entity natural keys

| Entity | Pattern | Samaysar example |
|---|---|---|
| Shastra | `{shastra_nk}` | `समयसार` |
| Author (text author) | `{author_nk}` | `कुन्दकुन्दाचार्य` |
| Primary teekakar | `{teekakar_a_nk}` | `अमृतचंद्राचार्य` |
| Secondary teekakar | `{teekakar_j_nk}` | `जयसेनाचार्य` |
| Primary teeka | `{teeka_a_nk}` | `समयसार:आत्मख्याति` |
| Secondary teeka | `{teeka_j_nk}` | `समयसार:तात्पर्यवृत्ति` |
| Primary publication | `{pub_a_nk}` | `समयसार:आत्मख्याति:0` |
| Secondary publication | `{pub_j_nk}` | `समयसार:तात्पर्यवृत्ति:0` |
| Gatha | `{gatha_nk}` | `समयसार:गाथा:1`, `समयसार:गाथा:9` |
| Primary kalash (global counter) | `{kalash_a_nk}` | `समयसार:आत्मख्याति:कलश:1` |
| Secondary kalash | `{kalash_j_nk}` | `समयसार:तात्पर्यवृत्ति:कलश:11` |
| Teeka chapter | `{teeka_a_nk}:अध्याय:{N}` | `समयसार:आत्मख्याति:अध्याय:1` |

### MongoDB doc natural keys

| Collection | Pattern | Samaysar example |
|---|---|---|
| `gatha_prakrit` | `{gatha_nk}:prakrit` | `समयसार:गाथा:1:prakrit` |
| `gatha_sanskrit` | `{gatha_nk}:sanskrit` | `समयसार:गाथा:1:sanskrit` |
| `gatha_hindi_chhand` | `{gatha_nk}:chhand:{N}` | `समयसार:गाथा:1:chhand:1` |
| `teeka_gatha_mapping` (primary) | `{teeka_a_nk}:{gatha_number}` | `समयसार:आत्मख्याति:1` |
| `gatha_teeka_sanskrit` (primary) | `{teeka_a_nk}:{gatha_number}:टीका:san` | `समयसार:आत्मख्याति:1:टीका:san` |
| `gatha_teeka_sanskrit` (secondary) | `{teeka_j_nk}:{gatha_number}:टीका:san` | `समयसार:तात्पर्यवृत्ति:1:टीका:san` |
| `gatha_teeka_bhaavarth_hindi` (primary) | `{pub_a_nk}:{gatha_number}:भावार्थ:hi` | `समयसार:आत्मख्याति:0:1:भावार्थ:hi` |
| `gatha_teeka_bhaavarth_hindi` (secondary) | `{pub_j_nk}:{gatha_number}:भावार्थ:hi` | `समयसार:तात्पर्यवृत्ति:0:1:भावार्थ:hi` |
| `kalash_sanskrit` | `{kalash_a_nk}:san` | `समयसार:आत्मख्याति:कलश:1:san` |
| `kalash_hindi` | `{kalash_a_nk}:hi` | `समयसार:आत्मख्याति:कलश:1:hi` |
| `kalash_word_meanings` | `{kalash_a_nk}:word_meanings` | `समयसार:आत्मख्याति:कलश:1:word_meanings` |

For **secondary-only kalash pages**, the gatha_nk slot is replaced by the kalash NK:
- `gatha_prakrit` → `{kalash_j_nk}:prakrit`
- `gatha_teeka_sanskrit` → `{kalash_j_nk}:टीका:san`
- `gatha_teeka_bhaavarth_hindi` → `{pub_j_nk}:कलश:{N}:भावार्थ:hi`

---

## 2. Postgres Writes

Order matters (FK dependencies):

```
1. upsert author (text author + teekakar authors)
2. upsert shastra
3. upsert teekas
4. upsert publications
5. for each GathaExtract:
       upsert gatha
6. for each primary-teeka kalash (global counter order):
       upsert kalash (with gatha_id FK)
7. for each secondary KalashExtract:
       upsert kalash (with gatha_id FK → preceding primary gatha)
```

### 2.1 `upsert_author`

```python
# Text author
await upsert_author(session,
    natural_key=cfg.shastra.author.natural_key,
    display_name=[{"lang": "hin", "script": "Deva", "text": cfg.shastra.author.display_name_hi}],
    kind=cfg.shastra.author.kind,
)
# Teekakar authors (one per teeka in config)
for teeka_cfg in cfg.shastra.teekas:
    await upsert_author(session,
        natural_key=teeka_cfg.teekakar_natural_key,
        display_name=[{"lang": "hin", "script": "Deva", "text": teeka_cfg.teekakar_display_name_hi}],
        kind="acharya",
    )
```

### 2.2 `upsert_shastra`

```python
shastra_id = await upsert_shastra(session,
    natural_key=cfg.shastra.natural_key,
    title=[{"lang": "hin", "script": "Deva", "text": cfg.shastra.title_hi}],
    author_natural_key=cfg.shastra.author.natural_key,
)
```

### 2.3 `upsert_teekas` and `upsert_publications`

```python
for teeka_cfg in cfg.shastra.teekas:
    await upsert_teeka(session,
        natural_key=teeka_cfg.natural_key,
        shastra_natural_key=cfg.shastra.natural_key,
        teekakar_natural_key=teeka_cfg.teekakar_natural_key,
    )
    await upsert_publication(session,
        natural_key=teeka_cfg.publication_natural_key,
        teeka_natural_key=teeka_cfg.natural_key,
        publisher_id=teeka_cfg.publisher_id,
    )
```

### 2.4 `upsert_gatha`

Called with each individual `GathaExtract` (after multi-page expansion):

```python
gatha_id = await upsert_gatha(session,
    natural_key=f"{shastra_nk}:{extract.gatha_number}",
    shastra_natural_key=shastra_nk,
    gatha_number=extract.gatha_number,
    adhikaar=[{"lang": "hin", "script": "Deva", "text": extract.adhikaar_hi}] if extract.adhikaar_hi else None,
    heading=[{"lang": "hin", "script": "Deva", "text": extract.heading_hi}] if extract.heading_hi else None,
    # doc IDs filled after Mongo writes (see §3)
)
```

### 2.5 `upsert_kalash` — Primary teeka global kalashes

```python
# For each primary kalash (global_num = 1-based, zero-padded to 3 digits):
kalash_nk = f"{teeka_a_nk}:kalash:{global_num:03d}"
await upsert_kalash(session,
    natural_key=kalash_nk,
    teeka_natural_key=teeka_a_nk,
    kalash_number=f"{global_num:03d}",
    gatha_id=gatha_id,         # UUID of the gatha this kalash belongs to
    # doc IDs filled after Mongo writes
)
```

### 2.6 `upsert_kalash` — Secondary teeka standalone kalashes

```python
for k in parse_result.secondary_kalashes:
    kalash_nk = f"{teeka_j_nk}:kalash:{k.kalash_number}"
    preceding_gatha_id = await _resolve_gatha_id(session,
        natural_key=f"{shastra_nk}:{k.preceding_primary_gatha_number}")
    await upsert_kalash(session,
        natural_key=kalash_nk,
        teeka_natural_key=teeka_j_nk,
        kalash_number=k.kalash_number,
        gatha_id=preceding_gatha_id,    # FK to preceding primary-gatha
    )
```

### 2.7 Update Gatha / Kalash doc IDs (after Mongo writes)

```python
await update_gatha_doc_ids(session, gatha_id,
    prakrit_doc_id=str(prakrit_oid),
    sanskrit_doc_id=str(sanskrit_oid),
    hindi_chhand_doc_ids=[str(oid) for oid in chhand_oids],
    prakrit_word_meanings_doc_id=str(wm_oid),
    teeka_mapping_doc_ids=[str(a_mapping_oid), str(j_mapping_oid)],
)
await update_kalash_doc_ids(session, kalash_id,
    sanskrit_doc_id=str(kalash_san_oid),
    hindi_doc_id=str(kalash_hi_oid),
)
```

---

## 3. MongoDB Writes

Use `stable_id(natural_key)` (SHA1 → 12-byte ObjectId) for deterministic IDs.

### 3.1 `gatha_prakrit`

One doc per individual `GathaExtract` (after multi-page expansion):

```json
{
  "natural_key": "{gatha_nk}:prakrit",
  "shastra_natural_key": "{shastra_nk}",
  "gatha_natural_key": "{gatha_nk}",
  "gatha_number": "001",
  "text": [{"lang": "pra", "script": "Deva", "text": "वंदित्तु सव्वसिद्धे..."}],
  "is_kalash": false,
  "raw_html_fragment": "<div class='gatha'>...</div>",
  "ingestion_run_id": "uuid"
}
```

For secondary-only kalash pages:
- `natural_key = "{kalash_j_nk}:prakrit"`
- `gatha_natural_key = "{kalash_j_nk}"`
- `is_kalash = true`

### 3.2 `gatha_sanskrit`

```json
{
  "natural_key": "{gatha_nk}:sanskrit",
  "shastra_natural_key": "{shastra_nk}",
  "gatha_natural_key": "{gatha_nk}",
  "gatha_number": "001",
  "text": [{"lang": "san", "script": "Deva", "text": "वंदित्वा सर्वसिद्धान्..."}],
  "ingestion_run_id": "uuid"
}
```

Skip if `extract.sanskrit_text is None`.

### 3.3 `gatha_hindi_chhand`

One doc per chhand (`chhand_index` zero-padded to 2 digits):

```json
{
  "natural_key": "{gatha_nk}:chhand:01",
  "gatha_natural_key": "{gatha_nk}",
  "chhand_index": 1,
  "chhand_type": "harigeet",
  "translator": [{"lang": "hin", "script": "Deva", "text": "nikkyjain"}],
  "text": [{"lang": "hin", "script": "Deva", "text": "ध्रुव अचल अनुपम..."}],
  "ingestion_run_id": "uuid"
}
```

### 3.4 `gatha_word_meanings` (**new field: `full_anyavaarth`**)

One doc per gatha. Includes the new `full_anyavaarth` top-level field:

```json
{
  "natural_key": "{gatha_nk}:word_meanings:prakrit",
  "gatha_natural_key": "{gatha_nk}",
  "source_language": "pra",
  "full_anyavaarth": "ध्रुव, अचल और अनुपम गति को प्राप्त हुए सर्व सिद्धों को नमस्कार करके...",
  "entries": [
    {
      "source_word": [{"lang": "pra", "script": "Deva", "text": "धुवमचलमणोवमं"}],
      "meanings": [{"lang": "hin", "script": "Deva", "text": "ध्रुव, अचल और अनुपम"}],
      "position": 1
    }
  ],
  "ingestion_run_id": "uuid"
}
```

Write even if `entries = []` (no tagged terms); `full_anyavaarth` is always required.

### 3.5 `teeka_gatha_mapping` (**new fields: `is_related`, `full_anyavaarth`**)

One doc per (teeka, gatha) pair:

```json
{
  "natural_key": "{teeka_a_nk}:001",
  "teeka_natural_key": "{teeka_a_nk}",
  "gatha_natural_key": "{gatha_nk}",
  "anvayartha": [{"lang": "hin", "script": "Deva", "text": "ध्रुव, अचल..."}],
  "tagged_terms": [
    {"source_word": "धुवमचलमणोवमं", "meaning": "ध्रुव, अचल और अनुपम"}
  ],
  "full_anyavaarth": "ध्रुव, अचल और अनुपम गति को...",
  "is_related": [],
  "ingestion_run_id": "uuid"
}
```

**Multi-gatha pages** — for each individual gatha on a combined page, write separate docs
with `is_related` listing the other gathas on that page:

```json
// For gatha 009 on page 009-010
{ "natural_key": "{teeka_a_nk}:009", "is_related": ["010"], ...same content... }
// For gatha 010 on page 009-010
{ "natural_key": "{teeka_a_nk}:010", "is_related": ["009"], ...same content... }
```

Write J's mapping doc similarly (same anyavartha, different `teeka_natural_key`).

### 3.6 `gatha_teeka_sanskrit`

One doc per (teeka, gatha) where teeka has Sanskrit prose:

```json
{
  "natural_key": "{teeka_a_nk}:{gatha_number}:teeka:san",
  "gatha_teeka_natural_key": "{teeka_a_nk}:{gatha_number}",
  "teeka_natural_key": "{teeka_a_nk}",
  "gatha_number": "001",
  "text": [{"lang": "san", "script": "Deva", "text": "अथ सूत्रावतार -\n\nअथ प्रथमत एव..."}],
  "ingestion_run_id": "uuid"
}
```

Skip if `gatha_teeka_san is None`.
For multi-gatha pages: write one doc per individual gatha (duplicate content, different natural_key).

### 3.7 `gatha_teeka_bhaavarth_hindi`

One doc per (publication, gatha) pair:

```json
{
  "natural_key": "{pub_a_nk}:{gatha_number}:bhaavarth:hi",
  "gatha_teeka_bhaavarth_natural_key": "{pub_a_nk}:{gatha_number}:bhaavarth:hi",
  "publication_natural_key": "{pub_a_nk}",
  "gatha_teeka_natural_key": "{teeka_a_nk}:{gatha_number}",
  "publisher_id": "nikkyjain",
  "gatha_number": "001",
  "text": [{"lang": "hin", "script": "Deva", "text": "यह पंचमगति..."}],
  "ingestion_run_id": "uuid"
}
```

`text[0].text` = the Markdown string (consumers display Markdown).

### 3.8 `kalash_sanskrit`

One doc per primary-teeka kalash (global counter):

```json
{
  "natural_key": "{kalash_a_nk}:san",
  "kalash_natural_key": "{kalash_a_nk}",
  "teeka_natural_key": "{teeka_a_nk}",
  "kalash_number": "001",
  "text": [{"lang": "san", "script": "Deva", "text": "नम: समयसाराय...॥१॥"}],
  "chhand_type": "अनुष्टुभ्",
  "ingestion_run_id": "uuid"
}
```

### 3.9 `kalash_hindi`

```json
{
  "natural_key": "{kalash_a_nk}:hi",
  "kalash_natural_key": "{kalash_a_nk}",
  "teeka_natural_key": "{teeka_a_nk}",
  "kalash_number": "001",
  "text": [{"lang": "hin", "script": "Deva", "text": "निज अनुभूति से प्रगट..."}],
  "chhand_type": "दोहा",
  "ingestion_run_id": "uuid"
}
```

### 3.10 `kalash_word_meanings` (**new collection**)

One doc per primary-teeka kalash that has word meanings (maroon-color entries):

```json
{
  "natural_key": "{kalash_a_nk}:word_meanings",
  "kalash_natural_key": "{kalash_a_nk}",
  "teeka_natural_key": "{teeka_a_nk}",
  "kalash_number": "001",
  "entries": [
    {"source_word": "स्वानुभूत्या चकासते", "meaning": "स्वानुभूति से प्रकाशित", "position": 1},
    {"source_word": "चित्स्वभावाय", "meaning": "चैतन्य-स्वभावी", "position": 2}
  ],
  "ingestion_run_id": "uuid"
}
```

Skip doc entirely if `entries` is empty.

---

## 4. Neo4j Writes

All Neo4j output is built by `_build_neo4j()` in `envelope.py` and emitted in `would_write.neo4j`.

### 4.1 Node types and key patterns

| Label | Key pattern | Samaysar example |
|---|---|---|
| `Shastra` | `{shastra_nk}` | `समयसार` |
| `Teeka` | `{teeka_nk}` | `समयसार:आत्मख्याति` |
| `Publication` | `{pub_nk}` | `समयसार:आत्मख्याति:0` |
| `Topic` | heading text (deduplicated) | `सिद्धों को नमस्कार` |
| `Gatha` | `{shastra_nk}:गाथा:{gatha_num}` | `समयसार:गाथा:1` |
| `GathaTeeka` | `{teeka_nk}:गाथा:टीका:{gatha_num}` | `समयसार:आत्मख्याति:गाथा:टीका:1` |
| `GathaTeekaBhaavarth` | `{pub_nk}:गाथा:टीका:भावार्थ:{gatha_num}` | `समयसार:आत्मख्याति:0:गाथा:टीका:भावार्थ:1` |
| `Kalash` | `{teeka_nk}:कलश:{kalash_num}` | `समयसार:आत्मख्याति:कलश:1` |
| `KalashBhaavarth` | `{pub_nk}:कलश:भावार्थ:{kalash_num}` | `समयसार:आत्मख्याति:0:कलश:भावार्थ:1` |

### 4.2 Edge types

| Edge | From | To |
|---|---|---|
| `HAS_TEEKA` | Shastra | Teeka |
| `HAS_PUBLICATION` | Teeka | Publication |
| `HAS_PUBLICATION` | Shastra | Publication |
| `MENTIONS_TOPIC` | Gatha | Topic |
| `HAS_GATHA_TEEKA` | Teeka | GathaTeeka |
| `HAS_BHAAVARTH` | Publication | GathaTeekaBhaavarth |
| `HAS_KALASH` | Teeka | Kalash |
| `HAS_BHAAVARTH` | Publication | KalashBhaavarth |

Notes:
- `GathaTeeka` is emitted only when the gatha has primary/secondary teeka data (`primary_teeka is not None` / `secondary_teeka is not None`).
- `GathaTeekaBhaavarth` is emitted only when `gatha_teeka_bhaavarth_md` is non-empty.
- `Kalash` and `KalashBhaavarth` are emitted for each `kalash_san` entry in the primary teeka, and for each secondary `KalashExtract`.
- Topic nodes are deduplicated by `heading_hi` text.

---

## 5. Apply Script Spec (`scripts/ingest_nj_apply.py`)

### 5.1 Interface

```bash
python scripts/ingest_nj_apply.py \
  --config parser_configs/nj/samaysaar.yaml \
  [--dry-run]                     # parse + print summary; no DB writes
  [--gatha 001]                   # apply a single gatha only (for testing)
  [--neo4j-database jainkb]
  [--ingestion-run-id <uuid>]     # optional; stamps Mongo docs
  [--clear-first]                 # wipe this shastra's data before apply
```

`--config` is the only required argument; all shastra identity comes from the config file.

### 5.2 Environment Variables

```
DATABASE_URL=postgresql+asyncpg://...
MONGO_URL=mongodb://localhost:27017
MONGO_DB_NAME=jain_kb
NEO4J_URL=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=...
NIKKYJAIN_LOCAL_PATH=/path/to/nikkyjain.github.io
```

### 5.3 Script Structure

```python
# scripts/ingest_nj_apply.py

async def _run(args):
    cfg = load_config(args.config)   # generic; works for any nj shastra config
    shastra_nk = cfg.shastra.natural_key
    teeka_a_cfg = next(t for t in cfg.shastra.teekas if t.role == "primary")
    teeka_j_cfg = next((t for t in cfg.shastra.teekas if t.role == "secondary"), None)

    parse_result = parse_shastra(cfg)   # workers/ingestion/nj/orchestrator.py

    if args.dry_run:
        _print_summary(parse_result, shastra_nk)
        return

    engine = create_async_engine(os.environ["DATABASE_URL"])
    mongo_client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    mongo_db = mongo_client[os.environ.get("MONGO_DB_NAME", "jain_kb")]
    neo4j_driver = get_driver(...)

    async with engine.begin() as conn:
        await _ensure_postgres_extensions(conn)
        await conn.run_sync(Base.metadata.create_all)
    await ensure_indexes(mongo_db)
    await ensure_constraints(neo4j_driver, ...)

    async with async_sessionmaker(engine)() as session:
        # 1. Upsert metadata entities
        await _upsert_metadata(session, cfg)

        # 2. Apply each gatha
        selected = [g for g in parse_result.gathas
                    if args.gatha is None or g.gatha_number == args.gatha]
        global_kalash_counter = _GlobalCounter()
        for extract in selected:
            await apply_gatha_extract(
                extract, session, mongo_db, neo4j_driver, cfg,
                ingestion_run_id=args.ingestion_run_id,
                neo4j_database=args.neo4j_database,
                global_kalash_counter=global_kalash_counter,
            )
            print(f"[{shastra_nk}] applied gatha {extract.gatha_number}")

        # 3. Apply secondary-only kalashes
        for k in parse_result.secondary_kalashes:
            await apply_secondary_kalash(k, session, mongo_db, neo4j_driver, cfg, ...)
            print(f"[{shastra_nk}] applied secondary kalash {k.kalash_number}")

    print(f"done: {len(selected)} gathas, {len(parse_result.secondary_kalashes)} secondary kalashes")


async def apply_gatha_extract(extract, session, mongo_db, neo4j_driver, cfg, ...):
    """Idempotently write one GathaExtract to all three databases."""
    shastra_nk = cfg.shastra.natural_key
    teeka_a_nk = _primary_teeka_nk(cfg)
    teeka_j_nk = _secondary_teeka_nk(cfg)
    pub_a_nk = _primary_pub_nk(cfg)
    pub_j_nk = _secondary_pub_nk(cfg)
    gatha_nk = f"{shastra_nk}:{extract.gatha_number}"

    # --- Mongo ---
    prakrit_oid = None
    if extract.prakrit_text:
        prakrit_oid = await upsert_gatha_prakrit(mongo_db, natural_key=f"{gatha_nk}:prakrit", ...)
    sanskrit_oid = None
    if extract.sanskrit_text:
        sanskrit_oid = await upsert_gatha_sanskrit(mongo_db, ...)
    chhand_oids = []
    for chhand in extract.hindi_chhands:
        oid = await upsert_gatha_hindi_chhand(mongo_db, ...)
        chhand_oids.append(oid)
    wm_oid = None
    if extract.anyavartha:
        wm_oid = await upsert_gatha_word_meanings(mongo_db, ...)
    a_mapping_oid = await upsert_teeka_gatha_mapping(mongo_db, teeka_nk=teeka_a_nk, ...)
    if teeka_j_nk:
        j_mapping_oid = await upsert_teeka_gatha_mapping(mongo_db, teeka_nk=teeka_j_nk, ...)

    # Primary teeka prose
    a_teeka = extract.primary_teeka
    if a_teeka and a_teeka.gatha_teeka_san:
        await upsert_gatha_teeka_sanskrit(mongo_db, teeka_nk=teeka_a_nk, ...)
    if a_teeka and a_teeka.gatha_teeka_bhaavarth_md:
        await upsert_gatha_teeka_bhaavarth_hindi(mongo_db, pub_nk=pub_a_nk, ...)

    # Secondary teeka prose
    j_teeka = extract.secondary_teeka
    if j_teeka and j_teeka.gatha_teeka_san:
        await upsert_gatha_teeka_sanskrit(mongo_db, teeka_nk=teeka_j_nk, ...)
    if j_teeka and j_teeka.gatha_teeka_bhaavarth_md:
        await upsert_gatha_teeka_bhaavarth_hindi(mongo_db, pub_nk=pub_j_nk, ...)

    # Primary teeka kalashes (page-level)
    kalash_oids: dict[int, dict] = {}
    if a_teeka:
        for local_idx, san_entry in enumerate(a_teeka.kalash_san, start=1):
            global_num = global_kalash_counter.next()
            kalash_nk = f"{teeka_a_nk}:kalash:{global_num:03d}"
            san_oid = await upsert_kalash_sanskrit(mongo_db, kalash_nk=kalash_nk, ...)
            hi_entry = a_teeka.kalash_hindi[local_idx - 1] if local_idx <= len(a_teeka.kalash_hindi) else None
            hi_oid = await upsert_kalash_hindi(mongo_db, kalash_nk=kalash_nk, ...) if hi_entry else None
            wm_entries = a_teeka.kalash_word_meanings.get(local_idx, [])
            wm_oid_k = await upsert_kalash_word_meanings(mongo_db, kalash_nk=kalash_nk, entries=wm_entries, ...) if wm_entries else None
            kalash_oids[global_num] = {"san": san_oid, "hi": hi_oid, "wm": wm_oid_k}

    # --- Postgres ---
    gatha_id = await upsert_gatha(session, natural_key=gatha_nk, ...)

    for global_num, oids in kalash_oids.items():
        await upsert_kalash(session,
            natural_key=f"{teeka_a_nk}:kalash:{global_num:03d}",
            teeka_natural_key=teeka_a_nk,
            kalash_number=f"{global_num:03d}",
            gatha_id=gatha_id,
            sanskrit_doc_id=str(oids["san"]) if oids["san"] else None,
            hindi_doc_id=str(oids["hi"]) if oids["hi"] else None,
        )

    # --- Neo4j ---
    await sync_gatha_to_neo4j(neo4j_driver, gatha_nk=gatha_nk, gatha_id=gatha_id, ...)
    if extract.heading_hi:
        await sync_gatha_topic(neo4j_driver, gatha_nk=gatha_nk, heading_hi=extract.heading_hi,
                               shastra_nk=shastra_nk)
```

### 5.4 Dry-Run Output

```
[samaysaar] 285 gathas, 18 secondary kalashes
primary kalashes total: 87 (across all gatha pages)
gathas with Sanskrit: 285
gathas with Hindi chhand: 285
gathas with anyavartha: 282 (3 missing)
would apply 285 gatha(s)
```

---

## 6. Idempotency

All DB writes use `on_conflict_do_update` (Postgres) and `update_one(upsert=True)` (Mongo),
keyed on `natural_key`. Running the script twice must produce identical row/document counts.

Check: `pytest workers/ingestion/nj/tests/test_idempotency.py --run-db-tests`
(uses test Postgres + Mongo; requires env vars).

---

## 7. Definition of Done

(Example assertions use Samaysar fixtures.)

- [ ] `ingest_nj_apply.py --config parser_configs/nj/samaysaar.yaml --dry-run` prints ≥ 270 gathas and ≥ 80 primary kalashes.
- [ ] `ingest_nj_apply.py --config parser_configs/nj/samaysaar.yaml --gatha 001` writes correctly to Postgres + Mongo + Neo4j; verified by spot queries.
- [ ] Primary kalash global counter is stable across runs (same `kalash_number` for the same kalash on page 001).
- [ ] Secondary kalash from page 012 writes `Kalash` PG row with `gatha_id` pointing to gatha `समयसार:10`.
- [ ] Multi-gatha page `009-010` produces **two** `teeka_gatha_mapping` docs (one per gatha), with `is_related` populated.
- [ ] `teeka_gatha_mapping` docs have non-empty `full_anyavaarth` field.
- [ ] `kalash_word_meanings` docs written for primary kalashes that have maroon-color word meanings.
- [ ] Running the script twice → identical Postgres row count, Mongo document count, and Neo4j node count.
- [ ] `gatha_teeka_bhaavarth_hindi` text is valid Markdown (no raw HTML except inline `<span style=...>` color tags).
- [ ] Script runs correctly with a different shastra config (e.g. a single-teeka shastra) without code changes.
- [ ] All natural key label segments use Hindi: `कलश`, `टीका`, `भावार्थ`, `अध्याय`.

---

## 8. Implementation Notes

### 8.1 What was implemented (2026-05-25)

#### 8.1.1 Hindi label segments in natural keys

All English label segments in natural keys were replaced with Hindi equivalents to match JainKosh style (which uses `गाथा`, `टीका` in compound keys like `समयसार:आत्मख्याति:गाथा:टीका:8`):

| Old (English) | New (Hindi) |
|---|---|
| `:kalash:` | `:कलश:` |
| `:teeka:` (label in key) | `:टीका:` |
| `:bhaavarth:` | `:भावार्थ:` |
| `:chapter:` | `:अध्याय:` |

These constants are defined in `envelope.py` as `_KALASH`, `_TEEKA`, `_BHAAVARTH`, `_ADHYAAY` for consistency.

#### 8.1.2 TeekaChapter SQLAlchemy model

Created `packages/jain_kb_common/jain_kb_common/db/postgres/teeka_chapters.py` — the `TeekaChapter` ORM model corresponding to the migration `0019_teeka_chapters.py`. Added `upsert_teeka_chapter` to `packages/jain_kb_common/jain_kb_common/db/postgres/upserts.py`.

#### 8.1.3 `upsert_kalash` updated

Added `gatha_id: uuid.UUID | None = None` to `upsert_kalash` so the FK to the parent gatha is persisted on every write.

#### 8.1.4 `workers/ingestion/nj/apply.py`

Core apply function `apply_nj_shastra_payload(*, envelope, pg_session, mongo_db, neo4j_driver, ...)`:

- NFC-normalizes all strings on entry
- Upserts Postgres entities in FK dependency order:
  1. `authors` → `shastras` → `teekas` → `publications`
  2. `gathas` — builds `gatha_nk → uuid` cache
  3. `kalashas` — resolves `teeka_id` and `gatha_id` from caches
  4. `teeka_chapters` — resolves `teeka_id`, `start_gatha_id`, `end_gatha_id`
- Upserts all Mongo collections in order (gatha content, then kalash content)
- Commits Postgres, then syncs Neo4j nodes (Shastra, Teekas, Publications, Gathas, Topic stubs) and edges (MENTIONS_TOPIC)
- Safe to call twice (idempotent throughout via ON CONFLICT / MERGE)

#### 8.1.5 `scripts/ingest_nj_apply.py`

CLI apply script:
```bash
python scripts/ingest_nj_apply.py \
  --config parser_configs/nj/samaysaar.yaml \
  [--dry-run] \
  [--gatha 001] \
  [--neo4j-database jainkb] \
  [--ingestion-run-id <uuid>]
```

Reads `DATABASE_URL`, `MONGO_URL`, `MONGO_DB_NAME`, `NEO4J_URL`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NIKKYJAIN_LOCAL_PATH` from environment.

#### 8.1.6 Tests

Added `tests/workers/nj/test_apply_unit.py` with 16 tests covering:

- NFC normalization of envelope strings
- Envelope structure completeness (all required collections present)
- Postgres row field requirements (gatha_natural_key on kalashes, start/end on chapters)
- Idempotency of `build_envelope`
- `stable_id` determinism
- Multi-gatha merge: combined pages produce correct `is_related` and separate docs
- **Cross-source merge (JK × NJ)**:
  - NJ shastra natural key matches JK's `shastra_natural_key` refs
  - JK GathaTeeka `gatha_number` + `shastra_natural_key` → derived Gatha NK matches NJ's output
  - Both NJ-first and JK-first orderings produce the same Gatha NK (idempotent merge)
  - Shastra node key is consistent in both Neo4j output streams
- Hindi label consistency (कलश in postgres and mongo kalash NKs must match)
- Teeka chapter NK is scoped under primary teeka NK with Hindi अध्याय label

All 72 NJ tests pass.

### 8.2 Pass-5: Gatha NK label, publisher ID, and full Neo4j graph (2026-05-25)

#### 8.2.1 Gatha natural key now includes `गाथा` label
`_gatha_nk(shastra_nk, gatha_number)` now returns `{shastra_nk}:गाथा:{norm_num}` (was `{shastra_nk}:{norm_num}`).

Impact: all places that use gatha NK are affected — postgres `gathas.natural_key`, all mongo `gatha_*` natural keys, neo4j Gatha node keys, kalash/chapter FK references.

Teeka-level keys (e.g. `teeka_gatha_mapping`, `gatha_teeka_sanskrit`, `gatha_teeka_bhaavarth_hindi`) are composed from `{teeka_nk}:{gatha_number}` directly and do NOT include the `गाथा` label.

#### 8.2.2 Publisher ID changed from `nikkyjain` to `0`
- `publishers.json`: nikkyjain entry updated to `"publisher_id": "0"`.
- `samaysaar.yaml`: both teekas updated to `publisher_id: "0"` and `publication_natural_key: समयसार:आत्मख्याति:0` / `समयसार:तात्पर्यवृत्ति:0`.
- All publication natural keys in envelope output use `0` instead of the ASCII string `nikkyjain`.

#### 8.2.3 Full Neo4j graph in `_build_neo4j`
Added new node types and edges to `_build_neo4j`:

**New node labels**: `Teeka`, `Publication`, `GathaTeeka`, `GathaTeekaBhaavarth`, `Kalash`, `KalashBhaavarth`.
**New edge types**: `HAS_TEEKA`, `HAS_PUBLICATION`, `HAS_GATHA_TEEKA`, `HAS_KALASH`, `HAS_BHAAVARTH`.

Key patterns: see §4.1 above.

Nodes are emitted for both primary and secondary teekas where applicable.
`GathaTeekaBhaavarth` only emitted when `gatha_teeka_bhaavarth_md` is non-empty.

#### 8.2.4 New idempotency contracts
Added `neo4j:Teeka`, `neo4j:Publication`, `neo4j:GathaTeeka`, `neo4j:GathaTeekaBhaavarth`, `neo4j:Kalash`, `neo4j:KalashBhaavarth` to `_NJ_CONTRACTS`.

#### 8.2.5 Tests updated
- All `आत्मख्याती` (long ī) → `आत्मख्याति` (short i) in test assertions (aligns with samaysaar.yaml).
- All gatha NK assertions updated to include `गाथा` label.
- `test_neo4j_no_edge_for_gatha_without_heading` → `test_neo4j_no_mentions_topic_edge_for_gatha_without_heading` (asserts only that no MENTIONS_TOPIC edges exist; structural edges like HAS_TEEKA are always present).
- `test_idempotency_contracts_are_detailed` updated to include new neo4j contract keys.
- All 72 NJ tests pass.

### 8.3 Known open items

- **Cross-source Gatha NK (NJ × JK)**: NJ now uses `समयसार:गाथा:8` while JK lazy GathaTeeka stubs may still derive `समयसार:8`. The JK parser must also adopt the `गाथा` label for cross-source Gatha node MERGE to work correctly.
- **Golden files**: Regenerate with `python -m workers.ingestion.nj.cli parse --config parser_configs/nj/samaysaar.yaml --format golden` (requires `NIKKYJAIN_LOCAL_PATH` env var).
- **Integration tests**: `test_apply_unit.py` is unit-based. DB integration tests deferred; add under `--run-db-tests` flag when CI DB environment is available.
