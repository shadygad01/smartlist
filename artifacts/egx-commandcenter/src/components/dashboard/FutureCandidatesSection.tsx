import React, { useState } from 'react';
import { Hourglass, ChevronDown, ChevronUp } from 'lucide-react';
import { useSnapshot } from '@/providers/SnapshotProvider';

export default function FutureCandidatesSection() {
  const { snapshot, loading } = useSnapshot();
  const [collapsed, setCollapsed] = useState(true);
  const candidates = snapshot?.future_candidates ?? [];

  if (!loading && candidates.length === 0) return null;

  return (
    <div className="rounded-xl" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', boxShadow: '0 2px 16px rgba(0,0,0,0.3)' }}>
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="section-header-btn w-full flex items-center justify-between px-4 py-3.5 rounded-t-xl"
        style={{ borderBottom: collapsed ? 'none' : '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <Hourglass size={13} style={{ color: 'var(--muted-foreground)' }} />
          <span className="font-mono font-semibold" style={{ fontSize: '12px', color: 'var(--foreground)', letterSpacing: '0.07em' }}>
            FUTURE CANDIDATES
          </span>
          <span className="font-mono px-2 py-0.5 rounded-md" style={{ fontSize: '9px', backgroundColor: 'rgba(255,255,255,0.04)', color: 'var(--muted-foreground)', border: '1px solid var(--border)' }}>
            {loading ? '…' : `${candidates.length} TICKERS`}
          </span>
        </div>
        {collapsed ? <ChevronDown size={13} style={{ color: 'var(--muted-foreground)' }} /> : <ChevronUp size={13} style={{ color: 'var(--muted-foreground)' }} />}
      </button>

      {!collapsed && (
        <div className="p-3 flex flex-col gap-1.5">
          <p className="font-mono px-1 mb-2" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>
            Monitor for future portfolio additions when constitutional conditions are met.
          </p>
          {loading ? (
            <div className="flex items-center justify-center py-4">
              <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>Loading…</span>
            </div>
          ) : (
            candidates.map((c) => (
              <div
                key={c.ticker}
                className="flex items-center gap-3 px-3 py-2.5 rounded-xl"
                style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}
              >
                <span className="font-mono font-semibold" style={{ fontSize: '12px', color: 'var(--foreground)', width: '88px', flexShrink: 0 }}>{c.ticker}</span>
                <span className="font-mono flex-1 min-w-0 truncate" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>{c.waiting_for_reason}</span>
                <span className="font-mono tabular-nums flex-shrink-0" style={{ fontSize: '11px', color: 'var(--foreground)' }}>{c.current_price.toFixed(2)}</span>
                <span className="font-mono flex-shrink-0" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>{c.last_scan}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
