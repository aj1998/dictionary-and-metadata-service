import { describe, it, expect } from "vitest";
import { routing } from "@/i18n/routing";

// Regression suite for the locale-routing bugs discovered after Phase 3.
// Bug 1: proxy.ts was mistakenly renamed to middleware.ts (reverted — Next.js 16
//        uses proxy.ts, not middleware.ts).
// Bug 2: missing src/app/[locale]/ folder — without it, /en/* routes all 404'd
//        because Next.js App Router had no page component registered at those paths.

describe("routing config", () => {
  it("supports exactly hi and en locales", () => {
    expect(routing.locales).toContain("hi");
    expect(routing.locales).toContain("en");
    expect(routing.locales).toHaveLength(2);
  });

  it("defaults to hi locale", () => {
    expect(routing.defaultLocale).toBe("hi");
  });

  it("uses as-needed prefix — hi has no prefix, en gets /en", () => {
    // 'as-needed' means the default locale (hi) is served at / with no prefix.
    // Non-default locales get a prefix: /en, /fr, etc.
    // This is why the [locale] folder must exist: /en maps to [locale]=en.
    expect(routing.localePrefix).toBe("as-needed");
  });

  it("has localeCookie enabled for locale persistence", () => {
    expect(routing.localeCookie).toBe(true);
  });
});
