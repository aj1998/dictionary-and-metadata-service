# Side Panel Vivaran — Three Fixes

**Date:** 2026-05-15  
**Scope:** Graph page `DetailsPanel` — keyword definitions, topic extracts, CTA button  
**Status:** Spec (not yet implemented)

---

## Background

When a node is expanded in the graph and clicked, the right `DetailsPanel` (380 px) shows a "विवरण" section. Three problems exist:

1. **Keyword nodes** — `विवरण` renders raw JSON (the entire `definition` object stringified). Should show formatted text with 1–2 preview blocks, then a "पूरा वर्णन पढ़े" button that opens a full scrollable modal.
2. **CTA button** — "पूरा विवरण पढ़ें" renders dark red (`bg-accent #E63946`) and the footer div clips the button bottom edge.
3. **Topic nodes** — `विवरण` shows `topic_path` (e.g. `"1.3"`). Should show actual `extracts` content similarly to keyword definitions.

---

## Issue 1 — Keyword Definition Rendering

### Data structure (from `/v1/keywords/{nk}`)

```
KeywordDetail.definition
  └── page_sections[]
        ├── section_index: number
        ├── section_kind: "siddhantkosh" | "puraankosh" | ...
        ├── h2_text: string          ← section header in Hindi
        └── definitions[]
              └── blocks[]
                    ├── kind: "hindi_text" | "sanskrit_text" | "prakrit_text" | ...
                    ├── text_devanagari: string   ← primary display text
                    ├── hindi_translation: string | null
                    └── references[]
                          └── text: string        ← citation text (inline)
```

### New types (to add to `ui/src/lib/types.ts`)

```typescript
export interface DefinitionReference {
  text: string;
  inline_reference: boolean;
  needs_manual_match: boolean;
  is_teeka: boolean;
  teeka_name: string;
  shastra_name: string | null;
  match_method: string | null;
  resolved_fields: Array<{ field: string; value: string }>;
}

export interface DefinitionBlock {
  kind: string;                        // 'hindi_text' | 'sanskrit_text' | 'prakrit_text' | ...
  text_devanagari: string;
  hindi_translation: string | null;
  references: DefinitionReference[];
  is_orphan_translation: boolean;
  is_bullet_point: boolean;
  raw_html: string | null;
  table_rows: unknown | null;
  target_keyword: unknown | null;
  target_topic_path: string | null;
  target_url: string | null;
  is_self: boolean;
  target_exists: boolean;
}

export interface DefinitionEntry {
  definition_index: number;
  blocks: DefinitionBlock[];
  raw_html: string | null;
}

export interface KeywordPageSection {
  section_index: number;
  section_kind: string;
  h2_text: string;
  definitions: DefinitionEntry[];
  label_topic_seeds: unknown[];
  extra_blocks: unknown[];
}

export interface KeywordDefinitionData {
  created_at: string;
  keyword_id: string;
  natural_key: string;
  page_sections: KeywordPageSection[];
  redirect_aliases: unknown[];
  source_url: string;
  updated_at: string;
}
```

Also update `KeywordDetail`:

```typescript
export interface KeywordDetail extends KeywordSummary {
  aliases: Array<{ id: string; alias_text: string; source: string }>;
  definition: KeywordDefinitionData | null;   // was: unknown | null
}
```

### `EntityDetail` extension (in `types.ts`)

Add optional fields to carry structured data past the normalisation step:

```typescript
export interface EntityDetail {
  nk: string;
  kind: EntityKind;
  title_hi: string;
  title_en?: string;
  description?: string;
  stats: Record<string, number>;
  connected: Array<{ nk: string; kind: EntityKind; title_hi: string; title_en?: string; edge_kind: EdgeKind }>;
  // NEW — populated only when kind === 'keyword'
  definitionSections?: KeywordPageSection[];
  // NEW — populated only when kind === 'topic'
  topicExtracts?: unknown[];
}
```

### `data.ts` change (`getEntityDetail` — keyword branch)

```typescript
if (kind === 'keyword') {
  const keyword = await apiFetch<KeywordDetail>(BASE_URL, `/v1/keywords/${nk}`);
  const sections = keyword.definition?.page_sections ?? [];
  // description = first block text for plain-text fallback
  const firstText = sections[0]?.definitions[0]?.blocks[0]?.text_devanagari ?? '';
  return {
    nk: keyword.natural_key,
    kind: 'keyword',
    title_hi: keyword.display_text,
    description: firstText.slice(0, 250) || undefined,
    stats: { aliases: keyword.aliases.length },
    connected: [],
    definitionSections: sections.length ? sections : undefined,
  };
}
```

### `data.ts` change (`getEntityDetail` — topic branch)

```typescript
if (kind === 'topic') {
  const topic = await apiFetch<TopicDetail>(BASE_URL, `/v1/topics/${nk}`);
  const hi = topic.display_text.find((row) => row.lang === 'hi')?.text ?? topic.natural_key;
  const parent = topic.parent_keyword;
  return {
    nk: topic.natural_key,
    kind: 'topic',
    title_hi: hi,
    description: topic.topic_path,
    stats: { extracts: topic.extracts.length, is_leaf: topic.is_leaf ? 1 : 0 },
    connected: parent ? [{ nk: parent.natural_key, kind: 'keyword', title_hi: parent.display_text, edge_kind: 'HAS_TOPIC' }] : [],
    topicExtracts: topic.extracts.length ? topic.extracts : undefined,
  };
}
```

---

## Issue 2 — CTA Button Color + Footer Clip

### Button color

"पूरा वर्णन पढ़े" should feel secondary/soft — not the same weight as a primary action.

**New variant:** use `bg-accent-soft` (`#FDECEE`) with `text-accent` (`#E63946`) text and a `border border-accent/40` ring. On hover: `bg-accent/10`.

Option A — add a `variant` prop to `PrimaryCTA`:

```typescript
export interface PrimaryCTAProps {
  variant?: 'primary' | 'soft';   // default: 'primary'
  ...
}
```

```
primary → bg-accent text-white hover:bg-accent-hover  (current)
soft    → bg-accent-soft text-accent border border-accent/30 hover:bg-accent/10
```

Option B — inline class override via `className` prop (already exists). Pass:
```
className="bg-accent-soft text-accent border border-accent/30 hover:bg-accent/10"
```
and remove the white text from inner `<span>` by adjusting PrimaryCTA to not hardcode `text-white` when a custom className overrides colour.

**Recommendation: Option A** — cleaner, reusable, avoids fighting specificity with inline overrides.

### Footer clip fix

In `DetailsPanel` the body container:

```tsx
<div className="flex h-full flex-col">
  <div className="border-b ...">header</div>
  <div className="flex-1 overflow-y-auto p-4">…</div>   {/* scrollable */}
  <div className="border-t py-4">
    <PrimaryCTA ... />
  </div>
</div>
```

The outer `<aside>` has no height set, so `h-full` on the flex container has nothing to anchor to — the aside grows unbounded and overflows the viewport, clipping the footer.

**Fix:** make the aside a full-height column:

```tsx
<aside className="w-[380px] shrink-0 border-l border-border bg-surface flex flex-col h-screen overflow-hidden">
  <div className="sticky top-0 z-10 ...">header</div>
  <div className="flex flex-col flex-1 overflow-hidden">
    {body}  {/* body already has h-full flex-col structure */}
  </div>
</aside>
```

Remove `h-full` from the body's outermost `<div>` and instead let flexbox propagate: the scrollable middle section takes `flex-1 overflow-y-auto`, footer is fixed.

---

## Issue 3 — Topic Extracts in DetailsPanel

Topic extracts are `unknown[]` from the API. In Phase 7 detail pages they're rendered as:
```
typeof extract === 'string' ? extract : JSON.stringify(extract)
```

For the panel we do the same safe fallback. The vivaran section for a topic should show:

- If no `definitionSections` (keyword path) and kind is `topic`:
  - Show `topicExtracts` as a scrollable list inside the panel, up to **2 items** (preview)
  - Each extract: left-accented block with the text
  - "पूरा वर्णन पढ़े" opens the full modal showing all extracts + topic_path

---

## New Component — `DefinitionModal`

**File:** `ui/src/components/DefinitionModal.tsx`

A full-screen overlay (Dialog from shadcn/ui) that renders:

### For keywords:

```
┌──────────────────────────────────────────────────────┐
│  द्रव्य                                  [✕ close]  │
│  ──────────────────────────────────────────────────  │
│  [सिद्धांतकोष से]                                   │
│                                                      │
│  लोक द्रव्यों का समूह है और वे द्रव्य छह मुख्य…   │
│                                                      │
│  ┌──────────────────────────────────────────────┐   │
│  │  (Sanskrit/Prakrit block rendered with        │   │
│  │   monospace-ish Devanagari serif, on a muted  │   │
│  │   bg-surface-muted background, border-l-4     │   │
│  │   border-cat-keyword accent)                  │   │
│  └──────────────────────────────────────────────┘   │
│                                                      │
│  _हरिवंशपुराण - 1.1, 2.108, 17.135_  (italic ref)  │
│  ──────────────────────────────────────────────────  │
│  [पुराणकोष से]                                      │
│  …                                                   │
└──────────────────────────────────────────────────────┘
```

### For topics:

```
┌──────────────────────────────────────────────────────┐
│  द्रव्य का लक्षण गुण समुदाय            [✕ close]   │
│  ──────────────────────────────────────────────────  │
│  विषय अंश (N)                                        │
│                                                      │
│  ▎ extract text 1 …                                  │
│  ▎ extract text 2 …                                  │
│  …                                                   │
└──────────────────────────────────────────────────────┘
```

### Props:
```typescript
interface DefinitionModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  // keyword path
  definitionSections?: KeywordPageSection[];
  // topic path
  topicExtracts?: unknown[];
}
```

### Block rendering rules (keyword):

| `block.kind` | Rendering |
|---|---|
| `hindi_text` | Plain Hindi text, `font-serif-hindi`, standard foreground |
| `sanskrit_text` | Inside `bg-surface-muted rounded p-3 border-l-4 border-cat-keyword`, `font-serif-hindi text-sm` |
| `prakrit_text` | Same as sanskrit_text |
| anything else | Same as hindi_text fallback |

References (for any block kind):
- Rendered below the block text, separated by a thin `<hr />`
- Each reference: `<p className="text-xs italic text-foreground-muted">{ref.text}</p>`
- If `resolved_fields` is non-empty: append resolved key=value pairs in small muted text

---

## DetailsPanel Changes

### Keyword vivaran preview (inside the existing `<section>` for विवरण)

Replace the current `detail?.description ?? 'विवरण उपलब्ध नहीं है।'` paragraph with:

```tsx
{detail?.definitionSections ? (
  <KeywordDefinitionPreview sections={detail.definitionSections} />
) : (
  <p className="font-serif-hindi text-[length:var(--font-size-body)] text-foreground">
    {detail?.description ?? 'विवरण उपलब्ध नहीं है।'}
  </p>
)}
```

**`KeywordDefinitionPreview`** (inline in DetailsPanel or separate small file):
- Take first section only, first definition only, up to **2 blocks** max
- Each block: render `text_devanagari` truncated at 180 chars with `…` if longer
- References: omit in preview (shown only in modal)
- Label the section with `h2_text` in `text-xs font-medium text-foreground-muted uppercase tracking-wide`

### Topic vivaran preview

When `detail?.topicExtracts?.length`:

```tsx
<div className="space-y-2">
  {detail.topicExtracts.slice(0, 2).map((extract, i) => (
    <p key={i} className="rounded border-l-4 border-accent/40 bg-background px-3 py-2 font-serif-hindi text-sm">
      {typeof extract === 'string' ? extract : JSON.stringify(extract)}
    </p>
  ))}
  {detail.topicExtracts.length > 2 && (
    <p className="text-xs text-foreground-muted">+{detail.topicExtracts.length - 2} और…</p>
  )}
</div>
```

### "पूरा वर्णन पढ़े" CTA

- Change label from `"पूरा विवरण पढ़ें"` to `"पूरा वर्णन पढ़ें"`
- Change variant to `soft` (or apply soft class override)
- Change from a link (`href`) to a `button` (`onClick`) that sets `definitionModalOpen = true`
- Only show when `detail?.definitionSections` or `detail?.topicExtracts` exists

State to add to DetailsPanel:
```typescript
const [definitionModalOpen, setDefinitionModalOpen] = useState(false);
```

---

## File Change Summary

| File | Change |
|---|---|
| `ui/src/lib/types.ts` | Add `DefinitionReference`, `DefinitionBlock`, `DefinitionEntry`, `KeywordPageSection`, `KeywordDefinitionData`; update `KeywordDetail.definition` type; add `definitionSections?` and `topicExtracts?` to `EntityDetail` |
| `ui/src/lib/api/data.ts` | Keyword branch: set `description` from first block, pass `definitionSections`; Topic branch: pass `topicExtracts` |
| `ui/src/components/DetailsPanel.tsx` | Replace raw JSON paragraph with `KeywordDefinitionPreview`, add topic extracts preview, wire `DefinitionModal`, fix footer height, change CTA to soft variant |
| `ui/src/components/DefinitionModal.tsx` | **New file** — Dialog-based full definition viewer for keywords and topics |
| `ui/src/components/PrimaryCTA.tsx` | Add `variant?: 'primary' \| 'soft'` prop; apply conditional class sets |
| `ui/src/lib/api/data.test.ts` | Add assertions for `definitionSections` and `topicExtracts` in normalised output |

---

## Open Questions / Not in Scope

- **Sanskrit/Prakrit block types**: The API returns `kind: "hindi_text"` for all blocks in the sample. Need to confirm what other `kind` values exist in production data (e.g. `"sanskrit_text"`, `"prakrit_text"`) before adding special styling. For now, treat all non-hindi as "secondary" background style.
- **References with `resolved_fields`**: The sample shows `resolved_fields: []`. When non-empty, the intent is to show the resolved shastra/chapter. Design TBD — hold for a follow-up.
- **Modal on mobile**: On small screens the `Sheet` (bottom drawer) should host the full definition inline instead of a separate Dialog. This can be handled by checking `isDesktop` and using `SheetContent` vs `DialogContent`. Defer if scope is tight.
- **Topic `extracts` schema**: Currently `unknown[]`. If the API returns structured objects (with `text_devanagari` etc.) they should be typed and rendered the same way as keyword blocks. For now render as text string with JSON fallback.
