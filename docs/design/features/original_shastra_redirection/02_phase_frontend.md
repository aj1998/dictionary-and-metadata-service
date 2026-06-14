# Phase 2 — Frontend (UI)

Parent: [00_overview.md](./00_overview.md)

Prerequisite: [01_phase_backend.md](./01_phase_backend.md) merged (endpoint + offset fields on the shastra-detail payload).

## Goals

1. Add a new **brown** `OriginalShastraLink` component that opens the locally-downloaded shastra PDF at the exact published page in a new tab.
2. Render it inside the four ref renderers: `RefBadge`, `GroupedRefRow`, `GroupedRefList`, `RefListItem` (all in [`ui/src/components/DefinitionModal.tsx`](../../../../ui/src/components/DefinitionModal.tsx)).
3. Reposition the existing blue / grey `RefMatchLink` so it sits **beside the gatha-type text** of its respective reference, not embedded inline with the field row. The brown link stays inline with the field row.
4. Add a shastra-offset registry (similar to `shastra-registry.ts`) that the UI uses to compute the PDF page client-side.

No backend calls beyond what already exists + the offset payload from Phase 1.

---

## 1. Files to add / modify

### Add

- `ui/src/components/OriginalShastraLink.tsx` — the brown link.
- `ui/src/lib/shastra-pdf-registry.ts` — `useShastraPdfOffsets()` hook.
- `ui/src/components/OriginalShastraLink.test.tsx` — vitest unit tests.
- `ui/src/lib/shastra-pdf-registry.test.ts` — page-math tests.

### Modify

- `ui/src/components/DefinitionModal.tsx` — wire the new link into ref renderers, move `RefMatchLink` to the gatha-type slot.
- `ui/src/lib/types.ts` — extend `EntityDetail` (or whichever type backs the shastra detail) with `pdf_page_offset?: number; pustak_offsets?: Record<string, number> | null`.
- `ui/messages/hi.json` and `ui/messages/en.json` — add a single string under a new `originalShastra` namespace (or extend `shastras`): `"viewOriginal": "मूल शास्त्र में देखें"` / `"View original shastra"`.
- `ui/README.md` §8 — add a row for `OriginalShastraLink` in the component catalogue and a sentence about the repositioned `RefMatchLink`.
- `ui/src/styles/theme.css` (optional) — confirm `--cat-page` (`#B5645A`) already exists; if so, reuse it. The brown link color should be `--cat-page` for the icon stroke + `text-amber-800` for the title attribute hover state, OR introduce `--link-original` if a precise brown is preferred. Reuse `--cat-page` to avoid sprawl.

---

## 2. `OriginalShastraLink` — component spec

Props:

```ts
interface OriginalShastraLinkProps {
  shastraNk: string;                         // ref.shastra_name (NFC-normalize on use)
  pustak: string | null;                     // resolved_fields entry where field === 'पुस्तक', else null
  publishedPage: number;                     // parsed from resolved_fields entry where field === 'पृष्ठ'
  pdfPageOffset: number;                     // from shastra detail
  pustakOffsets: Record<string, number> | null; // from shastra detail
}
```

Behavior:
- Compute `pdfPage = publishedPage + (pustakOffsets?.[pustak ?? ''] ?? pdfPageOffset)`.
- `href = ` `/api/metadata/shastras/${encodeURIComponent(shastraNk.normalize('NFC'))}/pdf-file${pustak ? '?pustak=' + encodeURIComponent(pustak) : ''}#page=${pdfPage}`
- Render `<a target="_blank" rel="noopener noreferrer">` with the `BookOpen` icon (or `FileText` — pick `BookOpen` for parity with the existing "मूल शास्त्र में देखें" semantics).
- Tailwind classes: `inline-flex items-center text-[var(--cat-page)] hover:text-amber-900 transition-colors`.
- Icon size: `size-4 shrink-0` (matches existing `RefMatchLink`).
- `title` / `aria-label`: `मूल शास्त्र में देखें — <shastraNk> पृष्ठ <publishedPage>`.
- Locale-aware label via `useTranslations('originalShastra').t('viewOriginal')`.

The component is **purely presentational** — it does not check availability. If the file is missing the browser shows the metadata service's 404.

---

## 3. Helper: extract page + pustak from a ref

Add to `ui/src/lib/shastra-pdf-registry.ts`:

```ts
export function extractOriginalShastraInfo(ref: DefinitionReference): { publishedPage: number; pustak: string | null } | null {
  let publishedPage: number | null = null;
  let pustak: string | null = null;
  for (const { field, value } of ref.resolved_fields) {
    if (field === 'पृष्ठ') {
      const n = parseInt(value.replace(/[०-९]/g, (d) => String('०१२३४५६७८९'.indexOf(d))).trim(), 10);
      if (!Number.isNaN(n)) publishedPage = n;
    } else if (field === 'पुस्तक') {
      pustak = value.trim();
    }
  }
  if (publishedPage === null) return null;
  return { publishedPage, pustak };
}
```

Returns `null` if the ref has no `पृष्ठ` — caller uses that to skip rendering.

---

## 4. Hook: `useShastraPdfOffsets`

Add to `ui/src/lib/shastra-pdf-registry.ts`. Pattern mirrors the existing `useIngestedShastras` in `ui/src/lib/shastra-registry.ts`.

```ts
export interface ShastraPdfOffsets {
  pdfPageOffset: number;
  pustakOffsets: Record<string, number> | null;
}

export function useShastraPdfOffsets(shastraNk: string | null): {
  offsets: ShastraPdfOffsets | null;
  loading: boolean;
};
```

Implementation:
- Calls the existing `getEntityDetail('shastra', shastraNk)` once per `shastraNk`.
- Memoizes results in a module-level `Map<string, ShastraPdfOffsets>`.
- Returns `{ pdfPageOffset: 0, pustakOffsets: null }` when the shastra detail is missing or the fields are absent (safe default — `OriginalShastraLink` will then build a `#page=<publishedPage>` URL with no offset).

> If multiple refs in the same modal share a shastra, only one fetch is made. The fetch is fire-and-forget; the brown link is rendered with the default offsets immediately and re-rendered with the real ones once the fetch resolves.

---

## 5. Wiring inside `DefinitionModal.tsx`

Current visual order inside `RefBadge` (lines ~203-227):

```
[badgeLabel | field:value · field:value][RefMatchLink (blue/grey)]
```

Target visual order:

```
[badgeLabel ↗ (RefMatchLink — moved here, next to gatha-type text)][| field:value · field:value][OriginalShastraLink (brown — only if पृष्ठ exists)]
```

Where:
- `badgeLabel` is the source label (`shastra_name` / `teeka_name`) — for refs where `is_teeka` is true the existing logic shows the teeka name. This counts as "gatha type text" for the purpose of the spec.
- For `GroupedRefRow` and `GroupedRefList` the same shift applies: the per-source label gets the `RefMatchLink` slot, and each per-ref row (with its own `पृष्ठ`) gets its own `OriginalShastraLink`.

Apply the same to `RefListItem` and to the popover-list rendered inside `समान संदर्भ`.

### Behaviour matrix

| Ref carries `पृष्ठ`? | `RefMatchLink` plan kind | Render |
|---|---|---|
| no | `matched` | blue gatha-link beside gatha-type text only |
| no | `fallback` | grey gatha-link beside gatha-type text only |
| no | `none` | nothing |
| yes | `matched` | blue gatha-link beside gatha-type text + brown link at end of field row |
| yes | `fallback` | grey gatha-link beside gatha-type text + brown link at end of field row |
| yes | `none` | brown link at end of field row only |

> The brown link is rendered **whenever the ref has `पृष्ठ`**, regardless of whether the file is locally available. This is the "always show, 404 on click" decision.

---

## 6. Tests (vitest)

1. `shastra-pdf-registry.test.ts`
   - `extractOriginalShastraInfo` parses Devanagari and ASCII page numbers; returns `null` when no `पृष्ठ`.
   - Page-math helper: `publishedPage + offset` with and without a matching `pustakOffsets` key.

2. `OriginalShastraLink.test.tsx`
   - URL fragment encoding includes `#page=<expected>`.
   - `pustak` is added as a query param when present, omitted when null.
   - `target="_blank"` + `rel="noopener noreferrer"` are present.
   - Icon color resolves to `--cat-page`.

3. Extend `DefinitionModal` tests (existing test file) with:
   - A ref with `पृष्ठ` renders both a `RefMatchLink` (when applicable) **and** an `OriginalShastraLink`.
   - A ref without `पृष्ठ` renders **no** `OriginalShastraLink`.
   - `RefMatchLink` appears next to the source label, not after the field row.

---

## 7. Manual verification

1. Place a test PDF at `$ORIGINAL_SHASTRA_PDF_DIR/<some shastra_name>.pdf`.
2. Add `pdf_page_offset` to that shastra entry in `shastra.json` (e.g. `0`).
3. Restart the core service. Restart `ui` dev server (`pnpm dev` in `ui/`).
4. Open a keyword whose definition has a ref into that shastra with `पृष्ठ: 12`.
5. Open `DefinitionModal`. Confirm:
   - Blue / grey gatha-link sits beside the source-label / teeka-name.
   - Brown book icon sits after the field row.
   - Clicking the brown link opens the PDF in a new tab at page 12 (browser native viewer).
6. Edit `shastra.json`, set `pdf_page_offset: 5` for that shastra, restart core service, hard-reload UI, click again — page should now open at 17.
7. Delete the local PDF — click should yield the browser's native 404 page.

---

---

## Implementation Notes

**Status:** ✅ Implemented

**Key decisions/diversions:**

- `useShastraPdfOffsets` uses a **promise cache** (`Map<string, Promise<ShastraPdfOffsets>>`) rather than a plain result cache — this prevents multiple concurrent hook instances (one per `RefBadge`) from racing to fetch the same shastra before any response arrives.
- The hook calls `getShastra(nk)` from `@/lib/api/metadata` directly (not `getEntityDetail`) since `getEntityDetail('shastra', nk)` returns `EntityDetail` which doesn't carry `pdf_page_offset`/`pustak_offsets`.
- For multi-ref groups in `GroupedRefRow` and `GroupedRefList`, the existing inline `span` renders were extracted into `MultiRefGroupBadge` and `MultiRefGroupListItem` **named components** so that `useShastraPdfOffsets` can be called at component scope (React hook rules — no hooks in loops).
- When `badgeLabel` is null (no source label shown in the badge), `RefMatchLink` is kept in the trailing position (after fields) rather than moved — there's no "gatha-type text" to sit beside.
- `OriginalShastraLink.tsx` exports `buildOriginalShastraHref` and `computePdfPage` as pure functions to enable vitest unit tests (no React rendering setup in the vitest config).
- Tests are in `src/__tests__/lib/shastra-pdf-registry.test.ts` (new, 37 tests) and extended `src/__tests__/components/DefinitionModal.test.ts` (5 new tests) — `.test.ts` not `.test.tsx` to match the existing vitest include pattern (`**/*.test.ts`, node environment).

---

## 8. Out of scope

- A "PDF unavailable" toast / fallback message (chose not to implement; 404 is acceptable).
- Inline PDF preview / thumbnail.
- Multi-page link (no need; `#page=N` is enough).
- Updating any non-modal contexts. If a future feature surfaces refs outside `DefinitionModal`, wire `OriginalShastraLink` in then.
