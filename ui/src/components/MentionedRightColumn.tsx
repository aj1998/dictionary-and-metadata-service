'use client';

import { useEffect, useState } from 'react';
import { Link } from '@/i18n/navigation';
import { X, Tag, Sparkles, ExternalLink, Loader2 } from '@/lib/icons';
import {
  getNodeMentionedKeywords,
  getNodeMentionedTopics,
  type NodeMentionedKeyword,
  type NodeMentionedTopic,
} from '@/lib/api/navigation';
import { useReaderActions, type MentionedRequest } from './ReaderActionsContext';

type Item =
  | { kind: 'topic'; data: NodeMentionedTopic }
  | { kind: 'keyword'; data: NodeMentionedKeyword };

function topicHref(t: NodeMentionedTopic): string {
  // Prefer parent-keyword scoped URL so TopicTreeBrowser auto-expands to this topic.
  if (t.parent_keyword_natural_key) {
    return `/dictionary/${encodeURIComponent(t.parent_keyword_natural_key)}?topic=${encodeURIComponent(t.natural_key)}`;
  }
  // Fallback: split on first ':'
  const idx = t.natural_key.indexOf(':');
  if (idx > 0) {
    const kw = t.natural_key.slice(0, idx);
    return `/dictionary/${encodeURIComponent(kw)}?topic=${encodeURIComponent(t.natural_key)}`;
  }
  return `/dictionary/${encodeURIComponent(t.natural_key)}`;
}

export function MentionedRightColumn() {
  const { request, close } = useReaderActions();
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!request) {
      setItems(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setItems(null);
    setError(null);
    (async () => {
      try {
        if (request.kind === 'topics') {
          const res = await getNodeMentionedTopics(request.sourceNk);
          if (cancelled) return;
          setItems(res.topics.map((t) => ({ kind: 'topic' as const, data: t })));
        } else {
          const res = await getNodeMentionedKeywords(request.sourceNk);
          if (cancelled) return;
          setItems(res.keywords.map((k) => ({ kind: 'keyword' as const, data: k })));
        }
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : 'त्रुटि हुई');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [request]);

  if (!request) return null;

  const isTopics = request.kind === 'topics';
  const Icon = isTopics ? Tag : Sparkles;
  const title = isTopics ? 'उल्लिखित विषय' : 'परिभाषित शब्द';
  const colorVar = isTopics ? 'var(--cat-topic)' : 'var(--cat-keyword)';

  return (
    <aside className="lg:sticky lg:top-[90px] lg:self-start lg:max-h-[calc(100vh-110px)] overflow-hidden flex flex-col rounded-[var(--radius-md)] border border-border bg-surface shadow-node">
      <header className="flex items-start justify-between gap-2 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Icon className="h-4 w-4 shrink-0" style={{ color: colorVar }} strokeWidth={1.5} />
            <h3 className="font-serif-hindi text-base font-semibold text-foreground">{title}</h3>
          </div>
          <p className="mt-1 text-xs text-foreground-muted truncate" title={request.sourceLabel}>
            {request.sourceLabel}
          </p>
        </div>
        <button
          onClick={close}
          aria-label="बंद करें"
          className="inline-flex h-7 w-7 items-center justify-center rounded-full text-foreground-muted hover:bg-surface-muted hover:text-foreground transition-colors"
        >
          <X className="h-4 w-4" strokeWidth={1.5} />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-2 py-2">
        {items === null && !error && (
          <div className="flex items-center justify-center py-8 text-foreground-muted">
            <Loader2 className="h-5 w-5 animate-spin" strokeWidth={1.5} />
          </div>
        )}
        {error && (
          <p className="px-3 py-4 text-sm text-[var(--danger)]">{error}</p>
        )}
        {items !== null && items.length === 0 && (
          <p className="px-3 py-4 text-sm text-foreground-muted">
            कोई {isTopics ? 'विषय' : 'शब्द'} उपलब्ध नहीं।
          </p>
        )}
        {items !== null && items.length > 0 && (
          <ul className="space-y-1">
            {items.map((it, i) => {
              if (it.kind === 'topic') {
                const t = it.data;
                const label = t.display_text_hi || t.natural_key;
                return (
                  <li key={`t-${t.natural_key}-${i}`}>
                    <Link
                      href={topicHref(t)}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="group flex items-center justify-between gap-2 rounded-[var(--radius-sm)] px-3 py-2 hover:bg-surface-muted transition-colors"
                    >
                      <span className="font-serif-hindi text-sm text-foreground truncate">
                        {label}
                      </span>
                      <ExternalLink className="h-3.5 w-3.5 shrink-0 text-foreground-subtle group-hover:text-accent" strokeWidth={1.5} />
                    </Link>
                  </li>
                );
              }
              const k = it.data;
              const label = k.display_text || k.natural_key;
              return (
                <li key={`k-${k.natural_key}-${i}`}>
                  <Link
                    href={`/dictionary/${encodeURIComponent(k.natural_key)}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group flex items-center justify-between gap-2 rounded-[var(--radius-sm)] px-3 py-2 hover:bg-surface-muted transition-colors"
                  >
                    <span className="font-serif-hindi text-sm text-foreground truncate">
                      {label}
                    </span>
                    <ExternalLink className="h-3.5 w-3.5 shrink-0 text-foreground-subtle group-hover:text-accent" strokeWidth={1.5} />
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}
