import React from 'react';
import { Switch, Route, Router as WouterRouter } from 'wouter';
import SnapshotProvider from '@/providers/SnapshotProvider';
import ToastProvider from '@/components/dashboard/ToastProvider';
import DashboardPage from '@/pages/DashboardPage';
import ArchivePage from '@/pages/ArchivePage';
import PortfolioPage from '@/pages/PortfolioPage';

function App() {
  return (
    <SnapshotProvider>
      <ToastProvider />
      <WouterRouter base={import.meta.env.BASE_URL.replace(/\/$/, '')}>
        <Switch>
          <Route path="/" component={DashboardPage} />
          <Route path="/archive" component={ArchivePage} />
          <Route path="/portfolio" component={PortfolioPage} />
          <Route>
            <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: 'var(--background)' }}>
              <div className="text-center">
                <p className="font-mono font-bold" style={{ fontSize: '48px', color: 'var(--foreground)', opacity: 0.2 }}>404</p>
                <p className="font-mono mt-2" style={{ fontSize: '13px', color: 'var(--muted-foreground)' }}>Page not found</p>
                <a href="/" className="font-mono mt-4 inline-block" style={{ fontSize: '11px', color: 'var(--signal-buy)' }}>← Back to dashboard</a>
              </div>
            </div>
          </Route>
        </Switch>
      </WouterRouter>
    </SnapshotProvider>
  );
}

export default App;
