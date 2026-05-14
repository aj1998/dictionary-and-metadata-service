"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";

export function LocaleSwitch({ className }: { className?: string }) {
  const locale = useLocale();
  const t = useTranslations("footer");
  const router = useRouter();

  function switchLocale(next: string) {
    document.cookie = `NEXT_LOCALE=${next};path=/;max-age=31536000;SameSite=Lax`;
    router.refresh();
  }

  return (
    <div
      className={cn(
        "flex items-center gap-1 text-xs text-foreground-muted",
        className
      )}
    >
      <button
        onClick={() => switchLocale("hi")}
        className={cn(
          "rounded px-1.5 py-0.5 transition-colors",
          locale === "hi"
            ? "font-semibold text-foreground"
            : "hover:text-foreground"
        )}
      >
        {t("switch_locale_hi")}
      </button>
      <span aria-hidden="true">/</span>
      <button
        onClick={() => switchLocale("en")}
        className={cn(
          "rounded px-1.5 py-0.5 transition-colors",
          locale === "en"
            ? "font-semibold text-foreground"
            : "hover:text-foreground"
        )}
      >
        {t("switch_locale_en")}
      </button>
    </div>
  );
}
