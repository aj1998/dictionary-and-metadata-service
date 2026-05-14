'use client';

import { Plus, Minus, Maximize2 } from '@/lib/icons';
import { cn } from '@/lib/utils';

interface ZoomControlsProps {
  onZoomIn(): void;
  onZoomOut(): void;
  onFit(): void;
  className?: string;
}

const BUTTONS = [
  { Icon: Plus,      labelHi: 'ज़ूम इन',          action: 'in'  },
  { Icon: Minus,     labelHi: 'ज़ूम आउट',         action: 'out' },
  { Icon: Maximize2, labelHi: 'कैनवास फ़िट करें', action: 'fit' },
] as const;

export function ZoomControls({ onZoomIn, onZoomOut, onFit, className }: ZoomControlsProps) {
  const handlers: Record<string, () => void> = { in: onZoomIn, out: onZoomOut, fit: onFit };

  return (
    <div
      className={cn('absolute bottom-4 left-4 flex flex-col gap-1', className)}
      aria-label="ज़ूम नियंत्रण"
    >
      {BUTTONS.map(({ Icon, labelHi, action }) => (
        <button
          key={action}
          type="button"
          aria-label={labelHi}
          onClick={handlers[action]}
          className={cn(
            'flex h-9 w-9 items-center justify-center rounded-lg border border-border',
            'bg-surface text-foreground-muted shadow-[var(--node-shadow)]',
            'transition-colors hover:bg-surface-muted hover:text-foreground',
          )}
        >
          <Icon size={16} strokeWidth={1.5} />
        </button>
      ))}
    </div>
  );
}
