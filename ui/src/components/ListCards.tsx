import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { BadgeChip } from "@/components/BadgeChip";
import { toDevanagariNumerals } from "@/lib/format/devanagari";
import type { EntityKind } from "@/lib/types";

export interface ListCardProps {
  kind: EntityKind;
  hideBadge?: boolean;
  titleHi: string;
  titleEn?: string;
  meta?: string;
  count?: number;
  href: string;
  className?: string;
}

function BaseCard({
  kind,
  hideBadge,
  titleHi,
  titleEn,
  meta,
  count,
  href,
  className,
}: ListCardProps) {
  return (
    <Link
      href={href}
      className={cn(
        "group flex flex-col gap-3 rounded-[var(--radius-md)] border border-border bg-surface p-4",
        "shadow-node transition-shadow hover:shadow-node-hover",
        className
      )}
    >
      {(!hideBadge || count !== undefined) && (
      <div className="flex items-start justify-between gap-2">
        {!hideBadge && <BadgeChip kind={kind} size="sm" />}
        {count !== undefined && (
          <span className="font-serif-hindi text-[length:var(--font-size-h2)] font-semibold text-foreground-muted">
            {toDevanagariNumerals(count)}
          </span>
        )}
      </div>
      )}

      <div className="flex flex-1 flex-col gap-0.5">
        <span className="font-serif-hindi text-[length:var(--font-size-h3)] font-semibold leading-snug text-foreground line-clamp-2">
          {titleHi}
        </span>
        {titleEn && (
          <span className="font-sans text-[length:var(--font-size-xs)] text-foreground-muted">
            {titleEn}
          </span>
        )}
        {meta && (
          <span className="mt-1 font-sans text-[length:var(--font-size-sm)] text-foreground-muted">
            {meta}
          </span>
        )}
      </div>

      <span className="flex items-center gap-1 font-sans text-[length:var(--font-size-sm)] font-medium text-accent">
        खोलें
        <ArrowRight
          className="size-3.5 transition-transform group-hover:translate-x-0.5"
          strokeWidth={1.5}
        />
      </span>
    </Link>
  );
}

export function KeywordCard(props: ListCardProps) {
  return <BaseCard {...props} kind="keyword" />;
}

export function TopicCard(props: ListCardProps) {
  return <BaseCard {...props} kind="topic" />;
}

export function GathaTile(props: ListCardProps) {
  return <BaseCard {...props} kind="gatha" hideBadge />;
}
