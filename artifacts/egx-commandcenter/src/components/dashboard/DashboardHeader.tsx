import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw, AlertCircle, Wifi } from 'lucide-react';
import { useSnapshot } from '@/providers/SnapshotProvider';

function formatCairoTime(date: Date): string {
  return date.toLocaleTimeString('en-GB', { timeZone: 'Africa/Cairo', hour12: false });
}

function formatCairoDateTime(iso: string | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString('en-GB', {
      timeZone: 'Africa/Cairo',
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hour12: false,
    }).replace(',', '');
  } catch {
    return iso.slice(0, 16).replace('T', ' ');
  }
}

export default function DashboardHeader() {
  const { snapshot, loading, error, refresh } = useSnapshot();
  const [timeStr, setTimeStr] = useState('--:--:--');
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    const tick = () => setTimeStr(formatCairoTime(new Date()));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    await refresh?.();
    setTimeout(() => setRefreshing(false), 1500);
  }, [refresh]);

  const isLive = !error && !loading;
  const marketStatus = snapshot?.market_status ?? (loading ? '…' : 'UNAVAILABLE');
  const isMarketOpen = marketStatus === 'OPEN';
  const commit = snapshot?.commit ?? '-------';

  const lastScanTs = snapshot?.last_scan_ts ? formatCairoDateTime(snapshot.last_scan_ts) : '—';
  const generatedAt = snapshot?.generated_at ? formatCairoDateTime(snapshot.generated_at) : '—';
  const dataAsOf = snapshot?.price_data_as_of ?? '—';

  return (
    <header
      className="fixed top-0 left-0 right-0 z-50"
      style={{
        backgroundColor: 'rgba(7, 11, 20, 0.97)',
        borderBottom: '2px solid #252645',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
      }}
    >
      <div className="flex items-center justify-between px-4 md:px-6 max-w-[1680px] mx-auto" style={{ height: '52px' }}>
        <div className="flex items-center gap-3">
          <span style={{ fontSize: '20px' }}>🏛</span>
          <span
            className="font-bold tracking-tight"
            style={{ fontSize: '15px', color: '#d0d4e8', letterSpacing: '-0.01em' }}
          >
            EGX Constitutional Command Center
          </span>
          <span
            className="hidden md:inline font-mono px-2 py-0.5 rounded"
            style={{
              fontSize: '9px',
              backgroundColor: 'rgba(16,185,129,0.1)',
              color: '#4caf50',
              border: '1px solid rgba(76,175,80,0.25)',
              letterSpacing: '0.04em',
            }}
          >
            {commit}
          </span>
        </div>

        <div className="hidden md:flex items-center gap-3">
          <span
            className="font-mono font-bold px-2.5 py-1 rounded"
            style={{
              fontSize: '10px',
              backgroundColor: isMarketOpen ? 'rgba(76,175,80,0.12)' : 'rgba(255,255,255,0.05)',
              color: isMarketOpen ? '#4caf50' : '#8b8fa8',
              border: `1px solid ${isMarketOpen ? 'rgba(76,175,80,0.3)' : 'rgba(255,255,255,0.1)'}`,
              letterSpacing: '0.07em',
            }}
          >
            {isMarketOpen ? '● EGX OPEN' : `● EGX ${marketStatus}`}
          </span>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded"
            style={{
              backgroundColor: 'rgba(80,216,208,0.08)',
              border: '1px solid rgba(80,216,208,0.3)',
              color: '#50d8d0',
              fontSize: '11px',
              fontWeight: 600,
              cursor: refreshing ? 'default' : 'pointer',
              opacity: refreshing ? 0.6 : 1,
            }}
          >
            <RefreshCw size={11} className={refreshing ? 'animate-spin' : ''} />
            <span className="hidden md:inline font-mono" style={{ fontSize: '10px', letterSpacing: '0.06em' }}>
              REFRESH
            </span>
          </button>

          <div
            className="flex items-center gap-2 px-3 py-1.5 rounded"
            style={{ backgroundColor: 'rgba(255,255,255,0.03)', border: '1px solid #252645' }}
          >
            <span
              className="font-mono font-bold tabular-nums"
              style={{ fontSize: '14px', color: '#d0d4e8', letterSpacing: '0.05em' }}
            >
              {timeStr}
            </span>
            <span
              className="font-mono px-1 py-0.5 rounded"
              style={{
                fontSize: '8px',
                backgroundColor: 'rgba(59,130,246,0.12)',
                color: '#9c6fff',
                border: '1px solid rgba(156,111,255,0.2)',
                letterSpacing: '0.06em',
              }}
            >
              CAI
            </span>
            <div
              className="p-1 rounded"
              style={{
                backgroundColor: isLive ? 'rgba(76,175,80,0.1)' : 'rgba(239,68,68,0.1)',
                border: `1px solid ${isLive ? 'rgba(76,175,80,0.2)' : 'rgba(239,68,68,0.2)'}`,
              }}
            >
              {isLive ? (
                <Wifi size={12} style={{ color: '#4caf50' }} />
              ) : (
                <AlertCircle size={12} style={{ color: '#ef4444' }} />
              )}
            </div>
          </div>
        </div>
      </div>

      <div style={{ borderTop: '1px solid #1a2040' }}>
        <div
          className="flex flex-wrap items-center gap-x-5 gap-y-0.5 px-4 md:px-6 max-w-[1680px] mx-auto"
          style={{ height: '26px' }}
        >
          <span className="font-mono" style={{ fontSize: '10px', color: '#8b8fa8', whiteSpace: 'nowrap' }}>
            Last Scan&nbsp;<b style={{ color: '#d0d4e8' }}>{lastScanTs} Cairo</b>
          </span>
          <span className="font-mono" style={{ fontSize: '10px', color: '#8b8fa8', whiteSpace: 'nowrap' }}>
            Generated&nbsp;<b style={{ color: '#d0d4e8' }}>{generatedAt} Cairo</b>
          </span>
          <span className="font-mono" style={{ fontSize: '10px', color: '#8b8fa8', whiteSpace: 'nowrap' }}>
            Data As Of&nbsp;<b style={{ color: '#d0d4e8' }}>{dataAsOf}</b>
          </span>
        </div>
      </div>
    </header>
  );
}
