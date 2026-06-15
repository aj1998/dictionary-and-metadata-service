'use client';

import { useTranslations } from 'next-intl';
import { ExternalLink } from '@/lib/icons';
import type { OffsetSpec } from '@/lib/api/metadata';

interface OriginalShastraLinkProps {
  shastraNk: string;
  pustak: string | null;
  publishedPage: number;
  pdfPageOffset: OffsetSpec;
  pustakOffsets: Record<string, OffsetSpec> | null;
  available: boolean;
}

export function resolveOffset(spec: OffsetSpec, publishedPage: number): number {
  if (typeof spec === 'number') return spec;
  if (spec.length === 0) return 0;
  const sorted = [...spec].sort((a, b) => a[0] - b[0]);
  for (const [upTo, off] of sorted) {
    if (publishedPage <= upTo) return off;
  }
  return sorted[sorted.length - 1][1];
}

export function buildOriginalShastraHref(
  shastraNk: string,
  pustak: string | null,
  pdfPage: number,
): string {
  const base = `/api/metadata/v1/shastras/${encodeURIComponent(shastraNk.normalize('NFC'))}/pdf-file`;
  const query = pustak ? `?pustak=${encodeURIComponent(pustak)}` : '';
  return `${base}${query}#page=${pdfPage}`;
}

export function computePdfPage(
  publishedPage: number,
  pdfPageOffset: OffsetSpec,
  pustakOffsets: Record<string, OffsetSpec> | null,
  pustak: string | null,
): number {
  const spec =
    pustakOffsets !== null && pustak !== null && pustak in pustakOffsets
      ? pustakOffsets[pustak]
      : pdfPageOffset;
  return publishedPage + resolveOffset(spec, publishedPage);
}

export function OriginalShastraLink({
  shastraNk,
  pustak,
  publishedPage,
  pdfPageOffset,
  pustakOffsets,
  available,
}: OriginalShastraLinkProps) {
  const t = useTranslations('originalShastra');
  const pdfPage = computePdfPage(publishedPage, pdfPageOffset, pustakOffsets, pustak);
  const href = buildOriginalShastraHref(shastraNk, pustak, pdfPage);
  const ariaLabel = `${t('viewOriginal')} — ${shastraNk} पृष्ठ ${publishedPage}`;

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className={available
        ? 'inline-flex items-center text-blue-600 hover:text-blue-700 transition-colors'
        : 'inline-flex items-center text-foreground-subtle hover:text-foreground-muted transition-colors'}
      aria-label={ariaLabel}
      title={ariaLabel}
    >
      <ExternalLink className="size-4 shrink-0" />
    </a>
  );
}
