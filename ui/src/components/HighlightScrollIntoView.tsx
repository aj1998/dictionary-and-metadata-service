'use client';

import { useEffect } from 'react';

interface HighlightScrollIntoViewProps {
  naturalKey: string;
}

export function HighlightScrollIntoView({ naturalKey }: HighlightScrollIntoViewProps) {
  useEffect(() => {
    const el = document.querySelector(`[data-match-target="${CSS.escape(naturalKey)}"]`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [naturalKey]);

  return null;
}
