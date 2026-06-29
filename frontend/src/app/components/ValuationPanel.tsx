'use client';

import React from 'react';
import type { ValuationCard } from '@/types/snapshot';

// Generic IVE panel — renders for ANY ticker that has a fair value in the snapshot.
// Condition: valuation != null && valuation.weighted_fair_value != null
// No ticker-specific logic. Caller is responsible for the guard.
// Upside % and Margin of Safety are display transformations computed here from
// the canonical snapshot fields — they are NOT business logic.

function _pct(a: number, b: number): string {
  if (!b) return '—';
  const v = ((a - b) / b) * 100;
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
}

function _mos(fair: number, price: number): string {
  if (!fair || fair <= 0) return '—';
  const v = ((fair - price) / fair) * 100;
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
}

export default function ValuationPanel({
  valuation,
  currentPrice,
}: {
  valuation: ValuationCard;
  currentPrice: number;
}) {
  const fv = valuation.weighted_fair_value;
  if (fv == null) return null;

  const upside     = _pct(fv, currentPrice);
  const mos        = _mos(fv, currentPrice);
  const upsideNum  = currentPrice ? ((fv - currentPrice) / currentPrice) * 100 : 0;
  const upsideColor = upsideNum >= 0 ? '#10b981' : '#ef4444';

  return (
    <div
      className="px-5 py-3 flex flex-col gap-2"
      style={{ borderTop: '1px solid rgba(255,255,255,0.06)', backgroundColor: 'rgba(80,216,208,0.03)' }}
    >
      <div className="flex items-center gap-2 mb-0.5">
        <span className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8', letterSpacing: '0.07em' }}>INSTITUTIONAL VALUATION</span>
        <span
          className="font-mono px-2 py-0.5 rounded"
          style={{ fontSize: '9px', color: '#50d8d0', backgroundColor: 'rgba(80,216,208,0.1)', border: '1px solid rgba(80,216,208,0.3)' }}
        >
          {valuation.valuation_date}
        </span>
        {valuation.last_stmt_year && (
          <span className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8' }}>
            FY{valuation.last_stmt_year}
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div>
          <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8', letterSpacing: '0.07em', marginBottom: '2px' }}>FAIR VALUE</p>
          <p className="font-mono font-bold tabular-nums" style={{ fontSize: '14px', color: '#50d8d0' }}>
            {fv.toFixed(2)}
          </p>
          <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8' }}>weighted</p>
        </div>

        <div>
          <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8', letterSpacing: '0.07em', marginBottom: '2px' }}>UPSIDE</p>
          <p className="font-mono font-bold tabular-nums" style={{ fontSize: '14px', color: upsideColor }}>
            {upside}
          </p>
          <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8' }}>vs current</p>
        </div>

        <div>
          <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8', letterSpacing: '0.07em', marginBottom: '2px' }}>MARGIN OF SAFETY</p>
          <p className="font-mono font-bold tabular-nums" style={{ fontSize: '14px', color: upsideColor }}>
            {mos}
          </p>
          <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8' }}>vs fair value</p>
        </div>

        <div>
          <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8', letterSpacing: '0.07em', marginBottom: '2px' }}>SCENARIOS</p>
          <p className="font-mono tabular-nums" style={{ fontSize: '10px', color: '#10b981' }}>
            ▲ {valuation.bull_case != null ? valuation.bull_case.toFixed(2) : '—'}
          </p>
          <p className="font-mono tabular-nums" style={{ fontSize: '10px', color: '#f0b840' }}>
            ◆ {valuation.base_case != null ? valuation.base_case.toFixed(2) : '—'}
          </p>
          <p className="font-mono tabular-nums" style={{ fontSize: '10px', color: '#ef4444' }}>
            ▼ {valuation.bear_case != null ? valuation.bear_case.toFixed(2) : '—'}
          </p>
        </div>
      </div>

      {valuation.analyst_consensus_price != null && (
        <div className="flex items-center gap-2 mt-1">
          <span className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8', letterSpacing: '0.07em' }}>ANALYST CONSENSUS</span>
          <span className="font-mono font-bold tabular-nums" style={{ fontSize: '11px', color: '#a78bfa' }}>
            {valuation.analyst_consensus_price.toFixed(2)}
          </span>
          <span className="font-mono" style={{ fontSize: '9px', color: upsideColor }}>
            {_pct(valuation.analyst_consensus_price, currentPrice)} vs current
          </span>
        </div>
      )}
    </div>
  );
}
