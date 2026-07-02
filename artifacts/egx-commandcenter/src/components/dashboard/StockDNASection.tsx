import React, { useState } from 'react';
import { Dna, ChevronDown, ChevronUp } from 'lucide-react';
import { useSnapshot } from '@/providers/SnapshotProvider';
import type { StockDNA } from '@/types/snapshot';

function fmt(v: number | null | undefined, decimals = 2): string {
  if (v == null) return '—';
  return v.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function signedPct(v: number | null | undefined): string {
  if (v == null) return '—';
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
}

function pctColor(v: number | null | undefined): string {
  if (v == null) return '#8b8fa8';
  return v >= 0 ? '#4caf50' : '#f44336';
}

function DNACard({ dna }: { dna: StockDNA }) {
  const totalEvents = (dna.buy_count ?? 0) + (dna.re_accum_count ?? 0);

  return (
    <div className="rounded-lg p-3.5" style={{ backgroundColor: '#181930', border: '1px solid #252645', marginBottom: '8px' }}>
      <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
        <div className="flex items-center gap-2">
          <span className="font-mono font-bold" style={{ fontSize: '14px', color: '#ffffff', letterSpacing: '1px' }}>
            {dna.ticker}
          </span>
          <span
            className="font-mono px-1.5 py-0.5 rounded"
            style={{ fontSize: '9px', backgroundColor: 'rgba(156,111,255,0.1)', color: '#9c6fff', border: '1px solid rgba(156,111,255,0.25)' }}
          >
            {dna.constitutional_memory_confidence ?? 'DEVELOPING'}
          </span>
        </div>
        <span className="font-mono font-bold" style={{ fontSize: '13px', color: pctColor(dna.avg_return_pct) }}>
          Avg {signedPct(dna.avg_return_pct)}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2">
        <div>
          <div className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8', textTransform: 'uppercase', marginBottom: '2px' }}>First BUY</div>
          <div className="font-mono" style={{ fontSize: '11px', color: '#d0d4e8' }}>{dna.first_buy_date ?? '—'}</div>
          <div className="font-mono" style={{ fontSize: '10px', color: '#8b8fa8' }}>@ {fmt(dna.first_buy_price)} EGP</div>
        </div>
        <div>
          <div className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8', textTransform: 'uppercase', marginBottom: '2px' }}>Avg Entry</div>
          <div className="font-mono font-bold" style={{ fontSize: '13px', color: '#d0d4e8' }}>{fmt(dna.avg_entry_price)} EGP</div>
          <div className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8' }}>Current: {fmt(dna.current_price)}</div>
        </div>
        <div>
          <div className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8', textTransform: 'uppercase', marginBottom: '2px' }}>Best Return</div>
          <div className="font-mono font-bold" style={{ fontSize: '13px', color: '#4caf50' }}>{signedPct(dna.best_return_pct)}</div>
          <div className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8' }}>Avg: {signedPct(dna.avg_return_pct)}</div>
        </div>
        <div>
          <div className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8', textTransform: 'uppercase', marginBottom: '2px' }}>Events</div>
          <div className="font-mono font-bold" style={{ fontSize: '13px', color: '#d0d4e8' }}>{totalEvents}</div>
          <div className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8' }}>
            {dna.buy_count ?? 0} BUY · {dna.re_accum_count ?? 0} Re-Accum
          </div>
        </div>
      </div>

      <div className="font-mono" style={{ fontSize: '10px', color: '#8b8fa8', marginTop: '4px' }}>
        Constitutional memory hits: <b style={{ color: '#d0d4e8' }}>{dna.constitutional_memory_hits ?? 0}</b>
      </div>
    </div>
  );
}

export default function StockDNASection() {
  const { snapshot, loading } = useSnapshot();
  const [collapsed, setCollapsed] = useState(true);

  const dnaMap = snapshot?.stock_dna ?? {};
  const dnaList: StockDNA[] = Object.values(dnaMap).sort(
    (a, b) => (b.avg_return_pct ?? 0) - (a.avg_return_pct ?? 0)
  );

  return (
    <div className="rounded-xl overflow-hidden" style={{ backgroundColor: '#10112a', border: '1px solid #252645' }}>
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-4 py-3.5"
        style={{ borderBottom: collapsed ? 'none' : '1px solid #252645', cursor: 'pointer', background: 'none' }}
      >
        <div className="flex items-center gap-2">
          <Dna size={13} style={{ color: '#50d8d0' }} />
          <span className="font-mono font-semibold" style={{ fontSize: '12px', color: '#d0d4e8', letterSpacing: '0.07em' }}>
            STOCK DNA
          </span>
          <span
            className="font-mono px-2 py-0.5 rounded"
            style={{ fontSize: '9px', backgroundColor: 'rgba(80,216,208,0.1)', color: '#50d8d0', border: '1px solid rgba(80,216,208,0.2)' }}
          >
            {loading ? '…' : `${dnaList.length} TICKERS`}
          </span>
        </div>
        {collapsed
          ? <ChevronDown size={13} style={{ color: '#8b8fa8' }} />
          : <ChevronUp size={13} style={{ color: '#8b8fa8' }} />}
      </button>

      {!collapsed && (
        <div className="p-3">
          {loading && (
            <div className="flex items-center justify-center py-8">
              <span className="font-mono" style={{ fontSize: '10px', color: '#8b8fa8' }}>Loading…</span>
            </div>
          )}
          {!loading && dnaList.length === 0 && (
            <div className="flex items-center justify-center py-8">
              <span className="font-mono" style={{ fontSize: '10px', color: '#8b8fa8' }}>No DNA data available.</span>
            </div>
          )}
          {dnaList.map((dna) => (
            <DNACard key={dna.ticker} dna={dna} />
          ))}
        </div>
      )}
    </div>
  );
}
