'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { DefinitionModal } from '@/components/DefinitionModal';
import { getTopicNeighbors } from '@/lib/api/navigation';
import { getEntityDetail } from '@/lib/api/data';
import type { EntityDetail } from '@/lib/types';
import { BookOpen, ChevronRight } from '@/lib/icons';

export interface TopicTreeItem {
  natural_key: string;
  display_text: string;
}

interface TopicTreeBrowserProps {
  initialItems: TopicTreeItem[];
}

interface Column {
  parentNk: string | null;
  parentPath: string;
  items: TopicTreeItem[];
  selectedNk: string | null;
  selectedIndex: number | null;
  loading: boolean;
}

export function TopicTreeBrowser({ initialItems }: TopicTreeBrowserProps) {
  const [columns, setColumns] = useState<Column[]>([
    { parentNk: null, parentPath: '', items: initialItems, selectedNk: null, selectedIndex: null, loading: false },
  ]);
  const [modal, setModal] = useState<{ open: boolean; title: string; detail: EntityDetail | null; loading: boolean }>({
    open: false,
    title: '',
    detail: null,
    loading: false,
  });
  const [hasExtracts, setHasExtracts] = useState<Set<string>>(new Set());
  const [nonLeaf, setNonLeaf] = useState<Set<string>>(new Set());
  const [probed, setProbed] = useState<Set<string>>(new Set());
  const detailCache = useRef<Map<string, EntityDetail>>(new Map());
  const inflight = useRef<Set<string>>(new Set());
  const checked = useRef<Set<string>>(new Set());

  useEffect(() => {
    const toFetch: string[] = [];
    for (const col of columns) {
      for (const item of col.items) {
        const nk = item.natural_key;
        if (checked.current.has(nk) || inflight.current.has(nk)) continue;
        toFetch.push(nk);
        inflight.current.add(nk);
      }
    }
    if (toFetch.length === 0) return;
    void Promise.all(
      toFetch.map(async (nk) => {
        try {
          const detail = await getEntityDetail('topic', nk);
          detailCache.current.set(nk, detail);
          if (detail.topicExtracts && detail.topicExtracts.length > 0) {
            setHasExtracts((prev) => {
              const next = new Set(prev);
              next.add(nk);
              return next;
            });
          }
          if (detail.stats?.is_leaf === 0) {
            setNonLeaf((prev) => {
              const next = new Set(prev);
              next.add(nk);
              return next;
            });
          }
        } catch (e) {
          console.error('Failed to probe topic extracts', { nk, e });
        } finally {
          checked.current.add(nk);
          inflight.current.delete(nk);
          setProbed((prev) => {
            const next = new Set(prev);
            next.add(nk);
            return next;
          });
        }
      })
    );
  }, [columns]);

  const handleExpand = useCallback(async (colIdx: number, item: TopicTreeItem, itemIdx: number) => {
    setColumns((prev) => {
      const next = prev.slice(0, colIdx + 1);
      next[colIdx] = { ...next[colIdx], selectedNk: item.natural_key, selectedIndex: itemIdx };
      next.push({
        parentNk: item.natural_key,
        parentPath: prev[colIdx].parentPath ? `${prev[colIdx].parentPath}.${itemIdx + 1}` : String(itemIdx + 1),
        items: [],
        selectedNk: null,
        selectedIndex: null,
        loading: true,
      });
      return next;
    });
    try {
      const res = await getTopicNeighbors(item.natural_key);
      const subs = res.neighbors
        .filter((n) => n.edge_type === 'PART_OF' && n.edge_direction === 'inbound')
        .map<TopicTreeItem>((n) => ({ natural_key: n.natural_key, display_text: n.display_text_hi }));
      setColumns((prev) => {
        const next = [...prev];
        const lastIdx = next.length - 1;
        if (next[lastIdx]?.parentNk === item.natural_key) {
          next[lastIdx] = { ...next[lastIdx], items: subs, loading: false };
        }
        return next;
      });
    } catch (e) {
      console.error('Failed to load subtopics', e);
      setColumns((prev) => {
        const next = [...prev];
        const lastIdx = next.length - 1;
        if (next[lastIdx]?.parentNk === item.natural_key) {
          next[lastIdx] = { ...next[lastIdx], loading: false };
        }
        return next;
      });
    }
  }, []);

  const handleOpenModal = useCallback(async (item: TopicTreeItem) => {
    const cached = detailCache.current.get(item.natural_key);
    if (cached) {
      setModal({ open: true, title: item.display_text || cached.title_hi, detail: cached, loading: false });
      return;
    }
    setModal({ open: true, title: item.display_text, detail: null, loading: true });
    try {
      const detail = await getEntityDetail('topic', item.natural_key);
      detailCache.current.set(item.natural_key, detail);
      setModal({ open: true, title: item.display_text || detail.title_hi, detail, loading: false });
    } catch (e) {
      console.error('Failed to load topic detail', e);
      setModal({ open: false, title: '', detail: null, loading: false });
    }
  }, []);

  return (
    <>
      <div className="flex gap-3 overflow-x-auto pb-2">
        {columns.map((col, colIdx) => (
          <div
            key={colIdx}
            className="min-w-[260px] flex-1 rounded-[var(--radius-md)] border border-border bg-surface p-3"
          >
            {col.loading && col.items.length === 0 && (
              <p className="text-sm text-foreground-muted">लोड हो रहा है…</p>
            )}
            {!col.loading && col.items.length === 0 && (
              <p className="text-sm text-foreground-muted">कोई उप-विषय नहीं</p>
            )}
            <ul className="space-y-1">
              {col.items.map((item, itemIdx) => {
                const path = col.parentPath ? `${col.parentPath}.${itemIdx + 1}` : String(itemIdx + 1);
                const isSelected = col.selectedNk === item.natural_key;
                return (
                  <li
                    key={item.natural_key}
                    className={`flex items-center gap-2 rounded px-2 py-1 text-sm ${
                      isSelected ? 'bg-accent-soft' : 'hover:bg-surface-muted'
                    }`}
                  >
                    <span className="shrink-0 font-sans text-xs text-foreground-muted">{path}</span>
                    {(() => {
                      const isLeaf = probed.has(item.natural_key) && !nonLeaf.has(item.natural_key);
                      return (
                        <button
                          type="button"
                          onClick={() => !isLeaf && handleExpand(colIdx, item, itemIdx)}
                          disabled={isLeaf}
                          className={`flex-1 truncate text-left font-serif-hindi ${
                            isLeaf ? 'cursor-default text-foreground-muted' : ''
                          }`}
                          title={item.display_text}
                        >
                          {item.display_text}
                        </button>
                      );
                    })()}
                    {hasExtracts.has(item.natural_key) && (
                      <button
                        type="button"
                        onClick={() => handleOpenModal(item)}
                        className="shrink-0 inline-flex items-center gap-1 rounded border border-accent px-2 py-0.5 text-xs text-accent hover:bg-accent-soft"
                        aria-label="परिभाषा देखें"
                        title="परिभाषा देखें"
                      >
                        <BookOpen className="size-3.5" strokeWidth={1.75} />
                      </button>
                    )}
                    {nonLeaf.has(item.natural_key) && (
                      <ChevronRight
                        className="size-4 shrink-0 text-foreground-muted"
                        strokeWidth={1.75}
                        aria-label="उप-विषय हैं"
                      />
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>

      <DefinitionModal
        open={modal.open}
        onClose={() => setModal((m) => ({ ...m, open: false }))}
        title={modal.title}
        topicExtracts={modal.detail?.topicExtracts}
      />
    </>
  );
}
