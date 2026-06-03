'use client';

import { useEffect, useState } from 'react';
import { getShastras } from '@/lib/api/metadata';
import { normalizeNFC } from '@/lib/format/devanagari';

// Module-level cache so every consumer in the page shares one network round-trip
// for the set of ingested shastra natural keys. Resets on full reload.
let cachedPromise: Promise<Set<string>> | null = null;

// Server caps `/v1/shastras?limit` at 200 (see core_service `_limit_offset`),
// so requesting more than that fails validation. Paginate in 200-sized chunks
// until we've drained the total count.
const REGISTRY_PAGE_SIZE = 200;
// Safety bound on the number of pages to prevent an infinite loop on a
// malformed server response.
const MAX_REGISTRY_PAGES = 50;

export function loadIngestedShastras(): Promise<Set<string>> {
  if (cachedPromise) return cachedPromise;
  cachedPromise = (async () => {
    const set = new Set<string>();
    let offset = 0;
    for (let i = 0; i < MAX_REGISTRY_PAGES; i++) {
      const page = await getShastras({ limit: REGISTRY_PAGE_SIZE, offset });
      for (const s of page.items) {
        // NFC-normalize so a Devanagari natural key with combining marks
        // compares equal to the parsed `ref.shastra_name`, which is also
        // NFC-normalized at parse time.
        if (s.natural_key) set.add(normalizeNFC(s.natural_key));
      }
      offset += page.items.length;
      const total = page.pagination?.total ?? offset;
      if (page.items.length === 0 || offset >= total) break;
    }
    return set;
  })().catch((err) => {
    // Reset the cache on failure so subsequent consumers can retry on next
    // mount instead of being stuck with the rejection forever.
    cachedPromise = null;
    throw err;
  });
  return cachedPromise;
}

// For tests: clears the module-level cache so each case starts fresh.
export function _resetIngestedShastrasForTest(): void {
  cachedPromise = null;
}

export interface UseIngestedShastrasResult {
  shastras: Set<string> | null;
  loading: boolean;
}

// Loads the ingested-shastras set once and shares it across all consumers via
// the module cache. Returns `null` while the request is in-flight (or has
// failed), and the resolved set once available.
export function useIngestedShastras(): UseIngestedShastrasResult {
  const [shastras, setShastras] = useState<Set<string> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loadIngestedShastras()
      .then((set) => {
        if (!cancelled) setShastras(set);
      })
      .catch(() => {
        // Swallow errors — callers treat `null` as "unknown" and suppress the
        // fallback grey link, which is the safe default on registry failure.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { shastras, loading };
}
