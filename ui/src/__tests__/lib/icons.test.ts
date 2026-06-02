import { describe, it, expect } from "vitest";
import * as icons from "@/lib/icons";

// Every icon in the reserved set from 01_design_system.md §6
const RESERVED_ICONS = [
  "Search",
  "Home",
  "Network",
  "BookOpen",
  "Tag",
  "ScrollText",
  "BookMarked",
  "BookText",
  "NotebookText",
  "Flower2",
  "FileText",
  "Sparkles",
  "LayoutList",
  "Info",
  "Bookmark",
  "ArrowRight",
  "ChevronRight",
  "Plus",
  "Minus",
  "Maximize2",
  "X",
  "Pin",
  "Menu",
  "Loader2",
] as const;

describe("icons registry", () => {
  it("exports every reserved icon from 01_design_system.md §6", () => {
    for (const name of RESERVED_ICONS) {
      expect(icons[name], `'${name}' is not exported from icons.ts`).toBeDefined();
    }
  });

  it("every exported icon is a renderable React component (function or forwardRef object)", () => {
    for (const name of RESERVED_ICONS) {
      const icon = icons[name];
      const renderable =
        typeof icon === "function" ||
        (typeof icon === "object" && icon !== null && "$$typeof" in icon);
      expect(renderable, `'${name}' is not a renderable React component`).toBe(true);
    }
  });

  it("exports exactly the reserved set — no extra icons", () => {
    const exported = Object.keys(icons);
    expect(new Set(exported)).toEqual(new Set(RESERVED_ICONS));
  });
});
