'use client';

import { type ReactNode } from 'react';
import { ReaderActionsProvider, useReaderActions } from './ReaderActionsContext';
import { MentionedRightColumn } from './MentionedRightColumn';

interface InnerProps {
  main: ReactNode;
  sidebar: ReactNode;
}

function Inner({ main, sidebar }: InnerProps) {
  const { request } = useReaderActions();
  const showRight = request !== null;
  // Default 2-col 40/60. When right column opens, 40/30/30.
  const gridCols = showRight
    ? 'lg:grid-cols-[minmax(0,40fr)_minmax(0,30fr)_minmax(0,30fr)]'
    : 'lg:grid-cols-[minmax(0,40fr)_minmax(0,60fr)]';
  return (
    <div className={`grid gap-6 ${gridCols}`}>
      {main}
      {sidebar}
      {showRight && <MentionedRightColumn />}
    </div>
  );
}

export function GathaReaderLayout(props: InnerProps) {
  return (
    <ReaderActionsProvider>
      <Inner {...props} />
    </ReaderActionsProvider>
  );
}
