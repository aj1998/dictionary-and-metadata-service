'use client';

import { useState, useCallback, useRef } from 'react';
import { useLocale } from 'next-intl';
import { DefinitionModal } from '@/components/DefinitionModal';
import { getEntityDetail } from '@/lib/api/data';
import type { EntityDetail } from '@/lib/types';
import { BookOpen, ExternalLink } from '@/lib/icons';

interface TopicNavActionProps {
  topicNk: string;
  displayText: string;
  isLeaf?: boolean;
  /**
   * Whether the topic has its own readable extracts (query_engine/08 Part C/E).
   * When provided, drives the पढ़ें affordance independently of `isLeaf` so a
   * content-bearing non-leaf topic shows BOTH पढ़ें and the expand link. When
   * omitted, falls back to the legacy behaviour (पढ़ें iff not a non-leaf).
   */
  hasExtracts?: boolean;
  parentKeywordNk?: string;
  variant?: 'button' | 'inline';
  className?: string;
}

export function TopicNavAction({
  topicNk,
  displayText,
  isLeaf,
  hasExtracts,
  parentKeywordNk,
  variant = 'button',
  className,
}: TopicNavActionProps) {
  const locale = useLocale();
  const prefix = locale === 'hi' ? '' : `/${locale}`;
  const [modal, setModal] = useState<{ open: boolean; detail: EntityDetail | null }>({
    open: false,
    detail: null,
  });
  const detailRef = useRef<EntityDetail | null>(null);

  // Part C/E: read action driven by hasExtracts when known; expand link driven
  // by isLeaf === false. Legacy fallback keeps the either/or when hasExtracts
  // is not supplied.
  const showRead = hasExtracts ?? isLeaf !== false;
  const showExpand = isLeaf === false;

  const ensureDetail = useCallback(async (): Promise<EntityDetail | null> => {
    if (detailRef.current) return detailRef.current;
    try {
      const d = await getEntityDetail('topic', topicNk);
      detailRef.current = d;
      return d;
    } catch (e) {
      console.error('Failed to load topic detail', { topicNk, e });
      return null;
    }
  }, [topicNk]);

  const navigateToKeyword = useCallback(
    async () => {
      const parentKw =
        parentKeywordNk ?? (await ensureDetail())?.connected.find(
          (c) => c.kind === 'keyword' && c.edge_kind === 'HAS_TOPIC'
        )?.nk;
      if (!parentKw) return;
      const url = `${prefix}/dictionary/${encodeURIComponent(parentKw)}?topic=${encodeURIComponent(topicNk)}`;
      window.open(url, '_blank', 'noopener,noreferrer');
    },
    [prefix, topicNk, parentKeywordNk, ensureDetail]
  );

  const onRead = useCallback(async () => {
    const detail = await ensureDetail();
    if (!detail) return;
    setModal({ open: true, detail });
  }, [ensureDetail]);

  const navigateHref = (() => {
    const d = modal.detail;
    if (!d) return undefined;
    const parentKw =
      parentKeywordNk ?? d.connected.find((c) => c.kind === 'keyword' && c.edge_kind === 'HAS_TOPIC')?.nk;
    if (!parentKw) return undefined;
    return `${prefix}/dictionary/${encodeURIComponent(parentKw)}?topic=${encodeURIComponent(topicNk)}`;
  })();

  const readClass =
    variant === 'inline'
      ? className ?? 'inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline'
      : className ??
        'inline-flex items-center gap-1.5 rounded border border-accent/40 bg-accent-soft px-3 py-1 text-sm font-medium text-accent hover:bg-accent/20';

  const expandClass =
    variant === 'inline'
      ? 'inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline'
      : 'inline-flex items-center gap-1.5 rounded border border-accent px-3 py-1 text-sm font-medium text-accent hover:bg-accent-soft';

  return (
    <>
      <span className="inline-flex items-center gap-2">
        {showRead && (
          <button
            type="button"
            onClick={onRead}
            className={readClass}
            aria-label="पढ़ें"
            title="पढ़ें"
          >
            <BookOpen className="size-4" strokeWidth={1.75} />
            पढ़ें
          </button>
        )}
        {showExpand && (
          <button
            type="button"
            onClick={navigateToKeyword}
            className={expandClass}
            aria-label="शब्दकोश में देखें"
            title="शब्दकोश में देखें"
          >
            <ExternalLink className="size-4" strokeWidth={1.75} />
          </button>
        )}
      </span>
      <DefinitionModal
        open={modal.open}
        onClose={() => setModal({ open: false, detail: null })}
        title={displayText}
        topicExtracts={modal.detail?.topicExtracts ?? undefined}
        navigateHref={navigateHref}
        navigateLabel="शब्दकोश में देखें"
        navigateLinks={[
          { href: `${prefix}/graph?node=${encodeURIComponent(topicNk)}`, label: 'ग्राफ में देखें' },
        ]}
      />
    </>
  );
}
