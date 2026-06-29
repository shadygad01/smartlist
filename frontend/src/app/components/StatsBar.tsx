'use client';

import React from 'react';
import { Zap, TrendingUp, Star, Globe } from 'lucide-react';
import { useSnapshot } from '@/providers/SnapshotProvider';

export default function StatsBar() {
  const { snapshot, loading } = useSnapshot();
  const stats = snapshot?.statistics;

  const badges = [
    {
      id: 'kpi-total-events',
      label: 'TOTAL EVENTS',
      value: stats?.total_timeline_events ?? (loading ? '…' : '—'),
      subLabel: 'constitutional timeline',
      icon: <Zap size={15} />,
      color: 'var(--foreground)',
      bgColor: 'rgba(255,255,255,0.03)',
      borderColor: 'var(--border)',
      glowColor: 'transparent',
    },
    {
      id: 'kpi-reaccum',
      label: 'RE-ACCUMULATION',
      value: stats?.re_accumulation_count ?? (loading ? '…' : '—'),
      subLabel: 'active events',
      icon: <TrendingUp size={15} />,
      color: 'var(--signal-buy)',
      bgColor: 'rgba(16,185,129,0.06)',
      borderColor: 'rgba(16,185,129,0.2)',
      glowColor: 'rgba(16,185,129,0.08)',
    },
    {
      id: 'kpi-near',
      label: 'NEAR ENTRY',
      value: stats?.near_constitutional_count ?? (loading ? '…' : '—'),
      subLabel: 'constitutional threshold',
      icon: <Star size={15} />,
      color: 'var(--signal-near)',
      bgColor: 'rgba(245,158,11,0.06)',
      borderColor: 'rgba(245,158,11,0.2)',
      glowColor: 'rgba(245,158,11,0.06)',
    },
    {
      id: 'kpi-universe',
      label: 'UNIVERSE',
      value: stats?.universe_size ?? snapshot?.universe_snapshot?.length ?? (loading ? '…' : '—'),
      subLabel: 'tickers monitored',
      icon: <Globe size={15} />,
      color: 'var(--signal-reaccum)',
      bgColor: 'rgba(59,130,246,0.06)',
      borderColor: 'rgba(59,130,246,0.2)',
      glowColor: 'rgba(59,130,246,0.06)',
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {badges.map((badge) => (
        <div
          key={badge.id}
          className="stat-card flex items-center gap-3.5 px-4 py-3.5 rounded-xl"
          style={{
            backgroundColor: badge.bgColor,
            border: `1px solid ${badge.borderColor}`,
            boxShadow:
              badge.glowColor !== 'transparent'
                ? `0 0 20px ${badge.glowColor}, 0 2px 12px rgba(0,0,0,0.3)`
                : '0 2px 12px rgba(0,0,0,0.3)',
          }}
        >
          <div
            className="flex-shrink-0 flex items-center justify-center rounded-lg"
            style={{
              width: '36px',
              height: '36px',
              backgroundColor: 'rgba(255,255,255,0.04)',
              border: '1px solid rgba(255,255,255,0.06)',
              color: badge.color,
            }}
          >
            {badge.icon}
          </div>

          <div className="min-w-0 flex-1">
            <p
              className="font-mono font-bold tabular-nums"
              style={{ fontSize: '26px', color: badge.color, lineHeight: 1, letterSpacing: '-0.02em' }}
            >
              {badge.value}
            </p>
            <p
              className="font-mono mt-0.5"
              style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.09em' }}
            >
              {badge.label}
            </p>
            <p
              className="font-mono"
              style={{ fontSize: '9px', color: badge.color, opacity: 0.65, letterSpacing: '0.04em' }}
            >
              {badge.subLabel}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}
