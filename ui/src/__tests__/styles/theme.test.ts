import { describe, it, expect } from "vitest";
import { readFileSync } from "fs";
import { resolve } from "path";

const css = readFileSync(resolve(__dirname, "../../styles/theme.css"), "utf-8");

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
  "--cat-gatha-teeka",
  "--cat-teeka",
  "--cat-bhaavarth",
  "--cat-kalash",
  "--cat-page",
  "--cat-topic",
  "--cat-keyword",
  "--cat-publication",
  "--cat-shastra-fg",
  "--cat-gatha-fg",
  "--cat-gatha-teeka-fg",
  "--cat-teeka-fg",
  "--cat-bhaavarth-fg",
  "--cat-kalash-fg",
  "--cat-page-fg",
  "--cat-topic-fg",
  "--cat-keyword-fg",
  "--cat-publication-fg",
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
    expect(css).toContain("#6bc7be"); // --cat-topic
    expect(css).toContain("#3382ab"); // --cat-keyword
  });

  it("declares category foreground tokens with correct hex values", () => {
    expect(css).toContain("--cat-shastra-fg: #FFFFFF");
    expect(css).toContain("--cat-gatha-fg:   #1A1A1A");
    expect(css).toContain("--cat-topic-fg:   #1A1A1A");
    expect(css).toContain("--cat-keyword-fg: #1A1A1A");
  });
});
