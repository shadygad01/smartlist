'use client';

import React, { useState } from 'react';
import { Target, ChevronDown, ChevronUp, ChevronRight } from 'lucide-react';
import R2ProgressBar from './R2ProgressBar';
import { useSnapshot } from '@/providers/SnapshotProvider';

export default function NearEntrySection() {
  const { snapshot, loading } = useSnapshot();
  const [collapsed, setCollapsed] = useState(true);

  const tickers = snapshot?.near_constitutional ?? [];

  if (!loading && tickers.length === 0) return null;

  return (
    <div className="rounded-xl h-full" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', boxShadow: '0 2px 16px rgba(0,0,0,0.3)' }}>
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="section-header-btn w-full flex items-center justify-between px-4 py-3.5 rounded-t-xl"
        style={{ borderBottom: collapsed ? 'none' : '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <Target size={13} style={{ color: 'var(--signal-near)' }} />
          <span className="font-mono font-semibold" style={{ fontSize: '12px', color: 'var(--foreground)', letterSpacing: '0.07em' }}>
            NEAR CONSTITUTIONAL ENTRY
          </span>
          <span
            className="font-mono px-2 py-0.5 rounded-md"
            style={{ fontSize: '9px', backgroundColor: 'rgba(245,158,11,0.1)', color: 'var(--signal-near)', border: '1px solid rgba(245,158,11,0.2)' }}
          >
            {loading ? '…' : `${tickers.length} TICKERS`}
          </span>
        </div>
        {collapsed
          ? <ChevronDown size={13} style={{ color: 'var(--muted-foreground)' }} />
          : <ChevronUp size={13} style={{ color: 'var(--muted-foreground)' }} />}
      </button>

      {!collapsed && (
        <div className="p-3 flex flex-col gap-2">
          {loading && (
            <div className="flex items-center justify-center py-8">
              <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>Loading…</span>
            </div>
          )}

          {tickers.map((t) => (
            <div
              key={t.ticker}
              className="px-3 py-3 rounded-xl"
              style={{ backgroundColor: 'rgba(245,158,11,0.04)', border: '1px solid rgba(245,158,11,0.15)' }}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono font-bold" style={{ fontSize: '13px', color: 'var(--foreground)' }}>{t.ticker}</span>
                  <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>{t.sector}</span>
                </div>
                <ChevronRight size={12} style={{ color: 'var(--muted-foreground)' }} />
              </div>

              <div className="grid grid-cols-2 gap-2 mb-2">
                <div>
                  <p className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>ENTRY ZONE</p>
                  <p className="font-mono font-bold tabular-nums" style={{ fontSize: '14px', color: 'var(--signal-near)' }}>
                    {t.candidate_entry_zone.toFixed(2)}
                  </p>
                </div>
                <div>
                  <p className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>CURRENT</p>
                  <p className="font-mono font-bold tabular-nums" style={{ fontSize: '14px', color: 'var(--foreground)' }}>
                    {t.current_price.toFixed(2)}
                  </p>
                </div>
              </div>

              <div className="flex items-center justify-between mb-1.5">
                <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>R² SCORE</span>
                <span className="font-mono font-bold" style={{ fontSize: '11px', color: 'var(--signal-reaccum)' }}>{t.candidate_r2}</span>
              </div>
              <R2ProgressBar value={t.candidate_r2 / 100} color="var(--signal-near)" height={3} />

              <div className="flex items-center justify-between mt-2">
                <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
                  Distance to constitutional: {t.distance_to_constitutional.toFixed(1)}%
                </span>
                {t.need_move_pct === 0 && (
                  <span className="font-mono" style={{ fontSize: '9px', color: 'var(--signal-near)', fontWeight: 600 }}>AT ZONE</span>
                )}
              </div>
            </div>
          ))}

          <div
            className="flex items-center gap-2 mt-1 px-3 py-2 rounded-lg"
            style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}
          >
            <Target size={10} style={{ color: 'var(--muted-foreground)', flexShrink: 0 }} />
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
              {tickers.length} tickers near constitutional threshold · {snapshot?.market_date ?? '—'}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
