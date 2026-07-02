import React, { useState } from 'react';
import { Target, ChevronDown, ChevronUp, ChevronRight } from 'lucide-react';
import R2ProgressBar from './R2ProgressBar';
import { useSnapshot } from '@/providers/SnapshotProvider';

export default function NearEntrySection() {
  const { snapshot, loading } = useSnapshot();
  const [collapsed, setCollapsed] = useState(true);

  const tickers = snapshot?.near_constitutional ?? [];

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
            style={{ fontSize: '9px', backgroundColor: 'rgba(245,158,11,0.08)', color: 'var(--signal-near)', border: '1px solid rgba(245,158,11,0.2)' }}
          >
            {loading ? '…' : `${tickers.length} TICKERS`}
          </span>
        </div>
        {collapsed
          ? <ChevronDown size={13} style={{ color: 'var(--muted-foreground)' }} />
          : <ChevronUp size={13} style={{ color: 'var(--muted-foreground)' }} />}
      </button>

      {!collapsed && (
        <div className="p-3 flex flex-col gap-1.5">
          {loading ? (
            <div className="flex items-center justify-center py-6">
              <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>Loading…</span>
            </div>
          ) : tickers.length === 0 ? (
            <div className="flex items-center justify-center py-6">
              <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>No near-entry tickers.</span>
            </div>
          ) : (
            tickers.map((t) => (
              <div
                key={t.ticker}
                className="flex flex-col gap-1.5 px-3 py-2.5 rounded-xl"
                style={{ backgroundColor: 'rgba(245,158,11,0.03)', border: '1px solid rgba(245,158,11,0.12)' }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold" style={{ fontSize: '13px', color: 'var(--foreground)' }}>{t.ticker}</span>
                    <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>{t.sector}</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <ChevronRight size={10} style={{ color: 'var(--signal-near)' }} />
                    <span className="font-mono font-bold tabular-nums" style={{ fontSize: '11px', color: 'var(--signal-near)' }}>
                      {t.need_move_pct != null ? `${t.need_move_pct > 0 ? '+' : ''}${t.need_move_pct.toFixed(1)}%` : '—'}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div>
                    <span className="font-mono" style={{ fontSize: '8px', color: 'var(--muted-foreground)' }}>ZONE</span>
                    <span className="font-mono font-semibold tabular-nums ml-1" style={{ fontSize: '11px', color: 'var(--signal-buy)' }}>
                      {t.candidate_entry_zone.toFixed(2)}
                    </span>
                  </div>
                  <div>
                    <span className="font-mono" style={{ fontSize: '8px', color: 'var(--muted-foreground)' }}>NOW</span>
                    <span className="font-mono tabular-nums ml-1" style={{ fontSize: '11px', color: 'var(--foreground)' }}>
                      {t.current_price.toFixed(2)}
                    </span>
                  </div>
                  <div className="ml-auto">
                    <span className="font-mono" style={{ fontSize: '8px', color: 'var(--muted-foreground)' }}>R²</span>
                    <span className="font-mono font-semibold tabular-nums ml-1" style={{ fontSize: '11px', color: 'var(--signal-reaccum)' }}>
                      {t.candidate_r2}
                    </span>
                  </div>
                </div>
                <R2ProgressBar value={t.candidate_r2 / 100} color="var(--signal-near)" height={3} />
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
