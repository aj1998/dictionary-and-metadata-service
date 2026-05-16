# 04 — Content Pages

Every page below uses **Shell B (centered)** from `02_layout_and_navigation.md`
unless explicitly noted. Every page inherits the global TopBar and the
red-accent palette from `01_design_system.md`. Cards, badges, stat tiles,
and CTAs are reused from `05_components.md`.

The visual "feel" of every page must echo `overall_theme_and_panels.png`:
white surface cards on light-grey background, generous whitespace, slim
borders, soft shadows, Hindi-first Devanagari body, English as captioned
subtitle.

## 1. `/` — Home

```
┌──────────────────────────────────────────────────────────────────┐
│  जैन ज्ञान कोष                                                       │   <- hero (text-display)
│  Jain Knowledge Base                                             │
│  एक संरचित ज्ञान-आधारित खोज परत                                       │   <- one-liner
│                                                                  │
│  [🔎 गाथा, शास्त्र, कीवर्ड खोजें…]   [विषय खोज ✦]                          │   <- pinned search + CTA
│                                                                  │
│  ┌────────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ 📖         │   │ 📜       │  │ 🏷       │  │ 🔗       │        │   <- 4 entry cards
│  │ शब्दकोष     │   │ शास्त्र      │  │ विषय     │  │ ग्राफ      │        │
│  │ Dictionary │  │ Shastras │  │ Topics   │  │ Graph    │        │
│  │ १२,४५२      │  │ ४८       │  │ ३,११७     │  │ खोलें →    │        │
│  └────────────┘  └──────────┘  └──────────┘  └──────────┘        │
│                                                                  │
│  जारी प्रवृत्ति (Recent activity)                                       │
│  • <last 10 approved ingestion runs as rows>                     │
└──────────────────────────────────────────────────────────────────┘
```

- Hero (`text-display` Hindi + `text-h2` English subtitle).
- Below hero: a second copy of the global search (visually identical),
  flanked by an `विषय खोज` (Topic search) outline button that goes to
  `/search`.
- 4 large entry-cards in a responsive grid (4 cols ≥ xl, 2 cols ≥ md,
  1 col mobile). Each card 200 px tall, white surface, `--radius-md`,
  `--node-shadow`, hover `--node-shadow-hover`. Big icon top-left, Hindi
  title + English subtitle, big Devanagari count (for each: entity count),
  arrow on hover.
- `जारी प्रवृत्ति` section below: a `--surface` card with a table of
  the last 10 approved ingestion runs (timestamp, source, entities
  touched). Pulled from `data-service` `/v1/activity/recent` (already
  spec'd).

## 2. `/shastras` — Shastras list

- **Filter row** (sticky under nav): chips for `अनुयोग` (anuyoga,
  multi-select), dropdown for author, sort menu (नाम / गाथा संख्या /
  हाल ही में जोड़ा गया), search-within. Chips use `--accent-soft` when
  active.
- **Card grid**: 3 cols at `xl`, 2 at `md`, 1 mobile. Each card:
  - Hindi title (h3), author (sm muted), 2–3 anuyoga pills, gatha count
    big Devanagari numeral, `खोलें →` outline button at the bottom.
- **Pagination**: shadcn `Pagination` at bottom, Hindi labels (पिछला /
  अगला).

## 3. `/shastras/[nk]` — Shastra detail

- **Hero card**: full-width white surface card.
  - Left: title (h1), author (linked), anuyoga pills, source URL pill
    `मूल स्रोत →`.
  - Right: 3 stat tiles (`गाथाएँ`, `टीकाएँ`, `पृष्ठ`).
- **Tabs** (shadcn `Tabs`, underline variant in `--accent`):
  - `विषयानुक्रमणिका (Index)` — collapsible tree of adhikaars → gathas.
  - `टीकाएँ (Teekas)` — table: teekakar, publisher, year, language.
  - `गाथाएँ (Gathas)` — paginated grid of `GathaTile`s (number + first
    Hindi line, click → gatha page).
- **Right rail** (sticky on `≥ xl`): "ग्राफ में खोलें" CTA card →
  `/graph?node=<shastra_nk>` plus a tiny mini-graph thumbnail (static SVG
  preview of 1-hop neighborhood, fetched server-side).

## 4. `/shastras/[nk]/gathas/[number]` — Gatha detail

Uses **Shell C (split-reading)**.

**Reader column** (top → bottom, each its own white card):

1. **Breadcrumb + heading**: `शास्त्र › अधिकार › गाथा ३९`.
2. **Prakrit panel** — big Devanagari, `font-serif-hindi`, line-break
   preserved, gold-tinted left border 3 px in `--cat-shastra` at 40%.
   `text-h2`, line-height 1.7.
3. **Sanskrit छाया panel** (if present) — same shell, no accent border.
4. **हिन्दी हरिगीत panel** — same shell, accent border `--accent` at
   40%.
5. **शब्दार्थ panel** — word-by-word. Each Prakrit token is a click
   target; clicking opens a `TaggedTermPopover` showing the Hindi
   gloss. Hovered tokens highlight in `--accent-soft`.
6. **टीका (अमृतचंद्राचार्य)** — long Hindi anvayartha with bracketed
   terms `[…]` rendered as inline `TaggedTermPopover` triggers. The
   term highlight is `--accent` underlined.

**Sidebar column** (sticky, scroll-isolated):

- `संबंधित विषय` card: list of topic chips.
- `संबंधित कीवर्ड` card: keyword chips.
- `ग्राफ में खोलें` CTA card: large `--accent` button →
  `/graph?node=gatha:<nk>`.
- `अन्य टीकाएँ` card: list of other teekas for this gatha.

## 5. `/dictionary` — Letters index

- **Letter grid**: Devanagari letters in a 8-col grid (अ आ इ ई … ज्ञ
  श्र क्ष). Each cell:
  - 96×96 px, white surface, `--radius-md`, hover `--accent-soft`.
  - Letter in `text-display` 600 centered.
  - Small Devanagari count under the letter (`text-xs` muted).
- **Side panel** on the right (`≥ xl`): "हाल ही में जोड़े गए शब्द"
  (recently scraped keywords) — vertical list of 10 keyword rows.
- Mobile: letter grid becomes 4 cols; recent-keywords list goes below.

## 6. `/dictionary/letters/[letter]` — Letter listing

- Top: big letter h1, count caption, search-within input, alphabetical
  jumper (sub-letters with diacritics).
- List: `KeywordRow` (Hindi name + transliteration + 2–3 topic chips +
  `ChevronRight`). 12 px vertical gap, hover row bg.
- Pagination at bottom.

## 7. `/dictionary/[nk]` — Keyword detail

```
┌──────────────────────────────────────────────────────────────────┐
│ केवलज्ञान                                                           │  <- title h1
│ Kevalajnana   • aliases: निरावरण ज्ञान, सर्वज्ञता                        │
│ [स्रोत: जैनकोष  ↗]   [ग्राफ में खोलें →]                                   │
├──────────────────────────────────────────────────────────────────┤
│ सिद्धांतकोष से                                                        │  <- collapsible section
│   ▸ subsection 1 heading                                         │
│     संदर्भ: धवला 13/...                                             │
│     [Sanskrit block]  [Prakrit block]  [Hindi block]             │
│   ▸ subsection 2 heading (topic)                  [विषय खोलें →]    │
├──────────────────────────────────────────────────────────────────┤
│ संबंधित विषय                                                        │
│ <list of TopicCard>                                              │
├──────────────────────────────────────────────────────────────────┤
│ ग्राफ संबंध                                                          │
│ IS_A →     PART_OF →    RELATED_TO ↔                             │
│ <each row clickable → opens /graph?node=...>                     │
└──────────────────────────────────────────────────────────────────┘
```

- All sections are white surface cards with consistent padding.
- Long sanskrit/prakrit/hindi blocks render in the same triple-panel
  visual language as the gatha page (small variant — single column,
  thin accent border).

## 8. `/topics` — Topic browser

- Filter row: source (jainkosh / nj / chat_candidate, segmented
  control), parent keyword (autocomplete), search.
- Card grid (3 / 2 / 1 cols): each `TopicCard` = heading, parent
  keyword chip, mention-count Devanagari numeral, "विषय खोलें →".

## 9. `/topics/[nk]` — Topic detail

- Hero card: title h1, parent keyword chip (clickable), source pill,
  mention count.
- Body sections, each in its own card:
  - **विषय अंश (Extracts)** — rendered Hindi blocks, accent border.
  - **उल्लेख (Mentions)** — table-ish rows; gatha mentions link to
    gatha pages; chat-candidate mentions open in a new tab to
    cataloguesearch-chat.
  - **ग्राफ पड़ोसी (Graph neighbors)** — three columns
    (IS_A, PART_OF, RELATED), each a vertical list of nodes; clicking
    any node opens `/graph?node=...`.
- Sticky right rail (≥ xl): `ग्राफ में खोलें` red CTA + 1-hop SVG
  preview.

## 10. `/search` — Topic retrieval

- Big centered search input (auto-focused), pill-shaped, 56 px tall.
- Placeholder: `कीवर्ड लिखें जैसे "पर्याय गुण भेद"`.
- Submit button `खोजें` in `--accent`.
- Results below as numbered cards:

```
1. द्रव्य गुण पर्याय भेद                    [overlap 2/3 • score 25.0]
   matched: पर्याय, गुण
   "द्रव्य के गुण और पर्याय में भेद ..."
   mentions: pravachansaar:०९३ • cs-chunk-44231
   [विषय खोलें →]   [ग्राफ में खोलें →]
```

- Each result is a white surface card. Matched tokens highlighted in
  `--accent-soft` background. Overlap pill in `--accent`, score in
  muted caption.
- Calls `POST /v1/graphrag/topics` with `caller="public-ui"` (see
  `../07_api_query_service.md`).

## 11. `/about`

A long-form prose page in a single 720 px-wide centered column.

- Project mission (Hindi-first paragraphs).
- "Sources & acknowledgments" section: jainkosh.org, nikkyjain.github.io,
  vyakaran-vishleshan authors — each a card with name, link, license note.
- Tech-stack section (small, in English): FastAPI, Postgres, Mongo, Neo4j.

## 12. `/feedback`

Centered form (640 px wide). Fields:

- Name (optional), email (optional, validated when present).
- Type: radio group — "बग रिपोर्ट / सुझाव / सामग्री त्रुटि".
- Message (textarea, 200 char min, 4000 max).
- Optional: route/page they were on (auto-populated from `referrer`).
- Submit button in `--accent`, "भेजें (Submit)".

POSTs to `/api/feedback` (Next.js route handler → writes to
`feedback` collection in MongoDB). On success: green inline confirmation
card, NOT a toast.
