'use client';

import React, { useState } from 'react';
import { TrendingUp, Award, Copy, CheckCircle, BarChart2, Clock, Target, Zap, Brain, Activity } from 'lucide-react';
import { toast } from 'sonner';
import R2ProgressBar from './R2ProgressBar';

const signal = {
  ticker: 'ABUK.CA',
  companyName: 'Abu Khashaba for Trade & Agencies',
  signalType: 'NEW BUY ELITE',
  tier: 'ELITE',
  entryPrice: 69.05,
  currentPrice: 67.80,
  discount: 1.81,
  winRate: 95,
  avgReturn: 52.6,
  r2Score: 0.94,
  priorSignals: 20,
  sector: 'Trade & Distribution',
  detectedAt: '05:14:22',
  confidence: 'VERY HIGH',
  target1: 78.50,
  target2: 89.30,
  volumeRatio: 2.4,
  ive: 84.30,
  behaviorPhase: 'ACCUMULATION',
};

const behaviorPhaseColor: Record<string, string> = {
  ACCUMULATION: '#3b82f6',
  BREAKOUT: '#10b981',
  DISTRIBUTION: '#f59e0b',
  MARKUP: '#10b981',
  MARKDOWN: '#ef4444',
};

export default function BuySignalCard() {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard?.writeText(signal?.ticker)?.catch(() => {});
    setCopied(true);
    toast?.success(`Copied ${signal?.ticker} to clipboard`, {
      duration: 2000,
      style: { background: 'var(--card)', border: '1px solid var(--signal-buy-border)', color: 'var(--foreground)' },
    });
    setTimeout(() => setCopied(false), 2000);
  };

  const phaseColor = behaviorPhaseColor[signal?.behaviorPhase] ?? '#f59e0b';

  return (
    <div
      className="rounded-xl glow-buy animate-fade-in-up"
      style={{
        backgroundColor: 'var(--card)',
        border: '1px solid var(--signal-buy-border)',
      }}
    >
      {/* Card Header */}
      <div
        className="flex items-center justify-between px-5 py-3.5 rounded-t-xl"
        style={{
          background: 'linear-gradient(135deg, rgba(16,185,129,0.1) 0%, rgba(16,185,129,0.03) 100%)',
          borderBottom: '1px solid var(--signal-buy-border)',
        }}
      >
        <div className="flex items-center gap-2.5">
          <div
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg"
            style={{
              backgroundColor: 'rgba(16,185,129,0.12)',
              border: '1px solid rgba(16,185,129,0.3)',
            }}
          >
            <TrendingUp size={12} style={{ color: 'var(--signal-buy)' }} />
            <span
              className="font-mono font-bold"
              style={{ fontSize: '11px', color: 'var(--signal-buy)', letterSpacing: '0.07em' }}
            >
              {signal?.signalType}
            </span>
          </div>

          <div
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg"
            style={{
              backgroundColor: 'rgba(167,139,250,0.1)',
              border: '1px solid rgba(167,139,250,0.25)',
            }}
          >
            <Award size={11} style={{ color: 'var(--signal-elite)' }} />
            <span
              className="font-mono font-bold"
              style={{ fontSize: '10px', color: 'var(--signal-elite)', letterSpacing: '0.07em' }}
            >
              ELITE
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <Clock size={10} style={{ color: 'var(--muted-foreground)' }} />
          <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>
            Detected {signal?.detectedAt} CAI
          </span>
        </div>
      </div>

      {/* Card Body */}
      <div className="px-5 py-5">

        {/* Ticker + Company */}
        <div className="flex items-start justify-between mb-5">
          <div>
            <div className="flex items-center gap-2.5 mb-1">
              <h2
                className="font-mono font-bold tabular-nums"
                style={{ fontSize: '36px', color: 'var(--foreground)', lineHeight: 1, letterSpacing: '-0.02em' }}
              >
                {signal?.ticker}
              </h2>
              <button
                onClick={handleCopy}
                className="p-1.5 rounded-md transition-all duration-150 hover:scale-105 active:scale-95"
                style={{
                  backgroundColor: copied ? 'rgba(16,185,129,0.1)' : 'rgba(255,255,255,0.04)',
                  border: `1px solid ${copied ? 'rgba(16,185,129,0.3)' : 'var(--border)'}`,
                  color: copied ? 'var(--signal-buy)' : 'var(--muted-foreground)',
                }}
                title="Copy ticker symbol"
              >
                {copied ? <CheckCircle size={13} /> : <Copy size={13} />}
              </button>
            </div>
            <p style={{ fontSize: '13px', color: 'var(--foreground)', fontWeight: 500, opacity: 0.8 }}>
              {signal?.companyName}
            </p>
            <p
              className="font-mono mt-0.5"
              style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}
            >
              {signal?.sector} · EGX
            </p>
          </div>

          <div className="flex flex-col items-end gap-1.5">
            <span
              className="font-mono font-semibold px-3 py-1.5 rounded-lg"
              style={{
                fontSize: '10px',
                backgroundColor: 'rgba(16,185,129,0.1)',
                color: 'var(--signal-buy)',
                border: '1px solid rgba(16,185,129,0.2)',
                letterSpacing: '0.06em',
              }}
            >
              {signal?.confidence} CONFIDENCE
            </span>
            <div className="flex items-center gap-1">
              <Zap size={10} style={{ color: 'var(--signal-near)' }} />
              <span className="font-mono" style={{ fontSize: '10px', color: 'var(--signal-near)' }}>
                Vol Ratio: {signal?.volumeRatio}x
              </span>
            </div>
          </div>
        </div>

        {/* ── IVE + BEHAVIOR PHASE ── */}
        <div className="grid grid-cols-2 gap-3 mb-5">
          {/* IVE */}
          <div
            className="flex flex-col gap-1.5 p-4 rounded-xl"
            style={{ backgroundColor: 'rgba(167,139,250,0.07)', border: '1px solid rgba(167,139,250,0.2)' }}
          >
            <div className="flex items-center gap-1.5 mb-0.5">
              <Brain size={11} style={{ color: '#a78bfa' }} />
              <span
                className="font-mono"
                style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.09em' }}
              >
                INTRINSIC VALUE EST.
              </span>
            </div>
            <span
              className="font-mono font-bold tabular-nums"
              style={{ fontSize: '24px', color: '#a78bfa', lineHeight: 1.1, letterSpacing: '-0.01em' }}
            >
              {signal?.ive?.toFixed(2)}
            </span>
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
              EGP · fair value
            </span>
          </div>

          {/* BEHAVIOR PHASE */}
          <div
            className="flex flex-col gap-1.5 p-4 rounded-xl"
            style={{
              backgroundColor: 'rgba(59,130,246,0.07)',
              border: `1px solid rgba(59,130,246,0.2)`,
            }}
          >
            <div className="flex items-center gap-1.5 mb-0.5">
              <Activity size={11} style={{ color: phaseColor }} />
              <span
                className="font-mono"
                style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.09em' }}
              >
                BEHAVIOR PHASE
              </span>
            </div>
            <span
              className="font-mono font-bold"
              style={{ fontSize: '19px', color: phaseColor, lineHeight: 1.2, letterSpacing: '0.02em' }}
            >
              {signal?.behaviorPhase}
            </span>
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
              Wyckoff cycle stage
            </span>
          </div>
        </div>

        {/* Price Block */}
        <div
          className="grid grid-cols-3 gap-0 mb-5 rounded-xl overflow-hidden"
          style={{ border: '1px solid var(--border)' }}
        >
          <div
            className="flex flex-col gap-1 p-4"
            style={{ borderRight: '1px solid var(--border)', backgroundColor: 'rgba(16,185,129,0.05)' }}
          >
            <span
              className="font-mono"
              style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.08em' }}
            >
              BUY LIMIT
            </span>
            <span
              className="font-mono font-bold tabular-nums"
              style={{ fontSize: '22px', color: 'var(--signal-buy)', lineHeight: 1.1, letterSpacing: '-0.01em' }}
            >
              {signal?.entryPrice?.toFixed(2)}
            </span>
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
              EGP
            </span>
          </div>

          <div
            className="flex flex-col gap-1 p-4"
            style={{ borderRight: '1px solid var(--border)', backgroundColor: 'rgba(255,255,255,0.02)' }}
          >
            <span
              className="font-mono"
              style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.08em' }}
            >
              CURRENT
            </span>
            <span
              className="font-mono font-bold tabular-nums"
              style={{ fontSize: '22px', color: 'var(--foreground)', lineHeight: 1.1, letterSpacing: '-0.01em' }}
            >
              {signal?.currentPrice?.toFixed(2)}
            </span>
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
              EGP
            </span>
          </div>

          <div
            className="flex flex-col gap-1 p-4"
            style={{ backgroundColor: 'rgba(16,185,129,0.04)' }}
          >
            <span
              className="font-mono"
              style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.08em' }}
            >
              DISCOUNT
            </span>
            <span
              className="font-mono font-bold tabular-nums"
              style={{ fontSize: '22px', color: 'var(--signal-buy)', lineHeight: 1.1, letterSpacing: '-0.01em' }}
            >
              -{signal?.discount?.toFixed(1)}%
            </span>
            <span
              className="font-mono"
              style={{ fontSize: '9px', color: 'var(--signal-buy)', opacity: 0.7 }}
            >
              below limit
            </span>
          </div>
        </div>

        {/* Targets row */}
        <div className="grid grid-cols-2 gap-3 mb-5">
          <div
            className="flex flex-col gap-1 p-3.5 rounded-xl"
            style={{ backgroundColor: 'rgba(16,185,129,0.05)', border: '1px solid rgba(16,185,129,0.15)' }}
          >
            <span
              className="font-mono"
              style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.08em' }}
            >
              TARGET 1
            </span>
            <span
              className="font-mono font-semibold tabular-nums"
              style={{ fontSize: '20px', color: 'var(--signal-buy)', letterSpacing: '-0.01em' }}
            >
              {signal?.target1?.toFixed(2)}
            </span>
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
              EGP
            </span>
          </div>
          <div
            className="flex flex-col gap-1 p-3.5 rounded-xl"
            style={{ backgroundColor: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.2)' }}
          >
            <span
              className="font-mono"
              style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.08em' }}
            >
              TARGET 2
            </span>
            <span
              className="font-mono font-semibold tabular-nums"
              style={{ fontSize: '20px', color: 'var(--signal-buy)', letterSpacing: '-0.01em' }}
            >
              {signal?.target2?.toFixed(2)}
            </span>
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
              EGP
            </span>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-3 gap-3 mb-5">
          {/* Win Rate */}
          <div
            className="flex flex-col gap-2 p-3.5 rounded-xl"
            style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)' }}
          >
            <span
              className="font-mono"
              style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.08em' }}
            >
              WIN RATE
            </span>
            <span
              className="font-mono font-bold tabular-nums"
              style={{ fontSize: '24px', color: 'var(--signal-buy)', lineHeight: 1, letterSpacing: '-0.02em' }}
            >
              {signal?.winRate}%
            </span>
            <div className="w-full rounded-full overflow-hidden" style={{ height: '3px', backgroundColor: 'rgba(255,255,255,0.07)' }}>
              <div
                className="h-full rounded-full r2-bar-fill"
                style={{ width: `${signal?.winRate}%`, backgroundColor: 'var(--signal-buy)' }}
              />
            </div>
          </div>

          {/* Avg Return */}
          <div
            className="flex flex-col gap-2 p-3.5 rounded-xl"
            style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)' }}
          >
            <span
              className="font-mono"
              style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.08em' }}
            >
              AVG RETURN
            </span>
            <span
              className="font-mono font-bold tabular-nums"
              style={{ fontSize: '24px', color: 'var(--signal-buy)', lineHeight: 1, letterSpacing: '-0.02em' }}
            >
              +{signal?.avgReturn}%
            </span>
            <div className="w-full rounded-full overflow-hidden" style={{ height: '3px', backgroundColor: 'rgba(255,255,255,0.07)' }}>
              <div
                className="h-full rounded-full r2-bar-fill"
                style={{ width: `${Math.min(signal?.avgReturn, 100)}%`, backgroundColor: 'var(--signal-buy)' }}
              />
            </div>
          </div>

          {/* Prior Signals */}
          <div
            className="flex flex-col gap-2 p-3.5 rounded-xl"
            style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)' }}
          >
            <span
              className="font-mono"
              style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.08em' }}
            >
              PRIOR SIGNALS
            </span>
            <span
              className="font-mono font-bold tabular-nums"
              style={{ fontSize: '24px', color: 'var(--foreground)', lineHeight: 1, letterSpacing: '-0.02em' }}
            >
              {signal?.priorSignals}
            </span>
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
              historical
            </span>
          </div>
        </div>

        {/* R2 Score */}
        <div
          className="p-4 rounded-xl"
          style={{ backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid var(--border)' }}
        >
          <div className="flex items-center justify-between mb-2.5">
            <div className="flex items-center gap-2">
              <BarChart2 size={12} style={{ color: 'var(--signal-reaccum)' }} />
              <span
                className="font-mono"
                style={{ fontSize: '10px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}
              >
                MODEL R² SCORE
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span
                className="font-mono font-bold tabular-nums"
                style={{ fontSize: '16px', color: 'var(--signal-reaccum)' }}
              >
                {(signal?.r2Score * 100)?.toFixed(0)}%
              </span>
              <span
                className="font-mono px-2 py-0.5 rounded-md"
                style={{
                  fontSize: '9px',
                  backgroundColor: 'rgba(59,130,246,0.1)',
                  color: 'var(--signal-reaccum)',
                  border: '1px solid rgba(59,130,246,0.2)',
                }}
              >
                EXCELLENT
              </span>
            </div>
          </div>
          <R2ProgressBar value={signal?.r2Score} color="var(--signal-reaccum)" />
          <div className="flex justify-between mt-1.5">
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>0.00</span>
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>0.50</span>
            <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>1.00</span>
          </div>
        </div>
      </div>

      {/* Card Footer */}
      <div
        className="flex items-center justify-between px-5 py-3.5 rounded-b-xl"
        style={{ borderTop: '1px solid var(--border)', backgroundColor: 'rgba(255,255,255,0.01)' }}
      >
        <div className="flex items-center gap-1.5">
          <Target size={11} style={{ color: 'var(--muted-foreground)' }} />
          <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>
            Constitutional Signal · EGX Listed
          </span>
        </div>
        <button
          className="flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg font-semibold transition-all duration-150 hover:opacity-90 active:scale-95"
          style={{
            fontSize: '11px',
            backgroundColor: 'var(--signal-buy)',
            color: '#000',
            fontFamily: 'var(--font-mono)',
            letterSpacing: '0.04em',
          }}
          onClick={() => toast?.info('Signal details logged', { duration: 2000, style: { background: 'var(--card)', color: 'var(--foreground)', border: '1px solid var(--border)' } })}
        >
          <TrendingUp size={11} />
          ADD TO WATCHLIST
        </button>
      </div>
    </div>
  );
}