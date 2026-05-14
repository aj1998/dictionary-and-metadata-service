import { describe, it, expect } from "vitest";
import {
  toDevanagariNumerals,
  normalizeNFC,
  minGraphemeLength,
} from "./devanagari";

describe("toDevanagariNumerals", () => {
  it("converts each ASCII digit to its Devanagari counterpart", () => {
    expect(toDevanagariNumerals(0)).toBe("०");
    expect(toDevanagariNumerals(1)).toBe("१");
    expect(toDevanagariNumerals(9)).toBe("९");
  });

  it("converts multi-digit numbers", () => {
    expect(toDevanagariNumerals(357)).toBe("३५७");
    expect(toDevanagariNumerals(1000)).toBe("१०००");
  });

  it("handles zero", () => {
    expect(toDevanagariNumerals(0)).toBe("०");
  });

  it("handles large numbers", () => {
    expect(toDevanagariNumerals(1234567890)).toBe("१२३४५६७८९०");
  });
});

describe("normalizeNFC", () => {
  it("returns an NFC-normalized string", () => {
    // NFD decomposed 'ā' (a + combining macron) → NFC precomposed
    const nfd = "ā"; // 'a' + combining macron = ā in NFD
    const nfc = "ā";       // precomposed ā
    expect(normalizeNFC(nfd)).toBe(nfc);
  });

  it("is idempotent on already-NFC strings", () => {
    const s = "जैन ज्ञान कोष";
    expect(normalizeNFC(s)).toBe(s);
  });

  it("passes through ASCII unchanged", () => {
    expect(normalizeNFC("hello")).toBe("hello");
  });
});

describe("minGraphemeLength", () => {
  it("counts ASCII characters as individual graphemes", () => {
    expect(minGraphemeLength("hello")).toBe(5);
  });

  it("counts a Devanagari conjunct as one grapheme", () => {
    // 'ज्ञ' is a conjunct (ज + ् + ञ) — 3 code points but 1 grapheme
    expect(minGraphemeLength("ज्ञ")).toBe(1);
  });

  it("counts graphemes in a mixed Devanagari string", () => {
    // 'कोश' = क + ो + श = 3 code points but how many graphemes depends on segmentation
    // 'को' is one grapheme (क with vowel sign ो), 'श' is one — total 2
    expect(minGraphemeLength("कोश")).toBe(2);
  });

  it("returns 0 for an empty string", () => {
    expect(minGraphemeLength("")).toBe(0);
  });
});
