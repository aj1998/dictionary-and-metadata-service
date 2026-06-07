import { describe, expect, test } from "vitest";
import { CATEGORY_DATA } from "@/components/CategoryFilterList";
import type { EntityKind } from "@/lib/types";

describe("CATEGORY_DATA", () => {
  test("has exactly 11 items", () => {
    expect(CATEGORY_DATA).toHaveLength(11);
  });

  test("each item has required fields and category var prefix", () => {
    for (const item of CATEGORY_DATA) {
      expect(typeof item.kind).toBe("string");
      expect(item.labelHi.length).toBeGreaterThan(0);
      expect(item.labelEn.length).toBeGreaterThan(0);
      expect(item.catVar.startsWith("var(--cat-")).toBe(true);
    }
  });

  test("covers all 11 EntityKinds with no duplicates", () => {
    const kinds = CATEGORY_DATA.map(item => item.kind);
    const uniqueKinds = new Set(kinds);
    expect(uniqueKinds.size).toBe(11);

    const expectedKinds: EntityKind[] = ["bhaavarth", "gatha", "gatha_teeka", "kalash", "keyword", "page", "publication", "shastra", "table", "teeka", "topic"];
    expect(Array.from(uniqueKinds).sort()).toEqual(expectedKinds);
  });
});
