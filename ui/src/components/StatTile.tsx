import { cn } from "@/lib/utils";
import { toDevanagariNumerals } from "@/lib/format/devanagari";

export interface StatTileProps {
  count: number;
  label: string;
  className?: string;
}

export function StatTile({ count, label, className }: StatTileProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-start rounded-[var(--radius-md)] border border-border bg-surface p-4",
        className
      )}
    >
      <span
        className="font-serif-hindi text-[length:var(--font-size-h1)] font-semibold leading-[var(--line-height-h1)] text-foreground"
      >
        {toDevanagariNumerals(count)}
      </span>
      <span
        className="mt-0.5 font-sans text-[length:var(--font-size-xs)] font-medium uppercase tracking-widest text-foreground-muted"
      >
        {label}
      </span>
    </div>
  );
}
