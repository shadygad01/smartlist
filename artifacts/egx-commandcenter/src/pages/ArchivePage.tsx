import React, { useState } from 'react';
import { Link } from 'wouter';
import { TrendingUp, TrendingDown, Clock, BarChart2, Filter, Search, RefreshCw } from 'lucide-react';
import { useSnapshot } from '@/providers/SnapshotProvider';
import type { ReAccumulationEvent } from '@/types/snapshot';

function statusColor(status: string): { color: string; bg: string; border: string } {
  if (status === 'PREMIUM_NOW')  return { color: '#a78bfa',           bg: 'rgba(167,139,250,0.12)', border: 'rgba(167,139,250,0.3)' };
  if (status === 'ACTIVE')       return { color: 'var(--signal-buy)', bg: 'rgba(16,185,129,0.08)',  border: 'rgba(16,185,129,0.25)' };
  if (status === 'CLOSED_WIN')   return { color: 'var(--signal-buy)', bg: 'rgba(16,185,129,0.08)',  border: 'rgba(16,185,129,0.2)' };
  if (status === 'CLOSED_LOSS')  return { color: '#ef4444',           bg: 'rgba(239,68,68,0.08)',   border: 'rgba(239,68,68,0.2)' };
  return { color: 'var(--muted-foreground)', bg: 'rgba(255,255,255,0.04)', border: 'var(--border)' };
}

export default function ArchivePage() {
  const { snapshot, loading, error } = useSnapshot();
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState<string>('ALL');
  const [filterSector, setFilterSector] = useState<string>('ALL');

  const events: ReAccumulationEvent[] = snapshot?.re_accumulation ?? [];
  const sectors = Array.from(new Set(events.map((e) => e.sector).filter(Boolean)));

  const filtered = events.filter((e) => {
    const matchSearch = searchQuery === '' || e.ticker.toLowerCase().includes(searchQuery.toLowerCase());
    const matchStatus = filterStatus === 'ALL' || e.status === filterStatus;
    const matchSector = filterSector === 'ALL' || e.sector === filterSector;
    return matchSearch && matchStatus && matchSector;
  });

  const wins     = events.filter((e) => e.return_pct > 0).length;
  const winRate  = events.length > 0 ? Math.round(wins / events.length * 100) : 0;
  const avgRet   = events.length > 0 ? events.reduce((s, e) => s + e.return_pct, 0) / events.length : 0;
  const peakBest = events.length > 0 ? Math.max(...events.map((e) => e.peak_return_pct)) : 0;
  const statuses = Array.from(new Set(events.map((e) => e.status)));

  return (
    <div className="min-h-screen" style={{ backgroundColor: 'var(--background)', paddingTop: '72px' }}>
      <div className="px-4 md:px-6 xl:px-10 py-6" style={{ borderBottom: '1px solid var(--border)' }}>
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg" style={{ backgroundColor: 'rgba(167,139,250,0.1)', border: '1px solid rgba(167,139,250,0.25)' }}>
              <BarChart2 size={18} style={{ color: 'var(--signal-elite)' }} />
            </div>
            <div>
              <h1 className="font-mono font-bold" style={{ fontSize: '18px', color: 'var(--foreground)', letterSpacing: '0.04em' }}>
                CONSTITUTIONAL SIGNAL ARCHIVE
              </h1>
              <p className="font-mono" style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>
                Re-accumulation timeline · scan {snapshot?.scan_id?.slice(0, 8) ?? '—'} · {snapshot?.market_date ?? '—'}
              </p>
            </div>
          </div>
          <Link
            href="/"
            className="font-mono px-3 py-1.5 rounded-lg transition-all duration-150 hover:opacity-80"
            style={{ fontSize: '11px', backgroundColor: 'var(--muted)', border: '1px solid var(--border)', color: 'var(--muted-foreground)', letterSpacing: '0.05em' }}
          >
            ← DASHBOARD
          </Link>
        </div>
      </div>

      <div className="px-4 md:px-6 xl:px-10 py-6 space-y-6">
        {error && (
          <div className="p-4 rounded-xl" style={{ backgroundColor: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)' }}>
            <span className="font-mono" style={{ fontSize: '11px', color: '#ef4444' }}>{error}</span>
          </div>
        )}

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'TOTAL EVENTS', value: loading ? '…' : events.length.toString(), color: 'var(--foreground)' },
            { label: 'WIN RATE', value: loading ? '…' : `${winRate}%`, color: 'var(--signal-buy)' },
            { label: 'AVG RETURN', value: loading ? '…' : `${avgRet >= 0 ? '+' : ''}${avgRet.toFixed(1)}%`, color: avgRet >= 0 ? 'var(--signal-buy)' : '#ef4444' },
            { label: 'PEAK RETURN', value: loading ? '…' : `+${peakBest.toFixed(1)}%`, color: '#a78bfa' },
          ].map((kpi) => (
            <div key={kpi.label} className="p-4 rounded-xl" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}>
              <p className="font-mono mb-2" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.08em' }}>{kpi.label}</p>
              <span className="font-mono font-bold tabular-nums" style={{ fontSize: '26px', color: kpi.color, lineHeight: 1 }}>{kpi.value}</span>
            </div>
          ))}
        </div>

        <div className="flex flex-col md:flex-row gap-3 flex-wrap">
          <div
            className="flex items-center gap-2 px-3 py-2 rounded-lg"
            style={{ backgroundColor: 'var(--muted)', border: '1px solid var(--border)', minWidth: '200px' }}
          >
            <Search size={13} style={{ color: 'var(--muted-foreground)' }} />
            <input
              type="text"
              placeholder="Search ticker…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-transparent outline-none font-mono w-full"
              style={{ fontSize: '12px', color: 'var(--foreground)' }}
            />
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <Filter size={12} style={{ color: 'var(--muted-foreground)' }} />
            {['ALL', ...statuses].map((s) => (
              <button
                key={s}
                onClick={() => setFilterStatus(s)}
                className="font-mono px-2.5 py-1 rounded-md"
                style={{
                  fontSize: '10px', letterSpacing: '0.05em',
                  backgroundColor: filterStatus === s ? 'rgba(167,139,250,0.15)' : 'var(--muted)',
                  border: `1px solid ${filterStatus === s ? 'rgba(167,139,250,0.4)' : 'var(--border)'}`,
                  color: filterStatus === s ? 'var(--signal-elite)' : 'var(--muted-foreground)',
                }}
              >
                {s}
              </button>
            ))}
          </div>

          {sectors.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap">
              {['ALL', ...sectors].map((sec) => (
                <button
                  key={sec}
                  onClick={() => setFilterSector(sec)}
                  className="font-mono px-2.5 py-1 rounded-md"
                  style={{
                    fontSize: '10px', letterSpacing: '0.05em',
                    backgroundColor: filterSector === sec ? 'rgba(59,130,246,0.12)' : 'var(--muted)',
                    border: `1px solid ${filterSector === sec ? 'rgba(59,130,246,0.3)' : 'var(--border)'}`,
                    color: filterSector === sec ? 'var(--signal-reaccum)' : 'var(--muted-foreground)',
                  }}
                >
                  {sec}
                </button>
              ))}
            </div>
          )}
        </div>

        <span className="font-mono" style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>
          Showing {filtered.length} of {events.length} events
        </span>

        <div className="rounded-xl overflow-hidden" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}>
          <div
            className="grid px-4 py-3"
            style={{ gridTemplateColumns: '1fr 80px 90px 90px 80px 80px 60px 110px 90px', borderBottom: '1px solid var(--border)', backgroundColor: 'rgba(255,255,255,0.02)' }}
          >
            {['TICKER / SECTOR', 'EVENT', 'ENTRY', 'CURRENT', 'RETURN', 'PEAK', 'DAYS', 'STATUS', 'DATE'].map((h) => (
              <span key={h} className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.08em' }}>{h}</span>
            ))}
          </div>

          {loading && (
            <div className="flex items-center justify-center py-16 gap-2">
              <RefreshCw size={14} style={{ color: 'var(--muted-foreground)' }} />
              <span className="font-mono" style={{ fontSize: '12px', color: 'var(--muted-foreground)' }}>Loading constitutional archive…</span>
            </div>
          )}

          {!loading && filtered.length === 0 && (
            <div className="flex items-center justify-center py-16">
              <span className="font-mono" style={{ fontSize: '13px', color: 'var(--muted-foreground)' }}>No events match the current filters</span>
            </div>
          )}

          {!loading && filtered.map((evt, idx) => {
            const sc = statusColor(evt.status);
            const retPos = evt.return_pct >= 0;
            return (
              <div
                key={evt.event_id}
                className="grid px-4 py-4 ticker-row"
                style={{
                  gridTemplateColumns: '1fr 80px 90px 90px 80px 80px 60px 110px 90px',
                  borderBottom: idx < filtered.length - 1 ? '1px solid var(--border)' : 'none',
                  alignItems: 'center',
                }}
              >
                <div className="flex flex-col gap-0.5">
                  <span className="font-mono font-bold" style={{ fontSize: '13px', color: 'var(--foreground)' }}>{evt.ticker}</span>
                  <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>{evt.sector}</span>
                  <span className="font-mono" style={{ fontSize: '9px', color: 'var(--signal-reaccum)' }}>R²{evt.constitutional_r2.toFixed(1)} · {evt.constitutional_score.toFixed(1)}</span>
                </div>
                <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.04em' }}>
                  {evt.event_type.replace('_', ' ')} #{evt.event_index}
                </span>
                <div className="flex flex-col gap-0.5">
                  <span className="font-mono font-semibold tabular-nums" style={{ fontSize: '12px', color: 'var(--signal-buy)' }}>{evt.constitutional_entry_price.toFixed(2)}</span>
                  <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>EGP</span>
                </div>
                <div className="flex flex-col gap-0.5">
                  <span className="font-mono font-semibold tabular-nums" style={{ fontSize: '12px', color: 'var(--foreground)' }}>{evt.current_price.toFixed(2)}</span>
                  <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>EGP</span>
                </div>
                <div className="flex items-center gap-1">
                  {retPos ? <TrendingUp size={10} style={{ color: 'var(--signal-buy)' }} /> : <TrendingDown size={10} style={{ color: '#ef4444' }} />}
                  <span className="font-mono font-bold tabular-nums" style={{ fontSize: '12px', color: retPos ? 'var(--signal-buy)' : '#ef4444' }}>
                    {retPos ? '+' : ''}{evt.return_pct.toFixed(1)}%
                  </span>
                </div>
                <span className="font-mono tabular-nums" style={{ fontSize: '11px', color: '#a78bfa' }}>
                  +{evt.peak_return_pct.toFixed(1)}%
                </span>
                <div className="flex items-center gap-1">
                  <Clock size={9} style={{ color: 'var(--muted-foreground)' }} />
                  <span className="font-mono tabular-nums" style={{ fontSize: '11px', color: 'var(--foreground)' }}>{evt.days_active}</span>
                </div>
                <span
                  className="font-mono font-semibold px-2 py-1 rounded-md inline-block"
                  style={{ fontSize: '9px', backgroundColor: sc.bg, color: sc.color, border: `1px solid ${sc.border}`, letterSpacing: '0.04em' }}
                >
                  {evt.status}
                </span>
                <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>{evt.event_date}</span>
              </div>
            );
          })}
        </div>

        <div className="flex items-center justify-center pb-6">
          <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)', opacity: 0.5 }}>
            Constitutional Signal Archive · scan {snapshot?.scan_id?.slice(0, 8) ?? '—'} · {snapshot?.statistics?.total_timeline_events ?? 0} total events
          </span>
        </div>
      </div>
    </div>
  );
}
