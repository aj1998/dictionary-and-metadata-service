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
  parentKeywordNk?: string;
  variant?: 'button' | 'inline';
  className?: string;
}

export function TopicNavAction({
  topicNk,
  displayText,
  isLeaf,
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
    (parentKw: string) => {
      const url = `${prefix}/dictionary/${encodeURIComponent(parentKw)}?topic=${encodeURIComponent(topicNk)}`;
      window.open(url, '_blank', 'noopener,noreferrer');
    },
    [prefix, topicNk]
  );

  const onClick = useCallback(async () => {
    if (isLeaf === false) {
      const parentKw =
        parentKeywordNk ?? (await ensureDetail())?.connected.find(
          (c) => c.kind === 'keyword' && c.edge_kind === 'HAS_TOPIC'
        )?.nk;
      if (parentKw) navigateToKeyword(parentKw);
      return;
    }
    const detail = await ensureDetail();
    if (!detail) return;
    setModal({ open: true, detail });
  }, [isLeaf, parentKeywordNk, ensureDetail, navigateToKeyword]);

  const showReadIcon = isLeaf !== false;
  const label = showReadIcon ? 'पढ़ें' : null;
  const Icon = showReadIcon ? BookOpen : ExternalLink;

  const navigateHref = (() => {
    const d = modal.detail;
    if (!d) return undefined;
    const parentKw =
      parentKeywordNk ?? d.connected.find((c) => c.kind === 'keyword' && c.edge_kind === 'HAS_TOPIC')?.nk;
    if (!parentKw) return undefined;
    return `${prefix}/dictionary/${encodeURIComponent(parentKw)}?topic=${encodeURIComponent(topicNk)}`;
  })();

  const buttonClass =
    variant === 'inline'
      ? className ?? 'inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline'
      : className ??
        'inline-flex items-center gap-1.5 rounded border border-accent px-3 py-1 text-sm font-medium text-accent hover:bg-accent-soft';

  return (
    <>
      <button
        type="button"
        onClick={onClick}
        className={buttonClass}
        aria-label={label ?? 'शब्दकोश में देखें'}
        title={label ?? 'शब्दकोश में देखें'}
      >
        <Icon className="size-4" strokeWidth={1.75} />
        {label}
      </button>
      <DefinitionModal
        open={modal.open}
        onClose={() => setModal({ open: false, detail: null })}
        title={displayText}
        topicExtracts={modal.detail?.topicExtracts ?? undefined}
        navigateHref={navigateHref}
        navigateLabel="शब्दकोश में देखें"
      />
    </>
  );
}
