import React, { useState } from 'react';
import { TrendingUp, Copy, CheckCircle, Clock, Zap, Activity, ChevronDown, ChevronUp } from 'lucide-react';
import { toast } from 'sonner';
import R2ProgressBar from './R2ProgressBar';
import SeenBeforePanel from './SeenBeforePanel';
import ValuationPanel from './ValuationPanel';
import { useSnapshot } from '@/providers/SnapshotProvider';
import type { UniverseItem, MPIBehavior, StockDNA, ValuationCard, Statistics } from '@/types/snapshot';

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
  const [collapsed, setCollapsed] = useState(true);
  const phaseColor: Record<string, string> = {
    Fear: '#f44336', Greed: '#4caf50', Accumulation: '#50d8d0',
    Distribution: '#f0b840', Neutral: '#8b8fa8',
  };
  const color = phaseColor[mpi.phase] ?? '#9c6fff';
  return (
    <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', backgroundColor: 'rgba(255,255,255,0.02)' }}>
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-5 py-2.5"
        style={{ background: 'none', cursor: 'pointer' }}
      >
        <div className="flex items-center gap-2">
          <span className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8', letterSpacing: '0.07em' }}>BEHAVIOR PHASE</span>
          <span className="font-mono font-bold px-2 py-0.5 rounded" style={{ fontSize: '10px', color, backgroundColor: `${color}18`, border: `1px solid ${color}44` }}>
            {mpi.phase.toUpperCase()}
          </span>
          <span className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8' }}>{mpi.confidence_label}</span>
        </div>
        {collapsed ? <ChevronDown size={11} style={{ color: '#8b8fa8' }} /> : <ChevronUp size={11} style={{ color: '#8b8fa8' }} />}
      </button>
      {!collapsed && (
        <div className="px-5 pb-3 flex flex-col gap-1">
          <span className="font-mono" style={{ fontSize: '10px', color: '#8b8fa8', lineHeight: 1.5 }}>{mpi.explanation}</span>
          {mpi.historical_cases > 0 && (
            <span className="font-mono" style={{ fontSize: '9px', color: '#8b8fa8', opacity: 0.75 }}>
              Historical similarity: {Math.round((mpi.similarity_score ?? 0) * 100)}% · Avg MFE40: +{(mpi.avg_mfe40 ?? 0).toFixed(0)}% ({mpi.historical_cases} cases)
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function _fvUpside(fv: number, price: number): number | null {
  if (!fv || !price) return null;
  return ((fv - price) / price) * 100;
}

function FairValueSignalBadge({ fv, price }: { fv: number; price: number }) {
  const upside = _fvUpside(fv, price);
  if (upside == null) return null;
  const isUndervalued = upside > 0;
  const sign = upside >= 0 ? '+' : '';
  const color    = isUndervalued ? '#10b981' : '#ef4444';
  const bg       = isUndervalued ? 'rgba(16,185,129,0.12)' : 'rgba(239,68,68,0.12)';
  const border   = isUndervalued ? 'rgba(16,185,129,0.35)' : 'rgba(239,68,68,0.35)';
  const label    = isUndervalued ? 'UNDERVALUED' : 'OVERVALUED';
  return (
    <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg" style={{ backgroundColor: bg, border: `1px solid ${border}` }}>
      <span className="font-mono font-bold" style={{ fontSize: '9px', color, letterSpacing: '0.07em' }}>{label}</span>
      <span className="font-mono font-bold tabular-nums" style={{ fontSize: '10px', color }}>
        {sign}{upside.toFixed(1)}%
      </span>
    </div>
  );
}

function ActionQueue({ stats }: { stats: Statistics }) {
  const rows = [
    { label: 'NEAR ENTRY', value: stats.near_constitutional_count, color: 'var(--signal-near)', href: '#priority-watchlist' },
    { label: 'PREMIUM', value: stats.premium_count ?? 0, color: 'var(--signal-buy)', href: '#priority-watchlist' },
    { label: 'FIRST BUY', value: stats.first_buys_count ?? 0, color: '#50d8d0', href: '#event-timeline' },
    { label: 'RE-ACCUMULATION', value: stats.re_accumulation_count, color: '#a78bfa', href: '#re-accumulation' },
  ];
  return (
    <aside className="signal-lane signal-action-lane">
      <div className="signal-lane-title"><Zap size={13} /> ACTION QUEUE</div>
      <p className="signal-lane-caption">Priority monitoring</p>
      <div className="signal-queue">
        {rows.map((row) => (
          <a key={row.label} href={row.href} className="signal-queue-row">
            <span className="font-mono font-bold tabular-nums" style={{ color: row.color, fontSize: '20px' }}>{row.value}</span>
            <span className="font-mono">{row.label}</span>
            <ChevronDown size={12} style={{ transform: 'rotate(-90deg)' }} />
          </a>
        ))}
      </div>
      <div className="signal-queue-total">
        <span>UNIVERSE</span><b>{stats.universe_size ?? '—'}</b>
      </div>
    </aside>
  );
}

function BuyCard({ signal, mpi, dna, valuation, stats }: { signal: UniverseItem; mpi?: MPIBehavior; dna?: StockDNA; valuation?: ValuationCard; stats: Statistics }) {
  const fv = valuation?.weighted_fair_value ?? null;
  return (
    <div className="signal-command-grid rounded-xl glow-buy animate-fade-in-up" style={{ backgroundColor: 'var(--card)', border: '1px solid var(--signal-buy-border)' }}>
      <section className="signal-lane signal-primary-lane">
      <div
        className="flex items-center justify-between pb-4"
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
              {fv != null && <FairValueSignalBadge fv={fv} price={signal.current_price} />}
            </div>
          </div>
        </div>
        <CopyButton ticker={signal.ticker} />
      </div>

      <div className="py-5 grid grid-cols-2 xl:grid-cols-4 gap-4">
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
        {fv != null ? (
          <div>
            <p className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>FAIR VALUE</p>
            <p className="font-mono font-bold tabular-nums" style={{ fontSize: '18px', color: '#50d8d0' }}>{fv.toFixed(2)}</p>
          </div>
        ) : (
          <div>
            <p className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>DISTANCE</p>
            <p className="font-mono font-bold tabular-nums" style={{ fontSize: '18px', color: signal.distance != null && signal.distance < 0 ? 'var(--signal-near)' : 'var(--foreground)' }}>
              {signal.distance != null ? `${signal.distance.toFixed(2)}%` : '—'}
            </p>
          </div>
        )}
        <div>
          <p className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>REWARD SCORE</p>
          <p className="font-mono font-bold tabular-nums" style={{ fontSize: '18px', color: 'var(--signal-reaccum)' }}>
            {signal.expected_reward_score?.toFixed(1) ?? '—'}
          </p>
        </div>
      </div>

      <div className="pb-4">
        <div className="flex items-center justify-between mb-2">
          <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.07em' }}>CONSTITUTIONAL R²</span>
          <span className="font-mono font-bold" style={{ fontSize: '12px', color: 'var(--signal-reaccum)' }}>
            {signal.candidate_r2 != null ? signal.candidate_r2 : '—'}
          </span>
        </div>
        <R2ProgressBar value={(signal.candidate_r2 ?? 0) / 100} color="var(--signal-reaccum)" height={5} />
      </div>

      <div className="mt-auto pt-3 flex items-center gap-2" style={{ borderTop: '1px solid rgba(16,185,129,0.12)' }}>
        <Zap size={11} style={{ color: 'var(--signal-buy)', flexShrink: 0 }} />
        <span className="font-mono" style={{ fontSize: '10px', color: 'var(--muted-foreground)' }}>{signal.waiting_for_reason}</span>
        <span className="font-mono ml-auto" style={{ fontSize: '9px', color: 'var(--muted-foreground)' }}>{signal.last_scan}</span>
      </div>
      </section>

      <section className="signal-lane signal-evidence-lane">
        <div className="signal-lane-title"><Activity size={13} /> WHY THIS SIGNAL</div>
        {mpi && <BehaviorPhaseBlock mpi={mpi} />}
        {dna && dna.constitutional_memory_hits > 0 && <SeenBeforePanel dna={dna} mpi={mpi} />}
        {valuation && valuation.weighted_fair_value != null && (
          <ValuationPanel valuation={valuation} currentPrice={signal.current_price} defaultExpanded />
        )}
      </section>

      <ActionQueue stats={stats} />
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
  const mpiMap        = snapshot.mpi_behavior ?? {};
  const dnaMap        = snapshot.stock_dna ?? {};
  const valuationMap  = snapshot.valuation ?? {};

  if (buySignals.length === 0) return <NoBuyState scanId={snapshot.scan_id} />;

  return (
    <div className="flex flex-col gap-4">
      {buySignals.map((signal) => (
        <BuyCard
          key={signal.ticker}
          signal={signal}
          mpi={mpiMap[signal.ticker]}
          dna={dnaMap[signal.ticker]}
          valuation={valuationMap[signal.ticker]}
          stats={snapshot.statistics}
        />
      ))}
    </div>
  );
}
