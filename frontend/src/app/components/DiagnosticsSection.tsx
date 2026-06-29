'use client';

import React, { useState } from 'react';
import { Activity, ChevronDown, ChevronUp, CheckCircle, AlertTriangle, XCircle, Cpu, Database, Wifi, BarChart2, Clock, Server } from 'lucide-react';

interface DiagnosticItem {
  id: string;
  label: string;
  status: 'healthy' | 'warning' | 'error';
  value: string;
  detail: string;
  icon: React.ReactNode;
}

const diagnostics: DiagnosticItem[] = [
  { id: 'diag-data-feed', label: 'EGX Data Feed', status: 'healthy', value: '12ms', detail: 'All 27 tickers streaming nominal', icon: <Wifi size={12} /> },
  { id: 'diag-algo-engine', label: 'Constitutional Algo Engine', status: 'healthy', value: 'v2.4.1', detail: 'Model parameters loaded, R² validation passed', icon: <Cpu size={12} /> },
  { id: 'diag-signal-db', label: 'Signal Database', status: 'healthy', value: '44 events', detail: 'Session events indexed, write latency 3ms', icon: <Database size={12} /> },
  { id: 'diag-scanner', label: 'Universe Scanner', status: 'healthy', value: '27/27', detail: 'Full coverage, last scan 5:14:22 CAI', icon: <BarChart2 size={12} /> },
  { id: 'diag-clock', label: 'Cairo Time Sync', status: 'healthy', value: 'UTC+3', detail: 'NTP synchronized, drift < 50ms', icon: <Clock size={12} /> },
  { id: 'diag-server', label: 'Compute Node', status: 'warning', value: '78% CPU', detail: 'Elevated load during morning scan — monitor', icon: <Server size={12} /> },
  { id: 'diag-api', label: 'Market Data API', status: 'healthy', value: '99.9%', detail: 'Uptime last 30 days, zero missed ticks today', icon: <Activity size={12} /> },
];

function StatusIcon({ status }: { status: DiagnosticItem['status'] }) {
  if (status === 'healthy') return <CheckCircle size={12} style={{ color: 'var(--signal-buy)', flexShrink: 0 }} />;
  if (status === 'warning') return <AlertTriangle size={12} style={{ color: 'var(--signal-near)', flexShrink: 0 }} />;
  return <XCircle size={12} style={{ color: '#ef4444', flexShrink: 0 }} />;
}

function getStatusColor(status: DiagnosticItem['status']) {
  if (status === 'healthy') return 'var(--signal-buy)';
  if (status === 'warning') return 'var(--signal-near)';
  return '#ef4444';
}

export default function DiagnosticsSection() {
  const [collapsed, setCollapsed] = useState(false);

  const healthyCount = diagnostics.filter((d) => d.status === 'healthy').length;
  const warningCount = diagnostics.filter((d) => d.status === 'warning').length;
  const errorCount = diagnostics.filter((d) => d.status === 'error').length;

  const overallStatus = errorCount > 0 ? 'error' : warningCount > 0 ? 'warning' : 'healthy';

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
          <Activity size={13} style={{ color: overallStatus === 'healthy' ? 'var(--signal-buy)' : overallStatus === 'warning' ? 'var(--signal-near)' : '#ef4444' }} />
          <span
            className="font-mono font-semibold"
            style={{ fontSize: '12px', color: 'var(--foreground)', letterSpacing: '0.07em' }}
          >
            SYSTEM DIAGNOSTICS
          </span>
          {/* Status summary */}
          <div className="flex items-center gap-1.5">
            <span
              className="font-mono"
              style={{
                fontSize: '9px',
                padding: '1px 7px',
                borderRadius: '4px',
                backgroundColor: 'rgba(16,185,129,0.08)',
                color: 'var(--signal-buy)',
                border: '1px solid rgba(16,185,129,0.15)',
              }}
            >
              {healthyCount} OK
            </span>
            {warningCount > 0 && (
              <span
                className="font-mono"
                style={{
                  fontSize: '9px',
                  padding: '1px 7px',
                  borderRadius: '4px',
                  backgroundColor: 'rgba(245,158,11,0.08)',
                  color: 'var(--signal-near)',
                  border: '1px solid rgba(245,158,11,0.15)',
                }}
              >
                {warningCount} WARN
              </span>
            )}
            {errorCount > 0 && (
              <span
                className="font-mono"
                style={{
                  fontSize: '9px',
                  padding: '1px 7px',
                  borderRadius: '4px',
                  backgroundColor: 'rgba(239,68,68,0.08)',
                  color: '#ef4444',
                  border: '1px solid rgba(239,68,68,0.15)',
                }}
              >
                {errorCount} ERR
              </span>
            )}
          </div>
        </div>
        {collapsed ? (
          <ChevronDown size={13} style={{ color: 'var(--muted-foreground)' }} />
        ) : (
          <ChevronUp size={13} style={{ color: 'var(--muted-foreground)' }} />
        )}
      </button>

      {/* Content */}
      {!collapsed && (
        <div className="p-3 flex flex-col gap-2">
          {diagnostics.map((item) => (
            <div
              key={item.id}
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl"
              style={{
                backgroundColor: item.status === 'warning' ? 'rgba(245,158,11,0.04)'
                  : item.status === 'error' ? 'rgba(239,68,68,0.04)' : 'rgba(255,255,255,0.02)',
                border: `1px solid ${
                  item.status === 'warning' ? 'rgba(245,158,11,0.18)'
                    : item.status === 'error' ? 'rgba(239,68,68,0.18)' : 'var(--border-subtle)'
                }`,
              }}
            >
              {/* Service icon */}
              <div
                className="flex-shrink-0 flex items-center justify-center rounded-lg"
                style={{
                  width: '30px',
                  height: '30px',
                  backgroundColor: 'rgba(255,255,255,0.04)',
                  border: '1px solid rgba(255,255,255,0.05)',
                  color: 'var(--muted-foreground)',
                }}
              >
                {item.icon}
              </div>

              {/* Label + detail */}
              <div className="flex-1 min-w-0">
                <span
                  className="font-mono font-semibold block truncate"
                  style={{ fontSize: '11px', color: 'var(--foreground)' }}
                >
                  {item.label}
                </span>
                <p
                  className="font-mono truncate"
                  style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}
                >
                  {item.detail}
                </p>
              </div>

              {/* Value + status */}
              <div className="flex items-center gap-2 flex-shrink-0">
                <span
                  className="font-mono font-semibold tabular-nums"
                  style={{ fontSize: '11px', color: getStatusColor(item.status) }}
                >
                  {item.value}
                </span>
                <StatusIcon status={item.status} />
              </div>
            </div>
          ))}

          {/* Footer note */}
          <div
            className="flex items-center gap-2 mt-1 px-3 py-2 rounded-lg"
            style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}
          >
            <Activity size={10} style={{ color: 'var(--muted-foreground)', flexShrink: 0 }} />
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
              Diagnostics refresh every 30s · Constitutional Algo System v2.4 · EGX Session 2026-06-29
            </span>
          </div>
        </div>
      )}
    </div>
  );
}