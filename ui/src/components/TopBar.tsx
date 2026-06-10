"use client";

import { useState, useRef, type FormEvent } from "react";
import { useTranslations, useLocale } from "next-intl";
import { Link, usePathname, useRouter } from "@/i18n/navigation";
import {
  BookOpen,
  Search,
  Menu,
  ChevronDown,
} from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetTrigger,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import {
  type NavItem,
  PRIMARY_NAV_ITEMS as PRIMARY_ITEMS,
  MORE_NAV_ITEMS as MORE_ITEMS,
  ALL_NAV_ITEMS as ALL_ITEMS,
  isNavActive as isActive,
} from "@/lib/nav";

function NavLink({
  item,
  pathname,
  onClick,
  isHi,
}: {
  item: NavItem;
  pathname: string;
  onClick?: () => void;
  isHi: boolean;
}) {
  const t = useTranslations("nav");
  const active = isActive(pathname, item.route);
  return (
    <Link
      href={item.route}
      onClick={onClick}
      className={cn(
        "inline-flex h-9 items-center rounded-[var(--radius-pill)] px-3",
        "font-medium transition-colors",
        isHi ? "text-[length:var(--font-size-body)]" : "text-[13px]",
        active
          ? "bg-accent-soft text-foreground outline outline-1 outline-accent/30"
          : "text-foreground-muted hover:bg-surface-muted hover:text-foreground"
      )}
    >
      {t(item.labelKey)}
    </Link>
  );
}

export interface TopBarProps {
  locale?: "hi" | "en";
}

export function TopBar({}: TopBarProps) {
  const t = useTranslations("nav");
  const locale = useLocale();
  const isHi = locale === "hi";
  const pathname = usePathname();
  const router = useRouter();
  const [moreOpen, setMoreOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);

  function handleSearch(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const q = searchRef.current?.value.trim();
    if (q) router.push(`/search?q=${encodeURIComponent(q)}`);
  }

  return (
    <header className="sticky top-0 z-40 h-14 shrink-0 border-b border-border bg-surface md:h-16">
      <div className="mx-auto flex h-full max-w-[1440px] items-center gap-4 px-6">

        {/* Brand */}
        <Link href="/" className="flex shrink-0 items-center gap-2">
          <BookOpen
            className="size-6 shrink-0"
            style={{ color: "var(--accent)" }}
            strokeWidth={1.5}
          />
          <span className="hidden flex-col sm:flex">
            <span
              className={cn(
                "font-semibold leading-none text-foreground",
                isHi
                  ? "font-serif-hindi text-[length:var(--font-size-h3)]"
                  : "font-sans text-[13px] tracking-tight",
              )}
            >
              {isHi ? "जैन ज्ञान कोष" : "Jain Knowledge Base"}
            </span>
            <span
              className={cn(
                "text-foreground-muted",
                isHi ? "text-[length:var(--font-size-xs)]" : "font-serif-hindi text-[11px] leading-tight",
              )}
            >
              {isHi ? "Jain Knowledge Base" : "जैन ज्ञान कोष"}
            </span>
          </span>
        </Link>

        {/* Search */}
        <form
          onSubmit={handleSearch}
          className="mx-4 hidden flex-1 md:flex md:max-w-[360px] xl:max-w-[480px]"
        >
          <div className="relative w-full">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-foreground-subtle"
              strokeWidth={1.5}
            />
            <input
              ref={searchRef}
              type="search"
              placeholder={t("search_placeholder")}
              className={cn(
                "h-10 w-full rounded-[var(--radius-pill)] border border-border bg-background pl-9 pr-4",
                "text-[length:var(--font-size-body)] text-foreground placeholder:text-foreground-subtle",
                "transition-colors focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
              )}
            />
          </div>
        </form>

        {/* Desktop / tablet nav — spacer to push right */}
        <div className="hidden flex-1 md:block" aria-hidden="true" />

        {/* Desktop nav (≥1280px: all items; md-xl: primary + More) */}
        <nav
          aria-label="मुख्य"
          className="hidden items-center gap-1 md:flex"
        >
          {/* Always-visible primary items */}
          {PRIMARY_ITEMS.map((item) => (
            <NavLink key={item.route} item={item} pathname={pathname} isHi={isHi} />
          ))}

          {/* More dropdown (hidden at xl when all items fit) */}
          <div className="relative xl:hidden">
            <button
              type="button"
              onClick={() => setMoreOpen((o) => !o)}
              aria-expanded={moreOpen}
              aria-haspopup="menu"
              className={cn(
                "inline-flex h-9 items-center gap-1 rounded-[var(--radius-pill)] px-3.5",
                "text-[length:var(--font-size-body)] font-medium transition-colors",
                MORE_ITEMS.some((i) => isActive(pathname, i.route))
                  ? "bg-accent-soft text-foreground outline outline-1 outline-accent/30"
                  : "text-foreground-muted hover:bg-surface-muted hover:text-foreground"
              )}
            >
              {t("more")}
              <ChevronDown
                className={cn("size-3.5 transition-transform", moreOpen && "rotate-180")}
                strokeWidth={1.5}
              />
            </button>

            {moreOpen && (
              <>
                {/* Backdrop */}
                <div
                  className="fixed inset-0 z-10"
                  onClick={() => setMoreOpen(false)}
                  aria-hidden="true"
                />
                <div
                  role="menu"
                  className={cn(
                    "absolute right-0 top-full z-20 mt-1 w-40 rounded-[var(--radius-md)]",
                    "border border-border bg-surface py-1 shadow-modal"
                  )}
                >
                  {MORE_ITEMS.map((item) => (
                    <Link
                      key={item.route}
                      href={item.route}
                      role="menuitem"
                      onClick={() => setMoreOpen(false)}
                      className={cn(
                        "flex h-9 items-center px-4",
                        "text-[length:var(--font-size-body)] font-medium transition-colors",
                        isActive(pathname, item.route)
                          ? "bg-accent-soft text-foreground"
                          : "text-foreground-muted hover:bg-surface-muted hover:text-foreground"
                      )}
                    >
                      {t(item.labelKey)}
                    </Link>
                  ))}
                </div>
              </>
            )}
          </div>

          {/* All more items visible at xl+ */}
          {MORE_ITEMS.map((item) => (
            <span key={item.route} className="hidden xl:inline-flex">
              <NavLink item={item} pathname={pathname} isHi={isHi} />
            </span>
          ))}
        </nav>

        {/* Mobile: search icon + menu */}
        <div className="ml-auto flex items-center gap-2 md:hidden">
          <button
            type="button"
            aria-label={t("search_placeholder")}
            onClick={() => searchRef.current?.focus()}
            className="inline-flex size-9 items-center justify-center rounded-[var(--radius-md)] text-foreground-muted hover:bg-surface-muted"
          >
            <Search className="size-5" strokeWidth={1.5} />
          </button>

          <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
            <SheetTrigger
              aria-label={t("open_menu")}
              className="inline-flex size-9 items-center justify-center rounded-[var(--radius-md)] text-foreground-muted hover:bg-surface-muted"
            >
              <Menu className="size-5" strokeWidth={1.5} />
            </SheetTrigger>

            <SheetContent side="left" className="w-72 p-0">
              <div className="flex h-14 items-center border-b border-border px-4">
                <BookOpen
                  className="size-5 shrink-0"
                  style={{ color: "var(--accent)" }}
                  strokeWidth={1.5}
                />
                <span className={cn(
                  "ml-2 text-[length:var(--font-size-h3)] font-semibold",
                  isHi ? "font-serif-hindi" : "font-sans",
                )}>
                  {isHi ? "जैन ज्ञान कोष" : "Jain Knowledge Base"}
                </span>
              </div>

              {/* Mobile search */}
              <form
                onSubmit={(e) => {
                  handleSearch(e);
                  setSheetOpen(false);
                }}
                className="border-b border-border p-4"
              >
                <div className="relative">
                  <Search
                    className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-foreground-subtle"
                    strokeWidth={1.5}
                  />
                  <input
                    type="search"
                    placeholder={t("search_placeholder")}
                    className={cn(
                      "h-10 w-full rounded-[var(--radius-pill)] border border-border bg-background pl-9 pr-4",
                      "text-[length:var(--font-size-body)] text-foreground placeholder:text-foreground-subtle",
                      "focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/20"
                    )}
                  />
                </div>
              </form>

              <nav aria-label="मुख्य" className="p-2">
                {ALL_ITEMS.map((item) => (
                  <NavLink
                    key={item.route}
                    item={item}
                    pathname={pathname}
                    isHi={isHi}
                    onClick={() => setSheetOpen(false)}
                  />
                ))}
              </nav>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </header>
  );
}
