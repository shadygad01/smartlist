import React from 'react';
import DashboardHeader from './components/DashboardHeader';
import StatsBar from './components/StatsBar';
import BuySignalCard from './components/BuySignalCard';
import NearEntrySection from './components/NearEntrySection';
import UniverseSection from './components/UniverseSection';
import TimelineSection from './components/TimelineSection';
import StockDNASection from './components/StockDNASection';
import DiagnosticsSection from './components/DiagnosticsSection';
import ToastProvider from './components/ToastProvider';

export default function EGXCommandCenter() {
  return (
    <div className="min-h-screen" style={{ backgroundColor: 'var(--background)' }}>
      <ToastProvider />
      {/* Fixed Header */}
      <DashboardHeader />

      {/* Main scrollable content — offset for fixed header */}
      <main className="pt-[68px] pb-16 px-4 md:px-6 xl:px-10 2xl:px-16 max-w-screen-2xl mx-auto">
        {/* Stats Bar */}
        <div className="mt-5">
          <StatsBar />
        </div>

        {/* Primary Signal Area */}
        <div className="mt-5 grid grid-cols-1 xl:grid-cols-3 gap-5">
          {/* BUY Signal Card — prominent hero */}
          <div className="xl:col-span-2">
            <BuySignalCard />
          </div>

          {/* Near Entry Section */}
          <div className="xl:col-span-1">
            <NearEntrySection />
          </div>
        </div>

        {/* Section divider */}
        <div className="mt-6 mb-1 flex items-center gap-3">
          <div style={{ height: '1px', flex: 1, background: 'linear-gradient(to right, var(--border), transparent)' }} />
          <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.1em' }}>
            MARKET INTELLIGENCE
          </span>
          <div style={{ height: '1px', flex: 1, background: 'linear-gradient(to left, var(--border), transparent)' }} />
        </div>

        {/* Secondary Data Sections */}
        <div className="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-5">
          <UniverseSection />
          <TimelineSection />
        </div>

        {/* Section divider */}
        <div className="mt-6 mb-1 flex items-center gap-3">
          <div style={{ height: '1px', flex: 1, background: 'linear-gradient(to right, var(--border), transparent)' }} />
          <span className="font-mono" style={{ fontSize: '9px', color: 'var(--muted-foreground)', letterSpacing: '0.1em' }}>
            ANALYSIS & DIAGNOSTICS
          </span>
          <div style={{ height: '1px', flex: 1, background: 'linear-gradient(to left, var(--border), transparent)' }} />
        </div>

        {/* DNA + Diagnostics */}
        <div className="mt-4 grid grid-cols-1 xl:grid-cols-2 gap-5">
          <StockDNASection />
          <DiagnosticsSection />
        </div>
      </main>
    </div>
  );
}