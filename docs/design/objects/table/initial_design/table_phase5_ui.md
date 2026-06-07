# Phase 5 — Table: UI (modal viewer + graph integration)

**Owner**: frontend
**Prereqs**: [Phase 4](./table_phase4_api.md) merged and reachable on `localhost:8001`.
**Scope**: `ui/` only.

> **Read first**: `ui/AGENTS.md` — this is Next.js 16 with breaking changes from your training data. Check `node_modules/next/dist/docs/` before guessing. Tailwind 4 tokens come from `src/app/globals.css @theme inline` and `src/styles/theme.css`. No `tailwind.config.ts`.

## Goal

A Table renders in a centered modal (Base UI `Dialog`, mirroring the existing `DefinitionModal`), launched from:

1. A Table node in the graph (click → modal).
2. A "Tables" section on Topic / Keyword / Gatha detail pages.
3. The reader page (Shell C), when the gatha/page has tables attached.

## 1. Types — `ui/src/lib/types.ts`

```ts
export type EntityKind =
  | "keyword" | "topic" | "gatha" | "teeka"
  | "bhaavarth" | "kalash" | "page" | "table";

export interface TableSummary {
  naturalKey: string;
  seq: number;
  caption: LangText[];
}

export interface TableFull {
  naturalKey: string;
  pgId: string;
  source: string;
  parentNaturalKey: string;
  parentKind:
    | "topic" | "keyword" | "gatha" | "gatha_teeka"
    | "gatha_teeka_bhaavarth" | "kalash" | "kalash_bhaavarth" | "page";
  seq: number;
  caption: LangText[];
  sourceUrl: string | null;
  rawHtml: string;
  cells: string[][];
  headerRows: number;
  plaintext: string | null;
  mentionedKeywordNaturalKeys: string[];
  mentionedTopicNaturalKeys: string[];
}
```

## 2. API client — `ui/src/lib/api/data.ts`

```ts
export async function getTable(naturalKey: string): Promise<TableFull> {
  return apiFetch<TableFull>(`/api/data/v1/tables/${encodeURIComponent(naturalKey)}`);
}

export async function listTablesForParent(parentNaturalKey: string): Promise<TableSummary[]> {
  return apiFetch<TableSummary[]>(
    `/api/data/v1/tables?parent_natural_key=${encodeURIComponent(parentNaturalKey)}`,
  );
}
```

Add fetchers for topic/keyword/gatha detail pages so `tables[]` (already returned from Phase 4) is parsed into typed `TableSummary[]`.

## 3. Design tokens — `ui/src/styles/theme.css`

Add a new EntityKind colour swatch for `table`:

```css
:root {
  --kind-table:        #6B7280;   /* neutral slate — non-competing with red accent */
  --kind-table-soft:   #E5E7EB;
}
```

Expose via `globals.css @theme inline` (`--color-kind-table`, etc.) so `bg-[--color-kind-table]/...` utilities work.

Icon: `lucide-react/Table` (reserve in `ui/src/lib/icons.ts` as `IconTable`).

Update §5 of `ui/README.md` to add the new swatch + icon, and update the EntityKind list everywhere it appears (`lib/types.ts`, `lib/icons.ts`, graph filter chips, content listing pages).

## 4. `TableModal` component — `ui/src/components/TableModal.tsx`

Pattern: copy `DefinitionModal.tsx` 1:1, replace body. Uses `@base-ui/react` `Dialog`.

Props:

```ts
interface TableModalProps {
  naturalKey: string | null;       // null = closed
  onClose: () => void;
}
```

Behaviour:

- Open when `naturalKey` is non-null; fetches via `getTable()` once and caches per nk in a `useRef<Map>`.
- Loading state: shimmer skeleton (reuse `globals.css` shimmer keyframe).
- Error: show retry button + the natural_key for debugging.
- Body sections, in order:
  1. **Caption** — `getHindiText(table.caption)` rendered as `<h2 class="font-serif text-2xl">`. Falls back to "तालिका" if caption is empty.
  2. **Source link** — small link to `table.sourceUrl` opening in new tab, only when present.
  3. **Rendered table** — render from `cells` (NOT `rawHtml` — see §5). First `headerRows` rows become `<th>`. Apply Tailwind: `border-collapse text-sm font-serif`, alternating row bg `bg-[--color-kind-table-soft]/40`, header bg `bg-[--color-kind-table]/15`. Make the wrapper horizontally scrollable on narrow viewports (`overflow-x-auto`).
  4. **Mentions** — two badge rows: "उल्लिखित कीवर्ड" + "उल्लिखित विषय", each badge a `Link` (locale-aware via `i18n/navigation`) to `/dictionary/[nk]` or `/topics/[nk]`. Only render the row if non-empty.
  5. **Raw HTML toggle (dev only)** — when `process.env.NODE_ENV !== "production"`, a collapsible `<details>` rendering `rawHtml` inside a sandboxed `<iframe srcDoc>` for debugging.

### Why render from `cells`, not `rawHtml`

Source HTML may carry inline styles, classes, JS, or `<a>` tags pointing to jainkosh.org — security risk and visual clash with our design system. The parsed `cells` matrix is already NFC-normalized plain text. Internal cross-links are surfaced as the Mentions section instead.

## 5. Wiring

### Graph page (`ui/src/app/[locale]/graph/`)

- `graphStore.ts` — add `tableModalNk: string | null` and `openTableModal(nk)` / `closeTableModal()` actions.
- Graph node renderer (search for the keyword/topic node component, follow the same conditional): when `kind === "table"`, draw using `--color-kind-table` border, fill `--color-kind-table-soft`, icon `IconTable`, smaller node diameter (tables are leaves).
- On node click, if `kind === "table"`, call `openTableModal(node.naturalKey)`. Mount `<TableModal naturalKey={tableModalNk} onClose={closeTableModal} />` at the graph page root.
- Add `table` to the filter chip group (left filter panel). Chip label "तालिकाएँ". Default: ON.

### Content pages

`ui/src/app/[locale]/(content)/`:

- `topics/[nk]/page.tsx`, `dictionary/[nk]/page.tsx` — when the response carries `tables.length > 0`, render a "तालिकाएँ" section as a horizontal scrollable strip of `TableCard` (small card with caption + first row preview). Click → `openTableModal(nk)`. Modal mount lives at the (content) layout level so it works across all detail pages.

### Reader page

`ui/src/app/[locale]/(reading)/shastras/[nk]/gathas/[number]/page.tsx`:

- When the gatha (or its current teeka/bhaavarth/kalash) has tables, surface them in the right info column as chips. Click → modal.

### TopBar / nav

No changes.

## 6. i18n strings

`ui/messages/hi.json` and `ui/messages/en.json` — add:

```json
"tables": {
  "section_title": "तालिकाएँ",
  "modal_title_fallback": "तालिका",
  "mentioned_keywords": "उल्लिखित कीवर्ड",
  "mentioned_topics": "उल्लिखित विषय",
  "open_source": "जैनकोश पर देखें",
  "loading": "लोड हो रहा है…",
  "error": "तालिका लोड नहीं हो सकी"
}
```

Mirror leaf keys exactly in `en.json`.

## 7. Tests — `ui/src/__tests__/`

Vitest only (no e2e):

- `TableModal.test.tsx` — renders cells, header rows applied, mentions render only when present, source link rendered only when present, raw HTML toggle hidden in production-mode mock.
- `api/data.test.ts` — `getTable` / `listTablesForParent` hit the proxy path and parse a fixture.
- `graphStore.test.ts` — `openTableModal` / `closeTableModal` transitions; existing modal state unaffected.

```bash
cd ui
pnpm test
pnpm build           # must pass with 0 errors
```

## 8. Manual verification (live)

```bash
# backend (in another shell)
uvicorn services.core_service.main:app --port 8001

# UI
cd ui && pnpm dev
```

1. Visit `http://localhost:3000/topics/द्रव्य:षट्द्रव्य-विभाजन:द्रव्य-के-या-वस्तु-के-एक-दो-आदि-भेदों-की-अपेक्षा-विभाग` — confirm "तालिकाएँ" section appears with one card; click → modal opens with 13 rows + 1 header row.
2. Visit `/graph?focus=...same nk...&depth=1` — confirm Table node visible with slate styling + Table icon; click → modal.
3. Toggle the "तालिकाएँ" filter chip OFF → table nodes hidden; back ON → reappear.
4. Switch locale to `/en/...` — labels translate, content stays Devanagari.

## 9. Doc updates

[`ui/README.md`](../../../../ui/README.md):

- §5 Design System — add the `--kind-table` swatch row to the EntityKind colour table; add `IconTable` to the reserved icon list.
- §8 Component Catalogue — add a `TableModal` row (sibling of `DefinitionModal`).
- §10 Graph Page — note the new `table` EntityKind in the filter list and the `openTableModal` store action.
- §12 Content Pages — note the new "तालिकाएँ" section on Topic/Keyword detail pages.
- §15 Implementation Phase Log — append "Phase 9 — Tables modal + graph integration".

[`docs/design/ui/`](../../ui) — if a UX template image exists for the modal, drop a markdown note; otherwise mark TBD.

## 10. Definition of Done

- [ ] `TableModal` opens from graph node click, topic detail card, keyword detail card, and reader chip.
- [ ] Filter chip toggles Table nodes in the graph.
- [ ] Vitest suite green; `pnpm build` succeeds with zero errors.
- [ ] Manual verification §8 steps all pass; screenshots attached to PR.
- [ ] `ui/README.md` updated; new i18n keys present in both hi.json and en.json.

## 11. Implementation notes (fill in during PR)

see ui/README.md