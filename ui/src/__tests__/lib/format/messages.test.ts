import { describe, it, expect } from "vitest";
import hi from "../../../../messages/hi.json";
import en from "../../../../messages/en.json";

type JsonValue = string | number | boolean | null | JsonObject | JsonValue[];
type JsonObject = { [key: string]: JsonValue };

function collectLeafKeys(obj: JsonObject, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) => {
    const full = prefix ? `${prefix}.${k}` : k;
    return v !== null && typeof v === "object" && !Array.isArray(v)
      ? collectLeafKeys(v as JsonObject, full)
      : [full];
  });
}

describe("i18n message files", () => {
  const hiKeys = new Set(collectLeafKeys(hi as JsonObject));
  const enKeys = new Set(collectLeafKeys(en as JsonObject));

  it("hi.json has no keys missing from en.json", () => {
    const missing = [...hiKeys].filter((k) => !enKeys.has(k));
    expect(missing, `Keys in hi.json but not in en.json: ${missing.join(", ")}`).toHaveLength(0);
  });

  it("en.json has no keys missing from hi.json", () => {
    const missing = [...enKeys].filter((k) => !hiKeys.has(k));
    expect(missing, `Keys in en.json but not in hi.json: ${missing.join(", ")}`).toHaveLength(0);
  });

  it("neither file is empty", () => {
    expect(hiKeys.size).toBeGreaterThan(0);
    expect(enKeys.size).toBeGreaterThan(0);
  });
});
