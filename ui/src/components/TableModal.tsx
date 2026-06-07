'use client';

import { useEffect, useRef, useState } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { Link } from '@/i18n/navigation';
import { X, ExternalLink } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { getHindiText } from '@/lib/content-listing';
import { getTable } from '@/lib/api/data';
import { useIngestedShastras } from '@/lib/shastra-registry';
import { RefBadge } from '@/components/DefinitionModal';
import type { DefinitionReference, TableFull } from '@/lib/types';

export interface TableModalProps {
  naturalKey: string | null;
  onClose: () => void;
}

export function TableModal({ naturalKey, onClose }: TableModalProps) {
  const open = naturalKey !== null;
  const cacheRef = useRef<Map<string, TableFull>>(new Map());
  const [table, setTable] = useState<TableFull | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!naturalKey) {
      setTable(null);
      setError(null);
      return;
    }
    const cached = cacheRef.current.get(naturalKey);
    if (cached) {
      setTable(cached);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    let cancelled = false;
    getTable(naturalKey)
      .then((t) => {
        if (cancelled) return;
        cacheRef.current.set(naturalKey, t);
        setTable(t);
      })
      .catch(() => {
        if (cancelled) return;
        setError(naturalKey);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [naturalKey, attempt]);

  return (
    <Dialog.Root open={open} onOpenChange={(v) => { if (!v) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-50 bg-black/40 transition-opacity duration-150 data-ending-style:opacity-0 data-starting-style:opacity-0 supports-backdrop-filter:backdrop-blur-sm" />
        <Dialog.Popup className="fixed left-1/2 top-1/2 z-50 flex max-h-[85vh] w-full max-w-3xl -translate-x-1/2 -translate-y-1/2 flex-col rounded-[var(--radius-lg)] bg-surface shadow-xl transition duration-150 data-ending-style:opacity-0 data-ending-style:scale-95 data-starting-style:opacity-0 data-starting-style:scale-95">
          <div className="flex shrink-0 items-start justify-between border-b border-border px-5 py-4">
            <Dialog.Title className="font-serif-hindi text-[length:var(--font-size-h1)] font-semibold text-foreground">
              {table ? getHindiText(table.caption, 'तालिका') : 'तालिका'}
            </Dialog.Title>
            <Dialog.Close
              className="ml-4 mt-0.5 shrink-0 rounded-[var(--radius-sm)] p-1 text-foreground-muted transition-colors hover:bg-surface-muted hover:text-foreground"
              aria-label="बंद करें"
            >
              <X className="size-4" />
            </Dialog.Close>
          </div>

          <div className="flex-1 overflow-y-auto px-5 py-4">
            {loading && <TableShimmer />}
            {error && !loading && (
              <div className="flex flex-col items-start gap-2 text-sm">
                <p className="text-danger">तालिका लोड नहीं हो सकी</p>
                <p className="text-foreground-muted text-xs">{error}</p>
                <button
                  type="button"
                  onClick={() => setAttempt((a) => a + 1)}
                  className="rounded bg-accent px-3 py-1 text-white text-xs"
                >
                  पुनः प्रयास करें
                </button>
              </div>
            )}
            {table && !loading && !error && <TableBody table={table} />}
          </div>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function TableShimmer() {
  return (
    <div className="space-y-2" data-testid="table-modal-shimmer">
      <div className="shimmer h-6 w-1/2 rounded" />
      <div className="shimmer h-32 w-full rounded" />
    </div>
  );
}

function CellRefs({ refs }: { refs: DefinitionReference[] }) {
  const { shastras: ingestedShastras } = useIngestedShastras();
  if (!refs || refs.length === 0) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {refs.map((ref, i) => (
        <RefBadge
          key={i}
          ref={ref}
          showShastra={true}
          matchEntry={undefined}
          loading={false}
          ingestedShastras={ingestedShastras}
        />
      ))}
    </div>
  );
}

function TableBody({ table }: { table: TableFull }) {
  const cellRefs = table.cell_refs;

  return (
    <div className="space-y-4">
      {table.sourceUrl && (
        <a
          href={table.sourceUrl}
          target="_blank"
          rel="noreferrer noopener"
          className="inline-flex items-center gap-1 text-sm text-accent hover:underline"
        >
          जैनकोश पर देखें
          <ExternalLink className="size-3" />
        </a>
      )}

      <div className="overflow-x-auto">
        <table className="border-collapse text-sm font-serif-hindi">
          <tbody>
            {table.cells.map((row, ri) => {
              const isHeader = ri < table.headerRows;
              return (
                <tr
                  key={ri}
                  className={cn(
                    !isHeader && ri % 2 === 1 && 'bg-[var(--cat-table-soft)]/40',
                  )}
                >
                  {row.map((cell, ci) => {
                    const refs = cellRefs?.[ri]?.[ci] ?? [];
                    const content = (
                      <>
                        {cell}
                        <CellRefs refs={refs} />
                      </>
                    );
                    return isHeader ? (
                      <th
                        key={ci}
                        className="border border-border bg-[var(--cat-table)]/15 px-3 py-1.5 text-left font-semibold"
                      >
                        {content}
                      </th>
                    ) : (
                      <td key={ci} className="border border-border px-3 py-1.5 align-top">
                        {content}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {(table.mentionedKeywordNaturalKeys?.length ?? 0) > 0 && (
        <MentionsRow
          title="उल्लिखित कीवर्ड"
          base="/dictionary"
          nks={table.mentionedKeywordNaturalKeys!}
        />
      )}
      {(table.mentionedTopicNaturalKeys?.length ?? 0) > 0 && (
        <MentionsRow
          title="उल्लिखित विषय"
          base="/topics"
          nks={table.mentionedTopicNaturalKeys!}
        />
      )}

      {process.env.NODE_ENV !== 'production' && (
        <details className="mt-4 text-xs text-foreground-muted">
          <summary className="cursor-pointer">Raw HTML (dev only)</summary>
          <iframe
            sandbox=""
            srcDoc={table.rawHtml}
            className="mt-2 h-64 w-full border border-border"
            title="raw-html-debug"
          />
        </details>
      )}
    </div>
  );
}

function MentionsRow({ title, base, nks }: { title: string; base: string; nks: string[] }) {
  return (
    <div>
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-foreground-muted">
        {title}
      </p>
      <div className="flex flex-wrap gap-1.5">
        {nks.map((nk) => (
          <Link
            key={nk}
            href={`${base}/${encodeURIComponent(nk)}`}
            className="rounded-[var(--radius-pill)] bg-surface-muted px-2.5 py-0.5 text-xs text-foreground hover:bg-[var(--cat-table-soft)]"
          >
            {nk}
          </Link>
        ))}
      </div>
    </div>
  );
}
