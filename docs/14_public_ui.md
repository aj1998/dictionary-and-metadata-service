# 14 — Public UI

Read-only, Hindi-first website. One Next.js app, four sections plus the admin section in `13_*`. Server-rendered for SEO / shareable URLs / Devanagari accessibility.

## Sections

| Route | Title (Hindi) | Title (English) | Backed by |
|---|---|---|---|
| `/` | होम | Home | static |
| `/shastras` | शास्त्र | Shastras | metadata-service |
| `/shastras/[nk]` | शास्त्र विवरण | Shastra detail | metadata-service + dictionary-service |
| `/shastras/[nk]/gathas/[number]` | गाथा | Gatha detail | dictionary-service |
| `/dictionary` | शब्दकोष | Dictionary | dictionary-service |
| `/dictionary/letters/[letter]` | अक्षर अनुसार | By letter | dictionary-service |
| `/dictionary/[nk]` | शब्द विवरण | Keyword detail | dictionary-service |
| `/topics` | विषय | Topics | dictionary-service |
| `/topics/[nk]` | विषय विवरण | Topic detail | dictionary-service |
| `/search` | विषय खोज | Search topics | query-service |
| `/about` | परिचय | About | static |

## Page details

### `/` — Home
- Hero with title and one-liner mission.
- Four cards linking to the four sections.
- "जारी प्रवृत्ति" (recent updates) — list of last 10 ingestion runs that produced changes (only shows after admin approval).

### `/shastras` — list
- Filters: anuyoga, author.
- Cards per shastra: title (Hindi), author, anuyoga chips, gatha count, "खोलें" button.
- Pagination.

### `/shastras/[nk]` — shastra detail
- Hero: title, author bio link, anuyogas, source URL.
- Tabs:
  - **विषयानुक्रमणिका (Index)**: adhikaars + gatha headings (links).
  - **टीकाएँ (Teekas)**: list of teekas with teekakar, publisher.
  - **गाथाएँ (Gathas)**: paginated grid.

### `/shastras/[nk]/gathas/[number]` — gatha detail
This is a high-information page. Rendered Hindi-first; switch panels (not tabs) for languages.

```
[adhikaar heading]
[gatha heading]
─────────────────────────────────────────
| गाथा (प्राकृत)                          |   <- Prakrit text in big Devanagari, with line break preserved
| जे णेव हि संजाया जे खलु णट्‌ठा भवीय पज्जया ।|
| ते होंति असब्भूदा पज्जाया णाणपच्चक्खा ॥39॥ |
─────────────────────────────────────────
| संस्कृत छाया (if present)                |
─────────────────────────────────────────
| हिन्दी हरिगीत                            |
| पर्याय जो अनुत्पन्न हैं या नष्ट जो हो गई हैं |
| असद्भावी वे सभी पर्याय ज्ञानप्रत्यक्ष हैं ॥३९॥|
─────────────────────────────────────────
| शब्दार्थ (word-by-word)                   |   <- click a Prakrit word, Hindi meaning shows in popover
─────────────────────────────────────────
| टीका (अमृतचंद्राचार्य)                     |
| <Hindi anvayartha with [terms] highlighted; click [term] for popover>
─────────────────────────────────────────
| संबंधित विषय                              |
| • भूत-भावि पर्यायें ...
─────────────────────────────────────────
| संबंधित कीवर्ड                             |
| [पर्याय]  [द्रव्य]  [ज्ञान]  ...
```

### `/dictionary` — letters index
- Devanagari letter grid (अ आ इ ई ... ज्ञ श्र क्ष). Each cell shows count.
- Recently scraped keywords side panel.

### `/dictionary/letters/[letter]` — letter listing
- Alphabetical list of keywords starting with that letter.
- Search box (filters within letter).
- Pagination.

### `/dictionary/[nk]` — keyword detail
```
केवलज्ञान   (aliases: निरावरण ज्ञान, सर्वज्ञता)

| स्रोत: जैनकोष  [Open original →]

[Section: सिद्धांतकोष से]
  ▸ subsection 1 heading
    संदर्भ: धवला पुस्तक 13/...
    [Sanskrit block]
    [Prakrit block]
    [Hindi block]
  ▸ subsection 2 heading (this is a topic)
    [Open topic page →]

संबंधित विषय:  [list of topic cards]
ग्राफ संबंध:    IS_A → ...   PART_OF → ...   RELATED_TO ↔ ...   (each clickable)
```

### `/topics` — topic browser
- Filters: source (jainkosh, nikkyjain, chat_candidate), parent keyword.
- Search.
- Cards per topic with heading, parent keyword, mention count.

### `/topics/[nk]` — topic detail
```
विषय: द्रव्य गुण पर्याय भेद
पैरेंट कीवर्ड: द्रव्य  [open]

विषय अंश (extracts):
  [rendered blocks]

उल्लेख:
  • गाथा pravachansaar:093  [open]
  • cataloguesearch चंक  cs-chunk-44231  [external link to chat search]
  ...

ग्राफ पड़ोसी:
  IS_A     → द्रव्य भेद
  PART_OF  → द्रव्य लक्षण
  RELATED  ↔ गुण-पर्याय भेद
```

### `/search` — topic retrieval
A user-facing entry point that mirrors what `cataloguesearch-chat` does internally, but for direct browsing.

```
[ Search box: type keywords like "पर्याय गुण भेद" ]   [ खोजें ]

results:
1. द्रव्य गुण पर्याय भेद                    (overlap 2/3, score 25.0)
   matched: पर्याय, गुण
   excerpt: "द्रव्य के गुण और पर्याय में भेद ..."
   mentions: pravachansaar:093, cs-chunk-44231
   [विषय खोलें →]
2. ...
```

Calls `POST /v1/graphrag/topics` with `caller="public-ui"`.

### `/about`
Static page describing the project and acknowledging sources (jainkosh, nikkyjain, vyakaran-vishleshan authors).

## Frontend stack

- Next.js 14 App Router.
- Tailwind CSS.
- `next-intl` for locale (Hindi default, English secondary).
- Devanagari font: **Noto Serif Devanagari** for body, **Noto Sans Devanagari** for UI chrome.
- Icons: lucide-react.
- Markdown rendering (for any rich-text descriptions): `react-markdown`.
- Data fetching: Server Components with `fetch` to backend services (`http://metadata-service:8001`, etc., resolved via Docker DNS).
- Client interactivity (popovers, panels): client components, no global state library needed.
- Caching: route segment `revalidate = 60` for browse pages, `revalidate = 0` (dynamic) for `/search`.

## Folder layout

```
ui/
├── app/
│   ├── layout.tsx
│   ├── page.tsx                       # /
│   ├── shastras/
│   │   ├── page.tsx
│   │   └── [nk]/
│   │       ├── page.tsx
│   │       └── gathas/[number]/page.tsx
│   ├── dictionary/
│   │   ├── page.tsx
│   │   ├── letters/[letter]/page.tsx
│   │   └── [nk]/page.tsx
│   ├── topics/
│   │   ├── page.tsx
│   │   └── [nk]/page.tsx
│   ├── search/page.tsx
│   ├── about/page.tsx
│   └── admin/...                      # see 13_*
├── lib/
│   ├── api/
│   │   ├── metadata.ts
│   │   ├── dictionary.ts
│   │   └── query.ts
│   ├── i18n/
│   │   ├── locales/hi.json
│   │   └── locales/en.json
│   └── format/
│       └── devanagari.ts              # NFC normalize before display
├── components/
│   ├── GathaPanels.tsx
│   ├── KeywordCard.tsx
│   ├── TopicCard.tsx
│   ├── TaggedTermPopover.tsx
│   └── BreadcrumbBar.tsx
├── messages/                          # next-intl messages
├── public/                            # fonts, images
└── tailwind.config.ts
```

## Performance & SEO

- All pages set `<html lang="hi">` by default.
- Each detail page exports `generateMetadata` with title, description (from heading + summary), and OpenGraph tags.
- `sitemap.ts` enumerates all keywords, topics, gathas, shastras.
- `robots.txt` allows everything except `/admin/`.
- Cache headers: `Cache-Control: public, s-maxage=300, stale-while-revalidate=600` for browse routes.

## Definition of Done

- [ ] All listed routes render against a seeded local stack with sample data.
- [ ] Hindi default; English locale switch works.
- [ ] Devanagari renders crisply on macOS, Windows, Android (Noto Serif loaded with `font-display: swap`).
- [ ] `/search` calls query-service and shows ranked topics with overlap badges.
- [ ] `/shastras/pravachansaar/gathas/039` shows Prakrit + Hindi chhand + word-by-word + anvayartha + related topics.
- [ ] sitemap.xml lists all approved entities.
- [ ] Lighthouse SEO ≥ 95 on a sample detail page.
