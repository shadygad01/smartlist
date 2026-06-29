'use client';

import React, { useState } from 'react';
import { Activity, ChevronDown, ChevronUp, CheckCircle, Database, BarChart2, Clock, GitBranch, Shield, Heart } from 'lucide-react';
import { useSnapshot } from '@/providers/SnapshotProvider';

export default function DiagnosticsSection() {
  const { snapshot, loading, error } = useSnapshot();
  const [collapsed, setCollapsed] = useState(true);

  const lineage = snapshot?._lineage;
  const stats = snapshot?.statistics;

  const overallStatus = error ? 'error' : loading ? 'loading' : 'healthy';

  return (
    <div className="rounded-xl" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', boxShadow: '0 2px 16px rgba(0,0,0,0.3)' }}>
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="section-header-btn w-full flex items-center justify-between px-4 py-3.5 rounded-t-xl"
        style={{ borderBottom: collapsed ? 'none' : '1px solid var(--border)' }}
      >
        <div className="flex items-center gap-2">
          <Activity size={13} style={{ color: overallStatus === 'healthy' ? 'var(--signal-buy)' : overallStatus === 'error' ? '#ef4444' : 'var(--muted-foreground)' }} />
          <span className="font-mono font-semibold" style={{ fontSize: '12px', color: 'var(--foreground)', letterSpacing: '0.07em' }}>
            SYSTEM DIAGNOSTICS
          </span>
          <span
            className="font-mono px-2 py-0.5 rounded-md"
            style={{
              fontSize: '9px',
              backgroundColor: overallStatus === 'healthy' ? 'rgba(16,185,129,0.08)' : overallStatus === 'error' ? 'rgba(239,68,68,0.08)' : 'rgba(255,255,255,0.04)',
              color: overallStatus === 'healthy' ? 'var(--signal-buy)' : overallStatus === 'error' ? '#ef4444' : 'var(--muted-foreground)',
              border: `1px solid ${overallStatus === 'healthy' ? 'rgba(16,185,129,0.2)' : overallStatus === 'error' ? 'rgba(239,68,68,0.2)' : 'var(--border)'}`,
            }}
          >
            {overallStatus === 'healthy' ? 'OK' : overallStatus === 'error' ? 'ERROR' : 'LOADING'}
          </span>
        </div>
        {collapsed ? <ChevronDown size={13} style={{ color: 'var(--muted-foreground)' }} /> : <ChevronUp size={13} style={{ color: 'var(--muted-foreground)' }} />}
      </button>

      {!collapsed && (
        <div className="p-3 flex flex-col gap-2">
          {error && (
            <div className="px-3 py-3 rounded-xl" style={{ backgroundColor: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.2)' }}>
              <span className="font-mono" style={{ fontSize: '11px', color: '#ef4444' }}>{error}</span>
            </div>
          )}

          {/* Snapshot identity */}
          {snapshot && (
            <>
              <DiagRow icon={<Shield size={12} />} label="Scan ID" value={snapshot.scan_id} status="healthy" />
              <DiagRow icon={<GitBranch size={12} />} label="Git Commit" value={`${snapshot.commit} · gate ${lineage?.gate_version?.slice(0, 8) ?? '—'}`} status="healthy" />
              <DiagRow icon={<Clock size={12} />} label="Snapshot Generated" value={snapshot.generated_at} status="healthy" />
              <DiagRow icon={<Database size={12} />} label="Producer" value={lineage?.producer ?? '—'} status="healthy" />
              <DiagRow icon={<BarChart2 size={12} />} label="Universe / Events" value={`${stats?.universe_size ?? '—'} tickers · ${stats?.total_timeline_events ?? '—'} events`} status="healthy" />
              <DiagRow icon={<CheckCircle size={12} />} label="Near Constitutional" value={`${stats?.near_constitutional_count ?? '—'} tickers at threshold`} status="healthy" />
              <DiagRow icon={<Activity size={12} />} label="Re-Accumulation" value={`${stats?.re_accumulation_count ?? '—'} active events`} status="healthy" />

              {/* Portfolio health */}
              {snapshot.health_label && (
                <div
                  className="px-3 py-2.5 rounded-xl flex items-start gap-3"
                  style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}
                >
                  <Heart size={12} style={{ color: 'var(--signal-near)', flexShrink: 0, marginTop: '2px' }} />
                  <div className="flex-1 min-w-0">
                    <span className="font-mono font-semibold block" style={{ fontSize: '11px', color: 'var(--foreground)' }}>
                      {snapshot.health_stars} {snapshot.health_label}
                    </span>
                    <p className="font-mono mt-1" style={{ fontSize: '9px', color: 'var(--muted-foreground)', lineHeight: 1.5 }}>
                      {snapshot.health_narrative}
                    </p>
                  </div>
                </div>
              )}

              {/* Source fingerprints */}
              {lineage?.source_fingerprints && (
                <div
                  className="px-3 py-2.5 rounded-xl"
                  style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}
                >
                  <p className="font-mono mb-1.5" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>SOURCE FINGERPRINTS</p>
                  {Object.entries(lineage.source_fingerprints).map(([src, hash]) => (
                    <div key={src} className="flex items-center justify-between">
                      <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>{src}</span>
                      <span className="font-mono tabular-nums" style={{ fontSize: '9px', color: 'var(--foreground)', opacity: 0.6 }}>{hash}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          <div
            className="flex items-center gap-2 mt-1 px-3 py-2 rounded-lg"
            style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}
          >
            <Activity size={10} style={{ color: 'var(--muted-foreground)', flexShrink: 0 }} />
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
              Constitutional Algo System · snapshot refreshes every 60s · {snapshot?.market_date ?? '—'}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

function DiagRow({ icon, label, value, status }: { icon: React.ReactNode; label: string; value: string; status: 'healthy' | 'warning' | 'error' }) {
  const color = status === 'healthy' ? 'var(--signal-buy)' : status === 'warning' ? 'var(--signal-near)' : '#ef4444';
  return (
    <div
      className="flex items-center gap-3 px-3 py-2.5 rounded-xl"
      style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}
    >
      <div
        className="flex-shrink-0 flex items-center justify-center rounded-lg"
        style={{ width: '28px', height: '28px', backgroundColor: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.05)', color: 'var(--muted-foreground)' }}
      >
        {icon}
      </div>
      <span className="font-mono font-semibold flex-shrink-0" style={{ fontSize: '11px', color: 'var(--foreground)', width: '140px' }}>{label}</span>
      <span className="font-mono truncate flex-1 min-w-0" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>{value}</span>
      <CheckCircle size={12} style={{ color, flexShrink: 0 }} />
    </div>
  );
}
