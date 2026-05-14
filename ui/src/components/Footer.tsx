import { useTranslations } from "next-intl";
import Link from "next/link";
import { LocaleSwitch } from "./LocaleSwitch";

export function Footer() {
  const t = useTranslations("footer");

  return (
    <footer className="h-14 shrink-0 border-t border-border bg-surface">
      <div className="mx-auto flex h-full max-w-[1440px] items-center justify-between px-6 text-xs text-foreground-muted">
        <div className="flex items-center gap-2">
          <span>{t("copyright")}</span>
          <span className="text-foreground-subtle">v0.1.0</span>
        </div>

        <div className="flex items-center gap-4">
          <Link href="/about" className="hover:text-foreground transition-colors">
            {t("about")}
          </Link>
          <a
            href="https://jainkosh.org"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-foreground transition-colors"
          >
            jainkosh.org
          </a>
          <LocaleSwitch />
        </div>
      </div>
    </footer>
  );
}
