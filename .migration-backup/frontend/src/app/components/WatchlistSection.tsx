'use client';

import React from 'react';
import { Eye } from 'lucide-react';
import { useSnapshot } from '@/providers/SnapshotProvider';

export default function WatchlistSection() {
  const { snapshot, loading } = useSnapshot();

  const tickers = snapshot?.watchlist ?? [];

  if (!loading && tickers.length === 0) return null;

  return (
    <div
      className="rounded-xl"
      style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', boxShadow: '0 2px 16px rgba(0,0,0,0.3)' }}
    >
      <div className="flex items-center justify-between px-4 py-3.5" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="flex items-center gap-2">
          <Eye size={13} style={{ color: 'var(--signal-near)' }} />
          <span className="font-mono font-semibold" style={{ fontSize: '12px', color: 'var(--foreground)', letterSpacing: '0.07em' }}>
            WATCH LIST
          </span>
        </div>
        <span
          className="font-mono px-2 py-0.5 rounded-md"
          style={{ fontSize: '9px', backgroundColor: 'rgba(245,158,11,0.1)', color: 'var(--signal-near)', border: '1px solid rgba(245,158,11,0.2)' }}
        >
          {loading ? '…' : `${tickers.length} TICKERS`}
        </span>
      </div>

      <div className="px-4 py-3">
        <p className="font-mono mb-3" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>
          Track for future portfolio additions.
        </p>
        <div className="flex flex-wrap gap-2">
          {loading ? (
            <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>Loading…</span>
          ) : (
            tickers.map((ticker) => (
              <span
                key={ticker}
                className="font-mono font-semibold px-3 py-1.5 rounded-lg"
                style={{
                  fontSize: '12px',
                  color: 'var(--foreground)',
                  backgroundColor: 'rgba(255,255,255,0.04)',
                  border: '1px solid var(--border)',
                }}
              >
                {ticker}
              </span>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
