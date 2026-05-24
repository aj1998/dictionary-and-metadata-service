# NJ Parser Manual Testing (Batch Run)

This document covers manual verification for the nikkyjain (`nj`) parser batch mode in `dictionary-and-metadata-service`.

## Scope

- Parser: `workers/ingestion/nj/orchestrator.py`
- Shastra config: `parser_configs/nj/samaysar.yaml`
- Batch controls:
  - `batch_offset`
  - `batch_limit`

## Prerequisites

1. Local repo path:
   - `/Users/anubhavjain/Coding/Jinvani/dictionary-and-metadata-service`
2. Local nikkyjain clone path:
   - `/Users/anubhavjain/Coding/Jinvani/nikkyjain.github.io`
3. Python venv available at:
   - `.venv/`
4. Parser dependencies installed in venv:
   - `beautifulsoup4`
   - `lxml`

## Commands

### 1. Install parser deps (if needed)

```bash
cd /Users/anubhavjain/Coding/Jinvani/dictionary-and-metadata-service
.venv/bin/pip install beautifulsoup4 lxml
```

### 1.1 Run full NJ unit test suite

```bash
cd /Users/anubhavjain/Coding/Jinvani/dictionary-and-metadata-service
.venv/bin/pytest -q workers/ingestion/nj/tests
```

This runs both:
- environment-independent unit tests (synthetic fixtures)
- local-clone integration tests (auto-skipped when `NIKKYJAIN_LOCAL_PATH` is not set)

### 2. Run first 10 pages as one batch

```bash
cd /Users/anubhavjain/Coding/Jinvani/dictionary-and-metadata-service
NIKKYJAIN_LOCAL_PATH=/Users/anubhavjain/Coding/Jinvani/nikkyjain.github.io \
.venv/bin/python - <<'PY'
from workers.ingestion.nj.config import load_config_for_shastra
from workers.ingestion.nj.orchestrator import parse_shastra

cfg = load_config_for_shastra('samaysar')
res = parse_shastra(cfg, batch_offset=0, batch_limit=10)
print('processed_pages=', res.total_html_files_processed)
print('gathas=', len(res.gathas))
print('secondary_kalashes=', len(res.secondary_kalashes))
print('warnings=', len(res.warnings))
if res.gathas:
    print('first_gatha=', res.gathas[0].gatha_number, res.gathas[0].html_filename)
    print('last_gatha=', res.gathas[-1].gatha_number, res.gathas[-1].html_filename)
if res.secondary_kalashes:
    print('first_secondary=', res.secondary_kalashes[0].kalash_number, res.secondary_kalashes[0].html_filename)
PY
```

### 3. Optional: run the next batch (pages 11-20)

```bash
cd /Users/anubhavjain/Coding/Jinvani/dictionary-and-metadata-service
NIKKYJAIN_LOCAL_PATH=/Users/anubhavjain/Coding/Jinvani/nikkyjain.github.io \
.venv/bin/python - <<'PY'
from workers.ingestion.nj.config import load_config_for_shastra
from workers.ingestion.nj.orchestrator import parse_shastra

cfg = load_config_for_shastra('samaysar')
res = parse_shastra(cfg, batch_offset=10, batch_limit=10)
print('processed_pages=', res.total_html_files_processed)
print('gathas=', len(res.gathas))
print('secondary_kalashes=', len(res.secondary_kalashes))
print('warnings=', len(res.warnings))
PY
```

### 4. Generate ingestion-ready golden JSON (first 10 pages)

```bash
cd /Users/anubhavjain/Coding/Jinvani/dictionary-and-metadata-service
NIKKYJAIN_LOCAL_PATH=/Users/anubhavjain/Coding/Jinvani/nikkyjain.github.io \
.venv/bin/python -m workers.ingestion.nj.cli parse \
  --config parser_configs/nj/samaysar.yaml \
  --batch-offset 0 \
  --batch-limit 10 \
  --format golden
```

Expected output line:

```text
wrote: workers/ingestion/nj/tests/golden/samaysar_golden_o0_l10.json
```

Golden JSON absolute path (this repo):

`/Users/anubhavjain/Coding/Jinvani/dictionary-and-metadata-service/workers/ingestion/nj/tests/golden/samaysar_golden_o0_l10.json`

## Manual Verification Checklist

- [ ] Batch command completes without exception.
- [ ] `processed_pages= 10` for `batch_limit=10`.
- [ ] First batch starts at `001.html` and includes combined page handling (`009-010.html`).
- [ ] `gathas` count is reasonable for selected files (combined pages may expand per-gatha count).
- [ ] `secondary_kalashes` appears when secondary-only files are inside batch (for first batch, `011.html` expected).
- [ ] `warnings= 0` (or warnings are reviewed and understood).
- [ ] Re-running the same batch gives stable counts.
- [ ] Running `offset=10, limit=10` shifts window and processes next set of pages.
- [ ] Golden generation writes a JSON envelope with top-level keys:
  - `shastra_parse_result`
  - `would_write`
- [ ] `would_write.mongo` contains NJ ingestion collections:
  - `gatha_prakrit`, `gatha_sanskrit`, `gatha_hindi_chhand`
  - `gatha_word_meanings`, `teeka_gatha_mapping`
  - `gatha_teeka_sanskrit`, `gatha_teeka_bhaavarth_hindi`
  - `kalash_sanskrit`, `kalash_hindi`, `kalash_word_meanings`

## Expected Output Snapshot (First Batch)

Observed reference output for:
`batch_offset=0, batch_limit=10`

```text
processed_pages= 10
gathas= 10
secondary_kalashes= 1
warnings= 0
first_gatha= 001 001.html
last_gatha= 010 009-010.html
first_secondary= 011 011.html
```

## Notes

- Batch slicing applies to sorted eligible HTML pages (after `skip_files` removal).
- `preceding_primary_gatha` for secondary-only pages is resolved against the full eligible file ordering, not only the current batch window.
- Golden JSON default location:
  - `workers/ingestion/nj/tests/golden/`
