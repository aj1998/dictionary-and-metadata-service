'use client';

import { useEffect } from 'react';
import { useGraphStore } from '@/lib/store/graphStore';
import { TableModal } from '@/components/TableModal';

export function BhaavarthTableLinkHost() {
  const tableModalNk = useGraphStore((s) => s.tableModalNk);
  const openTableModal = useGraphStore((s) => s.openTableModal);
  const closeTableModal = useGraphStore((s) => s.closeTableModal);

  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;
      if (!target) return;
      const btn = target.closest('[data-bhaavarth-table-nk]') as HTMLElement | null;
      if (!btn) return;
      const nk = btn.getAttribute('data-bhaavarth-table-nk');
      if (!nk) return;
      e.preventDefault();
      openTableModal(decodeURIComponent(nk));
    };
    document.addEventListener('click', onClick);
    return () => document.removeEventListener('click', onClick);
  }, [openTableModal]);

  return <TableModal naturalKey={tableModalNk} onClose={closeTableModal} />;
}
