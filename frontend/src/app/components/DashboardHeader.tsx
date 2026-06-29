'use client';

import React, { useState, useEffect } from 'react';
import { Wifi, RefreshCw, AlertCircle, Archive, Signal } from 'lucide-react';
import AppLogo from '@/components/ui/AppLogo';
import Link from 'next/link';

function formatCairoTime(date: Date): string {
  const utc = date.getTime() + date.getTimezoneOffset() * 60000;
  const cairo = new Date(utc + 3 * 3600000);
  const h = cairo.getHours().toString().padStart(2, '0');
  const m = cairo.getMinutes().toString().padStart(2, '0');
  const s = cairo.getSeconds().toString().padStart(2, '0');
  return `${h}:${m}:${s}`;
}

function formatCairoDate(date: Date): string {
  const utc = date.getTime() + date.getTimezoneOffset() * 60000;
  const cairo = new Date(utc + 3 * 3600000);
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  return `${days[cairo.getDay()]}, ${cairo.getDate()} ${months[cairo.getMonth()]} ${cairo.getFullYear()}`;
}

export default function DashboardHeader() {
  const [timeStr, setTimeStr] = useState('--:--:--');
  const [dateStr, setDateStr] = useState('');
  const [scanAge, setScanAge] = useState(0);
  const [isLive, setIsLive] = useState(true);

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setTimeStr(formatCairoTime(now));
      setDateStr(formatCairoDate(now));
      setScanAge((prev) => prev + 1);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const id = setInterval(() => {
      setIsLive(true);
    }, 30000);
    return () => clearInterval(id);
  }, []);

  const scanAgeDisplay = scanAge < 60
    ? `${scanAge}s ago`
    : scanAge < 3600
    ? `${Math.floor(scanAge / 60)}m ago`
    : `${Math.floor(scanAge / 3600)}h ago`;

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
                v2.4
              </span>
            </div>
            <span
              className="font-mono"
              style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.1em' }}
            >
              CONSTITUTIONAL SIGNAL SYSTEM
            </span>
          </div>
        </div>
      </div>

      {/* Center: Status indicators */}
      <div className="hidden md:flex items-center gap-1">
        {/* Live indicator */}
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
            {isLive ? 'LIVE' : 'RECONNECTING'}
          </span>
        </div>

        {/* Divider */}
        <div style={{ width: '1px', height: '20px', backgroundColor: 'var(--border)', margin: '0 8px' }} />

        {/* Scan status */}
        <div className="flex items-center gap-1.5">
          <RefreshCw size={11} style={{ color: 'var(--muted-foreground)' }} className="scan-blink" />
          <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>
            SCAN
          </span>
          <span className="font-mono font-medium" style={{ fontSize: '10px', color: 'var(--foreground)' }}>
            {scanAgeDisplay}
          </span>
        </div>

        {/* Divider */}
        <div style={{ width: '1px', height: '20px', backgroundColor: 'var(--border)', margin: '0 8px' }} />

        {/* Market status */}
        <div className="flex items-center gap-1.5">
          <Signal size={11} style={{ color: 'var(--signal-near)' }} />
          <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>
            EGX
          </span>
          <span
            className="font-mono font-bold"
            style={{ fontSize: '10px', color: 'var(--signal-near)', letterSpacing: '0.06em' }}
          >
            PRE-OPEN
          </span>
        </div>
      </div>

      {/* Right: Cairo Clock + Archive Link */}
      <div className="flex items-center gap-3">
        {/* Archive nav link */}
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

        {/* Clock block */}
        <div
          className="flex items-center gap-3 px-3 py-1.5 rounded-lg"
          style={{
            backgroundColor: 'rgba(255,255,255,0.03)',
            border: '1px solid var(--border)',
          }}
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

          {/* Connection icon */}
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