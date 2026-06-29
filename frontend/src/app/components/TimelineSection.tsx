'use client';

import React, { useState } from 'react';
import { Clock, ChevronDown, ChevronUp, Calendar } from 'lucide-react';
import { useSnapshot } from '@/providers/SnapshotProvider';

export default function TimelineSection() {
  const { snapshot, loading } = useSnapshot();
  const [collapsed, setCollapsed] = useState(false);

  const events = snapshot?.new_events_today ?? [];
  const totalEvents = snapshot?.statistics?.total_timeline_events ?? 0;
  const totalTickers = snapshot?.statistics?.total_tickers_in_timeline ?? 0;

  return (
    <div className="rounded-xl" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', boxShadow: '0 2px 16px rgba(0,0,0,0.3)' }}>
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="section-header-btn w-full flex items-center justify-between px-4 py-3.5 rounded-t-xl"
        style={{ borderBottom: collapsed ? 'none' : '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <Clock size={13} style={{ color: '#a78bfa' }} />
          <span className="font-mono font-semibold" style={{ fontSize: '12px', color: 'var(--foreground)', letterSpacing: '0.07em' }}>
            CONSTITUTIONAL TIMELINE
          </span>
          <span
            className="font-mono px-2 py-0.5 rounded-md"
            style={{ fontSize: '9px', backgroundColor: 'rgba(167,139,250,0.1)', color: '#a78bfa', border: '1px solid rgba(167,139,250,0.2)' }}
          >
            {loading ? '…' : `${events.length} TODAY`}
          </span>
        </div>
        {collapsed ? <ChevronDown size={13} style={{ color: 'var(--muted-foreground)' }} /> : <ChevronUp size={13} style={{ color: 'var(--muted-foreground)' }} />}
      </button>

      {!collapsed && (
        <div className="p-3 flex flex-col gap-2">
          {/* Summary row */}
          <div
            className="flex items-center gap-4 px-3 py-2.5 rounded-xl"
            style={{ backgroundColor: 'rgba(167,139,250,0.05)', border: '1px solid rgba(167,139,250,0.15)' }}
          >
            <div className="flex flex-col">
              <span className="font-mono font-bold tabular-nums" style={{ fontSize: '20px', color: '#a78bfa' }}>{loading ? '…' : totalEvents}</span>
              <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>TOTAL EVENTS</span>
            </div>
            <div style={{ width: '1px', height: '36px', backgroundColor: 'var(--border)' }} />
            <div className="flex flex-col">
              <span className="font-mono font-bold tabular-nums" style={{ fontSize: '20px', color: 'var(--foreground)' }}>{loading ? '…' : totalTickers}</span>
              <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>TICKERS IN TIMELINE</span>
            </div>
            <div style={{ width: '1px', height: '36px', backgroundColor: 'var(--border)' }} />
            <div className="flex flex-col">
              <span className="font-mono font-bold tabular-nums" style={{ fontSize: '20px', color: events.length > 0 ? 'var(--signal-buy)' : 'var(--muted-foreground)' }}>
                {loading ? '…' : events.length}
              </span>
              <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>NEW TODAY</span>
            </div>
          </div>

          {/* Today's events */}
          {events.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-6 gap-2">
              <Calendar size={20} style={{ color: 'var(--muted-foreground)' }} />
              <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>
                No new constitutional events today
              </span>
              <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', opacity: 0.6 }}>
                {snapshot?.market_date ?? '—'}
              </span>
            </div>
          ) : (
            events.map((evt, i) => (
              <div
                key={evt.event_id ?? i}
                className="px-3 py-2.5 rounded-xl flex items-center gap-3"
                style={{ backgroundColor: 'rgba(167,139,250,0.04)', border: '1px solid rgba(167,139,250,0.15)' }}
              >
                <span className="font-mono font-bold" style={{ fontSize: '12px', color: '#a78bfa' }}>{evt.ticker ?? '—'}</span>
                <span className="font-mono" style={{ fontSize: '10px', color: 'var(--foreground)' }}>{evt.event_type ?? '—'}</span>
                <span className="font-mono ml-auto" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>{evt.event_date ?? '—'}</span>
              </div>
            ))
          )}

          <div
            className="flex items-center gap-2 mt-1 px-3 py-2 rounded-lg"
            style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}
          >
            <Clock size={10} style={{ color: 'var(--muted-foreground)', flexShrink: 0 }} />
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
              Constitutional timeline · {totalEvents} historical events across {totalTickers} tickers · scan {snapshot?.scan_id?.slice(0, 8) ?? '—'}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
