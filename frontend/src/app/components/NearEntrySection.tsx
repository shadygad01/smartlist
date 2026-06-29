'use client';

import React from 'react';
import { Clock, TrendingUp, ArrowRight } from 'lucide-react';
import R2ProgressBar from './R2ProgressBar';

interface NearEntryTicker {
  id: string;
  ticker: string;
  company: string;
  r2Score: number;
  proximity: number;
  entryPrice: number;
  currentPrice: number;
  winRate: number;
  trend: 'approaching' | 'at_zone' | 'slightly_above';
}

const nearEntryTickers: NearEntryTicker[] = [
  {
    id: 'near-fwry',
    ticker: 'FWRY.CA',
    company: 'Fawry for Banking Technology',
    r2Score: 0.89,
    proximity: 2.3,
    entryPrice: 42.10,
    currentPrice: 43.07,
    winRate: 88,
    trend: 'approaching',
  },
  {
    id: 'near-btfh',
    ticker: 'BTFH.CA',
    company: 'Beltone Financial Holding',
    r2Score: 0.82,
    proximity: 1.1,
    entryPrice: 18.45,
    currentPrice: 18.65,
    winRate: 83,
    trend: 'at_zone',
  },
  {
    id: 'near-hrho',
    ticker: 'HRHO.CA',
    company: 'Hermes Financial Group',
    r2Score: 0.91,
    proximity: 3.7,
    entryPrice: 55.20,
    currentPrice: 57.24,
    winRate: 91,
    trend: 'approaching',
  },
  {
    id: 'near-mcqe',
    ticker: 'MCQE.CA',
    company: 'Madinet Masr for Housing',
    r2Score: 0.77,
    proximity: 0.8,
    entryPrice: 31.60,
    currentPrice: 31.85,
    winRate: 79,
    trend: 'at_zone',
  },
];

function getTrendBadge(trend: NearEntryTicker['trend']) {
  if (trend === 'at_zone') {
    return (
      <span
        className="font-mono px-2 py-0.5 rounded-md"
        style={{
          fontSize: '9px',
          backgroundColor: 'rgba(245,158,11,0.12)',
          color: 'var(--signal-near)',
          border: '1px solid rgba(245,158,11,0.25)',
          letterSpacing: '0.04em',
        }}
      >
        AT ZONE
      </span>
    );
  }
  return (
    <span
      className="font-mono px-2 py-0.5 rounded-md"
      style={{
        fontSize: '9px',
        backgroundColor: 'rgba(59,130,246,0.08)',
        color: 'var(--signal-reaccum)',
        border: '1px solid rgba(59,130,246,0.18)',
        letterSpacing: '0.04em',
      }}
    >
      APPROACHING
    </span>
  );
}

export default function NearEntrySection() {
  return (
    <div
      className="rounded-xl h-full glow-near"
      style={{
        backgroundColor: 'var(--card)',
        border: '1px solid var(--signal-near-border)',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3.5 rounded-t-xl"
        style={{
          background: 'linear-gradient(135deg, rgba(245,158,11,0.08) 0%, rgba(245,158,11,0.02) 100%)',
          borderBottom: '1px solid var(--signal-near-border)',
        }}
      >
        <div className="flex items-center gap-2">
          <Clock size={13} style={{ color: 'var(--signal-near)' }} />
          <span
            className="font-mono font-semibold"
            style={{ fontSize: '12px', color: 'var(--signal-near)', letterSpacing: '0.07em' }}
          >
            NEAR ENTRY
          </span>
          <span
            className="font-mono px-1.5 py-0.5 rounded-full"
            style={{
              fontSize: '9px',
              backgroundColor: 'rgba(245,158,11,0.12)',
              color: 'var(--signal-near)',
              border: '1px solid rgba(245,158,11,0.2)',
            }}
          >
            {nearEntryTickers.length}
          </span>
        </div>
        <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>
          WATCHLIST
        </span>
      </div>

      {/* Ticker list */}
      <div className="p-3 flex flex-col gap-2.5">
        {nearEntryTickers.map((item) => (
          <div
            key={item.id}
            className="ticker-row rounded-xl p-3.5 cursor-pointer"
            style={{
              backgroundColor: 'rgba(255,255,255,0.02)',
              border: '1px solid var(--border)',
            }}
          >
            {/* Row top: ticker + badge + proximity */}
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span
                  className="font-mono font-bold"
                  style={{ fontSize: '13px', color: 'var(--foreground)', letterSpacing: '0.02em' }}
                >
                  {item.ticker}
                </span>
                {getTrendBadge(item.trend)}
              </div>
              <div className="flex items-center gap-1">
                <TrendingUp size={10} style={{ color: 'var(--signal-near)' }} />
                <span
                  className="font-mono font-semibold tabular-nums"
                  style={{ fontSize: '11px', color: 'var(--signal-near)' }}
                >
                  +{item.proximity.toFixed(1)}%
                </span>
              </div>
            </div>

            {/* Company name */}
            <p
              className="mb-2.5 truncate"
              style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}
            >
              {item.company}
            </p>

            {/* Prices row */}
            <div
              className="flex items-center justify-between mb-2.5 px-3 py-2 rounded-lg"
              style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-subtle)' }}
            >
              <div>
                <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
                  ENTRY{' '}
                </span>
                <span
                  className="font-mono font-semibold tabular-nums"
                  style={{ fontSize: '12px', color: 'var(--signal-near)' }}
                >
                  {item.entryPrice.toFixed(2)}
                </span>
              </div>
              <ArrowRight size={10} style={{ color: 'var(--muted-foreground)' }} />
              <div>
                <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
                  NOW{' '}
                </span>
                <span
                  className="font-mono font-semibold tabular-nums"
                  style={{ fontSize: '12px', color: 'var(--foreground)' }}
                >
                  {item.currentPrice.toFixed(2)}
                </span>
              </div>
              <div>
                <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
                  WIN{' '}
                </span>
                <span
                  className="font-mono font-semibold tabular-nums"
                  style={{ fontSize: '12px', color: 'var(--signal-buy)' }}
                >
                  {item.winRate}%
                </span>
              </div>
            </div>

            {/* R2 bar */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
                  R² SCORE
                </span>
                <span
                  className="font-mono font-semibold tabular-nums"
                  style={{ fontSize: '9px', color: 'var(--signal-near)' }}
                >
                  {(item.r2Score * 100).toFixed(0)}%
                </span>
              </div>
              <R2ProgressBar value={item.r2Score} color="var(--signal-near)" height={3} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}