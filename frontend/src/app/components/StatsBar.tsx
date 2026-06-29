'use client';

import React from 'react';
import { useSnapshot } from '@/providers/SnapshotProvider';

interface StatBadge {
  id: string;
  label: string;
  value: number | string;
  color: string;
}

export default function StatsBar() {
  const { snapshot, loading } = useSnapshot();
  const stats = snapshot?.statistics;
  const L = loading ? '…' : '—';

  const badges: StatBadge[] = [
    {
      id: 'total-events',
      label: 'Total Events',
      value: stats?.total_timeline_events ?? L,
      color: '#d0d4e8',
    },
    {
      id: 'first-buy',
      label: 'First BUY',
      value: stats?.first_buys_count ?? L,
      color: '#50d8d0',
    },
    {
      id: 'reaccum',
      label: 'Re-Accum',
      value: stats?.re_accumulation_count ?? L,
      color: '#9c6fff',
    },
    {
      id: 'near-entry',
      label: 'Near Entry',
      value: stats?.near_constitutional_count ?? L,
      color: '#f0b840',
    },
    {
      id: 'premium',
      label: 'Premium',
      value: stats?.premium_count ?? L,
      color: '#4caf50',
    },
    {
      id: 'universe',
      label: 'Universe',
      value: stats?.universe_size ?? snapshot?.universe_snapshot?.length ?? L,
      color: '#d0d4e8',
    },
  ];

  return (
    <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
      {badges.map((badge) => (
        <div
          key={badge.id}
          className="flex flex-col items-center justify-center py-3 px-2 rounded-lg"
          style={{
            backgroundColor: '#181930',
            border: '1px solid #252645',
          }}
        >
          <div
            className="font-bold tabular-nums"
            style={{ fontSize: '20px', color: badge.color, lineHeight: 1 }}
          >
            {badge.value}
          </div>
          <div
            className="font-mono mt-1 text-center"
            style={{ fontSize: '9px', color: '#8b8fa8', letterSpacing: '0.05em', textTransform: 'uppercase' }}
          >
            {badge.label}
          </div>
        </div>
      ))}
    </div>
  );
}
