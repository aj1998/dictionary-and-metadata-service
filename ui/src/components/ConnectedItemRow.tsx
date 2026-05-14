import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { BadgeChip } from "@/components/BadgeChip";
import type { EntityKind } from "@/lib/types";

export interface ConnectedItemRowProps {
  kind: EntityKind;
  titleHi: string;
  titleEn?: string;
  href?: string;
  onClick?: () => void;
  className?: string;
}

function RowContent({ kind, titleHi, titleEn }: Pick<ConnectedItemRowProps, "kind" | "titleHi" | "titleEn">) {
  return (
    <>
      <BadgeChip kind={kind} size="sm" className="shrink-0" />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate font-serif-hindi text-[length:var(--font-size-body)] font-medium text-foreground">
          {titleHi}
        </span>
        {titleEn && (
          <span className="truncate font-sans text-[length:var(--font-size-xs)] text-foreground-muted">
            {titleEn}
          </span>
        )}
      </span>
      <ChevronRight
        className="size-[18px] shrink-0 text-foreground-subtle transition-colors"
        strokeWidth={1.5}
      />
    </>
  );
}

export function ConnectedItemRow({
  kind,
  titleHi,
  titleEn,
  href,
  onClick,
  className,
}: ConnectedItemRowProps) {
  const sharedClass = cn(
    "group flex w-full items-center gap-3 rounded-[var(--radius-md)] border border-border p-3",
    "transition-colors hover:bg-surface-muted",
    "[&:hover_svg:last-child]:text-accent",
    className
  );

  if (href) {
    return (
      <Link href={href} className={sharedClass}>
        <RowContent kind={kind} titleHi={titleHi} titleEn={titleEn} />
      </Link>
    );
  }

  return (
    <button type="button" onClick={onClick} className={sharedClass}>
      <RowContent kind={kind} titleHi={titleHi} titleEn={titleEn} />
    </button>
  );
}
