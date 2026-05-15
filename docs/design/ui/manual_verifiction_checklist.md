## Phase 4 -

### Manual UI verification checklist for phase 4 (/[locale]/graph):

1. Dotted grid renders, pans with drag, and scales correctly on zoom.
2. Node cards show all visual states (selected/faded/pinned/rest/hover behavior).
3. Edges render as Bézier with endpoint circles and midpoint pill labels.
4. Active edge uses accent styling; inactive edges use muted graph-edge color.

## Phase 5 -

### Manual UI checks for phase 5:

1. Open /en/graph and /graph; verify graph seeds when no ?node.
2. Open /graph?node=<nk>&depth=3&cat=topic; verify selected node expands and category/depth reflect URL.
3. Click a node; details panel opens with title, stats, description, related rows, CTA.
4. Click edge pill; edge details mode shows relation + source/target rows.
5. Click empty canvas; selection clears and panel closes.
6. Toggle category switches; matching nodes/edges disappear/reappear.
7. Change depth stepper; click unexpanded node; URL updates after ~500ms debounce.
8. Pin/unpin from node pin icon and verify pin state persists in current session.
9. On mobile width (<1100), verify details open as bottom sheet.
10. Inspect DOM for SR-only nav: nav[aria-label="ग्राफ लीनियर दृश्य"] contains visible-node links.

## Phase 6 -

### Manual UI verification checklist (Phase 6)
1. Open `http://localhost:3000/hi` and `http://localhost:3000/en`; verify Home hero, 4 entry cards, and recent activity table render.
2. On Home, submit the local search input; verify it routes to locale-preserved `/[locale]/search?q=...`.
3. Open `/[locale]/shastras`; verify filter row is visible, cards render, and previous/next pagination updates `?page=`.
4. Open `/[locale]/dictionary`; verify letter grid cells and recent keyword list render.
5. Click a letter cell; verify `/[locale]/dictionary/letters/[letter]` opens with keyword list and page controls.
6. Use `q` search-within on letter listing; verify list narrows and query param persists.
7. Open `/[locale]/topics`; verify source filter + search work and pagination updates.
8. Open `/[locale]/search?q=<term>`; verify ranked result cards, overlap/score pill, and both CTAs render.
9. Try `/[locale]/search?q=<gibberish>`; verify empty-state text "कोई परिणाम नहीं मिला" appears.
10. Resize at mobile (`~375px`), tablet (`~768px`), desktop (`>=1280px`) and verify the list/grid layouts reflow without overlap.

## Phase 7 -

### Manual UI verification checklist

1. Open /hi/shastras/<nk> and confirm hero card, stat tiles, teeka table, gatha cards, right rail CTA + mini graph.
2. Click a gatha from shastra detail and verify /hi/shastras/<nk>/gathas/<number> shows prakrit/sanskrit/hindi panels.
3. On gatha detail, click tagged terms in शब्दार्थ/टीका and verify popover appears with dialog semantics.
4. Verify related topics/keywords chips render in gatha sidebar and navigation links work.
5. Verify “ग्राफ में खोलें” from gatha and shastra detail opens /graph?node=....
6. Open /hi/dictionary/<nk> and verify aliases, source/graph CTAs, सिद्धांतकोष section, graph relation rows.
7. Open /hi/topics/<nk> and verify hero, extracts section, grouped neighbors (IS_A/PART_OF/RELATED_TO), right rail preview.
8. Hover mini graph preview on any detail page and verify overlay link “ग्राफ में खोलें” appears.