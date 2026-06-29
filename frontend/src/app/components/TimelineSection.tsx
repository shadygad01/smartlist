'use client';

import React, { useState } from 'react';
import { Clock, ChevronDown, ChevronUp, TrendingUp, RefreshCw, AlertTriangle, CheckCircle } from 'lucide-react';

interface TimelineEvent {
  id: string;
  time: string;
  type: 'buy_signal' | 'scan_complete' | 'near_entry' | 'alert' | 'system';
  ticker?: string;
  description: string;
  severity: 'high' | 'medium' | 'low' | 'info';
}

const timelineEvents: TimelineEvent[] = [
  { id: 'evt-001', time: '05:14:22', type: 'buy_signal', ticker: 'ABUK.CA', description: 'NEW BUY ELITE signal generated — BUY LIMIT @ 69.05 EGP', severity: 'high' },
  { id: 'evt-002', time: '05:12:07', type: 'near_entry', ticker: 'MCQE.CA', description: 'Entered near-entry zone — 0.8% above limit price', severity: 'medium' },
  { id: 'evt-003', time: '05:10:44', type: 'scan_complete', description: 'Full universe scan completed — 27 tickers processed', severity: 'info' },
  { id: 'evt-004', time: '05:08:31', type: 'near_entry', ticker: 'BTFH.CA', description: 'Price approaching accumulation zone — 1.1% above entry', severity: 'medium' },
  { id: 'evt-005', time: '05:06:18', type: 'alert', ticker: 'ETEL.CA', description: 'Volume anomaly detected — 3.2x average daily volume', severity: 'medium' },
  { id: 'evt-006', time: '05:04:55', type: 'scan_complete', description: 'Incremental scan batch completed — 9 tickers', severity: 'info' },
  { id: 'evt-007', time: '05:02:12', type: 'near_entry', ticker: 'HRHO.CA', description: 'Re-entered watchlist — R² score upgraded to 0.91', severity: 'medium' },
  { id: 'evt-008', time: '04:58:41', type: 'system', description: 'System health check passed — all 27 data feeds nominal', severity: 'low' },
  { id: 'evt-009', time: '04:54:03', type: 'near_entry', ticker: 'FWRY.CA', description: 'Approaching entry band — 2.3% above limit', severity: 'medium' },
  { id: 'evt-010', time: '04:49:27', type: 'scan_complete', description: 'Morning pre-open scan initiated — universe loaded', severity: 'info' },
  { id: 'evt-011', time: '04:41:15', type: 'alert', ticker: 'AMOC.CA', description: 'Breakout pattern detected — monitoring for confirmation', severity: 'medium' },
  { id: 'evt-012', time: '04:33:09', type: 'system', description: 'Constitutional model parameters recalibrated', severity: 'low' },
];

function getEventIcon(type: TimelineEvent['type']) {
  const size = 11;
  if (type === 'buy_signal') return <TrendingUp size={size} style={{ color: 'var(--signal-buy)' }} />;
  if (type === 'near_entry') return <Clock size={size} style={{ color: 'var(--signal-near)' }} />;
  if (type === 'alert') return <AlertTriangle size={size} style={{ color: '#f97316' }} />;
  if (type === 'scan_complete') return <RefreshCw size={size} style={{ color: 'var(--signal-reaccum)' }} />;
  return <CheckCircle size={size} style={{ color: 'var(--muted-foreground)' }} />;
}

function getEventDotColor(type: TimelineEvent['type']) {
  if (type === 'buy_signal') return 'var(--signal-buy)';
  if (type === 'near_entry') return 'var(--signal-near)';
  if (type === 'alert') return '#f97316';
  if (type === 'scan_complete') return 'var(--signal-reaccum)';
  return '#2d4a6e';
}

function getEventRowBg(type: TimelineEvent['type'], isFirst: boolean) {
  if (!isFirst) return 'transparent';
  if (type === 'buy_signal') return 'rgba(16,185,129,0.04)';
  if (type === 'near_entry') return 'rgba(245,158,11,0.03)';
  return 'transparent';
}

export default function TimelineSection() {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div
      className="rounded-xl"
      style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', boxShadow: '0 2px 16px rgba(0,0,0,0.3)' }}
    >
      {/* Header */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="section-header-btn w-full flex items-center justify-between px-4 py-3.5 rounded-t-xl"
        style={{ borderBottom: collapsed ? 'none' : '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <Clock size={13} style={{ color: 'var(--muted-foreground)' }} />
          <span
            className="font-mono font-semibold"
            style={{ fontSize: '12px', color: 'var(--foreground)', letterSpacing: '0.07em' }}
          >
            EVENT TIMELINE
          </span>
          <span
            className="font-mono px-1.5 py-0.5 rounded-full"
            style={{
              fontSize: '9px',
              backgroundColor: 'rgba(255,255,255,0.04)',
              color: 'var(--muted-foreground)',
              border: '1px solid var(--border)',
            }}
          >
            {timelineEvents.length}
          </span>
        </div>
        {collapsed ? (
          <ChevronDown size={13} style={{ color: 'var(--muted-foreground)' }} />
        ) : (
          <ChevronUp size={13} style={{ color: 'var(--muted-foreground)' }} />
        )}
      </button>

      {/* Content */}
      {!collapsed && (
        <div className="p-4 overflow-y-auto" style={{ maxHeight: '380px' }}>
          <div className="relative">
            {/* Timeline line */}
            <div
              className="absolute left-[5px] top-2 bottom-2"
              style={{ width: '1px', background: 'linear-gradient(to bottom, var(--border), transparent)' }}
            />

            <div className="flex flex-col gap-0">
              {timelineEvents.map((event, idx) => (
                <div
                  key={event.id}
                  className="flex gap-3 pb-3.5 last:pb-0 rounded-lg px-1"
                  style={{ backgroundColor: getEventRowBg(event.type, idx === 0) }}
                >
                  {/* Dot */}
                  <div className="flex-shrink-0 flex flex-col items-center" style={{ width: '12px' }}>
                    <div
                      className="w-2.5 h-2.5 rounded-full mt-1 flex-shrink-0"
                      style={{
                        backgroundColor: getEventDotColor(event.type),
                        boxShadow: idx === 0 ? `0 0 8px ${getEventDotColor(event.type)}` : 'none',
                        border: `1px solid ${getEventDotColor(event.type)}`,
                      }}
                    />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      {getEventIcon(event.type)}
                      {event.ticker && (
                        <span
                          className="font-mono font-semibold"
                          style={{ fontSize: '11px', color: 'var(--foreground)' }}
                        >
                          {event.ticker}
                        </span>
                      )}
                      <span
                        className="font-mono ml-auto flex-shrink-0"
                        style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}
                      >
                        {event.time}
                      </span>
                    </div>
                    <p
                      className="font-mono leading-relaxed"
                      style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}
                    >
                      {event.description}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}