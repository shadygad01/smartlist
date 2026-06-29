'use client';

import React, { useState } from 'react';
import { BarChart2, ChevronDown, ChevronUp, TrendingUp, TrendingDown } from 'lucide-react';
import { useSnapshot } from '@/providers/SnapshotProvider';

// Renamed to Active Positions — renders from the 'active' array in the production snapshot.
// No DNA metrics exist in the snapshot; no values are computed locally.
export default function StockDNASection() {
  const { snapshot, loading } = useSnapshot();
  const [collapsed, setCollapsed] = useState(false);

  const positions = snapshot?.active ?? [];

  return (
    <div className="rounded-xl" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', boxShadow: '0 2px 16px rgba(0,0,0,0.3)' }}>
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="section-header-btn w-full flex items-center justify-between px-4 py-3.5 rounded-t-xl"
        style={{ borderBottom: collapsed ? 'none' : '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <BarChart2 size={13} style={{ color: '#a78bfa' }} />
          <span className="font-mono font-semibold" style={{ fontSize: '12px', color: 'var(--foreground)', letterSpacing: '0.07em' }}>
            ACTIVE POSITIONS
          </span>
          <span
            className="font-mono px-2 py-0.5 rounded-md"
            style={{ fontSize: '9px', backgroundColor: 'rgba(167,139,250,0.1)', color: '#a78bfa', border: '1px solid rgba(167,139,250,0.2)' }}
          >
            {loading ? '…' : `${positions.length}`}
          </span>
        </div>
        {collapsed ? <ChevronDown size={13} style={{ color: 'var(--muted-foreground)' }} /> : <ChevronUp size={13} style={{ color: 'var(--muted-foreground)' }} />}
      </button>

      {!collapsed && (
        <div className="p-3 flex flex-col gap-1.5">
          {loading && (
            <div className="flex items-center justify-center py-8">
              <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>Loading…</span>
            </div>
          )}

          {!loading && positions.length === 0 && (
            <div className="flex items-center justify-center py-8">
              <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>No active positions in snapshot.</span>
            </div>
          )}

          {positions.map((pos) => {
            const isPositive = pos.return_pct != null && pos.return_pct >= 0;
            const returnColor = pos.return_pct == null ? 'var(--muted-foreground)'
              : isPositive ? 'var(--signal-buy)' : '#ef4444';

            return (
              <div
                key={pos.ticker}
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl"
                style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}
              >
                <div className="flex flex-col flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-mono font-bold" style={{ fontSize: '12px', color: 'var(--foreground)' }}>{pos.ticker}</span>
                    <span className="font-mono" style={{ fontSize: '8px', color: 'var(--muted-foreground)' }}>{pos.status}</span>
                  </div>
                  <span className="font-mono truncate" style={{ fontSize: '9px', color: 'var(--muted-foreground)', marginTop: '2px' }}>
                    {pos.action}
                  </span>
                </div>

                <div className="flex flex-col items-end flex-shrink-0">
                  <span className="font-mono font-bold tabular-nums" style={{ fontSize: '13px', color: 'var(--foreground)' }}>
                    {pos.current_price.toFixed(2)}
                  </span>
                  <div className="flex items-center gap-1">
                    {pos.return_pct != null && (
                      isPositive
                        ? <TrendingUp size={9} style={{ color: returnColor }} />
                        : <TrendingDown size={9} style={{ color: returnColor }} />
                    )}
                    <span className="font-mono tabular-nums" style={{ fontSize: '10px', color: returnColor }}>
                      {pos.return_pct != null ? `${pos.return_pct.toFixed(1)}%` : '—'}
                    </span>
                  </div>
                </div>
              </div>
            );
          })}

          <div
            className="flex items-center gap-2 mt-1 px-3 py-2 rounded-lg"
            style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}
          >
            <BarChart2 size={10} style={{ color: 'var(--muted-foreground)', flexShrink: 0 }} />
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
              {positions.length} active positions · constitutional entry prices · {snapshot?.price_data_as_of ?? '—'}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
