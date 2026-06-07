'use client';

import { useState, useCallback, useRef } from 'react';
import { DefinitionModal } from '@/components/DefinitionModal';
import { getEntityDetail } from '@/lib/api/data';
import type { EntityDetail } from '@/lib/types';

interface KeywordDefinitionButtonProps {
  keywordNk: string;
  displayText: string;
}

export function KeywordDefinitionButton({ keywordNk, displayText }: KeywordDefinitionButtonProps) {
  const [modal, setModal] = useState<{ open: boolean; detail: EntityDetail | null }>({
    open: false,
    detail: null,
  });
  const [loading, setLoading] = useState(false);
  const detailRef = useRef<EntityDetail | null>(null);

  const onClick = useCallback(async () => {
    if (detailRef.current) {
      setModal({ open: true, detail: detailRef.current });
      return;
    }
    setLoading(true);
    try {
      const d = await getEntityDetail('keyword', keywordNk);
      detailRef.current = d;
      setModal({ open: true, detail: d });
    } catch (e) {
      console.error('Failed to load keyword definition', { keywordNk, e });
    } finally {
      setLoading(false);
    }
  }, [keywordNk]);

  return (
    <>
      <button
        type="button"
        onClick={onClick}
        disabled={loading}
        className="rounded border border-accent bg-accent px-3 py-1 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-60"
      >
        {loading ? 'लोड हो रहा है…' : 'परिभाषा'}
      </button>
      <DefinitionModal
        open={modal.open}
        onClose={() => setModal({ open: false, detail: null })}
        title={displayText}
        definitionSections={modal.detail?.definitionSections ?? undefined}
      />
    </>
  );
}
