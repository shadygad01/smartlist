'use client';

import React, { useState } from 'react';
import { Clock, ChevronDown, ChevronUp } from 'lucide-react';
import { useSnapshot } from '@/providers/SnapshotProvider';
import type { TimelineEvent } from '@/types/snapshot';

function returnColor(pct: number | undefined): string {
  if (pct == null) return '#8b8fa8';
  return pct >= 0 ? '#4caf50' : '#f44336';
}

function EventRow({ evt }: { evt: TimelineEvent }) {
  const isFirstBuy = evt.event_type === 'FIRST_BUY';
  const typeColor = isFirstBuy ? '#50d8d0' : '#9c6fff';
  const typeLabel = isFirstBuy ? 'FIRST BUY' : 'RE-ACCUM';
  const ret = evt.return_pct as number | undefined;
  const entry = evt.constitutional_entry_price as number | undefined;
  const current = evt.current_price as number | undefined;

  return (
    <tr style={{ borderBottom: '1px solid #1a2040' }}>
      <td className="font-mono font-bold" style={{ padding: '9px 10px', color: '#ffffff', whiteSpace: 'nowrap' }}>
        {evt.ticker ?? '—'}
      </td>
      <td style={{ padding: '9px 10px', whiteSpace: 'nowrap' }}>
        <span
          className="font-mono font-bold px-2 py-0.5 rounded"
          style={{ fontSize: '10px', backgroundColor: `${typeColor}22`, color: typeColor, border: `1px solid ${typeColor}44` }}
        >
          {typeLabel}
        </span>
      </td>
      <td className="font-mono" style={{ padding: '9px 10px', color: '#8b8fa8', whiteSpace: 'nowrap', fontSize: '12px' }}>
        {evt.event_date ?? '—'}
      </td>
      <td className="font-mono" style={{ padding: '9px 10px', color: '#d0d4e8', whiteSpace: 'nowrap', fontSize: '12px' }}>
        {entry != null ? `${entry.toFixed(2)}` : '—'}
      </td>
      <td className="font-mono" style={{ padding: '9px 10px', color: '#d0d4e8', whiteSpace: 'nowrap', fontSize: '12px' }}>
        {current != null ? `${current.toFixed(2)}` : '—'}
      </td>
      <td className="font-mono font-bold" style={{ padding: '9px 10px', color: returnColor(ret), whiteSpace: 'nowrap', fontSize: '12px' }}>
        {ret != null ? `${ret >= 0 ? '+' : ''}${ret.toFixed(1)}%` : '—'}
      </td>
      <td className="font-mono" style={{ padding: '9px 10px', color: '#8b8fa8', whiteSpace: 'nowrap', fontSize: '11px' }}>
        {(evt.sector as string) ?? ''}
      </td>
    </tr>
  );
}

export default function TimelineSection() {
  const { snapshot, loading } = useSnapshot();
  const [collapsed, setCollapsed] = useState(false);

  const events: TimelineEvent[] = snapshot?.timeline ?? [];
  const totalEvents = snapshot?.statistics?.total_timeline_events ?? 0;
  const totalTickers = snapshot?.statistics?.total_tickers_in_timeline ?? 0;
  const newToday = (snapshot?.new_events_today ?? []).length;

  return (
    <div className="rounded-xl overflow-hidden" style={{ backgroundColor: '#10112a', border: '1px solid #252645' }}>
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-4 py-3.5"
        style={{ borderBottom: collapsed ? 'none' : '1px solid #252645', cursor: 'pointer', background: 'none' }}
      >
        <div className="flex items-center gap-2">
          <Clock size={13} style={{ color: '#a78bfa' }} />
          <span className="font-mono font-semibold" style={{ fontSize: '12px', color: '#d0d4e8', letterSpacing: '0.07em' }}>
            CONSTITUTIONAL TIMELINE
          </span>
          <span
            className="font-mono px-2 py-0.5 rounded"
            style={{ fontSize: '9px', backgroundColor: 'rgba(167,139,250,0.1)', color: '#a78bfa', border: '1px solid rgba(167,139,250,0.2)' }}
          >
            {loading ? '…' : `${totalEvents} EVENTS`}
          </span>
          {newToday > 0 && (
            <span
              className="font-mono px-2 py-0.5 rounded"
              style={{ fontSize: '9px', backgroundColor: 'rgba(76,175,80,0.15)', color: '#4caf50', border: '1px solid rgba(76,175,80,0.3)' }}
            >
              {newToday} NEW TODAY
            </span>
          )}
        </div>
        {collapsed
          ? <ChevronDown size={13} style={{ color: '#8b8fa8' }} />
          : <ChevronUp size={13} style={{ color: '#8b8fa8' }} />}
      </button>

      {!collapsed && (
        <div>
          {/* Summary row */}
          <div
            className="flex items-center gap-6 px-4 py-3"
            style={{ backgroundColor: 'rgba(167,139,250,0.04)', borderBottom: '1px solid #252645' }}
          >
            <div className="flex flex-col">
              <span className="font-mono font-bold" style={{ fontSize: '20px', color: '#a78bfa' }}>{loading ? '…' : totalEvents}</span>
              <span className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8', letterSpacing: '0.07em' }}>TOTAL EVENTS</span>
            </div>
            <div style={{ width: '1px', height: '32px', backgroundColor: '#252645' }} />
            <div className="flex flex-col">
              <span className="font-mono font-bold" style={{ fontSize: '20px', color: '#d0d4e8' }}>{loading ? '…' : totalTickers}</span>
              <span className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8', letterSpacing: '0.07em' }}>TICKERS</span>
            </div>
            <div style={{ width: '1px', height: '32px', backgroundColor: '#252645' }} />
            <div className="flex flex-col">
              <span className="font-mono font-bold" style={{ fontSize: '20px', color: newToday > 0 ? '#4caf50' : '#8b8fa8' }}>
                {loading ? '…' : newToday}
              </span>
              <span className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8', letterSpacing: '0.07em' }}>NEW TODAY</span>
            </div>
          </div>

          {/* Events table */}
          {events.length === 0 ? (
            <div className="flex items-center justify-center py-8">
              <span className="font-mono" style={{ fontSize: '10px', color: '#8b8fa8' }}>No timeline events</span>
            </div>
          ) : (
            <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', minWidth: '560px' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #252645' }}>
                    {['Ticker', 'Type', 'Signal Date', 'Entry Zone', 'Current', 'Return', 'Sector'].map(h => (
                      <th key={h} className="font-mono" style={{ padding: '9px 10px', color: '#8b8fa8', fontSize: '10px', fontWeight: 700, letterSpacing: '0.4px', textTransform: 'uppercase', textAlign: 'left', whiteSpace: 'nowrap' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {events.map((evt, i) => (
                    <EventRow key={(evt.event_id as string) ?? i} evt={evt} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
