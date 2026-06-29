'use client';

import React, { useState, useEffect } from 'react';
import { Wifi, RefreshCw, AlertCircle, Archive, Signal } from 'lucide-react';
import AppLogo from '@/components/ui/AppLogo';
import Link from 'next/link';
import { useSnapshot } from '@/providers/SnapshotProvider';

// Wall-clock display only — NOT used for trading date calculations.
// All trading dates and market status come from the production snapshot.
function formatCairoTime(date: Date): string {
  return date.toLocaleTimeString('en-GB', { timeZone: 'Africa/Cairo', hour12: false });
}

function formatCairoDate(date: Date): string {
  return date.toLocaleDateString('en-GB', {
    timeZone: 'Africa/Cairo',
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
}

export default function DashboardHeader() {
  const { snapshot, loading, error } = useSnapshot();

  const [timeStr, setTimeStr] = useState('--:--:--');
  const [dateStr, setDateStr] = useState('');

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setTimeStr(formatCairoTime(now));
      setDateStr(formatCairoDate(now));
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const isLive = !error && !loading;
  const marketStatus = snapshot?.market_status ?? (loading ? '...' : 'UNAVAILABLE');
  const scanId = snapshot?.scan_id ? snapshot.scan_id.slice(0, 8) : '--------';
  const commit = snapshot?.commit ?? '-------';

  return (
    <header
      className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-4 md:px-6 xl:px-10"
      style={{
        height: '68px',
        backgroundColor: 'rgba(7, 11, 20, 0.95)',
        borderBottom: '1px solid rgba(26, 37, 64, 0.8)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        boxShadow: '0 1px 0 rgba(255,255,255,0.03), 0 4px 24px rgba(0,0,0,0.4)',
      }}
    >
      {/* Left: Logo + Brand */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2.5">
          <div
            className="flex items-center justify-center rounded-lg"
            style={{
              width: '34px',
              height: '34px',
              background: 'linear-gradient(135deg, rgba(16,185,129,0.2) 0%, rgba(16,185,129,0.05) 100%)',
              border: '1px solid rgba(16,185,129,0.25)',
            }}
          >
            <AppLogo size={20} />
          </div>
          <div className="flex flex-col leading-tight">
            <div className="flex items-center gap-1.5">
              <span
                className="font-semibold tracking-tight"
                style={{ fontSize: '14px', color: 'var(--foreground)', letterSpacing: '-0.01em' }}
              >
                EGX<span style={{ color: 'var(--signal-buy)' }}>_</span>Command
              </span>
              <span
                className="font-mono px-1.5 py-0.5 rounded"
                style={{
                  fontSize: '9px',
                  backgroundColor: 'rgba(16,185,129,0.1)',
                  color: 'var(--signal-buy)',
                  border: '1px solid rgba(16,185,129,0.2)',
                  letterSpacing: '0.04em',
                }}
              >
                {commit}
              </span>
            </div>
            <span
              className="font-mono"
              style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.1em' }}
            >
              SCAN {scanId}
            </span>
          </div>
        </div>
      </div>

      {/* Center: Status indicators */}
      <div className="hidden md:flex items-center gap-1">
        <div
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg"
          style={{
            backgroundColor: isLive ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
            border: `1px solid ${isLive ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}`,
          }}
        >
          <span
            className="pulse-dot inline-block w-1.5 h-1.5 rounded-full"
            style={{ backgroundColor: isLive ? 'var(--signal-buy)' : 'var(--signal-danger)' }}
          />
          <span
            className="font-mono font-bold"
            style={{ fontSize: '10px', color: isLive ? 'var(--signal-buy)' : 'var(--signal-danger)', letterSpacing: '0.08em' }}
          >
            {isLive ? 'LIVE' : error ? 'ERROR' : 'LOADING'}
          </span>
        </div>

        <div style={{ width: '1px', height: '20px', backgroundColor: 'var(--border)', margin: '0 8px' }} />

        <div className="flex items-center gap-1.5">
          <RefreshCw size={11} style={{ color: 'var(--muted-foreground)' }} className="scan-blink" />
          <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>
            SNAPSHOT
          </span>
          <span className="font-mono font-medium" style={{ fontSize: '10px', color: 'var(--foreground)' }}>
            {snapshot?.price_data_as_of ?? '--'}
          </span>
        </div>

        <div style={{ width: '1px', height: '20px', backgroundColor: 'var(--border)', margin: '0 8px' }} />

        <div className="flex items-center gap-1.5">
          <Signal size={11} style={{ color: 'var(--signal-near)' }} />
          <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>
            EGX
          </span>
          <span
            className="font-mono font-bold"
            style={{ fontSize: '10px', color: 'var(--signal-near)', letterSpacing: '0.06em' }}
          >
            {marketStatus}
          </span>
        </div>
      </div>

      {/* Right: Cairo Clock + Archive Link */}
      <div className="flex items-center gap-3">
        <Link
          href="/archive"
          className="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all duration-150"
          style={{
            backgroundColor: 'rgba(167,139,250,0.06)',
            border: '1px solid rgba(167,139,250,0.18)',
          }}
        >
          <Archive size={11} style={{ color: 'var(--signal-elite)' }} />
          <span
            className="font-mono font-semibold"
            style={{ fontSize: '10px', color: 'var(--signal-elite)', letterSpacing: '0.07em' }}
          >
            ARCHIVE
          </span>
        </Link>

        <div
          className="flex items-center gap-3 px-3 py-1.5 rounded-lg"
          style={{ backgroundColor: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)' }}
        >
          <div className="flex flex-col items-end">
            <div className="flex items-center gap-1.5">
              <span
                className="font-mono font-bold tabular-nums"
                style={{ fontSize: '14px', color: 'var(--foreground)', letterSpacing: '0.05em' }}
              >
                {timeStr}
              </span>
              <span
                className="font-mono px-1 py-0.5 rounded"
                style={{
                  fontSize: '8px',
                  backgroundColor: 'rgba(59,130,246,0.12)',
                  color: 'var(--signal-reaccum)',
                  border: '1px solid rgba(59,130,246,0.18)',
                  letterSpacing: '0.06em',
                }}
              >
                CAI
              </span>
            </div>
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
              {dateStr}
            </span>
          </div>

          <div
            className="p-1.5 rounded-md"
            style={{
              backgroundColor: isLive ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
              border: `1px solid ${isLive ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}`,
            }}
          >
            {isLive ? (
              <Wifi size={14} style={{ color: 'var(--signal-buy)' }} />
            ) : (
              <AlertCircle size={14} style={{ color: 'var(--signal-danger)' }} />
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
