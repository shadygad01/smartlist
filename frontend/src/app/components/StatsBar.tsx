'use client';

import React from 'react';
import { Zap, TrendingUp, Star, Globe } from 'lucide-react';

interface KPIBadge {
  id: string;
  label: string;
  value: string | number;
  subLabel?: string;
  icon: React.ReactNode;
  color: string;
  bgColor: string;
  borderColor: string;
  glowColor: string;
}

const kpiBadges: KPIBadge[] = [
  {
    id: 'kpi-total-events',
    label: 'TOTAL EVENTS',
    value: '44',
    subLabel: 'this session',
    icon: <Zap size={15} />,
    color: 'var(--foreground)',
    bgColor: 'rgba(255,255,255,0.03)',
    borderColor: 'var(--border)',
    glowColor: 'transparent',
  },
  {
    id: 'kpi-buy-signals',
    label: 'BUY SIGNALS',
    value: '1',
    subLabel: 'ELITE tier',
    icon: <TrendingUp size={15} />,
    color: 'var(--signal-buy)',
    bgColor: 'rgba(16,185,129,0.06)',
    borderColor: 'rgba(16,185,129,0.2)',
    glowColor: 'rgba(16,185,129,0.08)',
  },
  {
    id: 'kpi-premium',
    label: 'NEAR ENTRY',
    value: '4',
    subLabel: 'watchlist',
    icon: <Star size={15} />,
    color: 'var(--signal-near)',
    bgColor: 'rgba(245,158,11,0.06)',
    borderColor: 'rgba(245,158,11,0.2)',
    glowColor: 'rgba(245,158,11,0.06)',
  },
  {
    id: 'kpi-universe',
    label: 'UNIVERSE',
    value: '27',
    subLabel: 'tickers monitored',
    icon: <Globe size={15} />,
    color: 'var(--signal-reaccum)',
    bgColor: 'rgba(59,130,246,0.06)',
    borderColor: 'rgba(59,130,246,0.2)',
    glowColor: 'rgba(59,130,246,0.06)',
  },
];

export default function StatsBar() {
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
      {kpiBadges.map((badge) => (
        <div
          key={badge.id}
          className="stat-card flex items-center gap-3.5 px-4 py-3.5 rounded-xl"
          style={{
            backgroundColor: badge.bgColor,
            border: `1px solid ${badge.borderColor}`,
            boxShadow: badge.glowColor !== 'transparent'
              ? `0 0 20px ${badge.glowColor}, 0 2px 12px rgba(0,0,0,0.3)`
              : '0 2px 12px rgba(0,0,0,0.3)',
          }}
        >
          {/* Icon */}
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

          {/* Text */}
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
            {badge.subLabel && (
              <p
                className="font-mono"
                style={{ fontSize: '9px', color: badge.color, opacity: 0.65, letterSpacing: '0.04em' }}
              >
                {badge.subLabel}
              </p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}