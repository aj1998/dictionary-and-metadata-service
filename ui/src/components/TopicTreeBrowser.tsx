'use client';

import { useState, useCallback, useEffect, useRef } from 'react';
import { useLocale } from 'next-intl';
import { DefinitionModal } from '@/components/DefinitionModal';
import { getTopicNeighbors, getTopicMentionedKeywords, getTopicRelated, getTopicAncestors } from '@/lib/api/navigation';
import { getEntityDetail, listTablesForParent } from '@/lib/api/data';
import type { EntityDetail } from '@/lib/types';
import { BookOpen, ChevronRight, Link2, IconTable } from '@/lib/icons';
import { TableModal } from '@/components/TableModal';

export interface TopicTreeItem {
  natural_key: string;
  display_text: string;
}

interface TopicTreeBrowserProps {
  initialItems: TopicTreeItem[];
  targetTopicNk?: string;
  currentKeywordNk?: string;
}

interface Column {
  parentNk: string | null;
  parentPath: string;
  items: TopicTreeItem[];
  selectedNk: string | null;
  selectedIndex: number | null;
  loading: boolean;
}

interface RelatedItem {
  nk: string;
  kind: 'topic' | 'keyword';
  title: string;
}

export function TopicTreeBrowser({ initialItems, targetTopicNk, currentKeywordNk }: TopicTreeBrowserProps) {
  const locale = useLocale();
  const localePrefix = locale === 'hi' ? '' : `/${locale}`;
  const buildKeywordTopicHref = useCallback(
    (kwNk: string, topicNk: string) =>
      `${localePrefix}/dictionary/${encodeURIComponent(kwNk)}?topic=${encodeURIComponent(topicNk)}`,
    [localePrefix]
  );
  const [columns, setColumns] = useState<Column[]>([
    { parentNk: null, parentPath: '', items: initialItems, selectedNk: null, selectedIndex: null, loading: false },
  ]);
  const [modal, setModal] = useState<{ open: boolean; title: string; detail: EntityDetail | null; loading: boolean; navigateHref?: string }>({
    open: false,
    title: '',
    detail: null,
    loading: false,
  });
  const [hasExtracts, setHasExtracts] = useState<Set<string>>(new Set());
  const [nonLeaf, setNonLeaf] = useState<Set<string>>(new Set());
  const [probed, setProbed] = useState<Set<string>>(new Set());
  const [isSeed, setIsSeed] = useState<Set<string>>(new Set());
  const [seedExpanded, setSeedExpanded] = useState<Set<string>>(new Set());
  const [seedRelated, setSeedRelated] = useState<Map<string, RelatedItem[]>>(new Map());
  const [seedLoading, setSeedLoading] = useState<Set<string>>(new Set());
  const [hasRelated, setHasRelated] = useState<Set<string>>(new Set());
  // topicNk → ordered list of table NKs (from CONTAINS_TABLE edges in EntityDetail.connected)
  const [topicTableNks, setTopicTableNks] = useState<Map<string, string[]>>(new Map());
  const [tableModalNk, setTableModalNk] = useState<string | null>(null);
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
          const [detail, tables, relatedRes, kwRes] = await Promise.all([
            getEntityDetail('topic', nk),
            listTablesForParent(nk).catch(() => []),
            getTopicRelated(nk).catch(() => ({ related: [] as Array<{ natural_key: string; display_text: string | null; label: string }> })),
            getTopicMentionedKeywords(nk).catch(() => ({ keywords: [] as Array<{ natural_key: string; display_text: string | null }> })),
          ]);
          const seen = new Set<string>();
          const merged: RelatedItem[] = [];
          for (const r of relatedRes.related) {
            if (r.natural_key === nk) continue; // skip self
            const kind: 'topic' | 'keyword' = r.label === 'Keyword' ? 'keyword' : 'topic';
            const key = `${kind}:${r.natural_key}`;
            if (seen.has(key)) continue;
            seen.add(key);
            merged.push({ nk: r.natural_key, kind, title: r.display_text || r.natural_key });
          }
          for (const k of kwRes.keywords) {
            if (k.natural_key === nk) continue; // skip self
            const key = `keyword:${k.natural_key}`;
            if (seen.has(key)) continue;
            seen.add(key);
            merged.push({ nk: k.natural_key, kind: 'keyword', title: k.display_text || k.natural_key });
          }
          // Pre-filter: drop topic targets that are themselves anya-vishay (no topicPath + no extracts).
          const filtered: RelatedItem[] = [];
          for (const r of merged) {
            if (r.kind !== 'topic') {
              filtered.push(r);
              continue;
            }
            let targetDetail = detailCache.current.get(r.nk);
            if (!targetDetail) {
              try {
                targetDetail = await getEntityDetail('topic', r.nk);
                detailCache.current.set(r.nk, targetDetail);
              } catch {
                filtered.push(r);
                continue;
              }
            }
            const targetIsAnya = !targetDetail.topicPath && (!targetDetail.topicExtracts || targetDetail.topicExtracts.length === 0);
            if (targetIsAnya) continue;
            filtered.push(r);
          }
          if (filtered.length > 0) {
            setHasRelated((prev) => {
              const next = new Set(prev);
              next.add(nk);
              return next;
            });
            setSeedRelated((prev) => {
              const next = new Map(prev);
              next.set(nk, filtered);
              return next;
            });
          }
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
          if (!detail.topicPath) {
            setIsSeed((prev) => {
              const next = new Set(prev);
              next.add(nk);
              return next;
            });
          }
          if (tables.length > 0) {
            setTopicTableNks((prev) => {
              const next = new Map(prev);
              // API returns snake_case: natural_key
              next.set(nk, tables.map((t) => (t as unknown as { natural_key: string }).natural_key));
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

  useEffect(() => {
    if (!targetTopicNk) return;
    let cancelled = false;
    void (async () => {
      try {
        const anc = await getTopicAncestors(targetTopicNk);
        if (cancelled) return;
        const chain = [...anc.ancestors, targetTopicNk];
        const newColumns: Column[] = [
          { parentNk: null, parentPath: '', items: initialItems, selectedNk: null, selectedIndex: null, loading: false },
        ];
        let currentItems = initialItems;
        let parentPath = '';
        for (let i = 0; i < chain.length; i++) {
          const nk = chain[i];
          const idx = currentItems.findIndex((it) => it.natural_key === nk);
          if (idx < 0) break;
          const colIdx = newColumns.length - 1;
          newColumns[colIdx] = { ...newColumns[colIdx], selectedNk: nk, selectedIndex: idx };
          if (i === chain.length - 1) break;
          try {
            const res = await getTopicNeighbors(nk);
            if (cancelled) return;
            const subs = res.neighbors
              .filter((n) => n.edge_type === 'PART_OF' && n.edge_direction === 'inbound')
              .map<TopicTreeItem>((n) => ({ natural_key: n.natural_key, display_text: n.display_text_hi }));
            parentPath = parentPath ? `${parentPath}.${idx + 1}` : String(idx + 1);
            newColumns.push({
              parentNk: nk,
              parentPath,
              items: subs,
              selectedNk: null,
              selectedIndex: null,
              loading: false,
            });
            currentItems = subs;
          } catch (e) {
            console.error('Auto-expand fetch failed', e);
            break;
          }
        }
        if (!cancelled) setColumns(newColumns);
      } catch (e) {
        console.error('Failed to load topic ancestors', e);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetTopicNk]);

  const handleExpand = useCallback(async (colIdx: number, item: TopicTreeItem, pathStr: string) => {
    setColumns((prev) => {
      const next = prev.slice(0, colIdx + 1);
      next[colIdx] = { ...next[colIdx], selectedNk: item.natural_key };
      next.push({
        parentNk: item.natural_key,
        parentPath: pathStr,
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

  const buildNavigateHref = useCallback(
    (detail: EntityDetail | null | undefined, topicNk: string): string | undefined => {
      const parentKw = detail?.connected?.find((c) => c.kind === 'keyword' && c.edge_kind === 'HAS_TOPIC')?.nk;
      if (!parentKw) return undefined;
      if (currentKeywordNk && parentKw === currentKeywordNk) return undefined;
      return buildKeywordTopicHref(parentKw, topicNk);
    },
    [buildKeywordTopicHref, currentKeywordNk]
  );

  const handleOpenModal = useCallback(async (nk: string, displayText: string) => {
    const cached = detailCache.current.get(nk);
    if (cached) {
      setModal({
        open: true,
        title: displayText || cached.title_hi,
        detail: cached,
        loading: false,
        navigateHref: buildNavigateHref(cached, nk),
      });
      return;
    }
    setModal({ open: true, title: displayText, detail: null, loading: true });
    try {
      const detail = await getEntityDetail('topic', nk);
      detailCache.current.set(nk, detail);
      setModal({
        open: true,
        title: displayText || detail.title_hi,
        detail,
        loading: false,
        navigateHref: buildNavigateHref(detail, nk),
      });
    } catch (e) {
      console.error('Failed to load topic detail', e);
      setModal({ open: false, title: '', detail: null, loading: false });
    }
  }, [buildNavigateHref]);

  const handleToggleSeed = useCallback(async (nk: string) => {
    setSeedExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(nk)) {
        next.delete(nk);
      } else {
        next.add(nk);
      }
      return next;
    });
    if (seedLoading.has(nk)) return;
    setSeedLoading((prev) => {
      const next = new Set(prev);
      next.add(nk);
      return next;
    });
    try {
      let related = seedRelated.get(nk);
      if (!related) {
        const [relatedRes, keywordsRes] = await Promise.all([
          getTopicRelated(nk).catch(() => ({ related: [] as Array<{ natural_key: string; display_text: string | null; label: string }> })),
          getTopicMentionedKeywords(nk).catch(() => ({ keywords: [] as Array<{ natural_key: string; display_text: string | null }> })),
        ]);
        const seen = new Set<string>();
        related = [];
        for (const r of relatedRes.related) {
          if (r.natural_key === nk) continue;
          const kind: 'topic' | 'keyword' = r.label === 'Keyword' ? 'keyword' : 'topic';
          const key = `${kind}:${r.natural_key}`;
          if (seen.has(key)) continue;
          seen.add(key);
          related.push({ nk: r.natural_key, kind, title: r.display_text || r.natural_key });
        }
        for (const k of keywordsRes.keywords) {
          if (k.natural_key === nk) continue;
          const key = `keyword:${k.natural_key}`;
          if (seen.has(key)) continue;
          seen.add(key);
          related.push({ nk: k.natural_key, kind: 'keyword', title: k.display_text || k.natural_key });
        }
      }
      // Filter out topic targets that are themselves anya-vishay (no topicPath + no extracts).
      const filtered: RelatedItem[] = [];
      for (const r of related) {
        if (r.kind !== 'topic') {
          filtered.push(r);
          continue;
        }
        let detail = detailCache.current.get(r.nk);
        if (!detail) {
          try {
            detail = await getEntityDetail('topic', r.nk);
            detailCache.current.set(r.nk, detail);
          } catch {
            filtered.push(r);
            continue;
          }
        }
        const targetIsAnya = !detail.topicPath && (!detail.topicExtracts || detail.topicExtracts.length === 0);
        if (targetIsAnya) continue;
        filtered.push(r);
      }
      setSeedRelated((prev) => {
        const next = new Map(prev);
        next.set(nk, filtered);
        return next;
      });
      if (filtered.length === 0) {
        setHasRelated((prev) => {
          if (!prev.has(nk)) return prev;
          const next = new Set(prev);
          next.delete(nk);
          return next;
        });
        setSeedExpanded((prev) => {
          if (!prev.has(nk)) return prev;
          const next = new Set(prev);
          next.delete(nk);
          return next;
        });
      }
    } catch (e) {
      console.error('Failed to load seed related', e);
    } finally {
      setSeedLoading((prev) => {
        const next = new Set(prev);
        next.delete(nk);
        return next;
      });
    }
  }, [seedRelated, seedLoading]);

  const handleRelatedClick = useCallback(
    async (r: RelatedItem) => {
      if (r.kind === 'keyword') {
        const url = `${localePrefix}/dictionary/${encodeURIComponent(r.nk)}`;
        window.open(url, '_blank', 'noopener,noreferrer');
        return;
      }
      let detail = detailCache.current.get(r.nk);
      if (!detail) {
        try {
          detail = await getEntityDetail('topic', r.nk);
          detailCache.current.set(r.nk, detail);
        } catch (e) {
          console.error('Failed to load related topic detail', e);
        }
      }
      const hasContent = !!(detail?.topicExtracts && detail.topicExtracts.length > 0);
      if (hasContent) {
        setModal({
          open: true,
          title: r.title || detail!.title_hi,
          detail: detail!,
          loading: false,
          navigateHref: buildNavigateHref(detail, r.nk),
        });
        return;
      }
      const parentKw = detail?.connected?.find((c) => c.kind === 'keyword' && c.edge_kind === 'HAS_TOPIC')?.nk;
      const href = parentKw ? buildKeywordTopicHref(parentKw, r.nk) : undefined;
      if (href) {
        window.open(href, '_blank', 'noopener,noreferrer');
      }
    },
    [localePrefix, buildNavigateHref, buildKeywordTopicHref]
  );

  return (
    <>
      <div className="flex gap-3 overflow-x-auto pb-2">
        {columns.map((col, colIdx) => {
          const pathItems: { item: TopicTreeItem; path: string }[] = [];
          const seedItems: TopicTreeItem[] = [];
          let pathCounter = 0;
          for (const item of col.items) {
            if (isSeed.has(item.natural_key)) {
              seedItems.push(item);
            } else {
              pathCounter += 1;
              const path = col.parentPath
                ? `${col.parentPath}.${pathCounter}`
                : String(pathCounter);
              pathItems.push({ item, path });
            }
          }

          return (
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
                {pathItems.map(({ item, path }) => {
                  const isSelected = col.selectedNk === item.natural_key;
                  const isLeaf = probed.has(item.natural_key) && !nonLeaf.has(item.natural_key);
                  const expanded = seedExpanded.has(item.natural_key);
                  const related = seedRelated.get(item.natural_key);
                  const loading = seedLoading.has(item.natural_key);
                  return (
                    <li key={item.natural_key}>
                    <div
                      className={`flex items-center gap-2 rounded px-2 py-1 text-sm ${
                        isSelected ? 'bg-accent-soft' : 'hover:bg-surface-muted'
                      }`}
                    >
                      <span className="shrink-0 font-sans text-xs text-foreground-muted">{path}</span>
                      <button
                        type="button"
                        onClick={() => !isLeaf && handleExpand(colIdx, item, path)}
                        disabled={isLeaf}
                        className={`flex-1 truncate text-left font-serif-hindi ${
                          isLeaf ? 'cursor-default text-foreground-muted' : ''
                        }`}
                        title={item.display_text}
                      >
                        {item.display_text}
                      </button>
                      {hasRelated.has(item.natural_key) && (
                        <button
                          type="button"
                          onClick={() => handleToggleSeed(item.natural_key)}
                          className="shrink-0 inline-flex items-center justify-center rounded border border-[color:var(--cat-topic)] text-[color:var(--cat-topic)] hover:bg-surface-muted size-6"
                          aria-label="संबंधित खोलें"
                          title="संबंधित खोलें"
                        >
                          <Link2 className="size-3.5" strokeWidth={1.75} />
                        </button>
                      )}
                      {hasExtracts.has(item.natural_key) && (
                        <button
                          type="button"
                          onClick={() => handleOpenModal(item.natural_key, item.display_text)}
                          className="shrink-0 inline-flex items-center gap-1 rounded border border-accent px-2 py-0.5 text-xs text-accent hover:bg-accent-soft"
                          aria-label="परिभाषा देखें"
                          title="परिभाषा देखें"
                        >
                          <BookOpen className="size-3.5" strokeWidth={1.75} />
                        </button>
                      )}
                      {topicTableNks.has(item.natural_key) && (
                        <button
                          type="button"
                          onClick={() => setTableModalNk(topicTableNks.get(item.natural_key)![0])}
                          className="shrink-0 inline-flex items-center gap-1 rounded border border-[color:var(--cat-table)] px-2 py-0.5 text-xs text-[color:var(--cat-table)] hover:bg-[var(--cat-table-soft)]"
                          aria-label="तालिका देखें"
                          title="तालिका देखें"
                        >
                          <IconTable className="size-3.5" strokeWidth={1.75} />
                        </button>
                      )}
                      {nonLeaf.has(item.natural_key) && (
                        <ChevronRight
                          className="size-4 shrink-0 text-foreground-muted"
                          strokeWidth={1.75}
                          aria-label="उप-विषय हैं"
                        />
                      )}
                    </div>
                    {expanded && (
                      <div className="ml-8 mt-1 mb-2 border-l border-border pl-2">
                        {loading && !related && (
                          <p className="px-2 py-1 text-xs text-foreground-muted">लोड हो रहा है…</p>
                        )}
                        {related && related.length === 0 && (
                          <p className="px-2 py-1 text-xs text-foreground-muted">कोई संबंधित नहीं</p>
                        )}
                        {related && related.length > 0 && (
                          <ul className="space-y-0.5">
                            {related.map((r) => (
                              <li key={`${r.kind}:${r.nk}`}>
                                <button
                                  type="button"
                                  onClick={() => handleRelatedClick(r)}
                                  className="flex w-full items-center gap-2 rounded px-2 py-1 text-left text-xs hover:bg-surface-muted"
                                >
                                  <span
                                    className={`shrink-0 rounded px-1.5 py-0.5 font-sans text-[10px] uppercase ${
                                      r.kind === 'keyword'
                                        ? 'bg-[color:var(--cat-keyword)]/10 text-[color:var(--cat-keyword)]'
                                        : 'bg-[color:var(--cat-topic)]/10 text-[color:var(--cat-topic)]'
                                    }`}
                                  >
                                    {r.kind === 'keyword' ? 'शब्द' : 'विषय'}
                                  </span>
                                  <span className="flex-1 truncate font-serif-hindi">{r.title}</span>
                                </button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}
                  </li>
                  );
                })}
              </ul>

              {seedItems.length > 0 && (
                <div className="mt-3 border-t border-border pt-2">
                  <p className="mb-1 px-2 text-xs font-medium uppercase tracking-wide text-foreground-muted">
                    अन्य विषय
                  </p>
                  <ul className="space-y-1">
                    {seedItems.map((item) => {
                      const expanded = seedExpanded.has(item.natural_key);
                      const related = seedRelated.get(item.natural_key);
                      const loading = seedLoading.has(item.natural_key);
                      const isSelected = col.selectedNk === item.natural_key;
                      return (
                        <li key={item.natural_key}>
                          <div className={`flex items-center gap-2 rounded px-2 py-1 text-sm ${isSelected ? 'bg-accent-soft' : 'hover:bg-surface-muted'}`}>
                            <button
                              type="button"
                              onClick={() => handleToggleSeed(item.natural_key)}
                              className="shrink-0 inline-flex items-center justify-center rounded border border-[color:var(--cat-topic)] text-[color:var(--cat-topic)] hover:bg-surface-muted size-6"
                              aria-label="संबंधित खोलें"
                              title="संबंधित खोलें"
                            >
                              <Link2 className="size-3.5" strokeWidth={1.75} />
                            </button>
                            <span className="flex-1 truncate font-serif-hindi" title={item.display_text}>
                              {item.display_text}
                            </span>
                            {hasExtracts.has(item.natural_key) && (
                              <button
                                type="button"
                                onClick={() => handleOpenModal(item.natural_key, item.display_text)}
                                className="shrink-0 inline-flex items-center gap-1 rounded border border-accent px-2 py-0.5 text-xs text-accent hover:bg-accent-soft"
                                aria-label="परिभाषा देखें"
                                title="परिभाषा देखें"
                              >
                                <BookOpen className="size-3.5" strokeWidth={1.75} />
                              </button>
                            )}
                            {topicTableNks.has(item.natural_key) && (
                              <button
                                type="button"
                                onClick={() => setTableModalNk(topicTableNks.get(item.natural_key)![0])}
                                className="shrink-0 inline-flex items-center gap-1 rounded border border-[color:var(--cat-table)] px-2 py-0.5 text-xs text-[color:var(--cat-table)] hover:bg-[var(--cat-table-soft)]"
                                aria-label="तालिका देखें"
                                title="तालिका देखें"
                              >
                                <IconTable className="size-3.5" strokeWidth={1.75} />
                              </button>
                            )}
                          </div>
                          {expanded && (
                            <div className="ml-8 mt-1 mb-2 border-l border-border pl-2">
                              {loading && !related && (
                                <p className="px-2 py-1 text-xs text-foreground-muted">लोड हो रहा है…</p>
                              )}
                              {related && related.length === 0 && (
                                <p className="px-2 py-1 text-xs text-foreground-muted">कोई संबंधित नहीं</p>
                              )}
                              {related && related.length > 0 && (
                                <ul className="space-y-0.5">
                                  {related.map((r) => (
                                    <li key={`${r.kind}:${r.nk}`}>
                                      <button
                                        type="button"
                                        onClick={() => handleRelatedClick(r)}
                                        className="flex w-full items-center gap-2 rounded px-2 py-1 text-left text-xs hover:bg-surface-muted"
                                      >
                                        <span
                                          className={`shrink-0 rounded px-1.5 py-0.5 font-sans text-[10px] uppercase ${
                                            r.kind === 'keyword'
                                              ? 'bg-[color:var(--cat-keyword)]/10 text-[color:var(--cat-keyword)]'
                                              : 'bg-[color:var(--cat-topic)]/10 text-[color:var(--cat-topic)]'
                                          }`}
                                        >
                                          {r.kind === 'keyword' ? 'शब्द' : 'विषय'}
                                        </span>
                                        <span className="flex-1 truncate font-serif-hindi">{r.title}</span>
                                      </button>
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <DefinitionModal
        open={modal.open}
        onClose={() => setModal((m) => ({ ...m, open: false }))}
        title={modal.title}
        topicExtracts={modal.detail?.topicExtracts}
        navigateHref={modal.navigateHref}
        navigateLabel="शब्द पृष्ठ पर इस विषय पर जाएँ"
      />

      <TableModal naturalKey={tableModalNk} onClose={() => setTableModalNk(null)} />
    </>
  );
}
