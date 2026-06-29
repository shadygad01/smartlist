'use client';

import React from 'react';
import { Target, ChevronRight } from 'lucide-react';
import R2ProgressBar from './R2ProgressBar';
import { useSnapshot } from '@/providers/SnapshotProvider';

export default function NearEntrySection() {
  const { snapshot, loading } = useSnapshot();

  const tickers = snapshot?.near_constitutional ?? [];

  return (
    <div className="rounded-xl h-full" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', boxShadow: '0 2px 16px rgba(0,0,0,0.3)' }}>
      <div className="flex items-center justify-between px-4 py-3.5" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="flex items-center gap-2">
          <Target size={13} style={{ color: 'var(--signal-near)' }} />
          <span className="font-mono font-semibold" style={{ fontSize: '12px', color: 'var(--foreground)', letterSpacing: '0.07em' }}>
            NEAR CONSTITUTIONAL ENTRY
          </span>
        </div>
        <span
          className="font-mono px-2 py-0.5 rounded-md"
          style={{ fontSize: '9px', backgroundColor: 'rgba(245,158,11,0.1)', color: 'var(--signal-near)', border: '1px solid rgba(245,158,11,0.2)' }}
        >
          {loading ? '…' : `${tickers.length} TICKERS`}
        </span>
      </div>

      <div className="p-3 flex flex-col gap-2">
        {loading && (
          <div className="flex items-center justify-center py-8">
            <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>Loading…</span>
          </div>
        )}

        {!loading && tickers.length === 0 && (
          <div className="flex items-center justify-center py-8">
            <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>No near-constitutional tickers this scan.</span>
          </div>
        )}

        {tickers.map((t) => {
          const mpi = snapshot?.mpi_behavior?.[t.ticker];
          const phaseColors: Record<string, string> = { Fear: '#f44336', Greed: '#4caf50', Accumulation: '#50d8d0', Distribution: '#f0b840' };
          const phaseColor = mpi ? (phaseColors[mpi.phase] ?? '#9c6fff') : undefined;
          return (
          <div
            key={t.ticker}
            className="px-3 py-3 rounded-xl"
            style={{ backgroundColor: 'rgba(245,158,11,0.04)', border: '1px solid rgba(245,158,11,0.15)' }}
          >
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="font-mono font-bold" style={{ fontSize: '13px', color: 'var(--foreground)' }}>{t.ticker}</span>
                <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>{t.sector}</span>
                {mpi && phaseColor && (
                  <span className="font-mono font-bold px-1.5 py-0.5 rounded" style={{ fontSize: '9px', color: phaseColor, backgroundColor: `${phaseColor}18`, border: `1px solid ${phaseColor}44` }}>
                    {mpi.phase.toUpperCase()}
                  </span>
                )}
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

            {mpi && (
              <div className="mt-2 pt-2" style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}>
                <p className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8', lineHeight: 1.5 }}>{mpi.explanation}</p>
                {mpi.historical_cases > 0 && (
                  <p className="font-mono mt-1" style={{ fontSize: '9px', color: '#8b8fa8', opacity: 0.7 }}>
                    {Math.round((mpi.similarity_score ?? 0) * 100)}% similarity · Avg MFE40 +{(mpi.avg_mfe40 ?? 0).toFixed(0)}% · {mpi.historical_cases} cases
                  </p>
                )}
              </div>
            )}
          </div>
          );
        })}

        <div
          className="flex items-center gap-2 mt-1 px-3 py-2 rounded-lg"
          style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}
        >
          <Target size={10} style={{ color: 'var(--muted-foreground)', flexShrink: 0 }} />
          <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
            Reward score: {snapshot?.statistics?.near_constitutional_count ?? 0} tickers near constitutional threshold · {snapshot?.market_date ?? '—'}
          </span>
        </div>
      </div>
    </div>
  );
}
