import React, { useState } from 'react';
import { TrendingUp, ChevronDown, ChevronUp } from 'lucide-react';
import { useSnapshot } from '@/providers/SnapshotProvider';
import type { ValuationCard } from '@/types/snapshot';

function fmtPrice(v: number | null | undefined): string {
  if (v == null) return '—';
  return v.toFixed(2);
}

function upsideColor(pct: number | null | undefined): string {
  if (pct == null) return '#8b8fa8';
  return pct >= 0 ? '#4caf50' : '#f44336';
}

function ValuationRow({ ticker, card, currentPrice }: { ticker: string; card: ValuationCard; currentPrice?: number }) {
  const fv = card.weighted_fair_value;
  const upside = (fv != null && currentPrice != null && currentPrice > 0)
    ? ((fv - currentPrice) / currentPrice) * 100
    : null;

  return (
    <tr style={{ borderBottom: '1px solid #1a2040' }}>
      <td className="font-mono font-bold" style={{ padding: '9px 10px', color: '#ffffff', whiteSpace: 'nowrap' }}>
        {ticker}
      </td>
      <td className="font-mono" style={{ padding: '9px 10px', color: '#d0d4e8', whiteSpace: 'nowrap', fontSize: '12px' }}>
        {fmtPrice(fv)}
      </td>
      <td className="font-mono font-bold" style={{ padding: '9px 10px', color: upsideColor(upside), whiteSpace: 'nowrap', fontSize: '12px' }}>
        {upside != null ? `${upside >= 0 ? '+' : ''}${upside.toFixed(1)}%` : '—'}
      </td>
      <td className="font-mono" style={{ padding: '9px 10px', color: '#4caf50', whiteSpace: 'nowrap', fontSize: '12px' }}>
        {fmtPrice(card.bull_case)}
      </td>
      <td className="font-mono" style={{ padding: '9px 10px', color: '#d0d4e8', whiteSpace: 'nowrap', fontSize: '12px' }}>
        {fmtPrice(card.base_case)}
      </td>
      <td className="font-mono" style={{ padding: '9px 10px', color: '#f44336', whiteSpace: 'nowrap', fontSize: '12px' }}>
        {fmtPrice(card.bear_case)}
      </td>
      <td className="font-mono" style={{ padding: '9px 10px', color: '#8b8fa8', whiteSpace: 'nowrap', fontSize: '12px' }}>
        {fmtPrice(card.analyst_consensus_price)}
      </td>
      <td className="font-mono" style={{ padding: '9px 10px', color: '#8b8fa8', whiteSpace: 'nowrap', fontSize: '11px' }}>
        {card.valuation_date ?? '—'}
      </td>
    </tr>
  );
}

export default function ValuationSection() {
  const { snapshot, loading } = useSnapshot();
  const [collapsed, setCollapsed] = useState(false);

  const valuation = snapshot?.valuation ?? {};
  const cards = Object.entries(valuation) as [string, ValuationCard][];

  const priceMap: Record<string, number> = {};
  for (const u of snapshot?.universe_snapshot ?? []) {
    if (u.ticker && u.current_price != null) priceMap[u.ticker] = u.current_price;
  }

  const cardCount = cards.length;

  return (
    <div className="rounded-xl overflow-hidden" style={{ backgroundColor: '#10112a', border: '1px solid #252645' }}>
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-4 py-3.5"
        style={{ borderBottom: collapsed ? 'none' : '1px solid #252645', cursor: 'pointer', background: 'none' }}
      >
        <div className="flex items-center gap-2">
          <TrendingUp size={13} style={{ color: '#50d8d0' }} />
          <span className="font-mono font-semibold" style={{ fontSize: '12px', color: '#d0d4e8', letterSpacing: '0.07em' }}>
            INSTITUTIONAL VALUATION ENGINE
          </span>
          <span
            className="font-mono px-2 py-0.5 rounded"
            style={{ fontSize: '9px', backgroundColor: 'rgba(80,216,208,0.1)', color: '#50d8d0', border: '1px solid rgba(80,216,208,0.2)' }}
          >
            {loading ? '…' : cardCount > 0 ? `${cardCount} VALUED` : 'AWAITING DATA'}
          </span>
        </div>
        {collapsed
          ? <ChevronDown size={13} style={{ color: '#8b8fa8' }} />
          : <ChevronUp size={13} style={{ color: '#8b8fa8' }} />}
      </button>

      {!collapsed && (
        <div>
          {cardCount === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 gap-2">
              <span className="font-mono font-semibold" style={{ fontSize: '11px', color: '#8b8fa8' }}>
                VALUATION DATA NOT YET AVAILABLE
              </span>
              <span className="font-mono" style={{ fontSize: '10px', color: '#4a4f70' }}>
                Run the valuation scheduler to populate fair-value estimates
              </span>
            </div>
          ) : (
            <div style={{ overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', minWidth: '700px' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid #252645' }}>
                    {['Ticker', 'Fair Value', 'Upside', 'Bull Case', 'Base Case', 'Bear Case', 'Consensus', 'Date'].map(h => (
                      <th key={h} className="font-mono" style={{ padding: '9px 10px', color: '#8b8fa8', fontSize: '10px', fontWeight: 700, letterSpacing: '0.4px', textTransform: 'uppercase', textAlign: 'left', whiteSpace: 'nowrap' }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {cards.map(([ticker, card]) => (
                    <ValuationRow key={ticker} ticker={ticker} card={card} currentPrice={priceMap[ticker]} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
