import { describe, it, expect } from "vitest";
import { existsSync } from "fs";
import { resolve } from "path";
import { ALL_NAV_ITEMS } from "./nav";

// Regression: before the [locale] folder was introduced, every URL under
// a non-default locale (e.g. /en, /en/dictionary) returned 404. Next.js App
// Router needs a [locale] dynamic segment to capture the locale from the URL
// and route to a page component.
//
// These tests act as a manifest: if a nav route exists in nav.ts, its page
// file must exist on disk inside src/app/[locale]/. Adding a nav item without
// a matching page will fail here before it can ever reach production.

const LOCALE_DIR = resolve(__dirname, "../app/[locale]");

// Maps every nav route to its page file relative to LOCALE_DIR.
const ROUTE_TO_PAGE: Record<string, string> = {
  "/": "(content)/page.tsx",
  "/graph": "graph/page.tsx",
  "/dictionary": "(content)/dictionary/page.tsx",
  "/about": "(content)/about/page.tsx",
  "/shastras": "(content)/shastras/page.tsx",
  "/topics": "(content)/topics/page.tsx",
  "/feedback": "(content)/feedback/page.tsx",
};

describe("[locale] folder structure", () => {
  it("src/app/[locale]/ directory exists", () => {
    expect(existsSync(LOCALE_DIR)).toBe(true);
  });

  it("[locale]/layout.tsx exists (locale shell with NextIntlClientProvider)", () => {
    expect(existsSync(resolve(LOCALE_DIR, "layout.tsx"))).toBe(true);
  });

  it("every nav route has an entry in ROUTE_TO_PAGE", () => {
    for (const item of ALL_NAV_ITEMS) {
      expect(
        ROUTE_TO_PAGE[item.route],
        `No page mapping defined for nav route "${item.route}" — add it to ROUTE_TO_PAGE`
      ).toBeDefined();
    }
  });

  it("every nav route's page file exists on disk", () => {
    for (const item of ALL_NAV_ITEMS) {
      const relative = ROUTE_TO_PAGE[item.route];
      if (!relative) continue; // already caught by the test above
      const full = resolve(LOCALE_DIR, relative);
      expect(
        existsSync(full),
        `Page file missing for nav route "${item.route}": ${full}`
      ).toBe(true);
    }
  });

  it("ROUTE_TO_PAGE covers all 7 nav routes", () => {
    expect(Object.keys(ROUTE_TO_PAGE)).toHaveLength(ALL_NAV_ITEMS.length);
  });

  it("shell layouts exist for all three shells", () => {
    // Shell B (centered content)
    expect(existsSync(resolve(LOCALE_DIR, "(content)/layout.tsx"))).toBe(true);
    // Shell C (split reading)
    expect(existsSync(resolve(LOCALE_DIR, "(reading)/layout.tsx"))).toBe(true);
    // Shell A (graph — no footer)
    expect(existsSync(resolve(LOCALE_DIR, "graph/layout.tsx"))).toBe(true);
  });
});
