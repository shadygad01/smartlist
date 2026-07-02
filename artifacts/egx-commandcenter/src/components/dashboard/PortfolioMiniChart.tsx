import React, { useEffect, useState } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { TrendingUp } from 'lucide-react';
import { Link } from 'wouter';
import {
  getTransactions,
  computePositions,
  computePnlHistory,
  buildPriceMapFromSnapshot,
  type PnlDataPoint,
} from '@/lib/portfolioStore';
import { useSnapshot } from '@/providers/SnapshotProvider';

interface PortfolioSummary {
  positionCount: number;
  totalCost: number;
  totalUnrealizedPnl: number | null;
}

function fmt(n: number) {
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return n.toFixed(0);
}

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div
      className="font-mono rounded-lg p-3"
      style={{ backgroundColor: '#181930', border: '1px solid #252645', fontSize: '11px' }}
    >
      <p style={{ color: '#6b7280', marginBottom: 4 }}>{label}</p>
      {payload.map((p: any) => (
        <p key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {fmt(p.value)} EGP
        </p>
      ))}
    </div>
  );
};

export default function PortfolioMiniChart() {
  const { snapshot } = useSnapshot();
  const [points, setPoints] = useState<PnlDataPoint[]>([]);
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const transactions = getTransactions();
    const priceMap = buildPriceMapFromSnapshot([
      ...(snapshot?.universe_snapshot ?? []),
      ...(snapshot?.portfolio_extra_prices ?? []),
    ]);
    setPoints(computePnlHistory(transactions, priceMap));
    const { positions, totalCost } = computePositions(transactions, priceMap);
    const pricedPositions = positions.filter((p) => p.unrealizedPnl != null);
    const totalUnrealizedPnl =
      pricedPositions.length > 0
        ? pricedPositions.reduce((s, p) => s + (p.unrealizedPnl ?? 0), 0)
        : null;
    setSummary({ positionCount: positions.length, totalCost, totalUnrealizedPnl });
    setLoading(false);
  }, [snapshot]);

  const hasData = points.length > 0;

  return (
    <div
      className="rounded-xl p-4"
      style={{ backgroundColor: '#181930', border: '1px solid #252645' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <TrendingUp size={14} color="#10b981" />
          <span className="font-mono font-bold" style={{ fontSize: '11px', color: '#c4c9df', letterSpacing: '0.08em' }}>
            PORTFOLIO P&amp;L
          </span>
        </div>
        <Link
          href="/portfolio"
          className="font-mono px-2 py-0.5 rounded transition-opacity hover:opacity-70"
          style={{
            fontSize: '10px',
            color: '#4a9fff',
            backgroundColor: 'rgba(74,159,255,0.08)',
            border: '1px solid rgba(74,159,255,0.2)',
          }}
        >
          OPEN →
        </Link>
      </div>

      {/* Summary pills */}
      {summary && (
        <div className="flex gap-2 mb-3">
          <span className="font-mono px-2 py-0.5 rounded" style={{ fontSize: '10px', color: '#10b981', backgroundColor: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.2)' }}>
            {summary.positionCount} positions
          </span>
          {summary.totalCost > 0 && (
            <span className="font-mono px-2 py-0.5 rounded" style={{ fontSize: '10px', color: '#3b82f6', backgroundColor: 'rgba(59,130,246,0.08)', border: '1px solid rgba(59,130,246,0.2)' }}>
              {fmt(summary.totalCost)} EGP
            </span>
          )}
          {summary.totalUnrealizedPnl != null && (() => {
            const up = summary.totalUnrealizedPnl >= 0;
            const color = up ? '#10b981' : '#ef4444';
            return (
              <span className="font-mono px-2 py-0.5 rounded" style={{ fontSize: '10px', color, backgroundColor: `${color}14`, border: `1px solid ${color}33` }}>
                {up ? '+' : ''}{fmt(summary.totalUnrealizedPnl)} EGP
              </span>
            );
          })()}
        </div>
      )}

      {/* Chart or empty state */}
      {loading ? (
        <div className="flex items-center justify-center" style={{ height: 120 }}>
          <div
            className="animate-spin rounded-full"
            style={{ width: 20, height: 20, border: '2px solid #252645', borderTopColor: '#10b981' }}
          />
        </div>
      ) : !hasData ? (
        <div className="flex flex-col items-center justify-center gap-2" style={{ height: 120 }}>
          <p className="font-mono text-center" style={{ fontSize: '11px', color: '#3b4565' }}>
            Upload a statement to see the chart
          </p>
          <Link
            href="/portfolio"
            className="font-mono px-3 py-1 rounded transition-opacity hover:opacity-80"
            style={{ fontSize: '10px', color: '#10b981', backgroundColor: 'rgba(16,185,129,0.08)', border: '1px solid rgba(16,185,129,0.25)' }}
          >
            Upload file →
          </Link>
        </div>
      ) : (
        <>
          {/* Legend */}
          <div className="flex gap-4 mb-2">
            <div className="flex items-center gap-1.5">
              <div className="rounded-full" style={{ width: 8, height: 8, backgroundColor: '#10b981' }} />
              <span className="font-mono" style={{ fontSize: '10px', color: '#6b7280' }}>Unrealized</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="rounded-full" style={{ width: 8, height: 8, backgroundColor: '#3b82f6' }} />
              <span className="font-mono" style={{ fontSize: '10px', color: '#6b7280' }}>Realized</span>
            </div>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={points} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1a1e35" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fontFamily: 'JetBrains Mono', fontSize: 9, fill: '#4a5070' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => v.slice(5)}
              />
              <YAxis
                tick={{ fontFamily: 'JetBrains Mono', fontSize: 9, fill: '#4a5070' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={fmt}
              />
              <Tooltip content={<CustomTooltip />} />
              <Line
                type="monotone"
                dataKey="unrealizedPnl"
                name="Unrealized"
                stroke="#10b981"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: '#10b981' }}
              />
              <Line
                type="monotone"
                dataKey="realizedPnl"
                name="Realized"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, fill: '#3b82f6' }}
              />
            </LineChart>
          </ResponsiveContainer>
        </>
      )}
    </div>
  );
}
