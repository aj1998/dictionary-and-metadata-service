# Implementation Notes - UI

## Phase 0:
    
    Phase 0 deliverables at ui/:
    
    ┌──────────────────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┬──────┐
    │ Step │ File(s)│ Done │
    ├──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
    │ 0.1 Next.js scaffold │ ui/ — Next.js 16, Tailwind 4, shadcn (Button, Card, Switch, Tabs, Tooltip, Pagination, Sheet, Popover, Separator, Badge) │ ✓    │
    ├──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
    │ 0.2 CSS token layer  │ src/styles/theme.css — all 30+ CSS custom properties from 01_design_system.md                                            │ ✓    │
    ├──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
    │ 0.3 Tailwind config  │ src/app/globals.css — @theme inline block mapping every token to a Tailwind utility                                      │ ✓    │
    ├──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
    │ 0.4 Fonts            │ src/app/layout.tsx — Noto_Serif_Devanagari + Inter via next/font, --font-serif-hindi / --font-sans variables             │ ✓    │
    ├──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
    │ 0.5 Global CSS       │ src/app/globals.css — body uses --background + font-serif-hindi; @keyframes shimmer + prefers-reduced-motion override    │ ✓    │
    ├──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
    │ 0.6 next-intl        │ src/i18n/routing.ts, src/i18n/request.ts, src/proxy.ts, messages/hi.json + messages/en.json (all chrome strings)         │ ✓    │
    ├──────────────────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┼──────┤
    │ 0.7 Devanagari utils │ src/lib/format/devanagari.ts — toDevanagariNumerals, normalizeNFC, minGraphemeLength                                     │ ✓    │
    └──────────────────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┴──────┘
    
    Notable adaptation: Next.js 16 (vs spec's Next.js 14) renamed middleware.ts → proxy.ts, and Tailwind 4 uses CSS-only @theme inline instead of tailwind.config.ts
Both changes are transparent to future phases —
    all token names and Tailwind classes work identically.
    
    Build passes cleanly (pnpm build — no errors, no warnings). The checkpoint criterion (correct background colour #F7F7F8, tokens resolve) is satisfied.

### Tests:

- src/lib/format/devanagari.test.ts -> toDevanagariNumerals (digits, multi-digit, large), normalizeNFC (idempotent, NFD→NFC, ASCII), minGraphemeLength (ASCII, Devanagari conjuncts, empty)
- src/lib/format/messages.test.ts -> hi.json and en.json have identical leaf-key sets; neither is empty
- src/styles/theme.test.ts -> Every required CSS token is declared in theme.css; accent/background/category hex values match the spec exactly

Run with pnpm test (single pass) or pnpm test:watch (interactive).

---

## Phase 1:
    
    ┌─────────────────────────────────┬──────────────────────────────────┬────────┐
    │Task                             │ File                             │ Status │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ 1.1 TopBar                      │ src/components/TopBar.tsx        │ ✅ │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ 1.2 BreadcrumbBar               │ src/components/BreadcrumbBar.tsx │ ✅ │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ 1.3 Footer                      │ src/components/Footer.tsx        │ ✅ │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ 1.4a Shell A — Graph            │ src/app/graph/layout.tsx         │ ✅ │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ 1.4b Shell B — Content          │ src/app/(content)/layout.tsx     │ ✅ │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ 1.4c Shell C — Reading          │ src/app/(reading)/layout.tsx     │ ✅ │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ 1.5 Skeleton                    │ src/components/Skeleton.tsx      │ ✅ │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ 1.6 Root layout                 │ src/app/layout.tsx               │ ✅ │
    ├─────────────────────────────────┼──────────────────────────────────┼────────┤
    │ LocaleSwitch (needed by Footer) │ src/components/LocaleSwitch.tsx  │ ✅ │
    └─────────────────────────────────┴──────────────────────────────────┴────────┘
    
    Key decisions:

    - TopBar is a 'use client' component mounted in the root layout — it derives activeRoute from usePathname() internally
    - Shell A (graph) has no footer; Shells B and C include the Footer
    - At < xl (1280px), the graph left pane hides; at < 1200px, nav items शस्त्र/विषय/प्रतिक्रिया fold into a "More ▾" popover; at < 768px, the entire nav moves into an off-canvas Sheet drawer
    - The old app/page.tsx was replaced by app/(content)/page.tsx
    - src/lib/nav.ts — extracted isNavActive, truncateLabel, and all three nav item arrays into a shared module, so TopBar and BreadcrumbBar import from it instead of defining their own copies.
    
### Tests:

    src/lib/nav.test.ts — 19 tests across three suites:
    
    ┌───────────────┬────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
    │ Suite         │ What it covers                                                                                                                 │
    ├───────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ isNavActive   │ Exact / match, prefix matching for sub-routes, false-positive prevention (/graph-preview ≠ /graph), trailing-slash edge case   │
    ├───────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ truncateLabel │ Under/at/over limit, custom max, ellipsis shape and length                                                                     │
    ├───────────────┼────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ nav item data │ Item counts, PRIMARY+MORE = ALL, unique routes, Devanagari labels non-empty, every labelKey maps to a real hi.json nav.* entry │

---
## Bug fix: locale routing (applied after Phase 3)

**Symptom:** `localhost:3000/en` returned 404 despite next-intl being configured.

**Root cause:** next-intl with URL-based locale switching (`localePrefix: "as-needed"`) requires an `src/app/[locale]/` folder so Next.js App Router can capture the locale segment from the URL. Without it, `/en` has no matching page component. The proxy.ts file itself was correct — Next.js 16 did rename `middleware.ts` → `proxy.ts` — but the `[locale]` folder structure was never created.

**Changes made:**

- Created `src/app/[locale]/layout.tsx` — locale shell: validates locale via `hasLocale()`, calls `getMessages()`, mounts `NextIntlClientProvider` and `TopBar`. Calls `notFound()` for unrecognised locales.
- Moved all route files under `src/app/[locale]/`:
  - `(content)/layout.tsx` + `(content)/page.tsx` (Shell B — homepage)
  - `(reading)/layout.tsx` (Shell C — reading view)
  - `graph/layout.tsx` + `graph/page.tsx` (Shell A — graph)
  - `dev/page.tsx` (component gallery)
- Simplified `src/app/layout.tsx` to a pure html/body shell (fonts + `lang` attribute via `getLocale()`). `NextIntlClientProvider` and `TopBar` moved to locale layout.

**Route table after fix:**

```
/[locale]        → homepage (Shell B)
/[locale]/dev    → component gallery
/[locale]/graph  → graph shell (Shell A)
```

Proxy (Middleware) row confirms next-intl locale routing is active.

**URL behaviour** (`localePrefix: "as-needed"`, defaultLocale `hi`):
- `localhost:3000/` → Hindi (no prefix for default locale)
- `localhost:3000/en` → English

---
## Bug fix: locale-aware navigation + stub pages (applied after Phase 3)

**Symptom:** Nav links from `/en` dropped the locale prefix (clicking शब्दकोश went to `/dictionary` not `/en/dictionary`); active-state highlight never fired on `/en/...` routes; `/en/dictionary` and all other nav routes returned 404.

**Root causes:**
1. `TopBar` imported `Link`, `usePathname`, `useRouter` from `next/navigation`. Next.js's own versions are not locale-aware: `usePathname()` returns the full path including the locale prefix (so `/en/dictionary` never matched `/dictionary` in `isNavActive`), and `Link` never prepends the locale segment.
2. Stub pages for nav routes (dictionary, about, shastras, topics, feedback) were never created — so even correct locale-prefixed URLs returned 404.

**Changes made:**
- Added `src/i18n/navigation.ts` — exports locale-aware `Link`, `redirect`, `usePathname`, `useRouter` via `createNavigation(routing)` from next-intl. These automatically strip the locale prefix from `usePathname()` output and prepend it on `Link` hrefs.
- Updated `src/components/TopBar.tsx` to import `Link`, `usePathname`, `useRouter` from `@/i18n/navigation` instead of `next/navigation`.
- Created stub pages (Shell B content shell) for all nav routes:
  - `src/app/[locale]/(content)/dictionary/page.tsx`
  - `src/app/[locale]/(content)/about/page.tsx`
  - `src/app/[locale]/(content)/shastras/page.tsx`
  - `src/app/[locale]/(content)/topics/page.tsx`
  - `src/app/[locale]/(content)/feedback/page.tsx`

**Nav label language:** Nav labels always render in Hindi (Devanagari) regardless of locale — this is by design for a Jain scripture application. The `locale` prop on `TopBar` is reserved for future phase use (e.g. aria attributes, locale-specific formatting).

---
## Phase 2:
    
    ┌─────────────────────────────────────┬───────────────────────────────────────────────────────────────────────────────────────────────────────┐
    │File                                 │ Component │
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/lib/types.ts                    │ EntityKind type shared across components│
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/lib/icons.ts                    │ Reserved icon re-exports (all 20 icons from 01_design_system.md §6)│
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/components/BadgeChip.tsx        │ Entity pill — 4 kinds × 2 sizes (sm/md), correct category colors│
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/components/StatTile.tsx         │ Stat card with Devanagari numerals, text-h1 count, muted uppercase label│
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/components/StatTileRow.tsx      │ 3-up flex row of StatTiles with 12 px gap│
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/components/ConnectedItemRow.tsx │ Badge + title + chevron row; renders as <a> when href given, <button> otherwise; hover accent chevron │
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/components/PrimaryCTA.tsx       │ 44 px red CTA button, Hindi + English label, right Bookmark icon, hover darkens│
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/components/ListCards.tsx        │ KeywordCard, TopicCard, GathaTile — white surface, hover lift, Devanagari count, arrow│
    ├─────────────────────────────────────┼───────────────────────────────────────────────────────────────────────────────────────────────────────┤
    │ src/app/dev/page.tsx                │ Checkpoint 2 gallery — all components in all states at /dev│
    └─────────────────────────────────────┴───────────────────────────────────────────────────────────────────────────────────────────────────────┘
    
    LocaleSwitch already existed from Phase 1 and is correct. TypeScript compiles clean and the production build succeeds with /dev in the route table
    
### Tests:
    
src/components/BadgeChip.test.ts (18 tests)
- BADGE_DEFAULT_LABELS — covers all 4 EntityKinds, non-empty Hindi/English labels, Devanagari script validation, exact label spot-checks
- BADGE_CAT_CLASSES — covers all 4 kinds, bg-cat-* prefix invariant, uniqueness, exact class name spot-checks

src/lib/icons.test.ts (3 tests)
- All 20 reserved icons from 01_design_system.md §6 are exported
- Each export is a renderable React component (handles both plain functions and forwardRef objects)
- No extra icons — export set matches the reserved set exactly
    
    BadgeChip.tsx had its two data constants renamed to BADGE_DEFAULT_LABELS / BADGE_CAT_CLASSES and exported so the tests can import them without rendering any JSX.

---
## Phase 3:

New files created: 
- ui/src/lib/api/_fetch.ts — apiFetch<T> base wrapper with ApiError class; Devanagari-safe path encoding (splits on ? so query strings aren't encoded) 
- ui/src/lib/api/metadata.ts — getShastras, getShastra, getShastraTeekas (port 8001) 
- ui/src/lib/api/data.ts — 12 functions: activity, stats, entity detail, keywords, topics, gathas (port 8002)
- ui/src/lib/api/navigation.ts — getNavLanding, expandNode, getPreview, getTopicNeighbors (port 8003)
- ui/src/lib/api/query.ts — searchTopics via POST, caller defaults to 'public-ui' (port 8004)

Updated: 
- ui/src/lib/types.ts — expanded from 1 line to all shared types: EdgeKind (11 variants), GraphNode/Edge/Payload, Paginated<T>, and all domain response shapes

### Tests
- 5 test files covering success paths, error paths (ApiError with correct status), URL construction, and Devanagari encoding 

From regressions -

- nav.test.ts (+1 suite) -> locale-prefixed paths fail isNavActive -> Documents the contract: isNavActive must receive the locale-stripped path, proving why next-intl's usePathname is required
- i18n/routing.test.ts -> locales, defaultLocale, localePrefix, localeCookie -> Locks the config that makes [locale] folder mandatory — changing defaultLocale or localePrefix must be an intentional decision
- i18n/navigation.test.ts -> 4 exports exist and are functions -> next-intl/navigation is mocked (it pulls in next/navigation which isn't resolvable in Node) — verifies the destructuring in navigation.ts is correct
- lib/locale-pages.test.ts -> every nav route has a page file on disk -> Acts as a manifest: adding a nav item in nav.ts without a matching page.tsx under [locale]/ will fail here

---