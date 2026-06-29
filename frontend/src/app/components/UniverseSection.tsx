'use client';

import React, { useState } from 'react';
import { Globe, ChevronDown, ChevronUp, TrendingUp, TrendingDown, Minus } from 'lucide-react';

interface UniverseTicker {
  id: string;
  ticker: string;
  sector: string;
  status: 'buy' | 'reaccum' | 'near' | 'neutral' | 'watch';
  change: number;
  r2Score: number;
}

const universeTickers: UniverseTicker[] = [
  { id: 'uni-abuk', ticker: 'ABUK.CA', sector: 'Trade', status: 'buy', change: 1.2, r2Score: 0.94 },
  { id: 'uni-fwry', ticker: 'FWRY.CA', sector: 'Fintech', status: 'near', change: -0.8, r2Score: 0.89 },
  { id: 'uni-btfh', ticker: 'BTFH.CA', sector: 'Finance', status: 'near', change: 0.3, r2Score: 0.82 },
  { id: 'uni-hrho', ticker: 'HRHO.CA', sector: 'Finance', status: 'near', change: -1.4, r2Score: 0.91 },
  { id: 'uni-mcqe', ticker: 'MCQE.CA', sector: 'Real Estate', status: 'near', change: 0.6, r2Score: 0.77 },
  { id: 'uni-comi', ticker: 'COMI.CA', sector: 'Banking', status: 'reaccum', change: 0.4, r2Score: 0.86 },
  { id: 'uni-etel', ticker: 'ETEL.CA', sector: 'Telecom', status: 'neutral', change: -0.2, r2Score: 0.71 },
  { id: 'uni-mnhd', ticker: 'MNHD.CA', sector: 'Real Estate', status: 'watch', change: 1.8, r2Score: 0.68 },
  { id: 'uni-swdy', ticker: 'SWDY.CA', sector: 'Industrials', status: 'reaccum', change: -0.5, r2Score: 0.79 },
  { id: 'uni-orwe', ticker: 'ORWE.CA', sector: 'Construction', status: 'neutral', change: 0.1, r2Score: 0.65 },
  { id: 'uni-ekhw', ticker: 'EKHW.CA', sector: 'Healthcare', status: 'watch', change: -1.1, r2Score: 0.73 },
  { id: 'uni-amoc', ticker: 'AMOC.CA', sector: 'Petroleum', status: 'neutral', change: 2.1, r2Score: 0.61 },
  { id: 'uni-ocdi', ticker: 'OCDI.CA', sector: 'Construction', status: 'reaccum', change: 0.9, r2Score: 0.84 },
  { id: 'uni-egts', ticker: 'EGTS.CA', sector: 'Tourism', status: 'neutral', change: -0.3, r2Score: 0.58 },
  { id: 'uni-phdc', ticker: 'PHDC.CA', sector: 'Real Estate', status: 'watch', change: 1.4, r2Score: 0.72 },
  { id: 'uni-efih', ticker: 'EFIH.CA', sector: 'Finance', status: 'neutral', change: 0.7, r2Score: 0.66 },
  { id: 'uni-tmgh', ticker: 'TMGH.CA', sector: 'Real Estate', status: 'reaccum', change: -0.9, r2Score: 0.81 },
  { id: 'uni-skpc', ticker: 'SKPC.CA', sector: 'Chemicals', status: 'neutral', change: 0.2, r2Score: 0.59 },
  { id: 'uni-cieb', ticker: 'CIEB.CA', sector: 'Banking', status: 'reaccum', change: 1.1, r2Score: 0.88 },
  { id: 'uni-qnba', ticker: 'QNBA.CA', sector: 'Banking', status: 'watch', change: -0.4, r2Score: 0.75 },
  { id: 'uni-ekho', ticker: 'EKHO.CA', sector: 'Retail', status: 'neutral', change: 0.5, r2Score: 0.62 },
  { id: 'uni-csag', ticker: 'CSAG.CA', sector: 'Food', status: 'watch', change: -0.6, r2Score: 0.69 },
  { id: 'uni-abcb', ticker: 'ABCB.CA', sector: 'Banking', status: 'neutral', change: 0.3, r2Score: 0.64 },
  { id: 'uni-spmd', ticker: 'SPMD.CA', sector: 'Pharma', status: 'watch', change: 1.6, r2Score: 0.76 },
  { id: 'uni-bkip', ticker: 'BKIP.CA', sector: 'Industrials', status: 'neutral', change: -0.7, r2Score: 0.57 },
  { id: 'uni-mpci', ticker: 'MPCI.CA', sector: 'Petroleum', status: 'reaccum', change: 0.8, r2Score: 0.83 },
  { id: 'uni-ccap', ticker: 'CCAP.CA', sector: 'Finance', status: 'neutral', change: -0.1, r2Score: 0.60 },
];

function getStatusBadge(status: UniverseTicker['status']) {
  const map = {
    buy: { label: 'BUY', color: 'var(--signal-buy)', bg: 'rgba(16,185,129,0.1)', border: 'rgba(16,185,129,0.25)' },
    reaccum: { label: 'RE-ACCUM', color: 'var(--signal-reaccum)', bg: 'rgba(59,130,246,0.08)', border: 'rgba(59,130,246,0.18)' },
    near: { label: 'NEAR', color: 'var(--signal-near)', bg: 'rgba(245,158,11,0.08)', border: 'rgba(245,158,11,0.2)' },
    neutral: { label: 'NEUTRAL', color: 'var(--muted-foreground)', bg: 'rgba(255,255,255,0.03)', border: 'var(--border)' },
    watch: { label: 'WATCH', color: '#a78bfa', bg: 'rgba(167,139,250,0.07)', border: 'rgba(167,139,250,0.18)' },
  };
  const s = map[status];
  return (
    <span
      className="font-mono"
      style={{
        fontSize: '9px',
        padding: '2px 7px',
        borderRadius: '5px',
        backgroundColor: s.bg,
        color: s.color,
        border: `1px solid ${s.border}`,
        letterSpacing: '0.05em',
      }}
    >
      {s.label}
    </span>
  );
}

export default function UniverseSection() {
  const [collapsed, setCollapsed] = useState(false);

  const buyCount = universeTickers.filter((t) => t.status === 'buy').length;
  const nearCount = universeTickers.filter((t) => t.status === 'near').length;
  const reaccumCount = universeTickers.filter((t) => t.status === 'reaccum').length;

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
          <Globe size={13} style={{ color: 'var(--signal-reaccum)' }} />
          <span
            className="font-mono font-semibold"
            style={{ fontSize: '12px', color: 'var(--foreground)', letterSpacing: '0.07em' }}
          >
            UNIVERSE
          </span>
          <span
            className="font-mono px-1.5 py-0.5 rounded-full"
            style={{
              fontSize: '9px',
              backgroundColor: 'rgba(59,130,246,0.1)',
              color: 'var(--signal-reaccum)',
              border: '1px solid rgba(59,130,246,0.18)',
            }}
          >
            {universeTickers.length}
          </span>
          {/* Mini stat pills */}
          <div className="hidden md:flex items-center gap-1.5 ml-1">
            <span
              className="font-mono"
              style={{ fontSize: '9px', padding: '1px 7px', borderRadius: '4px', backgroundColor: 'rgba(16,185,129,0.08)', color: 'var(--signal-buy)', border: '1px solid rgba(16,185,129,0.15)' }}
            >
              {buyCount} BUY
            </span>
            <span
              className="font-mono"
              style={{ fontSize: '9px', padding: '1px 7px', borderRadius: '4px', backgroundColor: 'rgba(245,158,11,0.07)', color: 'var(--signal-near)', border: '1px solid rgba(245,158,11,0.15)' }}
            >
              {nearCount} NEAR
            </span>
            <span
              className="font-mono"
              style={{ fontSize: '9px', padding: '1px 7px', borderRadius: '4px', backgroundColor: 'rgba(59,130,246,0.07)', color: 'var(--signal-reaccum)', border: '1px solid rgba(59,130,246,0.15)' }}
            >
              {reaccumCount} RE-ACC
            </span>
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
        <div className="p-3">
          {/* Table header */}
          <div
            className="grid gap-2 px-3 py-2 mb-1 rounded-lg"
            style={{
              gridTemplateColumns: '1fr 80px 60px 50px',
              backgroundColor: 'rgba(255,255,255,0.02)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.08em' }}>
              TICKER / SECTOR
            </span>
            <span className="font-mono text-center" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.08em' }}>
              STATUS
            </span>
            <span className="font-mono text-right" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.08em' }}>
              CHG%
            </span>
            <span className="font-mono text-right" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.08em' }}>
              R²
            </span>
          </div>

          {/* Scrollable list */}
          <div className="overflow-y-auto" style={{ maxHeight: '320px' }}>
            {universeTickers.map((item) => (
              <div
                key={item.id}
                className="ticker-row grid gap-2 px-3 py-2 rounded-lg cursor-pointer"
                style={{ gridTemplateColumns: '1fr 80px 60px 50px' }}
              >
                <div className="flex flex-col min-w-0">
                  <span
                    className="font-mono font-semibold truncate"
                    style={{ fontSize: '12px', color: 'var(--foreground)' }}
                  >
                    {item.ticker}
                  </span>
                  <span
                    className="font-mono truncate"
                    style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}
                  >
                    {item.sector}
                  </span>
                </div>
                <div className="flex items-center justify-center">
                  {getStatusBadge(item.status)}
                </div>
                <div className="flex items-center justify-end gap-1">
                  {item.change > 0 ? (
                    <TrendingUp size={9} style={{ color: 'var(--signal-buy)' }} />
                  ) : item.change < 0 ? (
                    <TrendingDown size={9} style={{ color: '#ef4444' }} />
                  ) : (
                    <Minus size={9} style={{ color: 'var(--muted-foreground)' }} />
                  )}
                  <span
                    className="font-mono tabular-nums"
                    style={{
                      fontSize: '11px',
                      color: item.change > 0 ? 'var(--signal-buy)' : item.change < 0 ? '#ef4444' : 'var(--muted-foreground)',
                    }}
                  >
                    {item.change > 0 ? '+' : ''}{item.change.toFixed(1)}%
                  </span>
                </div>
                <div className="flex items-center justify-end">
                  <span
                    className="font-mono tabular-nums"
                    style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}
                  >
                    {(item.r2Score * 100).toFixed(0)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}