# 28 — Research Tools Framework Spec

Scope context: [`scope/07_siri_bhoovalay_and_research_models.md`](../../scope/07_siri_bhoovalay_and_research_models.md) (Research Tools framework section), [`scope/11_suggested_research_tools.md`](../../scope/11_suggested_research_tools.md) item 26 (plugin contract), [`scope/01_pages_and_features.md`](../../scope/01_pages_and_features.md) (`#ResearchTools` shell). Depends on spec [`23_model_serving_registry_spec`](./23_model_serving_registry_spec.md) (model_registry FK target) and spec [`01_user_accounts_spec`](./01_user_accounts_spec.md) (auth for scratchpad CRUD).

A research tool is **one YAML config + one Postgres row + a small set of React pane components**. The framework owns: the plugin interface, the registry table, the catalog API, the runtime shell `ui/app/research-tools/[id]/page.tsx`, and the per-user scratchpad CRUD. Individual tools (siri-bhoovalay, jain-maths, ...) plug in via the YAML registry — they do not modify the framework.

Single phase.

## Files

```
packages/jain_kb_common/research_tools/
├── __init__.py
├── plugin.py             ResearchToolPlugin Protocol, PaneSpec dataclass
├── registry.py           load_registry_from_yaml(), seed_into_postgres()
└── panes.py              PaneKind enum + JSON-schema contract

parser_configs/research_tools/
├── _schema.yaml          JSON-schema for any <id>.yaml
├── siri-bhoovalay.yaml   (concrete tool — body owned by spec 29)
└── README.md             how to add a new tool

services/research_tools_service/
├── __init__.py
├── main.py               FastAPI app, /healthz (port 8010)
├── config.py             Settings (DATABASE_URL, MONGO_URL, PORT=8010)
├── deps.py               AsyncSession, Motor, current_user_optional/required
├── routers/
│   ├── catalog.py        GET /v1/research-tools, GET /v1/research-tools/{id}
│   └── scratchpad.py     GET/PUT/DELETE /v1/me/research-tools/{id}/scratchpad
└── tests/
    ├── conftest.py
    ├── test_registry_load.py
    ├── test_catalog_api.py
    ├── test_scratchpad_round_trip.py
    └── test_pane_schema_validation.py

ui/app/research-tools/
├── page.tsx                       catalog grid
├── [id]/page.tsx                  shell that renders panes from spec
└── _panes/
    ├── registry.ts                pane kind → React component
    ├── ChatPane.tsx
    ├── ScratchpadPane.tsx
    ├── CitationListPane.tsx
    ├── CalculatorPane.tsx
    ├── TableViewerPane.tsx
    ├── ThreeDViewerPane.tsx
    └── ComparisonGridPane.tsx

ui/lib/api/research_tools.ts       client SDK
```

## Plugin contract

```python
# packages/jain_kb_common/research_tools/plugin.py
from typing import Protocol, Literal, TypedDict

Lang = Literal['hi','en','kn','gu','sa','pr','ta']

class PaneSpec(TypedDict, total=False):
    kind: Literal[
      'chat', 'scratchpad', 'citation-list', 'calculator',
      'table-viewer', '3d-viewer', 'comparison-grid'
    ]
    id: str                             # unique within tool, used as DOM id
    title: dict[Lang, str]              # at minimum {'hi': ..., 'en': ...}
    config: dict                        # pane-kind-specific; validated by PaneKind schema
    layout: dict                        # {col: 1|2, row: int, span: int} grid hints

class ResearchToolPlugin(Protocol):
    id: str                             # e.g. 'maths', 'jain-physics', 'siri-bhoovalay'
    title: dict[Lang, str]
    icon: str                           # lucide-react icon name (e.g. 'calculator')
    default_model_id: str               # FK into model_registry.id
    panes: list[PaneSpec]
    scratchpad_schema: dict             # JSON schema (draft 2020-12)
```

`ResearchToolPlugin` is a Protocol, not a base class — implementations are *data* (YAML), not code. The Protocol is the type contract that loaders and seeding must satisfy.

### Pane kind contract

```python
# packages/jain_kb_common/research_tools/panes.py
PANE_CONFIG_SCHEMAS: dict[str, dict] = {
  'chat': {
    'type': 'object',
    'required': ['model_id'],
    'properties': {
      'model_id': {'type': 'string'},        # may override tool.default_model_id
      'system_prompt': {'type': 'string'},
      'show_citations': {'type': 'boolean', 'default': True},
      'show_model_picker': {'type': 'boolean', 'default': True}
    }
  },
  'scratchpad': {
    'type': 'object',
    'properties': {
      'autosave_ms': {'type': 'integer', 'default': 1500},
      'placeholder': {'type': 'string'}
    }
  },
  'citation-list': {
    'type': 'object',
    'properties': {
      'source': {'enum': ['chat', 'manual']},
      'group_by': {'enum': ['shastra', 'topic', 'none']}
    }
  },
  'calculator': {
    'type': 'object',
    'properties': {
      'engine': {'enum': ['basic', 'sympy']},
      'unit_conversions': {                 # for trilok / yojan conversions
        'type': 'array',
        'items': {'type': 'object',
                  'required': ['from','to','factor'],
                  'properties': {'from':{'type':'string'},
                                 'to':{'type':'string'},
                                 'factor':{'type':'number'}}}
      }
    }
  },
  'table-viewer': {
    'type': 'object', 'required': ['columns'],
    'properties': {
      'columns': {'type': 'array',
                  'items': {'type': 'object',
                            'required': ['key','header'],
                            'properties': {'key':{'type':'string'},
                                           'header':{'type':'object'},
                                           'sortable':{'type':'boolean'}}}}
    }
  },
  '3d-viewer': {
    'type': 'object', 'required': ['model_url'],
    'properties': {
      'model_url': {'type': 'string'},      # gltf / glb url under /static/3d/
      'click_targets': {'type': 'array',
                        'items': {'type': 'object',
                                  'properties': {'mesh': {'type': 'string'},
                                                 'topic_natural_key': {'type': 'string'}}}}
    }
  },
  'comparison-grid': {
    'type': 'object', 'required': ['axes'],
    'properties': {
      'axes': {'type': 'object',
               'required': ['rows','columns'],
               'properties': {
                 'rows':    {'type': 'array', 'items': {'type': 'string'}},
                 'columns': {'type': 'array', 'items': {'type': 'string'}}}}
    }
  }
}
```

### Adding a new pane kind

1. Add the enum value to `PaneSpec.kind` literal in `plugin.py`.
2. Add a JSON-schema entry in `PANE_CONFIG_SCHEMAS`.
3. Add a React component in `ui/app/research-tools/_panes/` and register it in `_panes/registry.ts`.
4. Add a backing test in `test_pane_schema_validation.py` covering a happy + a failing config.

No DB migration is needed to add a pane kind — the registry stores panes as `JSONB` and the framework validates against `PANE_CONFIG_SCHEMAS` at load time.

## Postgres schema (migration `0051_research_tools.py`)

```sql
CREATE TYPE research_tool_status AS ENUM ('staging','active','retired');

CREATE TABLE research_tools (
  id                TEXT PRIMARY KEY,                       -- e.g. 'jain-maths'
  title             JSONB NOT NULL,                         -- {hi, en, ...}
  icon              TEXT NOT NULL,
  default_model_id  TEXT NOT NULL REFERENCES model_registry(id) ON DELETE RESTRICT,
  panes             JSONB NOT NULL,                         -- list[PaneSpec]
  scratchpad_schema JSONB NOT NULL,                         -- JSON schema
  status            research_tool_status NOT NULL DEFAULT 'staging',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_research_tools_status ON research_tools(status);
```

Seeding: migration scans `parser_configs/research_tools/*.yaml` and upserts one row per file. The migration is idempotent — re-running it overwrites `title`, `icon`, `default_model_id`, `panes`, `scratchpad_schema`. `status` is preserved across re-runs (admin owns promotion staging → active; see spec 29 for promotion criteria).

### YAML registry format

```yaml
# parser_configs/research_tools/<id>.yaml
id: jain-maths
title:
  hi: जैन गणित
  en: Jain Maths
icon: calculator
default_model_id: jain-maths-lora-v1            # must exist in model_registry
status: staging                                 # initial status on first insert
panes:
  - kind: chat
    id: main
    title: { hi: संवाद, en: Chat }
    config:
      model_id: jain-maths-lora-v1
      system_prompt: "You are a Jain mathematics tutor..."
      show_citations: true
    layout: { col: 1, row: 1, span: 2 }
  - kind: calculator
    id: calc
    title: { hi: कैलकुलेटर, en: Calculator }
    config:
      engine: sympy
    layout: { col: 2, row: 1, span: 1 }
  - kind: scratchpad
    id: notes
    title: { hi: नोट्स, en: Notes }
    config: { autosave_ms: 1500 }
    layout: { col: 2, row: 2, span: 1 }
scratchpad_schema:
  type: object
  properties:
    note_md: { type: string }
    pinned_results: { type: array, items: { type: object } }
```

`_schema.yaml` is a JSON-schema for any tool YAML — `load_registry_from_yaml()` rejects files that fail it.

## Mongo schema

```python
# packages/jain_kb_common/db/mongo/scratchpads.py
COLLECTION = 'user_scratchpads'

# Document shape (one per (user_id, tool_id)):
# {
#   _id: stable_id(f"{user_id}:{tool_id}"),
#   user_id: "<uuid>",
#   tool_id: "jain-maths",
#   content: { /* matches tool.scratchpad_schema */ },
#   updated_at: ISODate(...),
#   created_at: ISODate(...)
# }
#
# Indexes:
#   { user_id: 1, tool_id: 1 } UNIQUE
```

`content` is validated server-side against the tool's `scratchpad_schema` (Draft 2020-12) on every PUT.

## API contracts

```
GET /v1/research-tools
  query: ?status=active|staging|all  (default: active)
  returns: [ { id, title, icon, status } ]            // catalog tiles

GET /v1/research-tools/{id}
  returns: full row + resolved panes + scratchpad_schema

GET /v1/me/research-tools/{id}/scratchpad     (auth required)
  returns: { content, updated_at }            // 404 if never saved

PUT /v1/me/research-tools/{id}/scratchpad     (auth required)
  body:    { content: <validated against tool.scratchpad_schema> }
  returns: { content, updated_at }
  errors:  422 on schema validation failure

DELETE /v1/me/research-tools/{id}/scratchpad  (auth required)
  returns: 204
```

Pydantic models:

```python
class ToolListItem(BaseModel):
    id: str
    title: dict[str, str]
    icon: str
    status: Literal['staging','active','retired']

class ToolDetail(ToolListItem):
    default_model_id: str
    panes: list[dict]                # PaneSpec list, validated against PANE_CONFIG_SCHEMAS
    scratchpad_schema: dict
    created_at: datetime
    updated_at: datetime

class ScratchpadIn(BaseModel):
    content: dict

class ScratchpadOut(BaseModel):
    content: dict
    updated_at: datetime
```

## UI shell

### Catalog (`ui/app/research-tools/page.tsx`)

Server component. Fetches `GET /v1/research-tools?status=active`, renders a grid of tiles (icon + title + "open"). Reuses the home-page card primitive from `14_public_ui.md`.

### Tool runtime (`ui/app/research-tools/[id]/page.tsx`)

Server component fetches `GET /v1/research-tools/{id}`; renders panes by mapping each `PaneSpec` through `_panes/registry.ts`:

```ts
// ui/app/research-tools/_panes/registry.ts
import { ChatPane } from './ChatPane';
import { ScratchpadPane } from './ScratchpadPane';
// ...

export const PANE_REGISTRY: Record<string, React.ComponentType<{spec: PaneSpec}>> = {
  'chat':            ChatPane,
  'scratchpad':      ScratchpadPane,
  'citation-list':   CitationListPane,
  'calculator':      CalculatorPane,
  'table-viewer':    TableViewerPane,
  '3d-viewer':       ThreeDViewerPane,
  'comparison-grid': ComparisonGridPane,
};
```

Layout: a 2-column CSS grid using `pane.layout.{col,row,span}`. Empty cells collapse. The shell does not own any pane state — each pane manages its own data via the client SDK (`ui/lib/api/research_tools.ts`).

**Per-pane responsibilities:**

- `ChatPane` — uses model-serving via the existing `cataloguesearch-chat` route, sends `system_prompt`, shows citation tiles when `show_citations`. Picks model from `config.model_id` (falls back to tool's `default_model_id`); if `show_model_picker`, surfaces the dropdown.
- `ScratchpadPane` — debounced autosave to `PUT /v1/me/.../scratchpad`. Renders Monaco editor for free-form `note_md` if schema includes that property; otherwise renders a JSON-schema-driven form (e.g. via `@rjsf/core`).
- `CitationListPane` — listens for a window event `'rt:citation:add'` from `ChatPane`; deduplicates by `gatha_natural_key`.
- `CalculatorPane` — `engine: 'sympy'` calls `POST /v1/tools/calc/sympy` on the model-serving sidecar; `'basic'` is pure client-side. Renders `unit_conversions` chips.
- `TableViewerPane` — pulls data from `config.data_url` (server-side fetch with revalidate=60). Columns from `config.columns`.
- `ThreeDViewerPane` — `@react-three/fiber` loader for `config.model_url`; click on a mesh in `click_targets` deep-links to `/topics/{topic_natural_key}`.
- `ComparisonGridPane` — renders a `rows × columns` table; cell content comes from chat assistant output keyed by `(row, col)`.

The catalog tile + tool runtime never read tool YAML directly; they only consume the API.

## Special-cased tools

Spec 27 (Siri Bhoovalay) is **not** routed through `[id]/page.tsx` — it has its own dedicated route under `ui/app/research-tools/siri-bhoovalay/` because its chakra viewer is too tool-specific to fit the generic pane grid. It still appears in the catalog (its `research_tools` row exists), but clicking its tile routes to `/research-tools/siri-bhoovalay` directly. This is the *only* exception — every other tool listed in spec 29 uses the generic shell.

## Tests (TDD — write these first)

1. `test_registry_load.py::test_loads_valid_yaml` — `parser_configs/research_tools/siri-bhoovalay.yaml` parses into a `ResearchToolPlugin`-shaped dict.
2. `test_registry_load.py::test_rejects_missing_default_model_id`.
3. `test_registry_load.py::test_rejects_unknown_pane_kind`.
4. `test_pane_schema_validation.py::test_each_pane_kind_has_schema` — every value in `PaneSpec.kind` Literal has an entry in `PANE_CONFIG_SCHEMAS`.
5. `test_pane_schema_validation.py::test_chat_pane_requires_model_id`.
6. `test_pane_schema_validation.py::test_3d_viewer_requires_model_url`.
7. `test_catalog_api.py::test_list_active_only_by_default` — staging tool hidden unless `?status=all`.
8. `test_catalog_api.py::test_get_returns_panes_and_schema`.
9. `test_catalog_api.py::test_get_unknown_id_404`.
10. `test_scratchpad_round_trip.py::test_put_then_get_returns_same_content`.
11. `test_scratchpad_round_trip.py::test_put_invalid_content_422` — content fails tool's scratchpad_schema.
12. `test_scratchpad_round_trip.py::test_get_unauth_401`.
13. `test_scratchpad_round_trip.py::test_delete_then_get_404`.
14. `test_scratchpad_round_trip.py::test_unique_per_user_per_tool` — two PUTs by same user → one row, second one overwrites.

UI (Playwright in `ui/tests/e2e/research_tools.spec.ts`):

15. Catalog renders ≥1 tile for an active tool.
16. Opening a tool with `[chat, scratchpad]` panes renders both.
17. Editing the scratchpad triggers a PUT within `autosave_ms + 500`.
18. Guest visiting a tool sees panes but the scratchpad-pane shows a "sign in to save" affordance instead of failing.

## Manual verification

```bash
# 1. Migration + seed
alembic upgrade 0051

# 2. Verify the catalog
curl http://localhost:8010/v1/research-tools | jq '.[].id'

# 3. Fetch tool detail
curl http://localhost:8010/v1/research-tools/jain-maths | jq '.panes[].kind'

# 4. Save a scratchpad (need a JWT from auth-service per spec 01)
curl -X PUT http://localhost:8010/v1/me/research-tools/jain-maths/scratchpad \
  -b cookies.txt -H 'content-type: application/json' \
  -d '{"content":{"note_md":"karm formula scratch ..."}}'

# 5. UI smoke
open http://localhost:3000/research-tools
open http://localhost:3000/research-tools/jain-maths
```

## Definition of done

- [ ] Migration `0051` creates `research_tools`, loads every YAML under `parser_configs/research_tools/`.
- [ ] All listed Python tests pass.
- [ ] All listed Playwright tests pass.
- [ ] Catalog + tool runtime render against at least one active tool.
- [ ] Adding a new tool requires only: drop a YAML file → re-run the migration → restart UI. No code change in `services/research_tools_service` or `ui/app/research-tools/[id]/page.tsx`.
- [ ] Adding a new pane *kind* is documented in `parser_configs/research_tools/README.md` and exercised by a new test.
- [ ] Scratchpad survives a logout/login cycle and is wiped on account deletion (covered by spec 01's purge task).

## Implementation notes

_(to be filled in after merge)_
