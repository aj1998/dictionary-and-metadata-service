import { describe, it, expect } from "vitest";
import {
  ALL_NAV_ITEMS,
  PRIMARY_NAV_ITEMS,
  MORE_NAV_ITEMS,
  isNavActive,
  truncateLabel,
} from "./nav";
import hi from "../../messages/hi.json";

// ── isNavActive ──────────────────────────────────────────────────────────────

describe("isNavActive", () => {
  it("home route matches only exact '/'", () => {
    expect(isNavActive("/", "/")).toBe(true);
    expect(isNavActive("/graph", "/")).toBe(false);
    expect(isNavActive("/dictionary/letters/क", "/")).toBe(false);
  });

  it("non-root route matches itself", () => {
    expect(isNavActive("/graph", "/graph")).toBe(true);
    expect(isNavActive("/dictionary", "/dictionary")).toBe(true);
  });

  it("non-root route matches sub-paths", () => {
    expect(isNavActive("/shastras/samaysar", "/shastras")).toBe(true);
    expect(isNavActive("/dictionary/letters/क", "/dictionary")).toBe(true);
    expect(isNavActive("/topics/ahimsa", "/topics")).toBe(true);
  });

  it("does not match unrelated routes with a common prefix", () => {
    // '/graph-preview' should NOT activate the '/graph' nav item
    expect(isNavActive("/graph-preview", "/graph")).toBe(false);
    expect(isNavActive("/dictionaries", "/dictionary")).toBe(false);
  });

  it("trailing slash edge case: sub-path must start with route + '/'", () => {
    expect(isNavActive("/graphextra", "/graph")).toBe(false);
  });

  it("locale-prefixed paths do NOT match nav routes (regression: next/navigation usePathname bug)", () => {
    // Bug: TopBar previously used next/navigation's usePathname(), which returns
    // the full locale-prefixed path (e.g. "/en/dictionary"). isNavActive then
    // compared "/en/dictionary" against "/dictionary" and returned false, so
    // the active-state pill never lit up on any /en/* route.
    // Fix: TopBar now uses next-intl's usePathname() which strips the locale prefix
    // before passing the path to isNavActive. These assertions document the contract:
    // isNavActive must receive the locale-STRIPPED path.
    expect(isNavActive("/en/dictionary", "/dictionary")).toBe(false);
    expect(isNavActive("/en/graph", "/graph")).toBe(false);
    expect(isNavActive("/en/shastras/samaysar", "/shastras")).toBe(false);
    expect(isNavActive("/en", "/")).toBe(false);

    // Locale-stripped paths (what next-intl's usePathname delivers) work correctly:
    expect(isNavActive("/dictionary", "/dictionary")).toBe(true);
    expect(isNavActive("/graph", "/graph")).toBe(true);
    expect(isNavActive("/shastras/samaysar", "/shastras")).toBe(true);
    expect(isNavActive("/", "/")).toBe(true);
  });
});

// ── truncateLabel ────────────────────────────────────────────────────────────

describe("truncateLabel", () => {
  it("returns string unchanged when at or under limit", () => {
    const s32 = "a".repeat(32);
    expect(truncateLabel(s32)).toBe(s32);
    expect(truncateLabel("short")).toBe("short");
    expect(truncateLabel("")).toBe("");
  });

  it("truncates to max characters + ellipsis when over limit", () => {
    const s33 = "a".repeat(33);
    const result = truncateLabel(s33);
    expect(result).toHaveLength(33); // 32 chars + "…" (1 char)
    expect(result.endsWith("…")).toBe(true);
    expect(result.startsWith("a".repeat(32))).toBe(true);
  });

  it("respects a custom max", () => {
    const result = truncateLabel("hello world", 5);
    expect(result).toBe("hello…");
    expect(result).toHaveLength(6);
  });

  it("does not truncate at exactly the limit", () => {
    expect(truncateLabel("12345", 5)).toBe("12345");
  });
});

// ── NAV_ITEMS structure ──────────────────────────────────────────────────────

describe("nav item data", () => {
  it("ALL_NAV_ITEMS contains exactly 7 items", () => {
    expect(ALL_NAV_ITEMS).toHaveLength(7);
  });

  it("PRIMARY_NAV_ITEMS contains exactly 4 items", () => {
    expect(PRIMARY_NAV_ITEMS).toHaveLength(4);
  });

  it("MORE_NAV_ITEMS contains exactly 3 items", () => {
    expect(MORE_NAV_ITEMS).toHaveLength(3);
  });

  it("ALL_NAV_ITEMS = PRIMARY + MORE (no overlap, no gaps)", () => {
    expect([...PRIMARY_NAV_ITEMS, ...MORE_NAV_ITEMS]).toEqual(ALL_NAV_ITEMS);
  });

  it("every item has a non-empty route starting with '/'", () => {
    for (const item of ALL_NAV_ITEMS) {
      expect(item.route).toMatch(/^\//);
    }
  });

  it("every item has a non-empty Devanagari label", () => {
    for (const item of ALL_NAV_ITEMS) {
      expect(item.labelHi.trim().length).toBeGreaterThan(0);
    }
  });

  it("routes are unique", () => {
    const routes = ALL_NAV_ITEMS.map((i) => i.route);
    expect(new Set(routes).size).toBe(routes.length);
  });

  it("every item's labelKey maps to hi.json nav.<key>", () => {
    for (const item of ALL_NAV_ITEMS) {
      const translated = (hi.nav as Record<string, string>)[item.labelKey];
      expect(
        translated,
        `hi.json nav.${item.labelKey} is missing or empty`
      ).toBeTruthy();
    }
  });

  it("home route is '/' and is in primary nav", () => {
    const home = PRIMARY_NAV_ITEMS.find((i) => i.labelKey === "home");
    expect(home?.route).toBe("/");
  });

  it("graph route is '/graph'", () => {
    const graph = ALL_NAV_ITEMS.find((i) => i.labelKey === "graph");
    expect(graph?.route).toBe("/graph");
  });
});
