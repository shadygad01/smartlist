import React from 'react';
import { Link } from 'wouter';
import DashboardHeader from '@/components/dashboard/DashboardHeader';
import StatsBar from '@/components/dashboard/StatsBar';
import BuySignalCard from '@/components/dashboard/BuySignalCard';
import NearEntrySection from '@/components/dashboard/NearEntrySection';
import ReAccumulationSection from '@/components/dashboard/ReAccumulationSection';
import UniverseSection from '@/components/dashboard/UniverseSection';
import TimelineSection from '@/components/dashboard/TimelineSection';
import StockDNASection from '@/components/dashboard/StockDNASection';
import WatchlistSection from '@/components/dashboard/WatchlistSection';
import FutureCandidatesSection from '@/components/dashboard/FutureCandidatesSection';
import EventTimelineSection from '@/components/dashboard/EventTimelineSection';
import ValuationSection from '@/components/dashboard/ValuationSection';
import DiagnosticsSection from '@/components/dashboard/DiagnosticsSection';

export default function DashboardPage() {
  return (
    <div style={{ backgroundColor: 'var(--background)', minHeight: '100vh' }}>
      <DashboardHeader />

      <main className="px-4 md:px-6 xl:px-10 pb-10" style={{ paddingTop: '88px' }}>
        <div className="flex flex-col gap-4">
          <StatsBar />

          <BuySignalCard />

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <NearEntrySection />
            <WatchlistSection />
          </div>

          <ReAccumulationSection />
          <EventTimelineSection />
          <TimelineSection />
          <ValuationSection />
          <UniverseSection />
          <StockDNASection />
          <FutureCandidatesSection />
          <DiagnosticsSection />

          <div className="flex items-center justify-center pt-4">
            <Link
              href="/archive"
              className="font-mono px-4 py-2 rounded-lg transition-all duration-150 hover:opacity-80"
              style={{
                fontSize: '11px',
                backgroundColor: 'rgba(167,139,250,0.08)',
                border: '1px solid rgba(167,139,250,0.25)',
                color: '#a78bfa',
                letterSpacing: '0.05em',
              }}
            >
              VIEW CONSTITUTIONAL SIGNAL ARCHIVE →
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
