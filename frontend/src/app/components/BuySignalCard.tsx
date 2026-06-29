'use client';

import React, { useState } from 'react';
import { TrendingUp, Copy, CheckCircle, Clock, Zap, Activity } from 'lucide-react';
import { toast } from 'sonner';
import R2ProgressBar from './R2ProgressBar';
import { useSnapshot } from '@/providers/SnapshotProvider';
import type { UniverseItem, MPIBehavior, StockDNA } from '@/types/snapshot';

// BUY-ready classification comes from the production snapshot field verbatim.
// The frontend never evaluates r2, score, or gate conditions itself.
// Production backend emits two distinct buy-ready strings:
//   "READY NOW — R2≥60, Score≥35"          (new first-buy tickers)
//   "READY FOR RE-ACCUMULATION"             (status=PREMIUM or ACTIVE)
// Both must be treated as active buy signals.
function isBuyReady(item: UniverseItem): boolean {
  const r = item.waiting_for_reason ?? '';
  return r.includes('READY NOW') || r.includes('READY FOR RE-ACCUMULATION');
}

function CopyButton({ ticker }: { ticker: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard?.writeText(ticker)?.catch(() => {});
    setCopied(true);
    toast?.success(`Copied ${ticker} to clipboard`, {
      duration: 2000,
      style: { background: 'var(--card)', border: '1px solid var(--signal-buy-border)', color: 'var(--foreground)' },
    });
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handleCopy}
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition-all duration-150"
      style={{ backgroundColor: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.2)', color: 'var(--signal-buy)', fontSize: '10px', fontFamily: 'monospace' }}
    >
      {copied ? <CheckCircle size={12} /> : <Copy size={12} />}
      {copied ? 'COPIED' : 'COPY'}
    </button>
  );
}

function BehaviorPhaseBlock({ mpi }: { mpi: MPIBehavior }) {
  const phaseColor: Record<string, string> = {
    Fear: '#f44336', Greed: '#4caf50', Accumulation: '#50d8d0',
    Distribution: '#f0b840', Neutral: '#8b8fa8',
  };
  const color = phaseColor[mpi.phase] ?? '#9c6fff';
  return (
    <div
      className="px-5 py-3 flex flex-col gap-1"
      style={{ borderTop: '1px solid rgba(255,255,255,0.06)', backgroundColor: 'rgba(255,255,255,0.02)' }}
    >
      <div className="flex items-center gap-2">
        <span className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8', letterSpacing: '0.07em' }}>BEHAVIOR PHASE</span>
        <span
          className="font-mono font-bold px-2 py-0.5 rounded"
          style={{ fontSize: '10px', color, backgroundColor: `${color}18`, border: `1px solid ${color}44` }}
        >
          {mpi.phase.toUpperCase()}
        </span>
        <span className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8' }}>{mpi.confidence_label}</span>
      </div>
      <span className="font-mono" style={{ fontSize: '10px', color: '#8b8fa8', lineHeight: 1.5 }}>{mpi.explanation}</span>
      {mpi.historical_cases > 0 && (
        <span className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8', opacity: 0.75 }}>
          Historical similarity: {Math.round((mpi.similarity_score ?? 0) * 100)}% · Avg MFE40: +{(mpi.avg_mfe40 ?? 0).toFixed(0)}% ({mpi.historical_cases} cases)
        </span>
      )}
    </div>
  );
}

function SeenBeforePanel({ dna, mpi }: { dna: StockDNA; mpi?: MPIBehavior }) {
  const confColor: Record<string, string> = {
    STRONG: '#10b981', CONFIRMED: '#50d8d0', DEVELOPING: '#f0b840', MONITORING: '#8b8fa8',
  };
  const color = confColor[dna.constitutional_memory_confidence] ?? '#8b8fa8';
  const totalEvents = dna.buy_count + dna.re_accum_count;

  return (
    <div
      className="px-5 py-3 flex flex-col gap-2"
      style={{ borderTop: '1px solid rgba(255,255,255,0.06)', backgroundColor: 'rgba(0,0,0,0.15)' }}
    >
      <div className="flex items-center gap-2 mb-0.5">
        <span className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8', letterSpacing: '0.07em' }}>SEEN BEFORE</span>
        <span
          className="font-mono font-bold px-2 py-0.5 rounded"
          style={{ fontSize: '10px', color, backgroundColor: `${color}18`, border: `1px solid ${color}44` }}
        >
          {dna.constitutional_memory_hits}× &nbsp;{dna.constitutional_memory_confidence}
        </span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <div>
          <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8', letterSpacing: '0.07em', marginBottom: '2px' }}>HISTORICAL EXPECTANCY</p>
          <p className="font-mono font-bold tabular-nums" style={{ fontSize: '13px', color: '#10b981' }}>
            {dna.avg_return_pct > 0 ? '+' : ''}{dna.avg_return_pct.toFixed(1)}%
          </p>
          <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8' }}>{totalEvents} event{totalEvents !== 1 ? 's' : ''}</p>
        </div>
        <div>
          <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8', letterSpacing: '0.07em', marginBottom: '2px' }}>AVG MFE40</p>
          <p className="font-mono font-bold tabular-nums" style={{ fontSize: '13px', color: '#50d8d0' }}>
            {mpi && mpi.avg_mfe40 != null ? `+${mpi.avg_mfe40.toFixed(0)}%` : '—'}
          </p>
          {mpi && mpi.historical_cases > 0 && (
            <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8' }}>{mpi.historical_cases} analogs</p>
          )}
        </div>
        <div>
          <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8', letterSpacing: '0.07em', marginBottom: '2px' }}>BEST / WORST</p>
          <p className="font-mono font-bold tabular-nums" style={{ fontSize: '13px', color: '#10b981' }}>
            +{dna.best_return_pct.toFixed(1)}%
          </p>
          <p className="font-mono tabular-nums" style={{ fontSize: '10px', color: '#f44336' }}>
            {dna.worst_return_pct != null && dna.worst_return_pct < 0
              ? `${dna.worst_return_pct.toFixed(1)}%`
              : dna.worst_return_pct != null
              ? `+${dna.worst_return_pct.toFixed(1)}%`
              : '—'}
          </p>
        </div>
        <div>
          <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8', letterSpacing: '0.07em', marginBottom: '2px' }}>LAST SIGNAL</p>
          <p className="font-mono font-bold tabular-nums" style={{ fontSize: '12px', color: '#8b8fa8' }}>
            {dna.last_event_date ?? dna.first_buy_date ?? '—'}
          </p>
          <p className="font-mono" style={{ fontSize: '8px', color: '#8b8fa8' }}>First: {dna.first_buy_date ?? '—'}</p>
        </div>
      </div>
    </div>
  );
}

function BuyCard({ signal, mpi, dna }: { signal: UniverseItem; mpi?: MPIBehavior; dna?: StockDNA }) {
  return (
    <div className="rounded-xl glow-buy animate-fade-in-up" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--signal-buy-border)' }}>
      <div
        className="flex items-center justify-between px-5 py-3.5 rounded-t-xl"
        style={{ background: 'linear-gradient(135deg, rgba(16,185,129,0.1) 0%, rgba(16,185,129,0.03) 100%)' }}
      >
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center rounded-lg" style={{ width: '32px', height: '32px', backgroundColor: 'rgba(16,185,129,0.15)', border: '1px solid rgba(16,185,129,0.3)' }}>
            <TrendingUp size={16} style={{ color: 'var(--signal-buy)' }} />
          </div>
          <div>
            <span className="font-mono font-bold" style={{ fontSize: '10px', color: 'var(--signal-buy)', letterSpacing: '0.12em' }}>
              CONSTITUTIONAL BUY SIGNAL
            </span>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="font-mono font-bold" style={{ fontSize: '18px', color: 'var(--foreground)' }}>{signal.ticker}</span>
              <span className="font-mono px-2 py-0.5 rounded-md" style={{ fontSize: '9px', backgroundColor: 'rgba(16,185,129,0.15)', color: 'var(--signal-buy)', border: '1px solid rgba(16,185,129,0.3)' }}>
                {signal.status}
              </span>
            </div>
          </div>
        </div>
        <CopyButton ticker={signal.ticker} />
      </div>

      <div className="px-5 py-4 grid grid-cols-2 md:grid-cols-4 gap-4">
        <div>
          <p className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>ENTRY ZONE</p>
          <p className="font-mono font-bold tabular-nums" style={{ fontSize: '18px', color: 'var(--signal-buy)' }}>
            {signal.constitutional_entry_price != null ? signal.constitutional_entry_price.toFixed(2) : '—'}
          </p>
        </div>
        <div>
          <p className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>CURRENT PRICE</p>
          <p className="font-mono font-bold tabular-nums" style={{ fontSize: '18px', color: 'var(--foreground)' }}>{signal.current_price.toFixed(2)}</p>
        </div>
        <div>
          <p className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>DISTANCE</p>
          <p className="font-mono font-bold tabular-nums" style={{ fontSize: '18px', color: signal.distance != null && signal.distance < 0 ? 'var(--signal-near)' : 'var(--foreground)' }}>
            {signal.distance != null ? `${signal.distance.toFixed(2)}%` : '—'}
          </p>
        </div>
        <div>
          <p className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>REWARD SCORE</p>
          <p className="font-mono font-bold tabular-nums" style={{ fontSize: '18px', color: 'var(--signal-reaccum)' }}>
            {signal.expected_reward_score?.toFixed(1) ?? '—'}
          </p>
        </div>
      </div>

      <div className="px-5 pb-4">
        <div className="flex items-center justify-between mb-2">
          <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>CONSTITUTIONAL R²</span>
          <span className="font-mono font-bold" style={{ fontSize: '12px', color: 'var(--signal-reaccum)' }}>
            {signal.candidate_r2 != null ? signal.candidate_r2 : '—'}
          </span>
        </div>
        <R2ProgressBar value={(signal.candidate_r2 ?? 0) / 100} color="var(--signal-reaccum)" height={5} />
      </div>

      {mpi && <BehaviorPhaseBlock mpi={mpi} />}

      {dna && dna.constitutional_memory_hits > 0 && (
        <SeenBeforePanel dna={dna} mpi={mpi} />
      )}

      <div className="px-5 py-3 rounded-b-xl flex items-center gap-2" style={{ backgroundColor: 'rgba(16,185,129,0.04)', borderTop: '1px solid rgba(16,185,129,0.12)' }}>
        <Zap size={11} style={{ color: 'var(--signal-buy)', flexShrink: 0 }} />
        <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>{signal.waiting_for_reason}</span>
        <span className="font-mono ml-auto" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>{signal.last_scan}</span>
      </div>
    </div>
  );
}

function NoBuyState({ scanId }: { scanId?: string }) {
  return (
    <div className="rounded-xl flex flex-col items-center justify-center py-12 px-6" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)', minHeight: '200px' }}>
      <Activity size={28} style={{ color: 'var(--muted-foreground)', marginBottom: '12px' }} />
      <p className="font-mono font-semibold" style={{ fontSize: '13px', color: 'var(--foreground)' }}>NO ACTIVE BUY SIGNAL</p>
      <p className="font-mono mt-2 text-center" style={{ fontSize: '10px', color: 'var(--muted-foreground)', maxWidth: '320px' }}>
        The Constitutional Engine found no qualifying buy opportunities in this scan. Monitor near-entry candidates.
      </p>
      {scanId && (
        <div className="flex items-center gap-1.5 mt-4 px-3 py-1.5 rounded-lg" style={{ backgroundColor: 'rgba(255,255,255,0.03)', border: '1px solid var(--border)' }}>
          <Clock size={10} style={{ color: 'var(--muted-foreground)' }} />
          <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>scan {scanId.slice(0, 8)}</span>
        </div>
      )}
    </div>
  );
}

export default function BuySignalCard() {
  const { snapshot, loading } = useSnapshot();

  if (loading || !snapshot) {
    return (
      <div className="rounded-xl flex items-center justify-center py-12" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--border)' }}>
        <span className="font-mono" style={{ fontSize: '11px', color: 'var(--muted-foreground)' }}>Loading snapshot…</span>
      </div>
    );
  }

  const buySignals = snapshot.universe_snapshot.filter(isBuyReady);
  const mpiMap = snapshot.mpi_behavior ?? {};
  const dnaMap = snapshot.stock_dna ?? {};

  if (buySignals.length === 0) return <NoBuyState scanId={snapshot.scan_id} />;

  return (
    <div className="flex flex-col gap-4">
      {buySignals.map((signal) => (
        <BuyCard key={signal.ticker} signal={signal} mpi={mpiMap[signal.ticker]} dna={dnaMap[signal.ticker]} />
      ))}
    </div>
  );
}
