import { describe, expect, test } from "vitest";
import { CATEGORY_DATA } from "./CategoryFilterList";
import type { EntityKind } from "@/lib/types";

describe("CATEGORY_DATA", () => {
  test("has exactly 4 items", () => {
    expect(CATEGORY_DATA).toHaveLength(4);
  });

  test("each item has required fields and category var prefix", () => {
    for (const item of CATEGORY_DATA) {
      expect(typeof item.kind).toBe("string");
      expect(item.labelHi.length).toBeGreaterThan(0);
      expect(item.labelEn.length).toBeGreaterThan(0);
      expect(item.catVar.startsWith("var(--cat-")).toBe(true);
    }
  });

  test("covers all 4 EntityKinds with no duplicates", () => {
    const kinds = CATEGORY_DATA.map(item => item.kind);
    const uniqueKinds = new Set(kinds);
    expect(uniqueKinds.size).toBe(4);

    const expectedKinds: EntityKind[] = ["gatha", "keyword", "shastra", "topic"];
    expect(Array.from(uniqueKinds).sort()).toEqual(expectedKinds);
  });
});
