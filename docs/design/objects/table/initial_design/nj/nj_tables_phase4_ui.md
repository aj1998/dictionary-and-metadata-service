# NJ Tables — Phase 4: UI (Shastra Reader inline link → TableModal)

Render the `[तालिका देखें](table://<natural_key>)` link emitted by the Phase-2 parser as an in-line, clickable element inside the Shastra Reader's bhaavarth Markdown, opening the existing `TableModal`.

Depends on: [Phase 1](./nj_tables_phase1_schema.md), [Phase 2](./nj_tables_phase2_parser.md), [Phase 3](./nj_tables_phase3_apply.md)
Parent wiki: [../README.md](../../README.md) §10

---

## 1. Where the Markdown is rendered today

Bhaavarth Markdown is rendered in the right-hand column of the Shastra Reader page at:
- `ui/src/app/[locale]/shastras/[shastraNk]/gathas/[gathaNk]/page.tsx` (or the route that loads `gatha_teeka_bhaavarth_hindi`).
- The Markdown renderer is `<ReactMarkdown>` (or `markdown-to-jsx` — verify in `ui/src/components/Bhaavarth*.tsx`).

Identify the component (`grep -r "gatha_teeka_bhaavarth\|bhaavarthMd"` under `ui/src/`) and locate the `components={{...}}` (or equivalent) override map.

---

## 2. Custom link renderer

Override the `a` component:

```tsx
import { useGraphStore } from "@/store/graphStore";

function BhaavarthLink({ href, children }: { href?: string; children: React.ReactNode }) {
  const openTableModal = useGraphStore((s) => s.openTableModal);
  if (href?.startsWith("table://")) {
    const nk = decodeURIComponent(href.slice("table://".length));
    return (
      <button
        type="button"
        onClick={() => openTableModal(nk)}
        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md border border-[var(--color-kind-table)] text-[var(--color-kind-table)] bg-[var(--color-kind-table-soft)]/30 hover:bg-[var(--color-kind-table-soft)]/60 transition"
        aria-label="तालिका देखें"
      >
        <IconTable className="h-3.5 w-3.5" />
        <span>{children}</span>
      </button>
    );
  }
  // fall back to default <a> (definition link, external link, etc.)
  return <a href={href}>{children}</a>;
}
```

Wire it into the Markdown renderer's `components={{ a: BhaavarthLink }}`.

---

## 3. Modal wiring

`TableModal` is already mounted at the layout level and reacts to `useGraphStore`. No new modal component is needed; just ensure the Shastra Reader page renders `<TableModal />` (already global in the layout per Phase-5 UI work — verify).

`getTable(naturalKey)` already returns `table_type` (Phase 1). Optionally show a tiny "सूची तालिका" badge in `TableModal` header when `table.tableType === "index"`:

```tsx
{table.tableType === "index" && (
  <span className="text-xs px-2 py-0.5 rounded-full bg-[var(--color-kind-table-soft)] text-[var(--color-kind-table)]">
    सूची
  </span>
)}
```

---

## 4. i18n

`ui/messages/hi.json` and `ui/messages/en.json`:

```json
"tables": {
  ...,
  "open_inline":        "तालिका देखें",      // (hi) / "View table" (en)
  "type_index":         "सूची"                // (hi) / "Index" (en)
}
```

The Markdown contains literal Devanagari `तालिका देखें` already — translate by reading the locale string and replacing the `children` only when the link is an inline table opener. (Optional polish — out of scope if it complicates the renderer.)

---

## 5. Tests (`ui/src/__tests__/`)

- `BhaavarthLink.test.tsx`
  - renders a `<button>` for `table://...` href and calls `openTableModal` on click.
  - renders a plain `<a>` for ordinary hrefs.
- `TableModal.test.tsx` — extend with: when `tableType === "index"`, the "सूची" badge is rendered.
- `ShastraReaderPage.test.tsx` (if exists) — mock `getGathaBhaavarth()` returning Markdown with the inline link; assert the button is in the DOM.

### Run

```bash
cd ui && pnpm test && pnpm build
```

---

## 6. Manual verification

1. Apply Phase 3 ingestion for पञ्चास्तिकाय gatha 7.
2. `uvicorn services.core_service.main:app --port 8001`
3. `cd ui && pnpm dev`
4. Open `/hi/shastras/पञ्चास्तिकाय/gathas/पञ्चास्तिकाय:गाथा:7`.
5. Scroll bhaavarth to where the सारिणी originally appeared.
6. Verify: an inline "तालिका देखें" pill appears in place of the table. Click → `TableModal` opens; rows + header + caption match the source HTML; "सूची" badge visible.
7. Close modal → reader scroll position preserved.
8. Switch locale to `/en/...` — bhaavarth Markdown unchanged (Devanagari), but the badge text changes if i18n applied.

---

## Implementation Notes (2026-06-10)

Spec diverged from reality in three places; adapted as follows:

1. **Markdown renderer**: BhaavarthPanel does NOT use `<ReactMarkdown>` — it pipes text through `teekaMarkdownToHtml` and renders via `dangerouslySetInnerHTML`. There is no `components={{ a: ... }}` override map. Instead, `teekaMarkdownToHtml` was extended to recognize `[text](table://nk)` markdown links and emit a `<button data-bhaavarth-table-nk="…" class="bhaavarth-table-link …">text</button>`. Ordinary `[text](https://…)` links are also now emitted as `<a target="_blank">`. See `ui/src/lib/format/teeka-markdown.ts`.
2. **Modal mounting & click delegation**: TableModal was NOT yet global. Added `ui/src/components/BhaavarthTableLinkHost.tsx` (`'use client'`) which mounts `<TableModal />` and delegates clicks on `[data-bhaavarth-table-nk]` to `useGraphStore.openTableModal`. Mounted once in `ui/src/app/[locale]/(reading)/layout.tsx`.
3. **Index badge**: TableModal header now shows a "सूची" pill when `table_type === 'index'` (checks both snake_case API field and the camelCase `tableType` on `TableFull`).

i18n keys (`open_inline`, `type_index`) were skipped — the spec marks them as optional polish and the Devanagari literals in the source Markdown remain authoritative.

Tests: `ui/src/__tests__/lib/format/teeka-markdown-tablelink.test.ts` covers the markdown→button conversion, non-table anchor handling, and chip-header non-interference. Full `pnpm test` (491 tests) and `pnpm build` pass.

---

## 7. Done when

- Inline pill appears in every NJ bhaavarth that originally contained a `<table>`.
- Click opens TableModal with cells rendered from `cells` (not `raw_html`).
- `TableModal` shows "सूची" indicator for `table_type='index'`.
- No regression in JainKosh tables (`table_type='general'`) — pill never appears in JK content (because JK Markdown never contains `table://` links; JK surfaces tables as section cards per existing UI).
- UI test suite green; `pnpm build` clean.
