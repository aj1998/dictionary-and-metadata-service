'use client';

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

export type MentionedKind = 'topics' | 'keywords';

export interface MentionedRequest {
  kind: MentionedKind;
  sourceNk: string;
  sourceLabel: string;
}

interface ReaderActionsValue {
  request: MentionedRequest | null;
  open: (req: MentionedRequest) => void;
  close: () => void;
}

const Ctx = createContext<ReaderActionsValue | null>(null);

export function ReaderActionsProvider({ children }: { children: ReactNode }) {
  const [request, setRequest] = useState<MentionedRequest | null>(null);
  const open = useCallback((req: MentionedRequest) => setRequest(req), []);
  const close = useCallback(() => setRequest(null), []);
  const value = useMemo(() => ({ request, open, close }), [request, open, close]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useReaderActions(): ReaderActionsValue {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useReaderActions must be used inside ReaderActionsProvider');
  return ctx;
}
