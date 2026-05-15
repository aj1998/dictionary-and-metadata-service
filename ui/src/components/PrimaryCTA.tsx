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
  variant?: 'primary' | 'soft';
}

export function PrimaryCTA({
  labelHi,
  labelEn,
  icon: Icon = Bookmark,
  href,
  onClick,
  className,
  variant = 'primary',
}: PrimaryCTAProps) {
  const isSoft = variant === 'soft';

  const sharedClass = cn(
    "mx-6 flex h-11 w-[calc(100%-3rem)] items-center justify-between",
    "rounded-[var(--radius-md)] px-4",
    "transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:ring-offset-2",
    isSoft
      ? "bg-accent-soft text-accent border border-accent/30 hover:bg-accent/10"
      : "bg-accent hover:bg-accent-hover hover:shadow-node-hover",
    className
  );

  const textColor = isSoft ? "text-accent" : "text-white";
  const subColor = isSoft ? "text-accent/80" : "text-white/80";
  const iconColor = isSoft ? "text-accent" : "text-white/90";

  const content = (
    <>
      <span className="flex flex-col items-start">
        <span className={cn("font-serif-hindi text-[length:var(--font-size-body)] font-semibold leading-tight", textColor)}>
          {labelHi}
        </span>
        {labelEn && (
          <span className={cn("font-sans text-[length:var(--font-size-xs)]", subColor)}>
            {labelEn}
          </span>
        )}
      </span>
      <Icon className={cn("size-[18px] shrink-0", iconColor)} strokeWidth={1.5} />
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
