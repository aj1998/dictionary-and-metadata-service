import Link from "next/link";
import { cn } from "@/lib/utils";
import { truncateLabel as truncate } from "@/lib/nav";

export interface BreadcrumbSegment {
  label: string;
  href?: string;
}

interface BreadcrumbBarProps {
  segments: BreadcrumbSegment[];
  className?: string;
}

export function BreadcrumbBar({ segments, className }: BreadcrumbBarProps) {
  return (
    <nav
      aria-label="Breadcrumb"
      className={cn(
        "flex items-center gap-1.5 text-[length:var(--font-size-sm)] text-foreground-muted",
        className
      )}
    >
      {segments.map((seg, i) => {
        const isLast = i === segments.length - 1;
        const label = truncate(seg.label);

        return (
          <span key={i} className="flex items-center gap-1.5">
            {i > 0 && (
              <span aria-hidden="true" className="text-foreground-subtle">
                ›
              </span>
            )}
            {isLast || !seg.href ? (
              <span
                className={cn(isLast && "font-semibold text-foreground")}
                aria-current={isLast ? "page" : undefined}
              >
                {label}
              </span>
            ) : (
              <Link
                href={seg.href}
                className="hover:text-foreground transition-colors"
              >
                {label}
              </Link>
            )}
          </span>
        );
      })}
    </nav>
  );
}
