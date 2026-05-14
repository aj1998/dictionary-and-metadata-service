import { cn } from "@/lib/utils";

function SkeletonBase({ className }: { className?: string }) {
  return (
    <div
      className={cn("shimmer rounded-[var(--radius-sm)] bg-surface-muted", className)}
      aria-hidden="true"
    />
  );
}

function Card({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "rounded-[var(--radius-md)] border border-border bg-surface p-4 shadow-node",
        className
      )}
      aria-hidden="true"
    >
      <SkeletonBase className="mb-3 h-5 w-2/3" />
      <SkeletonBase className="mb-2 h-3 w-full" />
      <SkeletonBase className="h-3 w-4/5" />
    </div>
  );
}

function Row({ className }: { className?: string }) {
  return (
    <div
      className={cn("flex items-center gap-3 py-2", className)}
      aria-hidden="true"
    >
      <SkeletonBase className="h-5 w-14 shrink-0 rounded-[var(--radius-pill)]" />
      <SkeletonBase className="h-4 flex-1" />
      <SkeletonBase className="h-4 w-4 shrink-0 rounded-full" />
    </div>
  );
}

function Title({ className }: { className?: string }) {
  return (
    <div className={cn("space-y-2", className)} aria-hidden="true">
      <SkeletonBase className="h-7 w-3/4" />
      <SkeletonBase className="h-4 w-1/2" />
    </div>
  );
}

export const Skeleton = { Card, Row, Title };
