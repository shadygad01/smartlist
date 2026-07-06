import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import type { ProductionSnapshot } from '@/types/snapshot';

const SNAPSHOT_URL =
  import.meta.env.VITE_SNAPSHOT_URL ?? '/presentation_snapshot.json';

const REFRESH_INTERVAL_MS = 60_000;

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

export default function SnapshotProvider({ children }: { children: React.ReactNode }) {
  const [snapshot, setSnapshot] = useState<ProductionSnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSnapshot = useCallback(async () => {
    try {
      // `cache: 'no-store'` only governs the browser's own HTTP cache — GitHub
      // Pages' CDN can still serve a stale cached copy of this fixed URL to a
      // fresh request. A per-request cache-busting query param gives every
      // fetch a distinct CDN cache key so it can never be served from a stale
      // edge cache.
      const res = await fetch(`${SNAPSHOT_URL}?t=${Date.now()}`, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status} fetching snapshot`);
      const data: ProductionSnapshot = await res.json();
      setSnapshot(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Snapshot unavailable');
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
