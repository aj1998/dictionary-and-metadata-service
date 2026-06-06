import { describe, it, expect } from "vitest";
import { BADGE_DEFAULT_LABELS, BADGE_CAT_CLASSES } from "@/components/BadgeChip";
import type { EntityKind } from "@/lib/types";

const KINDS: EntityKind[] = ["shastra", "gatha", "gatha_teeka", "teeka", "bhaavarth", "kalash", "page", "topic", "keyword", "publication"];

describe("BADGE_DEFAULT_LABELS", () => {
  it("covers every EntityKind", () => {
    for (const kind of KINDS) {
      expect(BADGE_DEFAULT_LABELS[kind], `missing entry for '${kind}'`).toBeDefined();
    }
  });

  it("every kind has a non-empty Hindi label", () => {
    for (const kind of KINDS) {
      expect(BADGE_DEFAULT_LABELS[kind].hi.trim().length).toBeGreaterThan(0);
    }
  });

  it("every kind has a non-empty English label", () => {
    for (const kind of KINDS) {
      expect(BADGE_DEFAULT_LABELS[kind].en.trim().length).toBeGreaterThan(0);
    }
  });

  it("Hindi labels use Devanagari script", () => {
    const devanagariRange = /[ऀ-ॿ]/;
    for (const kind of KINDS) {
      expect(
        devanagariRange.test(BADGE_DEFAULT_LABELS[kind].hi),
        `${kind}.hi is not Devanagari`
      ).toBe(true);
    }
  });

  it("spot-checks known labels", () => {
    expect(BADGE_DEFAULT_LABELS.shastra).toEqual({ hi: "शास्त्र", en: "Shastra" });
    expect(BADGE_DEFAULT_LABELS.gatha).toEqual({ hi: "गाथा", en: "Gatha" });
    expect(BADGE_DEFAULT_LABELS.topic).toEqual({ hi: "विषय", en: "Topic" });
    expect(BADGE_DEFAULT_LABELS.keyword).toEqual({ hi: "शब्द", en: "Keyword" });
  });
});

describe("BADGE_CAT_CLASSES", () => {
  it("covers every EntityKind", () => {
    for (const kind of KINDS) {
      expect(BADGE_CAT_CLASSES[kind], `missing entry for '${kind}'`).toBeDefined();
    }
  });

  it("every class starts with 'bg-cat-'", () => {
    for (const kind of KINDS) {
      expect(BADGE_CAT_CLASSES[kind]).toMatch(/^bg-cat-/);
    }
  });

  it("each kind maps to its own distinct class", () => {
    const classes = Object.values(BADGE_CAT_CLASSES);
    expect(new Set(classes).size).toBe(KINDS.length);
  });

  it("spot-checks class names", () => {
    expect(BADGE_CAT_CLASSES.shastra).toBe("bg-cat-shastra");
    expect(BADGE_CAT_CLASSES.gatha).toBe("bg-cat-gatha");
    expect(BADGE_CAT_CLASSES.topic).toBe("bg-cat-topic");
    expect(BADGE_CAT_CLASSES.keyword).toBe("bg-cat-keyword");
  });
});
