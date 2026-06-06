import { describe, expect, test } from "vitest";
import { EDGE_LABELS, EDGE_TOOLTIPS } from "@/components/RelationConnector";
import type { EdgeKind } from "@/lib/types";

describe("RelationConnector edge metadata", () => {
  test("EDGE_LABELS has exactly all 13 EdgeKind keys", () => {
    const keys = Object.keys(EDGE_LABELS).sort();
    const expected: EdgeKind[] = [
      "ALIAS_OF",
      "CONTAINS_DEFINITION",
      "HAS_PUBLICATION",
      "HAS_TEEKA",
      "HAS_TOPIC",
      "IN_PUBLICATION",
      "IN_SHASTRA",
      "IN_TEEKA",
      "IS_A",
      "MENTIONS_KEYWORD",
      "MENTIONS_TOPIC",
      "PART_OF",
      "RELATED_TO",
    ];
    expect(keys).toEqual(expected);
  });

  test("EDGE_TOOLTIPS keys match EDGE_LABELS keys exactly", () => {
    const labelKeys = Object.keys(EDGE_LABELS).sort();
    const tooltipKeys = Object.keys(EDGE_TOOLTIPS).sort();
    expect(tooltipKeys).toEqual(labelKeys);
  });

  test("all labels and tooltips are non-empty strings", () => {
    for (const value of Object.values(EDGE_LABELS)) {
      expect(typeof value).toBe("string");
      expect(value.length).toBeGreaterThan(0);
    }
    for (const value of Object.values(EDGE_TOOLTIPS)) {
      expect(typeof value).toBe("string");
      expect(value.length).toBeGreaterThan(0);
    }
  });

  test("matches expected spot-check labels", () => {
    expect(EDGE_LABELS.IS_A).toBe("है का प्रकार");
    expect(EDGE_LABELS.RELATED_TO).toBe("संबंधित");
  });
});
