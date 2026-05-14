# 08 — Accessibility & Internationalization

## 1. Locale model

- **Default locale**: `hi` (Hindi). `<html lang="hi">` everywhere.
- **Secondary locale**: `en`. Toggle in the footer.
- `next-intl` handles message lookup. Messages live under
  `ui/messages/{hi,en}.json`. Devanagari source-of-truth strings live
  in `hi.json`; `en.json` carries transliterations and tooltips.
- Even when the user switches to English, **Devanagari titles
  (gatha text, shastra names, keyword headings) remain in Devanagari**.
  Only chrome labels (nav, buttons, captions) translate.

## 2. Fonts

- Use `next/font/google` for `Noto Serif Devanagari` (400/500/600/700)
  and `Inter` (400/500/600/700). Self-hosted at build time.
- `font-display: swap`. A neutral fallback (`'Mangal', 'Devanagari MT',
  serif`) covers FOUT.
- Preload only the 500 + 600 weights of Noto Serif Devanagari on
  initial HTML; rest are async.

## 3. Devanagari normalization

- All strings rendered from the DB are NFC-normalized in
  `lib/format/devanagari.ts` before display.
- All user input (search box, feedback form) is normalized on submit.

## 4. Keyboard accessibility

- Every interactive element is reachable by `Tab` in DOM order.
- Visible focus ring on every focusable element (`--ring`, 2 px, 2 px
  offset). Never `outline: none` without an explicit replacement.
- The graph canvas is focusable as a single composite widget:
  - On focus, an aria-live region announces "ज्ञान ग्राफ — N नोड्स,
    M संबंध". Arrow keys move selection to the geometrically nearest
    adjacent node. `Enter` opens the details panel; `Esc` closes it.

## 5. ARIA

| Component | ARIA |
|---|---|
| TopBar | `<nav aria-label="मुख्य">` |
| Filter list | `<fieldset>` with `<legend>विषय</legend>` |
| NodeCard | `role="button" aria-pressed={selected} aria-label="<type>: <hindi> (<english>)"` |
| Edge label | `role="button"` with `aria-label="<type> संबंध, <src> से <dst>"` |
| Details panel | `<aside role="complementary" aria-label="विवरण">` |
| TaggedTermPopover | `aria-haspopup="dialog"` on trigger; popover has `role="dialog" aria-modal="false"` |
| Toast | `role="status"` (info), `role="alert"` (error) |

## 6. Color contrast

- Every text/background pair meets WCAG AA (≥ 4.5:1 for body,
  ≥ 3:1 for large).
- The red CTA on white (`--accent` `#E63946` on `#FFFFFF`) measures
  ≈ 4.6:1 — safe.
- Category dot colors are **decorative only**; they are never the sole
  carrier of meaning. The badge always has the Hindi+English text label.

## 7. Reduced motion

When `prefers-reduced-motion: reduce`:

- Force-simulation runs to alpha 0.05 instantly (no progressive layout).
- All transitions reduced to ≤ 80 ms or removed entirely.
- The "shimmer" skeleton becomes a static `--surface-muted` block.

## 8. Screen-reader heuristics for the graph

The graph is unusable to a non-sighted reader as a force-directed canvas.
Therefore every graph page also exposes a hidden, screen-reader-only
**linear navigation tree**:

```html
<nav class="sr-only" aria-label="ग्राफ लीनियर दृश्य">
  <ul>
    <li>तत्त्वार्थसूत्र (Tattvartha Sutra) — विषय
      <ul>
        <li>आचारंगसूत्र — संबंधित</li>
        ...
      </ul>
    </li>
  </ul>
</nav>
```

The tree mirrors the visible graph and updates with the store. Each
node is a link to its detail page so a screen reader can still
"traverse" the structure without ever rendering an SVG.

## 9. Definition of done (accessibility)

- [ ] Lighthouse a11y ≥ 95 on every page.
- [ ] Tab-only walkthrough of `/graph` completes node-select + open
      details + Read More CTA.
- [ ] All Devanagari renders without missing-glyph squares on Chrome
      latest, Safari latest, Firefox latest (macOS + Windows + Android).
- [ ] `prefers-reduced-motion` disables force-sim animation.
- [ ] Locale switch persists across navigation (cookie).
