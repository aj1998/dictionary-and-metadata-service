'use client';

import { useEffect } from 'react';

interface HighlightScrollIntoViewProps {
  naturalKey: string;
}

export function HighlightScrollIntoView({ naturalKey }: HighlightScrollIntoViewProps) {
  useEffect(() => {
    const el = document.querySelector(`[data-match-target="${CSS.escape(naturalKey)}"]`);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    // Pulse the enclosing panel (or the element itself) so the user can spot
    // which window the matcher landed in. The class drives a 3-cycle CSS
    // animation defined in globals.css; we strip it afterwards so the pulse
    // doesn't fire again on every re-render.
    const panel = (el.closest('section') ?? el) as HTMLElement;
    panel.classList.add('match-pulse');
    const tid = window.setTimeout(() => panel.classList.remove('match-pulse'), 4200);
    return () => {
      window.clearTimeout(tid);
      panel.classList.remove('match-pulse');
    };
  }, [naturalKey]);

  return null;
}
