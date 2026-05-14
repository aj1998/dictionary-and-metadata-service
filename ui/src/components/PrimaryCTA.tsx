import Link from "next/link";
import { Bookmark, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export interface PrimaryCTAProps {
  labelHi: string;
  labelEn?: string;
  icon?: LucideIcon;
  href?: string;
  onClick?: () => void;
  className?: string;
}

export function PrimaryCTA({
  labelHi,
  labelEn,
  icon: Icon = Bookmark,
  href,
  onClick,
  className,
}: PrimaryCTAProps) {
  const sharedClass = cn(
    "mx-6 flex h-11 w-[calc(100%-3rem)] items-center justify-between",
    "rounded-[var(--radius-md)] bg-accent px-4",
    "transition-all hover:bg-accent-hover hover:shadow-node-hover",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:ring-offset-2",
    className
  );

  const content = (
    <>
      <span className="flex flex-col items-start">
        <span className="font-serif-hindi text-[length:var(--font-size-body)] font-semibold leading-tight text-white">
          {labelHi}
        </span>
        {labelEn && (
          <span className="font-sans text-[length:var(--font-size-xs)] text-white/80">
            {labelEn}
          </span>
        )}
      </span>
      <Icon className="size-[18px] shrink-0 text-white/90" strokeWidth={1.5} />
    </>
  );

  if (href) {
    return (
      <Link href={href} className={sharedClass}>
        {content}
      </Link>
    );
  }

  return (
    <button type="button" onClick={onClick} className={sharedClass}>
      {content}
    </button>
  );
}
