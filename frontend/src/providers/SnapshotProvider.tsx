'use client';

import React, { createContext, useContext, useEffect, useState, useCallback } from 'react';
import type { ProductionSnapshot } from '@/types/snapshot';

// Static file is served under basePath (/smartlist) on GitHub Pages and dev server.
// Construct the correct path by reading the basePath from env (set in next.config.mjs).
// Override entirely with NEXT_PUBLIC_SNAPSHOT_URL for custom deployments.
const _basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? '';
const SNAPSHOT_URL =
  process.env.NEXT_PUBLIC_SNAPSHOT_URL ?? `${_basePath}/presentation_snapshot.json`;

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
      const res = await fetch(SNAPSHOT_URL, { cache: 'no-store' });
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
