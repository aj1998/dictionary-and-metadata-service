'use client';

import { useEffect } from 'react';

interface HighlightScrollIntoViewProps {
  // Panels to pulse (one per matched target). The first one that resolves to a
  // DOM node is also scrolled into view.
  naturalKeys: string[];
}

export function HighlightScrollIntoView({ naturalKeys }: HighlightScrollIntoViewProps) {
  const key = naturalKeys.join('|');
  useEffect(() => {
    const panels: HTMLElement[] = [];
    let scrolled = false;
    for (const nk of naturalKeys) {
      const el = document.querySelector(`[data-match-target="${CSS.escape(nk)}"]`);
      if (!el) continue;
      if (!scrolled) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        scrolled = true;
      }
      // Pulse the enclosing panel (or the element itself) so the user can spot
      // which window the matcher landed in. The class drives a 3-cycle CSS
      // animation defined in globals.css; we strip it afterwards so the pulse
      // doesn't fire again on every re-render.
      const panel = (el.closest('section') ?? el) as HTMLElement;
      panel.classList.add('match-pulse');
      panels.push(panel);
    }
    if (panels.length === 0) return;
    const tid = window.setTimeout(
      () => panels.forEach((p) => p.classList.remove('match-pulse')),
      4200,
    );
    return () => {
      window.clearTimeout(tid);
      panels.forEach((p) => p.classList.remove('match-pulse'));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return null;
}
