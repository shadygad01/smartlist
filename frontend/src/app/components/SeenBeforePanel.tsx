'use client';

import React, { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import type { StockDNA, MPIBehavior } from '@/types/snapshot';

// Generic SeenBeforePanel — renders for ANY ticker that has constitutional history.
// Condition: dna.constitutional_memory_hits > 0
// No ticker-specific logic. Caller is responsible for the guard.

const confColor: Record<string, string> = {
  STRONG: '#10b981', CONFIRMED: '#50d8d0', DEVELOPING: '#f0b840', MONITORING: '#8b8fa8',
};

export default function SeenBeforePanel({ dna, mpi }: { dna: StockDNA; mpi?: MPIBehavior }) {
  const [collapsed, setCollapsed] = useState(true);
  const color = confColor[dna.constitutional_memory_confidence] ?? '#8b8fa8';
  const totalEvents = dna.buy_count + dna.re_accum_count;

  return (
    <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', backgroundColor: 'rgba(0,0,0,0.15)' }}>
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-5 py-2.5"
        style={{ background: 'none', cursor: 'pointer' }}
      >
        <div className="flex items-center gap-2">
          <span className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8', letterSpacing: '0.07em' }}>SEEN BEFORE</span>
          <span
            className="font-mono font-bold px-2 py-0.5 rounded"
            style={{ fontSize: '10px', color, backgroundColor: `${color}18`, border: `1px solid ${color}44` }}
          >
            {dna.constitutional_memory_hits}× &nbsp;{dna.constitutional_memory_confidence}
          </span>
        </div>
        {collapsed
          ? <ChevronDown size={11} style={{ color: '#8b8fa8' }} />
          : <ChevronUp size={11} style={{ color: '#8b8fa8' }} />}
      </button>

      {!collapsed && (
        <div className="px-5 pb-3 flex flex-col gap-2">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8', letterSpacing: '0.07em', marginBottom: '2px' }}>HISTORICAL EXPECTANCY</p>
              <p className="font-mono font-bold tabular-nums" style={{ fontSize: '13px', color: '#10b981' }}>
                {dna.avg_return_pct > 0 ? '+' : ''}{dna.avg_return_pct.toFixed(1)}%
              </p>
              <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8' }}>{totalEvents} event{totalEvents !== 1 ? 's' : ''}</p>
            </div>
            <div>
              <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8', letterSpacing: '0.07em', marginBottom: '2px' }}>AVG MFE40</p>
              <p className="font-mono font-bold tabular-nums" style={{ fontSize: '13px', color: '#50d8d0' }}>
                {mpi && mpi.avg_mfe40 != null ? `+${mpi.avg_mfe40.toFixed(0)}%` : '—'}
              </p>
              {mpi && mpi.historical_cases > 0 && (
                <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8' }}>{mpi.historical_cases} analogs</p>
              )}
            </div>
            <div>
              <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8', letterSpacing: '0.07em', marginBottom: '2px' }}>BEST / WORST</p>
              <p className="font-mono font-bold tabular-nums" style={{ fontSize: '13px', color: '#10b981' }}>
                +{dna.best_return_pct.toFixed(1)}%
              </p>
              <p className="font-mono tabular-nums" style={{ fontSize: '10px', color: '#f44336' }}>
                {dna.worst_return_pct != null && dna.worst_return_pct < 0
                  ? `${dna.worst_return_pct.toFixed(1)}%`
                  : dna.worst_return_pct != null
                  ? `+${dna.worst_return_pct.toFixed(1)}%`
                  : '—'}
              </p>
            </div>
            <div>
              <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8', letterSpacing: '0.07em', marginBottom: '2px' }}>LAST SIGNAL</p>
              <p className="font-mono font-bold tabular-nums" style={{ fontSize: '12px', color: '#8b8fa8' }}>
                {dna.last_event_date ?? dna.first_buy_date ?? '—'}
              </p>
              <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8' }}>First: {dna.first_buy_date ?? '—'}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
