import { cn } from "@/lib/utils";
import type { EntityKind } from "@/lib/types";

export const BADGE_DEFAULT_LABELS: Record<EntityKind, { hi: string; en: string }> = {
  shastra:     { hi: "शास्त्र",  en: "Shastra" },
  gatha:       { hi: "गाथा",    en: "Gatha" },
  gatha_teeka: { hi: "गाथा टीका", en: "GathaTeeka" },
  teeka:       { hi: "टीका",    en: "Teeka" },
  bhaavarth:   { hi: "भावार्थ", en: "Bhaavarth" },
  kalash:      { hi: "कलश",    en: "Kalash" },
  page:        { hi: "पृष्ठ",   en: "Page" },
  topic:       { hi: "विषय",   en: "Topic" },
  keyword:     { hi: "शब्द",   en: "Keyword" },
  publication: { hi: "प्रकाशन", en: "Publication" },
};

export const BADGE_CAT_CLASSES: Record<EntityKind, string> = {
  shastra:     "bg-cat-shastra",
  gatha:       "bg-cat-gatha",
  gatha_teeka: "bg-cat-gatha-teeka",
  teeka:       "bg-cat-teeka",
  bhaavarth:   "bg-cat-bhaavarth",
  kalash:      "bg-cat-kalash",
  page:        "bg-cat-page",
  topic:       "bg-cat-topic",
  keyword:     "bg-cat-keyword",
  publication: "bg-cat-publication",
};

export interface BadgeChipProps {
  kind: EntityKind;
  size?: "sm" | "md";
  labelHi?: string;
  labelEn?: string;
  className?: string;
}

export function BadgeChip({
  kind,
  size = "md",
  labelHi,
  labelEn,
  className,
}: BadgeChipProps) {
  const { hi: defaultHi, en: defaultEn } = BADGE_DEFAULT_LABELS[kind];
  const hi = labelHi ?? defaultHi;
  const en = labelEn ?? defaultEn;

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-[var(--radius-pill)] px-2.5",
        "font-sans text-[length:var(--font-size-xs)] font-semibold tracking-wide text-white",
        BADGE_CAT_CLASSES[kind],
        size === "md" ? "h-[22px]" : "h-[18px]",
        className
      )}
    >
      {hi}
      <span className="opacity-70">&nbsp;/ {en}</span>
    </span>
  );
}
