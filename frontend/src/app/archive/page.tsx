'use client';

import React, { useState } from 'react';
import { TrendingUp, TrendingDown, Clock, Target, Award, Brain, Activity, Filter, Search, BarChart2 } from 'lucide-react';
import Link from 'next/link';

interface ArchivedSignal {
  id: string;
  ticker: string;
  companyName: string;
  sector: string;
  tier: 'ELITE' | 'STANDARD';
  signalType: string;
  detectedAt: string;
  sessionDate: string;
  entryPrice: number;
  currentPrice: number;
  target1: number;
  target2: number;
  ive: number;
  behaviorPhase: string;
  status: 'TARGET_1_HIT' | 'TARGET_2_HIT' | 'ACTIVE' | 'EXPIRED' | 'NEAR_ENTRY';
  returnPct: number | null;
  winRate: number;
  r2Score: number;
  confidence: string;
}

const archiveData: ArchivedSignal[] = [
  {
    id: '1',
    ticker: 'ABUK.CA',
    companyName: 'Abu Khashaba for Trade & Agencies',
    sector: 'Trade & Distribution',
    tier: 'ELITE',
    signalType: 'BUY ELITE',
    detectedAt: '05:14:22',
    sessionDate: '2026-06-29',
    entryPrice: 69.05,
    currentPrice: 67.80,
    target1: 78.50,
    target2: 89.30,
    ive: 84.30,
    behaviorPhase: 'ACCUMULATION',
    status: 'ACTIVE',
    returnPct: null,
    winRate: 95,
    r2Score: 0.94,
    confidence: 'VERY HIGH',
  },
  {
    id: '2',
    ticker: 'FWRY.CA',
    companyName: 'Fawry for Banking Technology',
    sector: 'Financial Technology',
    tier: 'ELITE',
    signalType: 'BUY ELITE',
    detectedAt: '06:02:11',
    sessionDate: '2026-06-26',
    entryPrice: 42.10,
    currentPrice: 51.80,
    target1: 49.50,
    target2: 58.20,
    ive: 55.40,
    behaviorPhase: 'MARKUP',
    status: 'TARGET_1_HIT',
    returnPct: 17.6,
    winRate: 92,
    r2Score: 0.91,
    confidence: 'HIGH',
  },
  {
    id: '3',
    ticker: 'HRHO.CA',
    companyName: 'Hassan Allam Holding',
    sector: 'Construction & Real Estate',
    tier: 'STANDARD',
    signalType: 'BUY STANDARD',
    detectedAt: '07:45:33',
    sessionDate: '2026-06-24',
    entryPrice: 18.75,
    currentPrice: 22.40,
    target1: 21.50,
    target2: 25.80,
    ive: 24.10,
    behaviorPhase: 'BREAKOUT',
    status: 'TARGET_2_HIT',
    returnPct: 37.9,
    winRate: 88,
    r2Score: 0.87,
    confidence: 'HIGH',
  },
  {
    id: '4',
    ticker: 'BTFH.CA',
    companyName: 'Beltone Financial Holding',
    sector: 'Financial Services',
    tier: 'STANDARD',
    signalType: 'BUY STANDARD',
    detectedAt: '05:58:47',
    sessionDate: '2026-06-22',
    entryPrice: 11.30,
    currentPrice: 10.85,
    target1: 13.20,
    target2: 15.60,
    ive: 14.50,
    behaviorPhase: 'ACCUMULATION',
    status: 'NEAR_ENTRY',
    returnPct: null,
    winRate: 85,
    r2Score: 0.83,
    confidence: 'MEDIUM',
  },
  {
    id: '5',
    ticker: 'MCQE.CA',
    companyName: 'Misr Chemical Industries',
    sector: 'Chemicals & Fertilizers',
    tier: 'ELITE',
    signalType: 'BUY ELITE',
    detectedAt: '06:30:15',
    sessionDate: '2026-06-19',
    entryPrice: 33.60,
    currentPrice: 29.10,
    target1: 39.80,
    target2: 46.20,
    ive: 42.00,
    behaviorPhase: 'DISTRIBUTION',
    status: 'EXPIRED',
    returnPct: -13.4,
    winRate: 90,
    r2Score: 0.89,
    confidence: 'HIGH',
  },
  {
    id: '6',
    ticker: 'EFIH.CA',
    companyName: 'EFG Hermes Holding',
    sector: 'Investment Banking',
    tier: 'ELITE',
    signalType: 'BUY ELITE',
    detectedAt: '05:22:08',
    sessionDate: '2026-06-17',
    entryPrice: 28.40,
    currentPrice: 34.90,
    target1: 33.00,
    target2: 38.50,
    ive: 36.80,
    behaviorPhase: 'MARKUP',
    status: 'TARGET_2_HIT',
    returnPct: 35.6,
    winRate: 93,
    r2Score: 0.92,
    confidence: 'VERY HIGH',
  },
  {
    id: '7',
    ticker: 'COMI.CA',
    companyName: 'Commercial International Bank',
    sector: 'Banking',
    tier: 'ELITE',
    signalType: 'BUY ELITE',
    detectedAt: '07:10:44',
    sessionDate: '2026-06-15',
    entryPrice: 72.50,
    currentPrice: 81.20,
    target1: 82.00,
    target2: 94.50,
    ive: 88.60,
    behaviorPhase: 'MARKUP',
    status: 'TARGET_1_HIT',
    returnPct: 12.0,
    winRate: 96,
    r2Score: 0.95,
    confidence: 'VERY HIGH',
  },
  {
    id: '8',
    ticker: 'SWDY.CA',
    companyName: 'El Sewedy Electric',
    sector: 'Electrical Equipment',
    tier: 'STANDARD',
    signalType: 'BUY STANDARD',
    detectedAt: '06:48:19',
    sessionDate: '2026-06-12',
    entryPrice: 15.90,
    currentPrice: 18.70,
    target1: 18.50,
    target2: 22.10,
    ive: 20.40,
    behaviorPhase: 'BREAKOUT',
    status: 'TARGET_1_HIT',
    returnPct: 16.4,
    winRate: 87,
    r2Score: 0.85,
    confidence: 'HIGH',
  },
];

const statusConfig: Record<string, { label: string; color: string; bg: string; border: string }> = {
  TARGET_2_HIT: { label: 'T2 HIT', color: '#10b981', bg: 'rgba(16,185,129,0.12)', border: 'rgba(16,185,129,0.3)' },
  TARGET_1_HIT: { label: 'T1 HIT', color: '#3b82f6', bg: 'rgba(59,130,246,0.12)', border: 'rgba(59,130,246,0.3)' },
  ACTIVE: { label: 'ACTIVE', color: '#f59e0b', bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.3)' },
  NEAR_ENTRY: { label: 'NEAR ENTRY', color: '#f59e0b', bg: 'rgba(245,158,11,0.08)', border: 'rgba(245,158,11,0.25)' },
  EXPIRED: { label: 'EXPIRED', color: '#ef4444', bg: 'rgba(239,68,68,0.1)', border: 'rgba(239,68,68,0.25)' },
};

const behaviorPhaseColor: Record<string, string> = {
  ACCUMULATION: '#3b82f6',
  BREAKOUT: '#10b981',
  DISTRIBUTION: '#f59e0b',
  MARKUP: '#10b981',
  MARKDOWN: '#ef4444',
};

type FilterStatus = 'ALL' | 'ACTIVE' | 'TARGET_1_HIT' | 'TARGET_2_HIT' | 'EXPIRED' | 'NEAR_ENTRY';

export default function ArchivePage() {
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [filterTier, setFilterTier] = useState<'ALL' | 'ELITE' | 'STANDARD'>('ALL');

  const filtered = archiveData.filter((s) => {
    const matchStatus = filterStatus === 'ALL' || s.status === filterStatus;
    const matchTier = filterTier === 'ALL' || s.tier === filterTier;
    const matchSearch =
      searchQuery === '' ||
      s.ticker.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.companyName.toLowerCase().includes(searchQuery.toLowerCase());
    return matchStatus && matchTier && matchSearch;
  });

  const totalSignals = archiveData.length;
  const wins = archiveData.filter((s) => s.status === 'TARGET_1_HIT' || s.status === 'TARGET_2_HIT').length;
  const avgReturn =
    archiveData
      .filter((s) => s.returnPct !== null)
      .reduce((acc, s) => acc + (s.returnPct ?? 0), 0) /
    (archiveData.filter((s) => s.returnPct !== null).length || 1);
  const eliteCount = archiveData.filter((s) => s.tier === 'ELITE').length;

  return (
    <div
      className="min-h-screen"
      style={{ backgroundColor: 'var(--background)', paddingTop: '72px' }}
    >
      {/* Page Header */}
      <div
        className="px-4 md:px-6 xl:px-10 py-6"
        style={{ borderBottom: '1px solid var(--border)' }}
      >
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-3">
            <div
              className="p-2 rounded-lg"
              style={{ backgroundColor: 'rgba(167,139,250,0.1)', border: '1px solid rgba(167,139,250,0.25)' }}
            >
              <BarChart2 size={18} style={{ color: 'var(--signal-elite)' }} />
            </div>
            <div>
              <h1
                className="font-mono font-bold"
                style={{ fontSize: '18px', color: 'var(--foreground)', letterSpacing: '0.04em' }}
              >
                SIGNAL ARCHIVE
              </h1>
              <p className="font-mono" style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>
                Constitutional signal history · all sessions
              </p>
            </div>
          </div>
          <Link
            href="/"
            className="font-mono px-3 py-1.5 rounded-lg transition-all duration-150 hover:opacity-80"
            style={{
              fontSize: '11px',
              backgroundColor: 'var(--muted)',
              border: '1px solid var(--border)',
              color: 'var(--muted-foreground)',
              letterSpacing: '0.05em',
            }}
          >
            ← DASHBOARD
          </Link>
        </div>
      </div>

      <div className="px-4 md:px-6 xl:px-10 py-6 space-y-6">

        {/* Performance KPIs */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {[
            { label: 'TOTAL SIGNALS', value: totalSignals.toString(), color: 'var(--foreground)', icon: <Activity size={13} style={{ color: 'var(--muted-foreground)' }} /> },
            { label: 'WIN RATE', value: `${((wins / totalSignals) * 100).toFixed(0)}%`, color: 'var(--signal-buy)', icon: <TrendingUp size={13} style={{ color: 'var(--signal-buy)' }} /> },
            { label: 'AVG RETURN', value: `${avgReturn >= 0 ? '+' : ''}${avgReturn.toFixed(1)}%`, color: avgReturn >= 0 ? 'var(--signal-buy)' : 'var(--signal-danger)', icon: <Target size={13} style={{ color: avgReturn >= 0 ? 'var(--signal-buy)' : 'var(--signal-danger)' }} /> },
            { label: 'ELITE SIGNALS', value: eliteCount.toString(), color: 'var(--signal-elite)', icon: <Award size={13} style={{ color: 'var(--signal-elite)' }} /> },
          ].map((kpi) => (
            <div
              key={kpi.label}
              className="p-4 rounded-xl"
              style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}
            >
              <div className="flex items-center gap-1.5 mb-2">
                {kpi.icon}
                <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.08em' }}>
                  {kpi.label}
                </span>
              </div>
              <span
                className="font-mono font-bold tabular-nums"
                style={{ fontSize: '26px', color: kpi.color, lineHeight: 1 }}
              >
                {kpi.value}
              </span>
            </div>
          ))}
        </div>

        {/* Filters */}
        <div className="flex flex-col md:flex-row gap-3">
          {/* Search */}
          <div
            className="flex items-center gap-2 px-3 py-2 rounded-lg flex-1 md:max-w-xs"
            style={{ backgroundColor: 'var(--muted)', border: '1px solid var(--border)' }}
          >
            <Search size={13} style={{ color: 'var(--muted-foreground)' }} />
            <input
              type="text"
              placeholder="Search ticker or company..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-transparent outline-none font-mono w-full"
              style={{ fontSize: '12px', color: 'var(--foreground)' }}
            />
          </div>

          {/* Status filter */}
          <div className="flex items-center gap-2 flex-wrap">
            <Filter size={12} style={{ color: 'var(--muted-foreground)' }} />
            {(['ALL', 'ACTIVE', 'TARGET_1_HIT', 'TARGET_2_HIT', 'NEAR_ENTRY', 'EXPIRED'] as FilterStatus[]).map((s) => (
              <button
                key={s}
                onClick={() => setFilterStatus(s)}
                className="font-mono px-2.5 py-1 rounded-md transition-all duration-150"
                style={{
                  fontSize: '10px',
                  letterSpacing: '0.05em',
                  backgroundColor: filterStatus === s ? 'rgba(167,139,250,0.15)' : 'var(--muted)',
                  border: `1px solid ${filterStatus === s ? 'rgba(167,139,250,0.4)' : 'var(--border)'}`,
                  color: filterStatus === s ? 'var(--signal-elite)' : 'var(--muted-foreground)',
                }}
              >
                {s === 'ALL' ? 'ALL' : s === 'TARGET_1_HIT' ? 'T1 HIT' : s === 'TARGET_2_HIT' ? 'T2 HIT' : s.replace('_', ' ')}
              </button>
            ))}
          </div>

          {/* Tier filter */}
          <div className="flex items-center gap-2">
            {(['ALL', 'ELITE', 'STANDARD'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setFilterTier(t)}
                className="font-mono px-2.5 py-1 rounded-md transition-all duration-150"
                style={{
                  fontSize: '10px',
                  letterSpacing: '0.05em',
                  backgroundColor: filterTier === t ? 'rgba(16,185,129,0.12)' : 'var(--muted)',
                  border: `1px solid ${filterTier === t ? 'rgba(16,185,129,0.3)' : 'var(--border)'}`,
                  color: filterTier === t ? 'var(--signal-buy)' : 'var(--muted-foreground)',
                }}
              >
                {t}
              </button>
            ))}
          </div>
        </div>

        {/* Signal count */}
        <div className="flex items-center gap-2">
          <span className="font-mono" style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>
            Showing {filtered.length} of {totalSignals} signals
          </span>
        </div>

        {/* Signal Table */}
        <div
          className="rounded-xl overflow-hidden"
          style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}
        >
          {/* Table Header */}
          <div
            className="grid px-4 py-3"
            style={{
              gridTemplateColumns: '1fr 1fr 90px 90px 90px 90px 110px 90px',
              borderBottom: '1px solid var(--border)',
              backgroundColor: 'rgba(255,255,255,0.02)',
            }}
          >
            {['TICKER', 'SESSION', 'ENTRY', 'CURRENT', 'TARGET 1', 'TARGET 2', 'STATUS', 'RETURN'].map((h) => (
              <span
                key={h}
                className="font-mono"
                style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.08em' }}
              >
                {h}
              </span>
            ))}
          </div>

          {/* Rows */}
          {filtered.length === 0 ? (
            <div className="flex items-center justify-center py-16">
              <span className="font-mono" style={{ fontSize: '13px', color: 'var(--muted-foreground)' }}>
                No signals match the current filters
              </span>
            </div>
          ) : (
            filtered.map((signal, idx) => {
              const sc = statusConfig[signal.status];
              const phaseColor = behaviorPhaseColor[signal.behaviorPhase] ?? '#f59e0b';
              const isPositive = (signal.returnPct ?? 0) >= 0;

              return (
                <div
                  key={signal.id}
                  className="grid px-4 py-4 ticker-row"
                  style={{
                    gridTemplateColumns: '1fr 1fr 90px 90px 90px 90px 110px 90px',
                    borderBottom: idx < filtered.length - 1 ? '1px solid var(--border)' : 'none',
                  }}
                >
                  {/* Ticker + Meta */}
                  <div className="flex flex-col gap-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span
                        className="font-mono font-bold"
                        style={{ fontSize: '14px', color: 'var(--foreground)' }}
                      >
                        {signal.ticker}
                      </span>
                      {signal.tier === 'ELITE' && (
                        <span
                          className="font-mono px-1.5 py-0.5 rounded"
                          style={{
                            fontSize: '8px',
                            backgroundColor: 'rgba(167,139,250,0.12)',
                            color: 'var(--signal-elite)',
                            border: '1px solid rgba(167,139,250,0.25)',
                            letterSpacing: '0.06em',
                          }}
                        >
                          ELITE
                        </span>
                      )}
                    </div>
                    <span
                      className="font-mono truncate"
                      style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}
                    >
                      {signal.companyName}
                    </span>
                    <div className="flex items-center gap-2 mt-0.5">
                      <div className="flex items-center gap-1">
                        <Brain size={9} style={{ color: '#a78bfa' }} />
                        <span className="font-mono" style={{ fontSize: '9px', color: '#a78bfa' }}>
                          IVE {signal.ive.toFixed(2)}
                        </span>
                      </div>
                      <span
                        className="font-mono"
                        style={{ fontSize: '9px', color: phaseColor }}
                      >
                        {signal.behaviorPhase}
                      </span>
                    </div>
                  </div>

                  {/* Session */}
                  <div className="flex flex-col gap-1">
                    <div className="flex items-center gap-1">
                      <Clock size={10} style={{ color: 'var(--muted-foreground)' }} />
                      <span className="font-mono" style={{ fontSize: '11px', color: 'var(--foreground)' }}>
                        {signal.sessionDate}
                      </span>
                    </div>
                    <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>
                      {signal.detectedAt} CAI
                    </span>
                    <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', opacity: 0.7 }}>
                      W/R {signal.winRate}% · R² {signal.r2Score}
                    </span>
                  </div>

                  {/* Entry */}
                  <div className="flex flex-col gap-0.5">
                    <span
                      className="font-mono font-semibold tabular-nums"
                      style={{ fontSize: '13px', color: 'var(--signal-buy)' }}
                    >
                      {signal.entryPrice.toFixed(2)}
                    </span>
                    <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
                      EGP
                    </span>
                  </div>

                  {/* Current */}
                  <div className="flex flex-col gap-0.5">
                    <span
                      className="font-mono font-semibold tabular-nums"
                      style={{ fontSize: '13px', color: 'var(--foreground)' }}
                    >
                      {signal.currentPrice.toFixed(2)}
                    </span>
                    <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
                      EGP
                    </span>
                  </div>

                  {/* Target 1 */}
                  <div className="flex flex-col gap-0.5">
                    <span
                      className="font-mono tabular-nums"
                      style={{ fontSize: '12px', color: 'var(--signal-reaccum)' }}
                    >
                      {signal.target1.toFixed(2)}
                    </span>
                    <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
                      EGP
                    </span>
                  </div>

                  {/* Target 2 */}
                  <div className="flex flex-col gap-0.5">
                    <span
                      className="font-mono tabular-nums"
                      style={{ fontSize: '12px', color: 'var(--signal-elite)' }}
                    >
                      {signal.target2.toFixed(2)}
                    </span>
                    <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
                      EGP
                    </span>
                  </div>

                  {/* Status */}
                  <div>
                    <span
                      className="font-mono font-semibold px-2 py-1 rounded-md inline-block"
                      style={{
                        fontSize: '10px',
                        backgroundColor: sc.bg,
                        color: sc.color,
                        border: `1px solid ${sc.border}`,
                        letterSpacing: '0.05em',
                      }}
                    >
                      {sc.label}
                    </span>
                  </div>

                  {/* Return */}
                  <div className="flex flex-col gap-0.5">
                    {signal.returnPct !== null ? (
                      <>
                        <div className="flex items-center gap-1">
                          {isPositive ? (
                            <TrendingUp size={11} style={{ color: 'var(--signal-buy)' }} />
                          ) : (
                            <TrendingDown size={11} style={{ color: 'var(--signal-danger)' }} />
                          )}
                          <span
                            className="font-mono font-bold tabular-nums"
                            style={{
                              fontSize: '13px',
                              color: isPositive ? 'var(--signal-buy)' : 'var(--signal-danger)',
                            }}
                          >
                            {isPositive ? '+' : ''}{signal.returnPct.toFixed(1)}%
                          </span>
                        </div>
                        <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>
                          realized
                        </span>
                      </>
                    ) : (
                      <span className="font-mono" style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>
                        —
                      </span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Footer note */}
        <div className="flex items-center justify-center pb-6">
          <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)', opacity: 0.5 }}>
            Constitutional Signal · EGX Listed · Archive v1.0
          </span>
        </div>
      </div>
    </div>
  );
}
