import React, { useState } from 'react';
import { Globe, ChevronDown, ChevronUp } from 'lucide-react';
import { useSnapshot } from '@/providers/SnapshotProvider';

const STATUS_COLORS: Record<string, string> = {
  UNDER_REVIEW: 'var(--signal-near)',
  ACTIVE: 'var(--signal-buy)',
  PREMIUM: '#a78bfa',
  BELOW_THRESHOLD: 'var(--muted-foreground)',
};

function statusColor(status: string): string {
  return STATUS_COLORS[status] ?? 'var(--muted-foreground)';
}

export default function UniverseSection() {
  const { snapshot, loading } = useSnapshot();
  const [collapsed, setCollapsed] = useState(true);

  const tickers = snapshot?.universe_snapshot ?? [];

  return (
    <div className="rounded-xl" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', boxShadow: '0 2px 16px rgba(0,0,0,0.3)' }}>
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="section-header-btn w-full flex items-center justify-between px-4 py-3.5 rounded-t-xl"
        style={{ borderBottom: collapsed ? 'none' : '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <Globe size={13} style={{ color: 'var(--signal-reaccum)' }} />
          <span className="font-mono font-semibold" style={{ fontSize: '12px', color: 'var(--foreground)', letterSpacing: '0.07em' }}>
            UNIVERSE SNAPSHOT
          </span>
          <span
            className="font-mono px-2 py-0.5 rounded-md"
            style={{ fontSize: '9px', backgroundColor: 'rgba(59,130,246,0.1)', color: 'var(--signal-reaccum)', border: '1px solid rgba(59,130,246,0.2)' }}
          >
            {loading ? '…' : `${tickers.length} TICKERS`}
          </span>
        </div>
        {collapsed ? <ChevronDown size={13} style={{ color: 'var(--muted-foreground)' }} /> : <ChevronUp size={13} style={{ color: 'var(--muted-foreground)' }} />}
      </button>

      {!collapsed && (
        <div className="p-3">
          {loading && (
            <div className="flex items-center justify-center py-8">
              <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>Loading…</span>
            </div>
          )}
          {!loading && tickers.length === 0 && (
            <div className="flex items-center justify-center py-8">
              <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>No universe data in snapshot.</span>
            </div>
          )}
          <div className="flex flex-col gap-1.5">
            {tickers.map((t) => (
              <div
                key={t.ticker}
                className="flex items-center gap-3 px-3 py-2 rounded-lg"
                style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}
              >
                <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ backgroundColor: statusColor(t.status) }} />
                <span className="font-mono font-semibold" style={{ fontSize: '11px', color: 'var(--foreground)', width: '80px', flexShrink: 0 }}>{t.ticker}</span>
                <span className="font-mono" style={{ fontSize: '9px', color: statusColor(t.status), width: '100px', flexShrink: 0 }}>{t.status}</span>
                <span className="font-mono tabular-nums" style={{ fontSize: '11px', color: 'var(--foreground)', marginLeft: 'auto' }}>
                  {t.current_price.toFixed(2)}
                </span>
                <span
                  className="font-mono tabular-nums"
                  style={{
                    fontSize: '10px',
                    color: t.distance != null && t.distance < 0 ? 'var(--signal-near)' : t.distance != null ? 'var(--signal-buy)' : 'var(--muted-foreground)',
                    width: '64px', textAlign: 'right', flexShrink: 0,
                  }}
                >
                  {t.distance != null ? `${t.distance.toFixed(1)}%` : '—'}
                </span>
                <span className="font-mono tabular-nums" style={{ fontSize: '10px', color: 'var(--signal-reaccum)', width: '48px', textAlign: 'right', flexShrink: 0 }}>
                  {t.candidate_r2 != null ? `R²${t.candidate_r2}` : '—'}
                </span>
              </div>
            ))}
          </div>
          <div
            className="flex items-center gap-2 mt-2 px-3 py-2 rounded-lg"
            style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}
          >
            <Globe size={10} style={{ color: 'var(--muted-foreground)', flexShrink: 0 }} />
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
              {snapshot?.statistics?.universe_size ?? tickers.length} tickers · scan {snapshot?.scan_id?.slice(0, 8) ?? '—'} · {snapshot?.price_data_as_of ?? '—'}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
