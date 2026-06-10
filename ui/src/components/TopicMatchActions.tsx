'use client';

import { useEffect, useState } from 'react';
import { TopicNavAction } from '@/components/TopicNavAction';
import { TopicPathInfo } from '@/components/TopicPathInfo';
import { getEntityDetail } from '@/lib/api/data';

interface Props {
  topicNk: string;
  displayText: string;
  dictionaryHref?: string;
}

export function TopicMatchActions({ topicNk, displayText, dictionaryHref }: Props) {
  const [state, setState] = useState<{ loaded: boolean; hasExtracts: boolean; isLeaf: boolean }>(
    { loaded: false, hasExtracts: false, isLeaf: false },
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const d = await getEntityDetail('topic', topicNk);
        if (cancelled) return;
        const hasExtracts = !!(d.topicExtracts && d.topicExtracts.length > 0);
        const isLeaf = d.stats?.is_leaf === 1;
        setState({ loaded: true, hasExtracts, isLeaf });
      } catch {
        if (!cancelled) setState({ loaded: true, hasExtracts: false, isLeaf: false });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [topicNk]);

  const showAction = state.loaded && state.hasExtracts;

  return (
    <>
      {showAction ? (
        <TopicNavAction
          topicNk={topicNk}
          displayText={displayText}
          isLeaf={state.isLeaf}
        />
      ) : (
        <span />
      )}
      <TopicPathInfo topicNk={topicNk} dictionaryHref={dictionaryHref} />
    </>
  );
}
