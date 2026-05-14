import { describe, expect, test } from "vitest";
import { NODE_KIND_META } from "./NodeCard";
import type { EntityKind } from "@/lib/types";

describe("NODE_KIND_META", () => {
  test("covers all 4 entity kinds", () => {
    const keys = Object.keys(NODE_KIND_META).sort();
    const expected: EntityKind[] = ["gatha", "keyword", "shastra", "topic"];
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
