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

// Teekas that have their own printed volume (a `teeka_of` entry in
// parser_configs/_manual_configs/shastra.json). For these the published page +
// पुस्तक belong to the teeka's own PDF, so the link must resolve against the
// teeka name. Every other teeka is nested under its parent shastra and shares
// the parent's PDF, so its page must resolve against the parent shastra name.
const TEEKAS_WITH_OWN_PDF = new Set(
  ['राजवार्तिक', 'श्लोकवार्तिक', 'सर्वार्थसिद्धि'].map((s) => s.normalize('NFC')),
);

// The shastra whose ORIGINAL PDF this ref points to. For a teeka ref that has
// its own printed volume (see TEEKAS_WITH_OWN_PDF) the published page + पुस्तक
// belong to the teeka's own PDF, so the link must resolve against the teeka
// name. All other refs (non-teeka, or teekas nested under a parent shastra)
// resolve against the parent shastra name.
export function pdfShastraNkOf(ref: DefinitionReference): string | null {
  if (
    ref.is_teeka &&
    ref.teeka_name &&
    TEEKAS_WITH_OWN_PDF.has(ref.teeka_name.normalize('NFC'))
  ) {
    return ref.teeka_name;
  }
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
