import React, { useState } from 'react';
import { RefreshCw, TrendingUp, ChevronDown, ChevronUp, Clock } from 'lucide-react';
import { useSnapshot } from '@/providers/SnapshotProvider';
import type { ReAccumulationEvent, StockDNA, MPIBehavior, ValuationCard } from '@/types/snapshot';
import R2ProgressBar from './R2ProgressBar';
import SeenBeforePanel from './SeenBeforePanel';
import ValuationPanel from './ValuationPanel';

function statusStyle(status: string): { color: string; bg: string; border: string } {
  if (status === 'PREMIUM_NOW')  return { color: '#a78bfa', bg: 'rgba(167,139,250,0.12)', border: 'rgba(167,139,250,0.3)' };
  if (status === 'ACTIVE')       return { color: 'var(--signal-buy)', bg: 'rgba(16,185,129,0.08)', border: 'rgba(16,185,129,0.25)' };
  if (status === 'CLOSED_WIN')   return { color: 'var(--signal-buy)', bg: 'rgba(16,185,129,0.08)', border: 'rgba(16,185,129,0.2)' };
  if (status === 'CLOSED_LOSS')  return { color: '#ef4444', bg: 'rgba(239,68,68,0.08)', border: 'rgba(239,68,68,0.2)' };
  return { color: 'var(--muted-foreground)', bg: 'rgba(255,255,255,0.04)', border: 'var(--border)' };
}

function EventCard({
  evt, dna, mpi, valuation,
}: {
  evt: ReAccumulationEvent;
  dna?: StockDNA;
  mpi?: MPIBehavior;
  valuation?: ValuationCard;
}) {
  const [expanded, setExpanded] = useState(false);
  const sc = statusStyle(evt.status);
  const retPos = evt.return_pct >= 0;

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ backgroundColor: 'rgba(255,255,255,0.015)', border: '1px solid var(--border-subtle)' }}
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-3 py-2.5 text-left"
        style={{ background: 'none', cursor: 'pointer' }}
      >
        <span className="font-mono font-bold flex-shrink-0" style={{ fontSize: '13px', color: 'var(--foreground)', width: '96px' }}>{evt.ticker}</span>
        <span className="font-mono flex-shrink-0 tabular-nums" style={{ fontSize: '12px', color: 'var(--signal-buy)', width: '72px' }}>
          {evt.constitutional_entry_price.toFixed(2)}
        </span>
        <span className="font-mono flex-shrink-0 tabular-nums" style={{ fontSize: '12px', color: 'var(--foreground)', width: '64px' }}>
          {evt.current_price.toFixed(2)}
        </span>
        <div className="flex items-center gap-1 flex-shrink-0" style={{ width: '60px' }}>
          <span className="font-mono font-bold tabular-nums" style={{ fontSize: '12px', color: retPos ? 'var(--signal-buy)' : '#ef4444' }}>
            {retPos ? '+' : ''}{evt.return_pct.toFixed(1)}%
          </span>
        </div>
        <span className="font-mono tabular-nums flex-shrink-0" style={{ fontSize: '10px', color: 'var(--signal-reaccum)', width: '48px' }}>
          R²{evt.constitutional_r2.toFixed(1)}
        </span>
        <div className="flex items-center gap-1 flex-shrink-0" style={{ width: '44px' }}>
          <Clock size={9} style={{ color: 'var(--muted-foreground)' }} />
          <span className="font-mono tabular-nums" style={{ fontSize: '10px', color: 'var(--foreground)' }}>{evt.days_active}d</span>
        </div>
        <span
          className="font-mono font-semibold px-2 py-0.5 rounded-md ml-auto flex-shrink-0"
          style={{ fontSize: '9px', backgroundColor: sc.bg, color: sc.color, border: `1px solid ${sc.border}` }}
        >
          {evt.status}
        </span>
        {expanded ? <ChevronUp size={11} style={{ color: 'var(--muted-foreground)', flexShrink: 0 }} /> : <ChevronDown size={11} style={{ color: 'var(--muted-foreground)', flexShrink: 0 }} />}
      </button>

      {expanded && (
        <div style={{ borderTop: '1px solid var(--border-subtle)' }}>
          <div className="px-3 py-2 grid grid-cols-2 md:grid-cols-4 gap-2">
            <div>
              <p className="font-mono" style={{ fontSize: '8px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>SECTOR</p>
              <p className="font-mono" style={{ fontSize: '11px', color: 'var(--foreground)' }}>{evt.sector}</p>
            </div>
            <div>
              <p className="font-mono" style={{ fontSize: '8px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>EVENT DATE</p>
              <p className="font-mono" style={{ fontSize: '11px', color: 'var(--foreground)' }}>{evt.event_date}</p>
            </div>
            <div>
              <p className="font-mono" style={{ fontSize: '8px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>PEAK RETURN</p>
              <p className="font-mono font-bold" style={{ fontSize: '11px', color: '#a78bfa' }}>+{evt.peak_return_pct.toFixed(1)}%</p>
            </div>
            <div>
              <p className="font-mono" style={{ fontSize: '8px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>SCORE</p>
              <p className="font-mono font-bold" style={{ fontSize: '11px', color: 'var(--signal-reaccum)' }}>{evt.constitutional_score.toFixed(1)}</p>
            </div>
          </div>
          <div className="px-3 pb-2">
            <R2ProgressBar value={evt.constitutional_r2 / 100} color="var(--signal-reaccum)" height={3} />
          </div>
          {dna && dna.constitutional_memory_hits > 0 && <SeenBeforePanel dna={dna} mpi={mpi} />}
          {valuation && valuation.weighted_fair_value != null && (
            <ValuationPanel valuation={valuation} currentPrice={evt.current_price} />
          )}
        </div>
      )}
    </div>
  );
}

export default function ReAccumulationSection() {
  const { snapshot, loading } = useSnapshot();
  const [collapsed, setCollapsed] = useState(true);

  const events        = snapshot?.re_accumulation ?? [];
  const dnaMap        = snapshot?.stock_dna ?? {};
  const mpiMap        = snapshot?.mpi_behavior ?? {};
  const valuationMap  = snapshot?.valuation ?? {};

  if (!loading && events.length === 0) return null;

  return (
    <div className="rounded-xl" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', boxShadow: '0 2px 16px rgba(0,0,0,0.3)' }}>
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="section-header-btn w-full flex items-center justify-between px-4 py-3.5 rounded-t-xl"
        style={{ borderBottom: collapsed ? 'none' : '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <RefreshCw size={13} style={{ color: '#a78bfa' }} />
          <span className="font-mono font-semibold" style={{ fontSize: '12px', color: 'var(--foreground)', letterSpacing: '0.07em' }}>
            RE-ACCUMULATION EVENTS
          </span>
          <span
            className="font-mono px-2 py-0.5 rounded-md"
            style={{ fontSize: '9px', backgroundColor: 'rgba(167,139,250,0.1)', color: '#a78bfa', border: '1px solid rgba(167,139,250,0.2)' }}
          >
            {loading ? '…' : `${events.length} EVENTS`}
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
          ) : (
            <>
              <div className="flex items-center gap-3 px-3 pb-1">
                <span className="font-mono flex-shrink-0" style={{ fontSize: '9px', color: 'var(--muted-foreground)', width: '96px', letterSpacing: '0.07em' }}>TICKER / SECTOR</span>
                <span className="font-mono flex-shrink-0" style={{ fontSize: '9px', color: 'var(--muted-foreground)', width: '72px', letterSpacing: '0.07em' }}>ENTRY</span>
                <span className="font-mono flex-shrink-0" style={{ fontSize: '9px', color: 'var(--muted-foreground)', width: '64px', letterSpacing: '0.07em' }}>CURRENT</span>
                <span className="font-mono flex-shrink-0" style={{ fontSize: '9px', color: 'var(--muted-foreground)', width: '60px', letterSpacing: '0.07em' }}>RETURN</span>
                <span className="font-mono flex-shrink-0" style={{ fontSize: '9px', color: 'var(--muted-foreground)', width: '48px', letterSpacing: '0.07em' }}>R²</span>
                <span className="font-mono flex-shrink-0" style={{ fontSize: '9px', color: 'var(--muted-foreground)', width: '44px', letterSpacing: '0.07em' }}>DAYS</span>
                <span className="font-mono ml-auto flex-shrink-0" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>STATUS</span>
              </div>
              {events.map((evt) => (
                <EventCard
                  key={evt.event_id}
                  evt={evt}
                  dna={dnaMap[evt.ticker]}
                  mpi={mpiMap[evt.ticker]}
                  valuation={valuationMap[evt.ticker]}
                />
              ))}
            </>
          )}
          <div
            className="flex items-center gap-2 mt-1 px-3 py-2 rounded-lg"
            style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}
          >
            <TrendingUp size={10} style={{ color: 'var(--muted-foreground)', flexShrink: 0 }} />
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
              {events.length} constitutional re-accumulation events · scan {snapshot?.scan_id?.slice(0, 8) ?? '—'} · {snapshot?.market_date ?? '—'}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
