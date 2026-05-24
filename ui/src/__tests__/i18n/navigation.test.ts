import { vi, describe, it, expect } from "vitest";

// next-intl/navigation pulls in next/navigation at import time, which is only
// resolvable inside a Next.js runtime (not a plain Node.js test environment).
// We mock the factory so we can verify that navigation.ts correctly wires up
// and re-exports the four locale-aware primitives.
vi.mock("next-intl/navigation", () => ({
  createNavigation: () => ({
    Link: vi.fn(),
    redirect: vi.fn(),
    usePathname: vi.fn(),
    useRouter: vi.fn(),
  }),
}));

// Import AFTER the mock is registered.
import * as navigation from "@/i18n/navigation";

// Regression: TopBar previously imported Link, usePathname, useRouter from
// "next/navigation". Those are NOT locale-aware:
//   • next/navigation usePathname() returns "/en/dictionary" — isNavActive
//     compared this against "/dictionary" and returned false, so the active-
//     state pill never lit up on any /en/* route.
//   • next/navigation Link does not prepend the locale segment, so clicking a
//     nav item from /en navigated to /dictionary (Hindi) instead of /en/dictionary.
//
// Fix: src/i18n/navigation.ts wraps createNavigation(routing) from next-intl,
// which returns locale-aware versions of all four exports. TopBar now imports
// from here instead of from "next/navigation".

describe("i18n/navigation exports", () => {
  it("exports Link", () => {
    expect(navigation.Link).toBeDefined();
    expect(typeof navigation.Link).toBe("function");
  });

  it("exports redirect", () => {
    expect(navigation.redirect).toBeDefined();
    expect(typeof navigation.redirect).toBe("function");
  });

  it("exports usePathname", () => {
    expect(navigation.usePathname).toBeDefined();
    expect(typeof navigation.usePathname).toBe("function");
  });

  it("exports useRouter", () => {
    expect(navigation.useRouter).toBeDefined();
    expect(typeof navigation.useRouter).toBe("function");
  });

  it("exports exactly the four navigation primitives (no extras)", () => {
    const keys = Object.keys(navigation);
    expect(keys).toHaveLength(4);
    expect(keys).toEqual(
      expect.arrayContaining(["Link", "redirect", "usePathname", "useRouter"])
    );
  });
});
