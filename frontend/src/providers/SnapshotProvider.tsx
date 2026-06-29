'use client';

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import type { ProductionSnapshot } from '@/types/snapshot';

interface SnapshotContextValue {
  snapshot: ProductionSnapshot | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

const SnapshotContext = createContext<SnapshotContextValue>({
  snapshot: null,
  loading: true,
  error: null,
  refresh: () => {},
});

export function useSnapshot(): SnapshotContextValue {
  return useContext(SnapshotContext);
}

const REFRESH_INTERVAL_MS = 60_000;

export default function SnapshotProvider({ children }: { children: React.ReactNode }) {
  const [snapshot, setSnapshot] = useState<ProductionSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSnapshot = useCallback(async () => {
    try {
      const res = await fetch('/api/snapshot', { cache: 'no-store' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body?.error ?? `HTTP ${res.status}`);
      }
      const data: ProductionSnapshot = await res.json();
      setSnapshot(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSnapshot();
    const id = setInterval(fetchSnapshot, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [fetchSnapshot]);

  return (
    <SnapshotContext.Provider value={{ snapshot, loading, error, refresh: fetchSnapshot }}>
      {children}
    </SnapshotContext.Provider>
  );
}
