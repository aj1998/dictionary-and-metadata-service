import { describe, expect, test } from "vitest";
import { NODE_KIND_META, EXPAND_ARIA_LABEL, DETAILS_ARIA_LABEL } from "@/components/NodeCard";
import type { EntityKind } from "@/lib/types";

describe("NODE_KIND_META", () => {
  test("covers all entity kinds", () => {
    const keys = Object.keys(NODE_KIND_META).sort();
    const expected: EntityKind[] = ["bhaavarth", "gatha", "kalash", "keyword", "page", "shastra", "teeka", "topic"];
    expect(keys).toEqual(expected);
  });

  test("has non-empty labels, category vars, and icon components", () => {
    for (const entry of Object.values(NODE_KIND_META)) {
      expect(entry.labelHi.length).toBeGreaterThan(0);
      expect(entry.labelEn.length).toBeGreaterThan(0);
      expect(entry.catVar.startsWith("var(--cat-")).toBe(true);
      const renderable =
        typeof entry.Icon === "function" ||
        (typeof entry.Icon === "object" && entry.Icon !== null && "$$typeof" in entry.Icon);
      expect(renderable).toBe(true);
    }
  });

  test("matches shastra spot-check values", () => {
    expect(NODE_KIND_META.shastra.labelHi).toBe("शास्त्र");
    expect(NODE_KIND_META.shastra.catVar).toBe("var(--cat-shastra)");
  });
});

describe("expand/collapse button constants", () => {
  test("EXPAND_ARIA_LABEL is the Hindi label for expand", () => {
    expect(EXPAND_ARIA_LABEL).toBe('इस नोड से ग्राफ़ का विस्तार करें');
  });

  test("DETAILS_ARIA_LABEL is the Hindi label for open details", () => {
    expect(DETAILS_ARIA_LABEL).toBe('विवरण देखें');
  });
});

describe("Section 3 — full-band color coding", () => {
  test("all four kinds expose a non-empty bandFg field", () => {
    for (const entry of Object.values(NODE_KIND_META)) {
      expect(entry.bandFg).toBeTruthy();
      expect(typeof entry.bandFg).toBe('string');
    }
  });

  test("bandFg references the correct CSS variable per kind", () => {
    expect(NODE_KIND_META.shastra.bandFg).toBe('var(--cat-shastra-fg)');
    expect(NODE_KIND_META.gatha.bandFg).toBe('var(--cat-gatha-fg)');
    expect(NODE_KIND_META.topic.bandFg).toBe('var(--cat-topic-fg)');
    expect(NODE_KIND_META.keyword.bandFg).toBe('var(--cat-keyword-fg)');
  });
});
