export interface NavItem {
  labelKey: string;
  labelHi: string;
  route: string;
}

export const PRIMARY_NAV_ITEMS: NavItem[] = [
  { labelKey: "home",       labelHi: "होम",       route: "/" },
  { labelKey: "graph",      labelHi: "ग्राफ",      route: "/graph" },
  { labelKey: "dictionary", labelHi: "शब्दकोश",   route: "/dictionary" },
  { labelKey: "about",      labelHi: "परिचय",      route: "/about" },
];

export const MORE_NAV_ITEMS: NavItem[] = [
  { labelKey: "shastras",  labelHi: "शास्त्र",     route: "/shastras" },
  { labelKey: "topics",    labelHi: "विषय",         route: "/topics" },
  { labelKey: "feedback",  labelHi: "प्रतिक्रिया",  route: "/feedback" },
];

export const ALL_NAV_ITEMS: NavItem[] = [...PRIMARY_NAV_ITEMS, ...MORE_NAV_ITEMS];

/** Returns true when `pathname` belongs to the nav `route`. */
export function isNavActive(pathname: string, route: string): boolean {
  if (route === "/") return pathname === "/";
  return pathname === route || pathname.startsWith(route + "/");
}

/** Truncates `s` to at most `max` characters, appending "…" when cut. */
export function truncateLabel(s: string, max = 32): string {
  return s.length > max ? s.slice(0, max) + "…" : s;
}
