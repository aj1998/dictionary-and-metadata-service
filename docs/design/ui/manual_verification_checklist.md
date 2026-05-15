# Manual Verification Checklist — Phase 8

Run these checks after Phase 8 is deployed. The app must be running (`pnpm dev` or production build) with all four backend services live.

---

## 8.1 — About page (`/about`)

- [ ] Page loads at `/about` (and `/en/about`) without errors.
- [ ] Title "परिचय" renders in Noto Serif Devanagari at `text-h1` size.
- [ ] All three mission paragraphs are visible in Hindi/Devanagari.
- [ ] "स्रोत और आभार" section shows three source cards.
- [ ] jainkosh.org and nikkyjain.github.io links open in a new tab.
- [ ] Tech stack line ("FastAPI · PostgreSQL · …") renders in small muted English.
- [ ] Page is max 720px wide and centered on desktop.
- [ ] No horizontal scroll on mobile (375px viewport).

---

## 8.2 — Feedback form (`/feedback`)

### Form rendering
- [ ] Form renders at max 640px wide, centered.
- [ ] All four fields visible: नाम, ईमेल, प्रकार (radio group), संदेश.
- [ ] Three radio buttons render: "बग रिपोर्ट", "सुझाव", "सामग्री त्रुटि".
- [ ] Char counter below the message textarea shows Devanagari numerals (e.g. "०/४०००").
- [ ] Submit button reads "भेजें (Submit)" in accent red on white text.

### Validation
- [ ] Submit with empty type → inline Hindi error below the radio group.
- [ ] Submit with message < 200 chars → inline error below textarea.
- [ ] Enter invalid email (e.g. "notanemail") and blur field → inline error "कृपया एक वैध ईमेल पता दर्ज करें।" appears.
- [ ] Fix email → error disappears.
- [ ] Message counter updates as you type.

### Submission
- [ ] With MongoDB running locally: fill name + type + message (≥200 chars) → click submit → green inline card appears: "धन्यवाद! आपकी प्रतिक्रिया मिल गई."
- [ ] Record appears in MongoDB `jain_kb.feedback` collection.
- [ ] With MongoDB down: submit → inline error "कुछ गड़बड़ी हुई। कृपया पुनः प्रयास करें।" (no toast, no crash).

---

## 8.3 — ARIA completeness

Open Chrome DevTools → Accessibility panel. Check each component:

- [ ] **TopBar**: `<nav aria-label="मुख्य">` — confirmed in Accessibility tree.
- [ ] **CategoryFilterList**: `<fieldset>` with `<legend>विषय</legend>` visible in Accessibility tree on `/graph`.
- [ ] **NodeCard**: each card node has `role="button"`, `aria-pressed` (false/true), and an `aria-label` like `"Shastra: तत्त्वार्थसूत्र"`.
- [ ] **RelationConnector**: edge groups have `role="button"` and an `aria-label`.
- [ ] **DetailsPanel desktop** (`>= 1280px`): the right panel is an `<aside role="complementary" aria-label="विवरण">`.
- [ ] **TaggedTermPopover**: trigger has `aria-haspopup="dialog"`; popover has `role="dialog" aria-modal="false"`.

---

## 8.4 — Focus ring

Tab through the following pages and verify every focused element shows a visible ring (2px, `--ring` color, 2px offset):

- [ ] `/` (Home) — search input, entry cards, activity rows.
- [ ] `/graph` — `NodeCard` elements receive focus ring when tab-focused (not just clicked).
- [ ] `/feedback` — all inputs, radio buttons, textarea, submit button.
- [ ] `/about` — links to jainkosh.org and nikkyjain.github.io.
- [ ] Confirm: no element shows `outline: none` without a replacement ring.

---

## 8.5 — prefers-reduced-motion

In Chrome DevTools → Rendering → Emulate CSS media feature → set `prefers-reduced-motion: reduce`:

- [ ] Navigate to `/graph`. The force simulation settles instantly (no visible animation of nodes spreading out).
- [ ] Skeleton blocks (if visible during loading) render as static `--surface-muted` blocks without shimmer.
- [ ] All transitions complete in ≤ 80ms (no slow slides or fades).
- [ ] DetailsPanel still opens and closes (just without the 200ms slide animation).

---

## 8.6 — Devanagari rendering (cross-browser)

Test the following URL on each browser/OS combination:
- `/shastras/[any-nk]` (gatha detail with Prakrit text)
- `/dictionary/[any-nk]` (keyword with Sanskrit/Prakrit blocks)
- `/feedback` (Devanagari labels and error messages)

Browsers/OS:
- [ ] Chrome latest — macOS
- [ ] Safari latest — macOS
- [ ] Firefox latest — macOS
- [ ] Chrome — Windows 11
- [ ] Safari — iOS (any recent version)
- [ ] Chrome — Android (any recent version)

For each: confirm no missing-glyph boxes (□ or ◌), text renders in Noto Serif Devanagari, fallback font is readable when Noto hasn't loaded.

---

## 8.7 — Locale switch end-to-end

- [ ] Navigate to `/` in Hindi.
- [ ] Click the `हिन्दी / English` toggle in the Footer → page reloads at `/en/`.
- [ ] Nav labels, button labels, captions translate to English.
- [ ] Devanagari titles (gatha text, shastra names, keyword headings) **remain in Devanagari**.
- [ ] Navigate to `/en/shastras` — page loads correctly.
- [ ] Reload browser — locale remains `en` (cookie persists).
- [ ] Switch back to Hindi → nav returns to Devanagari labels.
- [ ] Verify locale cookie `NEXT_LOCALE=en` (or `hi`) is set in DevTools → Application → Cookies.

---

## 8.8 — Lighthouse a11y score (target ≥ 95)

Run `pnpm lighthouse` (or Chrome DevTools Lighthouse) in incognito mode (no extensions) against each route:

| Route | Target | Result |
|-------|--------|--------|
| `/` | ≥ 95 | |
| `/graph` | ≥ 95 | |
| `/shastras` | ≥ 95 | |
| `/shastras/[nk]` | ≥ 95 | |
| `/shastras/[nk]/gathas/[number]` | ≥ 95 | |
| `/dictionary` | ≥ 95 | |
| `/dictionary/[nk]` | ≥ 95 | |
| `/topics` | ≥ 95 | |
| `/topics/[nk]` | ≥ 95 | |
| `/search` | ≥ 95 | |
| `/about` | ≥ 95 | |
| `/feedback` | ≥ 95 | |

Common a11y failures to watch for: missing `alt` on `<img>`, buttons without accessible name, color contrast < 4.5:1, missing `<label>` on inputs.

---

## 8.9 — Final visual review

Open `docs/design/ui/ux_template_images/overall_theme_and_panels.png` and `navigation_and_graph_look.png` side by side with the running app. Verify:

- [ ] Red-on-white palette matches — accent `#E63946`, body background `#F7F7F8`.
- [ ] Whitespace is generous; borders are slim (1px `--border`).
- [ ] Graph canvas shows dotted grid and rounded white card nodes.
- [ ] `NodeCard` selected state: fills red, text turns white, no category stripe.
- [ ] `DetailsPanel` right panel matches the panel in `overall_theme_and_panels.png`.
- [ ] Nav-bar active route: pill background `--accent-soft`, outline 30% alpha.
- [ ] `/about` and `/feedback` pages feel consistent with other Shell B pages (same card style, same typography scale).
- [ ] Feedback success card is green (not red), inline (not a toast/overlay).

---

## Keyboard-only tab walkthrough — graph page

Tab through `/graph` using only keyboard (no mouse):

- [ ] Tab reaches the TopBar nav items → active route is announced.
- [ ] Tab reaches a `NodeCard` → press Enter → DetailsPanel opens.
- [ ] Tab into DetailsPanel → connected item rows reachable.
- [ ] Tab to "View All Connections →" button → press Enter → graph expands.
- [ ] Tab to "पूरा वर्णन पढ़ें" CTA → press Enter → DefinitionModal opens.
- [ ] Press Escape → DetailsPanel closes.
- [ ] Tab reaches ZoomControls (+, −, fit) → each works with Enter.
- [ ] Confirm the `sr-only` linear navigation tree is present in DOM (DevTools → Elements, search for `aria-label="ग्राफ लीनियर दृश्य"`).
