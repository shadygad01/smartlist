'use client';

import React, { useState } from 'react';
import { RefreshCw, ChevronDown, ChevronUp, TrendingUp } from 'lucide-react';
import SeenBeforePanel from './SeenBeforePanel';
import ValuationPanel from './ValuationPanel';
import { useSnapshot } from '@/providers/SnapshotProvider';
import type { ReAccumulationEvent, StockDNA, MPIBehavior, ValuationCard } from '@/types/snapshot';

function statusColor(status: string): string {
  if (status === 'PREMIUM_NOW') return '#a78bfa';
  if (status === 'ACTIVE')      return 'var(--signal-buy)';
  if (status === 'CLOSED_WIN')  return 'var(--signal-buy)';
  if (status === 'CLOSED_LOSS') return '#ef4444';
  return 'var(--muted-foreground)';
}

function EventCard({ evt, dna, mpi, valuation }: { evt: ReAccumulationEvent; dna?: StockDNA; mpi?: MPIBehavior; valuation?: ValuationCard }) {
  const retColor = evt.return_pct >= 0 ? 'var(--signal-buy)' : '#ef4444';
  const sign = evt.return_pct >= 0 ? '+' : '';
  const hasDna = dna != null && dna.constitutional_memory_hits > 0;
  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{ backgroundColor: 'rgba(167,139,250,0.04)', border: '1px solid rgba(167,139,250,0.12)' }}
    >
      {/* Compact metrics row */}
      <div className="flex items-center gap-3 px-3 py-2.5">
        {/* Ticker + sector */}
        <div className="flex flex-col flex-shrink-0" style={{ width: '96px' }}>
          <span className="font-mono font-bold" style={{ fontSize: '12px', color: 'var(--foreground)' }}>{evt.ticker}</span>
          <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>{evt.sector}</span>
        </div>

        {/* Entry + current */}
        <div className="flex flex-col flex-shrink-0" style={{ width: '72px' }}>
          <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.06em' }}>ENTRY</span>
          <span className="font-mono tabular-nums font-semibold" style={{ fontSize: '11px', color: 'var(--foreground)' }}>
            {evt.constitutional_entry_price.toFixed(2)}
          </span>
        </div>

        <div className="flex flex-col flex-shrink-0" style={{ width: '64px' }}>
          <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.06em' }}>NOW</span>
          <span className="font-mono tabular-nums font-semibold" style={{ fontSize: '11px', color: 'var(--foreground)' }}>
            {evt.current_price.toFixed(2)}
          </span>
        </div>

        {/* Return */}
        <div className="flex flex-col flex-shrink-0" style={{ width: '60px' }}>
          <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.06em' }}>RETURN</span>
          <span className="font-mono tabular-nums font-bold" style={{ fontSize: '12px', color: retColor }}>
            {sign}{evt.return_pct.toFixed(1)}%
          </span>
        </div>

        {/* R2 */}
        <div className="flex flex-col flex-shrink-0" style={{ width: '48px' }}>
          <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.06em' }}>R²</span>
          <span className="font-mono tabular-nums" style={{ fontSize: '11px', color: 'var(--signal-reaccum)' }}>
            {evt.constitutional_r2.toFixed(1)}
          </span>
        </div>

        {/* Days */}
        <div className="flex flex-col flex-shrink-0" style={{ width: '44px' }}>
          <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.06em' }}>DAYS</span>
          <span className="font-mono tabular-nums" style={{ fontSize: '11px', color: 'var(--foreground)' }}>
            {evt.days_active}
          </span>
        </div>

        {/* Status */}
        <span
          className="font-mono ml-auto flex-shrink-0"
          style={{ fontSize: '9px', color: statusColor(evt.status), letterSpacing: '0.06em' }}
        >
          {evt.status}
        </span>
      </div>

      {/* Seen Before — generic: renders whenever constitutional history exists */}
      {hasDna && <SeenBeforePanel dna={dna!} mpi={mpi} />}

      {/* IVE Valuation — generic: renders whenever fair value exists in snapshot */}
      {valuation && valuation.weighted_fair_value != null && (
        <ValuationPanel valuation={valuation} currentPrice={evt.current_price} />
      )}
    </div>
  );
}

export default function ReAccumulationSection() {
  const { snapshot, loading } = useSnapshot();
  const [collapsed, setCollapsed] = useState(false);

  const events        = snapshot?.re_accumulation ?? [];
  const dnaMap        = snapshot?.stock_dna ?? {};
  const mpiMap        = snapshot?.mpi_behavior ?? {};
  const valuationMap  = snapshot?.valuation ?? {};

  if (!loading && events.length === 0) return null;

  return (
    <div
      className="rounded-xl"
      style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', boxShadow: '0 2px 16px rgba(0,0,0,0.3)' }}
    >
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
              {/* Column headers */}
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
