'use client';

import { useEffect, useState } from 'react';
import { getShastraPdfOffsets, type OffsetSpec } from '@/lib/api/metadata';
import type { DefinitionReference } from '@/lib/types';

export function extractOriginalShastraInfo(
  ref: DefinitionReference,
): { publishedPage: number; pustak: string | null } | null {
  let publishedPage: number | null = null;
  let pustak: string | null = null;
  for (const { field, value } of ref.resolved_fields) {
    if (field === 'पृष्ठ') {
      const str = String(value);
      const n = parseInt(
        str.replace(/[०-९]/g, (d) => String('०१२३४५६७८९'.indexOf(d))).trim(),
        10,
      );
      if (!Number.isNaN(n)) publishedPage = n;
    } else if (field === 'पुस्तक') {
      pustak = String(value).trim();
    }
  }
  if (publishedPage === null) return null;
  return { publishedPage, pustak };
}

// The shastra whose ORIGINAL PDF this ref points to. For a teeka ref (e.g.
// श्लोकवार्तिक of तत्त्वार्थसूत्र) the published page + पुस्तक belong to the
// teeka's own printed volume, so the PDF link must resolve against the teeka
// name, not the parent shastra. Non-teeka refs use the shastra name as before.
export function pdfShastraNkOf(ref: DefinitionReference): string | null {
  if (ref.is_teeka && ref.teeka_name) return ref.teeka_name;
  return ref.shastra_name ?? null;
}

export interface ShastraPdfOffsets {
  pdfPageOffset: OffsetSpec;
  pustakOffsets: Record<string, OffsetSpec> | null;
  // true only when pdf_page_offset is explicitly configured on the shastra
  available: boolean;
}

const promiseCache = new Map<string, Promise<ShastraPdfOffsets>>();

export function _resetShastraPdfOffsetsForTest(): void {
  promiseCache.clear();
}

function loadShastraPdfOffsets(nk: string): Promise<ShastraPdfOffsets> {
  if (promiseCache.has(nk)) return promiseCache.get(nk)!;
  const promise = getShastraPdfOffsets(nk)
    .then(
      (res): ShastraPdfOffsets => ({
        pdfPageOffset: res.pdf_page_offset ?? 0,
        pustakOffsets: res.pustak_offsets ?? null,
        available: res.available,
      }),
    )
    .catch((): ShastraPdfOffsets => {
      promiseCache.delete(nk);
      return { pdfPageOffset: 0, pustakOffsets: null, available: false };
    });
  promiseCache.set(nk, promise);
  return promise;
}

export function useShastraPdfOffsets(shastraNk: string | null): {
  offsets: ShastraPdfOffsets | null;
  loading: boolean;
} {
  const nk = shastraNk ? shastraNk.normalize('NFC') : null;
  const [offsets, setOffsets] = useState<ShastraPdfOffsets | null>(null);
  const [loading, setLoading] = useState(nk !== null);

  useEffect(() => {
    if (!nk) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    loadShastraPdfOffsets(nk).then((result) => {
      if (!cancelled) {
        setOffsets(result);
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [nk]);

  return { offsets, loading };
}
