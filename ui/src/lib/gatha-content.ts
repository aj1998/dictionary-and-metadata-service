export type TeekaPart = { type: 'text' | 'term'; value: string };

export function extractBracketTerms(text: string): string[] {
  const matches = text.match(/\[([^\]]+)\]/g) ?? [];
  const unique = new Set<string>();
  for (const match of matches) {
    const term = match.slice(1, -1).trim();
    if (term) unique.add(term);
  }
  return [...unique];
}

export function splitTeekaByBracketTerms(text: string): TeekaPart[] {
  const parts: TeekaPart[] = [];
  const pattern = /\[([^\]]+)\]/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = pattern.exec(text)) !== null) {
    const start = match.index;
    const end = pattern.lastIndex;

    if (start > lastIndex) {
      parts.push({ type: 'text', value: text.slice(lastIndex, start) });
    }

    const term = match[1]?.trim();
    if (term) {
      parts.push({ type: 'term', value: term });
    }

    lastIndex = end;
  }

  if (lastIndex < text.length) {
    parts.push({ type: 'text', value: text.slice(lastIndex) });
  }

  return parts;
}
