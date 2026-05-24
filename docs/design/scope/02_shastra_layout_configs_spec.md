# 02 — Shastra Layout Configs Spec

Scope context: [`scope/03_shastra_reader.md`](../../scope/03_shastra_reader.md), open question Q4 in [`scope/09_open_questions.md`](../../scope/09_open_questions.md).

Per-shastra layout YAML declares the native structural hierarchy (adhikaar → gatha, parva → sarga → shloka, etc.) and the panel order/visibility for the Shastra Reader. New shastras only require a new YAML — no code change. A small Postgres registry (`shastra_layouts`) names the *active* version so the API can serve it deterministically.

Storage: small YAML files under `parser_configs/shastra_layouts/<family>/<natural_key>.yaml`, version-controlled like [`parser_configs/jainkosh.yaml`](../../../parser_configs/jainkosh.yaml). The registry table parallels `parser_configs` from [`02_data_model_postgres.md`](../data_model/02_data_model_postgres.md).

## Phase A — schema, Pydantic model, loader

### Files

```
packages/jain_kb_common/shastra_layouts/
├── __init__.py
├── schema.py             # Pydantic v2 ShastraLayoutConfig + nested models
├── loader.py             # load_from_path(), load_active(shastra_nk, session)
├── registry.py           # register_config(), set_active(), get_active()
├── validator.py          # validate_dict() -> list[ValidationError]; cross-ref to parser_configs/_schemas/
└── tests/
    ├── conftest.py
    ├── test_schema_validation.py
    ├── test_loader_roundtrip.py
    ├── test_registry_active_version.py
    └── test_natural_keys_match_units.py

parser_configs/_schemas/
└── shastra_layout.schema.json    # JSON schema mirror of Pydantic model, used by admin UI

parser_configs/shastra_layouts/
├── dravyanuyoga/
│   ├── samaysaar.yaml
│   ├── pravachansaar.yaml
│   ├── niyamsaar.yaml
│   └── tatvarth-sutra.yaml
├── karananuyoga/
│   └── gommatsaar.yaml
└── prathmanuyoga/
    └── padma-puraan.yaml
```

Files under `parser_configs/shastra_layouts/` are seeded by Phase C; Phases A and B do not touch them beyond one fixture.

### Postgres schema (migration `0020_shastra_layouts.py`)

```sql
CREATE TABLE shastra_layouts (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  shastra_id      UUID NOT NULL REFERENCES shastras(id) ON DELETE CASCADE,
  config_path     TEXT NOT NULL,                 -- relative to repo root, e.g. parser_configs/shastra_layouts/dravyanuyoga/samaysaar.yaml
  version         TEXT NOT NULL,                 -- semver authored in the YAML
  checksum        TEXT NOT NULL,                 -- sha256 of file content at registration time
  active          BOOLEAN NOT NULL DEFAULT false,
  authored_by     TEXT,                          -- admin user id or 'seed'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (shastra_id, version)
);

CREATE UNIQUE INDEX idx_shastra_layouts_one_active
  ON shastra_layouts(shastra_id) WHERE active = true;

CREATE INDEX idx_shastra_layouts_shastra ON shastra_layouts(shastra_id);
```

Exactly one row per `shastra_id` may have `active = true` (partial unique index enforces this).

### YAML schema (authoritative — Pydantic mirror in `schema.py`)

```yaml
# parser_configs/shastra_layouts/dravyanuyoga/samaysaar.yaml
version: "1.0.0"
shastra_natural_key: "samaysaar"
family: "dravyanuyoga"           # one of: dravyanuyoga | karananuyoga | charananuyoga | prathmanuyoga

# Native structural hierarchy, outermost first.
native_structure:
  - kind: "adhikaar"             # arbitrary slug
    label:
      hi: "अधिकार"
      en: "Adhikaar"
    natural_key_template: "{shastra}:adhikaar:{adhikaar_idx}"
  - kind: "gatha"
    label:
      hi: "गाथा"
      en: "Gatha"
    natural_key_template: "{shastra}:{gatha_number}"
    is_leaf: true                # leaf level = the unit URL navigates to

# Panel order rendered top-to-bottom. Unknown kinds are skipped.
panels:
  - { kind: "prakrit",            visible_default: true,  collapsible: false }
  - { kind: "sanskrit_chhaaya",   visible_default: true,  collapsible: false }
  - { kind: "hindi_chhand",       visible_default: true,  collapsible: false }
  - { kind: "anvayartha",         visible_default: true,  collapsible: true  }
  - { kind: "bhaavarth",          visible_default: true,  collapsible: true  }
  - { kind: "drushtaant",         visible_default: false, collapsible: true  }
  - { kind: "related_topics",     visible_default: false, collapsible: true  }
  - { kind: "audio",              visible_default: true,  collapsible: false }
  - { kind: "references",         visible_default: false, collapsible: true  }

# Navigation (prev/next) semantics for the unit.
navigation:
  prev_next_scope: "shastra"     # one of: shastra | adhikaar | parva | sarga
  loop: false                    # if true, wrap-around at boundaries

# Audio.
audio_voice_id: "elevenlabs:rachel-hi-v1"   # see spec 06
audio_enabled: true

# Drushtaant.
drushtaant_enabled: true

# JainKosh highlight overlay default for this shastra.
jainkosh_highlights_default: true

# Optional: per-teeka rendering order. Empty → all teekas alphabetical.
teeka_order: ["amritchandra", "jaysenacharya"]
```

Allowed `panels[].kind` values (enum, exhaustive):
`prakrit`, `sanskrit_chhaaya`, `hindi_chhand`, `anvayartha`, `bhaavarth`, `drushtaant`, `related_topics`, `audio`, `references`, `word_meanings`, `notes`.

### Pydantic contracts (excerpt)

```python
# packages/jain_kb_common/shastra_layouts/schema.py
from pydantic import BaseModel, Field, constr
from typing import Literal

PanelKind = Literal[
    "prakrit","sanskrit_chhaaya","hindi_chhand","anvayartha","bhaavarth",
    "drushtaant","related_topics","audio","references","word_meanings","notes",
]
Family = Literal["dravyanuyoga","karananuyoga","charananuyoga","prathmanuyoga"]

class MultilingualLabel(BaseModel):
    hi: constr(min_length=1)
    en: str | None = None

class UnitLevel(BaseModel):
    kind: constr(pattern=r"^[a-z_][a-z0-9_]*$")
    label: MultilingualLabel
    natural_key_template: constr(min_length=1)
    is_leaf: bool = False

class PanelEntry(BaseModel):
    kind: PanelKind
    visible_default: bool = True
    collapsible: bool = True

class NavigationConfig(BaseModel):
    prev_next_scope: Literal["shastra","adhikaar","parva","sarga","chapter","adhyaay"] = "shastra"
    loop: bool = False

class ShastraLayoutConfig(BaseModel):
    version: constr(pattern=r"^\d+\.\d+\.\d+$")
    shastra_natural_key: constr(min_length=1)
    family: Family
    native_structure: list[UnitLevel] = Field(min_length=1)
    panels: list[PanelEntry] = Field(min_length=1)
    navigation: NavigationConfig = NavigationConfig()
    audio_voice_id: str | None = None
    audio_enabled: bool = True
    drushtaant_enabled: bool = True
    jainkosh_highlights_default: bool = True
    teeka_order: list[str] = []
```

### Loader contract

```python
# packages/jain_kb_common/shastra_layouts/loader.py
async def load_active(session, shastra_natural_key: str) -> ShastraLayoutConfig:
    """Return the active config for a shastra. Raises NoActiveLayoutError if none."""

async def load_from_path(path: pathlib.Path) -> ShastraLayoutConfig:
    """Parse + validate one YAML file. Raises pydantic ValidationError on bad schema."""
```

`load_active` first looks up `shastra_layouts` (active=true), then reads the file at `config_path`, verifies sha256 matches `checksum` (warn + fall through on mismatch in dev; hard-fail in prod via `SAAR_STRICT_LAYOUT_CHECKSUM=1`), and returns the parsed model.

### Registry contract

```python
# packages/jain_kb_common/shastra_layouts/registry.py
async def register_config(session, *, shastra_id: UUID, path: pathlib.Path,
                          authored_by: str) -> ShastraLayout:
    """Parse + validate file, compute checksum, insert row (active=false)."""

async def set_active(session, *, shastra_id: UUID, version: str) -> None:
    """Atomically flip active for one version, deactivating others within the same shastra."""
```

`set_active` uses a single SQL statement that demotes existing active rows and promotes the target in one transaction.

### Tests (TDD — write these first)

1. `test_schema_validation.py::test_minimal_config_accepted` — minimal YAML with one unit + one panel parses.
2. `test_schema_validation.py::test_unknown_panel_kind_rejected` — `panels[0].kind = "bogus"` → ValidationError.
3. `test_schema_validation.py::test_version_must_be_semver` — `"1.0"` rejected.
4. `test_schema_validation.py::test_natural_key_template_required_per_level` — empty template rejected.
5. `test_loader_roundtrip.py::test_load_active_reads_file_at_path` — seed a row, write file, `load_active` returns parsed model.
6. `test_loader_roundtrip.py::test_checksum_mismatch_strict_raises` — mutate file after registration, `SAAR_STRICT_LAYOUT_CHECKSUM=1` → raises.
7. `test_registry_active_version.py::test_only_one_active_per_shastra` — `set_active(v2)` demotes `v1`.
8. `test_registry_active_version.py::test_register_then_set_active_atomic` — concurrent flips end with exactly one active.
9. `test_natural_keys_match_units.py::test_template_placeholders_in_known_set` — only `{shastra}`, `{adhikaar_idx}`, `{gatha_number}`, `{parva_idx}`, `{sarga_idx}`, `{shloka_number}`, `{adhyaay_idx}`, `{sutra_number}`, `{chapter_idx}` permitted.

## Phase B — admin UI editor

### Files

```
ui/app/admin/shastra-layouts/
├── page.tsx                          # list of shastras + active version + edit button
├── [nk]/page.tsx                     # YAML editor + live preview (Server Component shell)
├── [nk]/EditorClient.tsx             # Monaco editor + JSON-schema validation + preview pane
└── [nk]/PreviewClient.tsx            # renders skeleton panel stack from current YAML

ui/lib/api/shastra_layouts.ts         # GET /v1/shastras/{nk}/layout, POST /admin/shastra-layouts/...
```

### Editor behaviour

- Monaco loaded with `parser_configs/_schemas/shastra_layout.schema.json` for inline validation.
- `Save draft` → `POST /admin/shastra-layouts/{shastra_nk}/draft` with `{yaml_text}`. Backend writes a `_draft_<timestamp>.yaml` file, validates server-side, returns errors.
- `Publish` → bumps version, registers, calls `set_active`. Old file kept on disk; new active row in DB.
- Preview pane renders panel placeholders top-to-bottom honouring `visible_default` and `collapsible`. Uses the same `<PanelStack>` component as the reader (spec 03), passing dummy props.

### API endpoints (on data-service)

```
GET    /v1/shastras/{nk}/layout                  # public
POST   /admin/shastra-layouts/{nk}/validate      # body: {yaml_text} -> {errors:[...]}
POST   /admin/shastra-layouts/{nk}/draft         # body: {yaml_text} -> {path, version}
POST   /admin/shastra-layouts/{nk}/publish       # body: {version} -> {ok}
GET    /admin/shastra-layouts/{nk}/history       # list of past versions for a shastra
```

`/admin/*` requires `require_role("admin","reviewer")` from [`spec 01`](./01_user_accounts_spec.md). `/v1/shastras/{nk}/layout` is public (guest allowed).

### Tests (Phase B)

1. `test_admin_validate_endpoint.py::test_bad_yaml_returns_errors` — malformed YAML → 200 with errors list.
2. `test_admin_publish_atomic.py::test_publish_flips_active_and_caches` — publish v2 while v1 active → only v2 active.
3. `ui` Playwright: open `/admin/shastra-layouts/samaysaar`, mutate panel order, click Save draft, expect status toast.

## Phase C — seed configs

Author and register YAML for: `samaysaar`, `pravachansaar`, `niyamsaar`, `tatvarth-sutra`, `gommatsaar`, `padma-puraan`.

### Per-shastra native structure

| natural_key | family | native_structure |
|---|---|---|
| samaysaar | dravyanuyoga | adhikaar → gatha |
| pravachansaar | dravyanuyoga | adhikaar → gatha |
| niyamsaar | dravyanuyoga | adhikaar → gatha |
| tatvarth-sutra | dravyanuyoga | adhyaay → sutra |
| gommatsaar | karananuyoga | chapter → shloka |
| padma-puraan | prathmanuyoga | parva → sarga → shloka |

All six ship `panels` in the order listed in the YAML template above. `samaysaar`, `pravachansaar`, `niyamsaar` set `teeka_order: ["amritchandra","jaysenacharya"]`. `padma-puraan` sets `audio_enabled: true, drushtaant_enabled: true`. `tatvarth-sutra` omits `hindi_chhand` from `panels` (no chhand for sutras) and uses `prev_next_scope: "adhyaay"`.

### Seed script

```
scripts/seed_shastra_layouts.py
```

Idempotent: for each YAML file under `parser_configs/shastra_layouts/`, look up shastra by `shastra_natural_key`, call `register_config` if checksum changed, call `set_active` for the highest semver. Logs every action.

### Tests (Phase C)

1. `test_seed_idempotent.py::test_running_twice_no_new_rows` — seed → assert count; seed again → identical count.
2. `test_seed_picks_highest_active.py::test_active_version_is_max_semver` — register v1.0.0 and v1.1.0, only v1.1.0 active.
3. `test_seed_per_shastra.py::test_six_shastras_have_active_config` — after seed, `GET /v1/shastras/{nk}/layout` returns 200 for each of six.

## Manual verification

```bash
# Apply migration
alembic upgrade head

# Seed configs
python scripts/seed_shastra_layouts.py

# Verify API
curl http://localhost:8002/v1/shastras/samaysaar/layout | jq '.panels | map(.kind)'
# → ["prakrit","sanskrit_chhaaya","hindi_chhand","anvayartha","bhaavarth","drushtaant","related_topics","audio","references"]

# Admin editor
open http://localhost:3000/admin/shastra-layouts/samaysaar
# Mutate panel order, Save draft, Publish; refresh public API and confirm new order.
```

## Definition of done

- [ ] Migration `0020_shastra_layouts.py` applied; partial unique index enforces single active per shastra.
- [ ] `ShastraLayoutConfig` Pydantic model + JSON schema mirror exist and cross-validate identically.
- [ ] All Phase A tests pass.
- [ ] Admin editor saves, validates, publishes a new version without server restart.
- [ ] Six seed YAMLs registered and active; `GET /v1/shastras/{nk}/layout` returns each one.
- [ ] `load_active` p95 latency under 5 ms (file is on local disk + small).

## Implementation notes

_(to be filled in after merge)_
