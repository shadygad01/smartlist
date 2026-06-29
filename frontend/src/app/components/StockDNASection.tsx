'use client';

import React, { useState } from 'react';
import { Dna, ChevronDown, ChevronUp, BarChart2 } from 'lucide-react';
import R2ProgressBar from './R2ProgressBar';

interface DNAMetric {
  id: string;
  label: string;
  value: number;
  raw: string;
  color: string;
  description: string;
}

const dnaMetrics: DNAMetric[] = [
  { id: 'dna-momentum', label: 'MOMENTUM SCORE', value: 87, raw: '87 / 100', color: 'var(--signal-buy)', description: 'Price momentum vs. 20-day moving average' },
  { id: 'dna-volume', label: 'VOLUME PROFILE', value: 76, raw: '2.4x avg', color: 'var(--signal-near)', description: 'Volume ratio relative to 30-day average' },
  { id: 'dna-trend', label: 'TREND STRENGTH', value: 93, raw: 'ADX 38.2', color: 'var(--signal-buy)', description: 'Average Directional Index — trend conviction' },
  { id: 'dna-support', label: 'SUPPORT QUALITY', value: 91, raw: '3 confluences', color: 'var(--signal-reaccum)', description: 'Number of technical support levels at entry zone' },
  { id: 'dna-sector', label: 'SECTOR ALIGNMENT', value: 68, raw: 'Trade +1.2%', color: 'var(--signal-near)', description: 'Sector performance vs. EGX30 benchmark' },
  { id: 'dna-r2', label: 'MODEL FIT (R²)', value: 94, raw: '0.94', color: 'var(--signal-reaccum)', description: 'Constitutional model coefficient of determination' },
  { id: 'dna-winrate', label: 'HISTORICAL WIN RATE', value: 95, raw: '19/20 signals', color: 'var(--signal-buy)', description: 'Percentage of profitable prior signals for this ticker' },
];

export default function StockDNASection() {
  const [collapsed, setCollapsed] = useState(false);

  const overallScore = Math.round(
    dnaMetrics.reduce((sum, m) => sum + m.value, 0) / dnaMetrics.length
  );

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
          <Dna size={13} style={{ color: '#a78bfa' }} />
          <span
            className="font-mono font-semibold"
            style={{ fontSize: '12px', color: 'var(--foreground)', letterSpacing: '0.07em' }}
          >
            STOCK DNA — ABUK.CA
          </span>
          {/* Overall score badge */}
          <span
            className="font-mono font-bold px-2 py-0.5 rounded-md"
            style={{
              fontSize: '10px',
              backgroundColor: 'rgba(16,185,129,0.1)',
              color: 'var(--signal-buy)',
              border: '1px solid rgba(16,185,129,0.2)',
            }}
          >
            {overallScore}/100
          </span>
        </div>
        {collapsed ? (
          <ChevronDown size={13} style={{ color: 'var(--muted-foreground)' }} />
        ) : (
          <ChevronUp size={13} style={{ color: 'var(--muted-foreground)' }} />
        )}
      </button>

      {/* Content */}
      {!collapsed && (
        <div className="p-4">
          {/* Overall score bar */}
          <div
            className="flex items-center gap-4 p-3.5 rounded-xl mb-4"
            style={{ backgroundColor: 'rgba(16,185,129,0.05)', border: '1px solid rgba(16,185,129,0.15)' }}
          >
            <BarChart2 size={15} style={{ color: 'var(--signal-buy)', flexShrink: 0 }} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>
                  COMPOSITE SIGNAL STRENGTH
                </span>
                <span
                  className="font-mono font-bold tabular-nums"
                  style={{ fontSize: '15px', color: 'var(--signal-buy)' }}
                >
                  {overallScore}%
                </span>
              </div>
              <R2ProgressBar value={overallScore / 100} color="var(--signal-buy)" height={6} />
            </div>
          </div>

          {/* DNA metrics grid */}
          <div className="grid grid-cols-1 gap-3">
            {dnaMetrics.map((metric) => (
              <div key={metric.id} className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex flex-col">
                    <span
                      className="font-mono"
                      style={{ fontSize: '10px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}
                    >
                      {metric.label}
                    </span>
                    <span
                      className="font-mono"
                      style={{ fontSize: '9px', color: 'var(--muted-foreground)', opacity: 0.45 }}
                    >
                      {metric.description}
                    </span>
                  </div>
                  <span
                    className="font-mono font-semibold tabular-nums flex-shrink-0 ml-3"
                    style={{ fontSize: '12px', color: metric.color }}
                  >
                    {metric.raw}
                  </span>
                </div>
                <R2ProgressBar value={metric.value / 100} color={metric.color} height={3} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}