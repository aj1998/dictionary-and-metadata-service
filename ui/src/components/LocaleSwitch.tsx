"use client";

import { useLocale, useTranslations } from "next-intl";
import { useRouter, usePathname } from "@/i18n/navigation";
import { useSearchParams } from "next/navigation";
import { cn } from "@/lib/utils";
import type { Locale } from "@/i18n/routing";

export function LocaleSwitch({ className }: { className?: string }) {
  const locale = useLocale();
  const t = useTranslations("footer");
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  function switchLocale(next: Locale) {
    if (next === locale) return;
    document.cookie = `NEXT_LOCALE=${next};path=/;max-age=31536000;SameSite=Lax`;
    const qs = searchParams?.toString();
    const href = qs ? `${pathname}?${qs}` : pathname;
    router.replace(href, { locale: next });
  }

  return (
    <div
      className={cn(
        "flex items-center gap-1 text-xs text-foreground-muted",
        className
      )}
    >
      <button
        type="button"
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
        type="button"
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
