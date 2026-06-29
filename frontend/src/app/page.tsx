import React from 'react';
import DashboardHeader from './components/DashboardHeader';
import StatsBar from './components/StatsBar';
import BuySignalCard from './components/BuySignalCard';
import NearEntrySection from './components/NearEntrySection';
import ReAccumulationSection from './components/ReAccumulationSection';
import UniverseSection from './components/UniverseSection';
import TimelineSection from './components/TimelineSection';
import StockDNASection from './components/StockDNASection';
import WatchlistSection from './components/WatchlistSection';
import FutureCandidatesSection from './components/FutureCandidatesSection';
import ToastProvider from './components/ToastProvider';

function Divider({ label }: { label: string }) {
  return (
    <div className="mt-6 mb-1 flex items-center gap-3">
      <div style={{ height: '1px', flex: 1, background: 'linear-gradient(to right, var(--border), transparent)' }} />
      <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.1em' }}>{label}</span>
      <div style={{ height: '1px', flex: 1, background: 'linear-gradient(to left, var(--border), transparent)' }} />
    </div>
  );
}

export default function EGXCommandCenter() {
  return (
    <div className="min-h-screen" style={{ backgroundColor: 'var(--background)' }}>
      <ToastProvider />

      {/* Fixed Header — scan_id, market_status, commit, wall clock */}
      <DashboardHeader />

      <main className="pt-[78px] pb-16 px-4 md:px-6 xl:px-10 2xl:px-16 max-w-screen-2xl mx-auto">

        {/* ── TIER 1: Statistics ─────────────────────────────────────────────── */}
        <div className="mt-5">
          <StatsBar />
        </div>

        {/* ── TIER 2: Critical Constitutional Decisions ─────────────────────── */}
        <Divider label="CONSTITUTIONAL DECISIONS" />

        <div className="mt-4 grid grid-cols-1 xl:grid-cols-3 gap-5">
          {/* BUY Signal — renders only when snapshot has a BUY-ready ticker */}
          <div className="xl:col-span-2">
            <BuySignalCard />
          </div>
          {/* Near Constitutional Entry */}
          <div className="xl:col-span-1">
            <NearEntrySection />
          </div>
        </div>

        {/* ── TIER 3: Constitutional Timeline ───────────────────────────────── */}
        <Divider label="CONSTITUTIONAL TIMELINE" />

        {/* Re-Accumulation events — renders only when events exist */}
        <div className="mt-4">
          <ReAccumulationSection />
        </div>

        {/* Today's timeline events + statistics */}
        <div className="mt-4">
          <TimelineSection />
        </div>

        {/* ── TIER 4: Market Context / Universe ─────────────────────────────── */}
        <Divider label="MARKET CONTEXT" />

        <div className="mt-4">
          <UniverseSection />
        </div>

        {/* ── TIER 5: Portfolio ─────────────────────────────────────────────── */}
        <Divider label="PORTFOLIO" />

        <div className="mt-4">
          {/* Active Positions (status: ACTIVE | PREMIUM | UNDER_REVIEW) */}
          <StockDNASection />
        </div>

        {/* Watch List + Future Candidates */}
        <div className="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-5">
          <WatchlistSection />
          <FutureCandidatesSection />
        </div>

      </main>
    </div>
  );
}
