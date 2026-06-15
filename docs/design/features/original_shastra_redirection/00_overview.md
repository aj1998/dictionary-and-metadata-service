# Original Shastra Redirection — Overview

## Goal

For any definition / topic-extract reference that carries a `पृष्ठ` (page) field, render a **brown link** beside the reference that opens the locally-downloaded original shastra PDF at the exact published page. The existing blue / grey "शास्त्र में देखें" link (gatha-reader deep-link) keeps working but is repositioned next to the gatha-type text so the two affordances don't collide.

## Scope summary

- **Backend** (metadata API, `services/core_service/domains/metadata/`)
  - New config fields on each shastra entry (`parser_configs/_manual_configs/shastra.json`): `pdf_page_offset` and (multi-volume) `pustak_offsets`.
  - New env var: PDF directory root.
  - New endpoint that streams the PDF file for a `(shastra_nk, pustak?)` tuple, plus extension of the existing shastra entity-detail payload with offset fields so the UI can compute the page client-side.
- **Frontend** (`ui/`)
  - New `OriginalShastraLink` component (brown `BookOpen` icon, `text-amber-800` / `--cat-page` family) rendered inside `RefBadge` / `GroupedRefRow` / `GroupedRefList` / `RefListItem` whenever the ref's `resolved_fields` include a `पृष्ठ` value.
  - Repositioning of the existing `RefMatchLink` (blue / grey) — moved out from inside the ref-field row to a slot beside the gatha-type label so both links coexist visually.
  - Lightweight client-side hook to fetch shastra PDF metadata (offset + pustak map) once and memoize.

## Non-goals

- No in-app PDF viewer. The brown link opens the raw file in a new tab using the browser's native PDF viewer with a `#page=N` URL fragment.
- No availability gating. Brown link is always rendered when ref has `पृष्ठ`; if the file is missing, the endpoint returns 404 and the browser shows its native error.
- No automatic shastra downloads. The user manages PDFs in the configured directory.

## Decisions (locked, from clarifying round)

| Topic | Decision |
|---|---|
| Storage | Flat directory; filename = `<shastra_name>.pdf`; multi-volume = `<shastra_name>_<pustak>.pdf` |
| Page mapping | `pdf_page = published_प्रिष्ठ + offset` where offset is either a scalar or a piecewise spec `[[upToPublishedPage, offset], ...]` (per-pustak override allowed). The piecewise form handles books where insert pages (e.g. "178 अ") shift the offset partway through a volume. |
| Open behavior | New tab → raw PDF with `#page=N` URL fragment |
| When to render brown link | Always, whenever ref has `पृष्ठ` field; 404 on click if file missing |
| Offset config home | New fields on each shastra.json entry |

## Phase plan

| Phase | Doc | Implements |
|---|---|---|
| 1 | [01_phase_backend.md](./01_phase_backend.md) | Config additions, env var, file-streaming endpoint, shastra-detail payload extension, tests |
| 2 | [02_phase_frontend.md](./02_phase_frontend.md) | `OriginalShastraLink` component, ref-row repositioning, hook for PDF metadata, tests |

## Reference files

- Config: [`parser_configs/_manual_configs/shastra.json`](../../../../parser_configs/_manual_configs/shastra.json)
- Backend metadata domain: [`services/core_service/domains/metadata/`](../../../../services/core_service/domains/metadata/)
- Ref rendering: [`ui/src/components/DefinitionModal.tsx`](../../../../ui/src/components/DefinitionModal.tsx) (`RefBadge`, `GroupedRefRow`, `GroupedRefList`, `RefListItem`)
- Existing match link: [`ui/src/components/ViewInShastraButton.tsx`](../../../../ui/src/components/ViewInShastraButton.tsx) (`RefMatchLink`, `planRefLink`)
- UI README: [`ui/README.md`](../../../../ui/README.md) (sections 5, 8 — design tokens and component catalogue)
