import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { resolve } from "path";

const css = readFileSync(resolve(__dirname, "theme.css"), "utf-8");

const REQUIRED_TOKENS = [
  "--background",
  "--surface",
  "--surface-muted",
  "--foreground",
  "--foreground-muted",
  "--foreground-subtle",
  "--border",
  "--border-strong",
  "--accent",
  "--accent-hover",
  "--accent-foreground",
  "--accent-soft",
  "--ring",
  "--success",
  "--warning",
  "--danger",
  "--graph-grid-dot",
  "--graph-edge",
  "--graph-edge-muted",
  "--node-bg",
  "--node-bg-selected",
  "--node-border",
  "--node-shadow",
  "--node-shadow-hover",
  "--cat-shastra",
  "--cat-gatha",
  "--cat-topic",
  "--cat-keyword",
  "--radius-sm",
  "--radius-md",
  "--radius-lg",
  "--radius-pill",
];

describe("theme.css token completeness", () => {
  it.each(REQUIRED_TOKENS)("declares %s", (token) => {
    expect(css).toContain(`${token}:`);
  });

  it("uses the correct accent red (#E63946)", () => {
    expect(css).toContain("#E63946");
  });

  it("uses the correct body background (#F7F7F8)", () => {
    expect(css).toContain("#F7F7F8");
  });

  it("uses the correct category colors", () => {
    expect(css).toContain("#F4A261"); // --cat-gatha
    expect(css).toContain("#2A9D8F"); // --cat-topic
    expect(css).toContain("#264653"); // --cat-keyword
  });
});
