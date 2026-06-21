'use client';

import { TopicNavAction } from '@/components/TopicNavAction';
import { TopicPathInfo } from '@/components/TopicPathInfo';

interface Props {
  topicNk: string;
  displayText: string;
  dictionaryHref?: string;
  // query_engine/08 Part E: content/leaf signals come from the topics_match
  // result itself — no per-card getEntityDetail round-trip.
  extractCount: number;
  isLeaf: boolean;
}

export function TopicMatchActions({
  topicNk,
  displayText,
  dictionaryHref,
  extractCount,
  isLeaf,
}: Props) {
  const hasExtracts = extractCount > 0;
  // Render the action group when there is anything to show: पढ़ें (has extracts)
  // and/or the expand link (non-leaf). Detail is fetched lazily on click.
  const showAction = hasExtracts || !isLeaf;

  return (
    <>
      {showAction ? (
        <TopicNavAction
          topicNk={topicNk}
          displayText={displayText}
          isLeaf={isLeaf}
          hasExtracts={hasExtracts}
        />
      ) : (
        <span />
      )}
      <TopicPathInfo topicNk={topicNk} dictionaryHref={dictionaryHref} />
    </>
  );
}
