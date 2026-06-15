# Compound Identifiers for Gatha / Kalash — Overview

> **Scope**: Some shastras (starting with **परमात्मप्रकाश**) identify each gatha
> by more than one field — e.g. `अधिकार` + `गाथा`. Today the codebase assumes a
> single integer/string `gatha_number` per shastra, which makes adhikaar-1 गाथा 1
> and adhikaar-2 गाथा 1 collide. This series of specs adds first-class compound
> identifier support across **parser → envelope → ingestion → graph → API → UI**.
>
> **Source of truth**: `parser_configs/_manual_configs/shastra.json` —
> per-shastra `gatha_identifier` (comma-separated field list) and the optional
> `kalash_identifier`. If absent, behaviour is **unchanged** for that shastra.
>
> **Implementation phases**: read in order; each subsequent phase assumes the
> previous one is merged. Each phase doc is self-contained enough to be
> implemented end-to-end (parsing → tests → updating authoritative docs) in
> a single context window.

---

## Phase index

| # | Spec | Scope |
|---|---|---|
| 1 ✓ | [`01_shastra_json_and_config_loader.md`](./01_shastra_json_and_config_loader.md) | Update `shastra.json` for परमात्मप्रकाश; add `gatha_identifier` / `kalash_identifier` reader util in `jain_kb_common`. |
| 2 | [`02_nj_parser_compound_id_support.md`](./02_nj_parser_compound_id_support.md) | Fix NJ `parse_myitem.py` (no-`<optgroup>` form), expand multi-gatha range, emit compound `gatha_identifier_values` per Gatha/Kalash extract. |
| 3 | [`03_envelope_and_apply_compound_nk.md`](./03_envelope_and_apply_compound_nk.md) | Compound NK builder; Postgres `gathas.gatha_number` stores full NK suffix; Neo4j Gatha/Kalash/GathaTeeka/GathaTeekaBhaavarth/KalashBhaavarth NKs all use compound suffix. |
| 4 | [`04_jainkosh_reference_compound_nk.md`](./04_jainkosh_reference_compound_nk.md) | Reference parser pulls `gatha_identifier` from shastra.json at resolve time and assembles the compound NK so jainkosh-side citations land on the same node as the NJ-emitted one. |
| 5 | [`05_api_and_ui_compound_routes.md`](./05_api_and_ui_compound_routes.md) | API: accept compound `gatha_id` path segment. UI: `/shastras/{nk}/gathas/{compound}` route + breadcrumb. |

---

## Canonical examples

### Identifier declaration (shastra.json — single source of truth)
```json
{
  "shastra_name": "परमात्मप्रकाश",
  "gatha_identifier": "अधिकार,परमात्मप्रकाशगाथा",
  "kalash_identifier": null
}
```
The field name `परमात्मप्रकाशगाथा` keeps the legacy `format` semantics
(jainkosh reference grammar). At NK-emit time the implementation strips the
exact shastra-name prefix → `गाथा`.

### Natural-key shape

| Node | NK (single-field, today) | NK (compound, new) |
|---|---|---|
| `Gatha` | `समयसार:गाथा:8` | `परमात्मप्रकाश:अधिकार:1:गाथा:2` |
| `GathaTeeka` | `समयसार:आत्मख्याति:गाथा:टीका:8` | `परमात्मप्रकाश:टीका:अधिकार:1:गाथा:टीका:2` |
| `GathaTeekaBhaavarth` | `समयसार:आत्मख्याति:राजचंद्र:गाथा:टीका:भावार्थ:8` | `परमात्मप्रकाश:टीका:0:अधिकार:1:गाथा:टीका:भावार्थ:2` |
| `Kalash` | `समयसार:आत्मख्याति:कलश:8` | (same shape; uses `kalash_identifier` if set) |

**Field segments appear in the order declared in `gatha_identifier`** —
canonical noun (after stripping shastra prefix) is the last segment of each
field-value pair.

### Multi-gatha pages
`1-019-021.html` (adhikaar 1, gathas 19–21) → **three separate Gatha nodes**:
- `परमात्मप्रकाश:अधिकार:1:गाथा:19`
- `परमात्मप्रकाश:अधिकार:1:गाथा:20`
- `परमात्मप्रकाश:अधिकार:1:गाथा:21`

Each carries `related_gatha_natural_keys` listing the others, mirroring
the current `is_combined_page` behaviour for समयसार.

---

## Doc-update obligation (applies to every phase)

When implementing a phase, the implementing agent **MUST** also update the
corresponding authoritative docs once the change is in:

| Phase | Doc(s) to update with Implementation Notes |
|---|---|
| 1 | this overview (mark phase 1 ✓), `docs/design/data_model/data_model_postgres.md` (note `gathas.gatha_number` semantics for compound shastras) |
| 2 | `docs/design/data_sources/nikkyjain/nj_parser.md` (Known edge cases section + new "Compound identifier" section) |
| 3 | `docs/design/data_model/data_model_graph.md` (Natural-key format conventions table), `docs/design/data_sources/nikkyjain/nj_ingestion.md` |
| 4 | `docs/design/data_sources/jainkosh/parser.md` (§ Reference Parser), `docs/design/data_sources/jainkosh/ingestion.md` |
| 5 | `docs/design/api/data/01_spec.md`, `docs/design/api/navigation/01_spec.md`, `ui/README.md` |

This instruction is intentionally repeated in each phase spec.

---

## Hard decisions (locked)

1. **`gatha_identifier` / `kalash_identifier` live ONLY in `shastra.json`.** NJ
   yaml may carry adhikaar **names** (display strings) but never the identifier
   structure.
2. **NK uses field-labelled segments**, with the exact `{shastra_name}` prefix
   stripped from the field name (e.g. `परमात्मप्रकाशगाथा` → `गाथा`).
3. **Multi-gatha pages emit one Gatha node per gatha** (range-expand).
4. **No new `Adhikaar` node label** — `अधिकार` appears only inside identifiers
   and as `Gatha.adhikaar_number` / `Gatha.adhikaar_hi` properties.
5. **Backwards-compatibility**: shastras without `gatha_identifier` keep their
   current NK shape (`{shastra}:गाथा:{n}`). Zero migration for those.
6. Build `kalash_identifier` plumbing now even though no shastra currently
   declares one — future-proofing, no extra runtime cost.

---

## Non-goals

- No URL/route changes for shastras without `gatha_identifier`.
- No Postgres schema change beyond making `gatha_number TEXT` hold the
  full compound NK suffix (e.g. `अधिकार:1:गाथा:2`). The existing
  `adhikaar JSONB` column on `gathas` is reused for the structured form.
- No `Adhikaar` graph node, no `HAS_ADHIKAAR` edge, no admin tooling for
  adhikaar editing.
