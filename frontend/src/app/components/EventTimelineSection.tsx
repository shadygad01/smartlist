'use client';

import React, { useState, useMemo } from 'react';
import {
  Clock,
  TrendingUp,
  RefreshCw,
  AlertTriangle,
  Settings,
  ChevronDown,
  ChevronUp,
  Filter,
  Circle,
} from 'lucide-react';
import { useSnapshot } from '@/providers/SnapshotProvider';
import type { EventTimelineItem } from '@/types/snapshot';

// ── helpers ───────────────────────────────────────────────────────────────────

function relativeTime(ts: string): string {
  if (!ts) return '';
  try {
    const now = Date.now();
    const then = new Date(ts).getTime();
    const diff = Math.floor((now - then) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return ts.slice(11, 16); // HH:MM fallback
  } catch {
    return ts.slice(11, 16);
  }
}

function wallTime(ts: string): string {
  if (!ts) return '';
  return ts.slice(11, 19); // HH:MM:SS
}

function engineAge(ts: string | null | undefined): string {
  if (!ts) return 'never';
  try {
    const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000);
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  } catch {
    return '—';
  }
}

// ── event config ──────────────────────────────────────────────────────────────

type EventType = 'BUY_SIGNAL' | 'NEAR_ENTRY' | 'SCAN' | 'VOL_SPIKE' | 'SYSTEM';

const EVENT_CONFIG: Record<EventType, {
  dot: string;
  badge: string;
  badgeBg: string;
  badgeText: string;
  tickerColor: string;
  Icon: React.FC<{ size?: number; style?: React.CSSProperties }>;
}> = {
  BUY_SIGNAL: {
    dot: '#4caf50',
    badge: 'BUY SIGNAL',
    badgeBg: 'rgba(76,175,80,0.15)',
    badgeText: '#4caf50',
    tickerColor: '#ffffff',
    Icon: TrendingUp,
  },
  NEAR_ENTRY: {
    dot: '#f5a623',
    badge: 'NEAR ENTRY',
    badgeBg: 'rgba(245,166,35,0.15)',
    badgeText: '#f5a623',
    tickerColor: '#ffffff',
    Icon: Clock,
  },
  SCAN: {
    dot: '#4a9eff',
    badge: 'SCAN',
    badgeBg: 'rgba(74,158,255,0.12)',
    badgeText: '#4a9eff',
    tickerColor: '#4a9eff',
    Icon: RefreshCw,
  },
  VOL_SPIKE: {
    dot: '#f5a623',
    badge: 'VOL SPIKE',
    badgeBg: 'rgba(245,80,30,0.15)',
    badgeText: '#f5803e',
    tickerColor: '#ffffff',
    Icon: AlertTriangle,
  },
  SYSTEM: {
    dot: '#6b7280',
    badge: 'SYSTEM',
    badgeBg: 'rgba(107,114,128,0.12)',
    badgeText: '#8b8fa8',
    tickerColor: '#8b8fa8',
    Icon: Settings,
  },
};

const ALL_FILTERS: EventType[] = ['BUY_SIGNAL', 'NEAR_ENTRY', 'SCAN', 'VOL_SPIKE', 'SYSTEM'];

// ── sub-components ────────────────────────────────────────────────────────────

function LiveDot() {
  return (
    <span
      style={{
        display: 'inline-block',
        width: 7,
        height: 7,
        borderRadius: '50%',
        backgroundColor: '#4caf50',
        boxShadow: '0 0 0 0 rgba(76,175,80,0.6)',
        animation: 'etl-pulse 2s infinite',
        flexShrink: 0,
      }}
    />
  );
}

function EventRow({ evt }: { evt: EventTimelineItem }) {
  const cfg = EVENT_CONFIG[evt.event_type] ?? EVENT_CONFIG.SYSTEM;
  const { Icon } = cfg;
  const isScan = evt.event_type === 'SCAN';
  const isSystem = evt.event_type === 'SYSTEM';

  return (
    <div
      className="flex items-start gap-3 px-4 py-3"
      style={{ borderBottom: '1px solid rgba(37,38,69,0.7)' }}
    >
      {/* Dot */}
      <div className="flex-shrink-0 flex items-center" style={{ paddingTop: 3 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            backgroundColor: cfg.dot,
            display: 'inline-block',
            flexShrink: 0,
          }}
        />
      </div>

      {/* Icon */}
      <div className="flex-shrink-0 flex items-center" style={{ paddingTop: 2 }}>
        <Icon size={12} style={{ color: cfg.dot, opacity: 0.9 }} />
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          {!isScan && !isSystem && evt.ticker && (
            <span
              className="font-mono font-bold"
              style={{ fontSize: '12px', color: cfg.tickerColor }}
            >
              {evt.ticker}
            </span>
          )}
          <span
            className="font-mono font-bold px-1.5 py-0.5 rounded"
            style={{
              fontSize: '9px',
              backgroundColor: cfg.badgeBg,
              color: cfg.badgeText,
              border: `1px solid ${cfg.badgeText}44`,
              letterSpacing: '0.05em',
              flexShrink: 0,
            }}
          >
            {evt.badge || cfg.badge}
          </span>
        </div>
        {evt.description && (
          <div
            className="font-mono mt-0.5"
            style={{ fontSize: '11px', color: '#8b8fa8', lineHeight: 1.4 }}
          >
            {evt.description}
          </div>
        )}
      </div>

      {/* Time */}
      <div className="flex-shrink-0 flex flex-col items-end gap-0.5" style={{ paddingTop: 2 }}>
        <span className="font-mono" style={{ fontSize: '11px', color: '#6b7280' }}>
          {wallTime(evt.timestamp)}
        </span>
        <span className="font-mono" style={{ fontSize: '9px', color: '#4a4d6a' }}>
          {relativeTime(evt.timestamp)}
        </span>
      </div>
    </div>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export default function EventTimelineSection() {
  const { snapshot, loading } = useSnapshot();
  const [collapsed, setCollapsed] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const [activeFilters, setActiveFilters] = useState<Set<EventType>>(new Set(ALL_FILTERS));

  const events: EventTimelineItem[] = snapshot?.event_timeline ?? [];
  const engineStatus = snapshot?.event_timeline_engine;

  const filtered = useMemo(
    () => events.filter(e => activeFilters.has(e.event_type as EventType)),
    [events, activeFilters]
  );

  const toggleFilter = (f: EventType) => {
    setActiveFilters(prev => {
      const next = new Set(prev);
      if (next.has(f)) {
        if (next.size > 1) next.delete(f);
      } else {
        next.add(f);
      }
      return next;
    });
  };

  const lastTs = engineStatus?.last_event_ts ?? (events[0]?.timestamp ?? null);

  return (
    <>
      {/* Keyframe for pulsing dot */}
      <style>{`
        @keyframes etl-pulse {
          0%   { box-shadow: 0 0 0 0 rgba(76,175,80,0.6); }
          70%  { box-shadow: 0 0 0 5px rgba(76,175,80,0); }
          100% { box-shadow: 0 0 0 0 rgba(76,175,80,0); }
        }
      `}</style>

      <div className="rounded-xl overflow-hidden" style={{ backgroundColor: '#10112a', border: '1px solid #252645' }}>

        {/* ── Header ── */}
        <div
          className="flex items-center justify-between px-4 py-3"
          style={{ borderBottom: collapsed ? 'none' : '1px solid #252645' }}
        >
          {/* Left: title + count + live dot */}
          <div className="flex items-center gap-2">
            <Clock size={13} style={{ color: '#a78bfa' }} />
            <span
              className="font-mono font-semibold"
              style={{ fontSize: '12px', color: '#d0d4e8', letterSpacing: '0.07em' }}
            >
              EVENT TIMELINE
            </span>

            {/* Count badge */}
            <span
              className="font-mono font-bold flex items-center justify-center rounded-full"
              style={{
                fontSize: '10px',
                minWidth: 22,
                height: 22,
                padding: '0 6px',
                backgroundColor: 'rgba(167,139,250,0.15)',
                color: '#a78bfa',
                border: '1px solid rgba(167,139,250,0.3)',
              }}
            >
              {loading ? '…' : filtered.length}
            </span>

            {/* Live dot */}
            <LiveDot />
          </div>

          {/* Right: filter + collapse */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setFilterOpen(p => !p)}
              className="flex items-center gap-1 px-2 py-1 rounded"
              style={{
                background: filterOpen ? 'rgba(167,139,250,0.1)' : 'none',
                border: '1px solid rgba(37,38,69,0.8)',
                cursor: 'pointer',
              }}
              title="Filter events"
            >
              <Filter size={11} style={{ color: '#8b8fa8' }} />
            </button>
            <button
              onClick={() => setCollapsed(p => !p)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2 }}
            >
              {collapsed
                ? <ChevronDown size={13} style={{ color: '#8b8fa8' }} />
                : <ChevronUp size={13} style={{ color: '#8b8fa8' }} />}
            </button>
          </div>
        </div>

        {/* ── Filter chips (when open) ── */}
        {!collapsed && filterOpen && (
          <div
            className="flex items-center gap-2 px-4 py-2 flex-wrap"
            style={{ borderBottom: '1px solid #252645', backgroundColor: 'rgba(16,17,42,0.6)' }}
          >
            {ALL_FILTERS.map(f => {
              const cfg = EVENT_CONFIG[f];
              const active = activeFilters.has(f);
              return (
                <button
                  key={f}
                  onClick={() => toggleFilter(f)}
                  className="font-mono px-2 py-0.5 rounded"
                  style={{
                    fontSize: '9px',
                    cursor: 'pointer',
                    backgroundColor: active ? cfg.badgeBg : 'transparent',
                    color: active ? cfg.badgeText : '#6b7280',
                    border: `1px solid ${active ? cfg.badgeText + '66' : '#2d2f50'}`,
                    transition: 'all 0.15s',
                    letterSpacing: '0.05em',
                  }}
                >
                  {cfg.badge}
                </button>
              );
            })}
          </div>
        )}

        {/* ── Events list ── */}
        {!collapsed && (
          <div>
            {loading ? (
              <div className="flex items-center justify-center py-8">
                <span className="font-mono" style={{ fontSize: '10px', color: '#8b8fa8' }}>Loading…</span>
              </div>
            ) : filtered.length === 0 ? (
              <div className="flex items-center justify-center py-8">
                <span className="font-mono" style={{ fontSize: '10px', color: '#8b8fa8' }}>
                  No events yet — engine will populate on next scan
                </span>
              </div>
            ) : (
              <div style={{ maxHeight: 480, overflowY: 'auto' }}>
                {filtered.map(evt => (
                  <EventRow key={evt.id} evt={evt} />
                ))}
              </div>
            )}

            {/* ── Footer: engine status ── */}
            <div
              className="flex items-center gap-2 px-4 py-2"
              style={{ borderTop: '1px solid rgba(37,38,69,0.5)' }}
            >
              <Circle
                size={6}
                style={{ color: lastTs ? '#4caf50' : '#6b7280', fill: lastTs ? '#4caf50' : '#6b7280', flexShrink: 0 }}
              />
              <span
                className="font-mono"
                style={{ fontSize: '10px', color: '#6b7280', letterSpacing: '0.04em' }}
              >
                ENGINE LIVE · {engineAge(lastTs)}
              </span>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
