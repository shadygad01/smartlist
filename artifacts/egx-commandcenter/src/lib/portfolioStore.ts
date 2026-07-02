// Client-side Portfolio Tracker data layer. Runs entirely in the visitor's
// own browser via localStorage — no server, no shared database, so it works
// on the static GitHub Pages dashboard with zero hosting. Trade-off: data is
// per-browser only (clearing site data or switching devices loses history).
//
// Position/P&L math is ported as-is from artifacts/api-server/src/routes/portfolio.ts
// so behavior matches what the server version would have done.
import type { ParsedTransaction } from './portfolioParser';

export interface StoredUpload {
  id: number;
  fileName: string;
  fileHash: string;
  contentType: string;
  status: 'pending' | 'parsed' | 'failed' | 'duplicate';
  transactionCount: number;
  errorMessage?: string | null;
  createdAt: string;
}

export interface StoredTransaction {
  id: number;
  uploadId: number;
  ticker: string;
  transactionType: 'BUY' | 'SELL';
  quantity: string;
  price: string;
  tradeDate: string;
}

export interface PortfolioPosition {
  ticker: string;
  totalQuantity: number;
  avgBuyPrice: number;
  totalCost: number;
  currentPrice: number | null;
  currentValue: number | null;
  unrealizedPnl: number | null;
  unrealizedPnlPct: number | null;
  firstBuyDate: string;
  lastBuyDate: string;
}

export interface PnlDataPoint {
  date: string;
  realizedPnl: number;
  unrealizedPnl: number;
}

const STORAGE_KEY = 'egx-portfolio-tracker-v1';

interface StoreState {
  nextUploadId: number;
  nextTransactionId: number;
  uploads: StoredUpload[];
  transactions: StoredTransaction[];
}

function emptyState(): StoreState {
  return { nextUploadId: 1, nextTransactionId: 1, uploads: [], transactions: [] };
}

function load(): StoreState {
  if (typeof localStorage === 'undefined') return emptyState();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyState();
    return JSON.parse(raw) as StoreState;
  } catch {
    return emptyState();
  }
}

function save(state: StoreState) {
  if (typeof localStorage === 'undefined') return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export function getUploads(): StoredUpload[] {
  return [...load().uploads].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

export function getTransactions(): StoredTransaction[] {
  return [...load().transactions].sort((a, b) => b.tradeDate.localeCompare(a.tradeDate));
}

// Creates a pending upload record, then stores parsed transactions (or a
// failure reason) against it — mirrors the server's POST /portfolio/uploads.
export function recordUpload(params: {
  fileName: string;
  contentType: string;
  fileHash: string;
}): StoredUpload {
  const state = load();
  const upload: StoredUpload = {
    id: state.nextUploadId,
    fileName: params.fileName,
    fileHash: params.fileHash,
    contentType: params.contentType,
    status: 'pending',
    transactionCount: 0,
    createdAt: new Date().toISOString(),
  };
  state.uploads.push(upload);
  state.nextUploadId += 1;
  save(state);
  return upload;
}

// Identity for cross-upload dedup: same ticker/date/side/qty/price already
// recorded from an earlier upload means this row is old news, not a new
// trade. Normalized to fixed decimals so "45.5" and "45.50" match. Deliberately
// NOT used to dedupe rows against each other within the same upload — two
// genuinely identical trades placed the same day should both be kept.
function transactionKey(t: {
  ticker: string;
  transactionType: string;
  quantity: number | string;
  price: number | string;
  tradeDate: string | Date;
}): string {
  const date = t.tradeDate instanceof Date ? t.tradeDate.toISOString() : t.tradeDate;
  return [
    t.ticker,
    date.slice(0, 10),
    t.transactionType,
    Number(t.quantity).toFixed(4),
    Number(t.price).toFixed(4),
  ].join('|');
}

export function completeUpload(
  uploadId: number,
  parsed: ParsedTransaction[],
  noTradesMessage = "No transactions found in the file. Make sure it's a Thunder report."
): { status: 'parsed' | 'failed' | 'duplicate'; transactionCount: number; newCount: number; duplicateCount: number } {
  const state = load();
  const upload = state.uploads.find((u) => u.id === uploadId);
  if (!upload) return { status: 'failed', transactionCount: 0, newCount: 0, duplicateCount: 0 };

  if (parsed.length === 0) {
    upload.status = 'failed';
    upload.errorMessage = noTradesMessage;
    save(state);
    return { status: 'failed', transactionCount: 0, newCount: 0, duplicateCount: 0 };
  }

  const existingKeys = new Set(state.transactions.map(transactionKey));

  let newCount = 0;
  let duplicateCount = 0;
  for (const t of parsed) {
    if (existingKeys.has(transactionKey(t))) {
      duplicateCount += 1;
      continue;
    }
    state.transactions.push({
      id: state.nextTransactionId,
      uploadId,
      ticker: t.ticker,
      transactionType: t.transactionType,
      quantity: String(t.quantity),
      price: String(t.price),
      tradeDate: t.tradeDate.toISOString(),
    });
    state.nextTransactionId += 1;
    newCount += 1;
    // Not added to existingKeys: duplicates *within this same upload* should
    // still all be kept (see function doc comment above).
  }

  upload.status = newCount > 0 ? 'parsed' : 'duplicate';
  upload.transactionCount = newCount;
  if (newCount === 0) {
    upload.errorMessage = `All ${duplicateCount} transaction(s) in this file were already recorded.`;
  }
  save(state);
  return { status: upload.status, transactionCount: parsed.length, newCount, duplicateCount };
}

export function failUpload(uploadId: number, message: string) {
  const state = load();
  const upload = state.uploads.find((u) => u.id === uploadId);
  if (!upload) return;
  upload.status = 'failed';
  upload.errorMessage = message;
  save(state);
}

// Live prices come from presentation_snapshot.json's universe_snapshot — the
// same constitutional-scanner pipeline (price_authority.py / main.py's
// yfinance -> Yahoo chart API -> TradingView scanner fallback chain) already
// powers the rest of this dashboard, fetched app-wide by SnapshotProvider.
// Reusing it here means the Portfolio Tracker never needs its own price feed
// and always agrees with the scanner on "today's price" for a ticker.
// Snapshot tickers carry a ".CA" suffix (e.g. "COMI.CA"); parsed transactions
// don't, so this strips it before building the lookup map.
export function buildPriceMapFromSnapshot(
  universeSnapshot: Array<{ ticker: string; current_price: number }> | undefined
): Record<string, number> {
  const map: Record<string, number> = {};
  if (!universeSnapshot) return map;
  for (const item of universeSnapshot) {
    if (typeof item.current_price !== 'number' || item.current_price <= 0) continue;
    const bareTicker = item.ticker.replace(/\.CA$/i, '').toUpperCase();
    map[bareTicker] = item.current_price;
  }
  return map;
}

// ─── Positions (FIFO-ish quantity aggregation) ─────────────────────────────
// Ported as-is from the server route: SELL reduces quantity but does not
// reduce totalCost, matching prior behavior exactly. currentPrice/currentValue/
// unrealizedPnl stay null for any ticker missing from priceMap (outside the
// scanner's tracked universe) rather than guessing.
export function computePositions(
  transactions: StoredTransaction[],
  priceMap: Record<string, number> = {}
): {
  positions: PortfolioPosition[];
  totalCost: number;
} {
  const sorted = [...transactions].sort((a, b) => a.tradeDate.localeCompare(b.tradeDate));

  const posMap = new Map<
    string,
    { ticker: string; totalQuantity: number; totalCost: number; firstBuyDate: string; lastBuyDate: string }
  >();

  for (const row of sorted) {
    const qty = parseFloat(row.quantity);
    const price = parseFloat(row.price);
    const existing = posMap.get(row.ticker);

    if (row.transactionType === 'BUY') {
      if (existing) {
        existing.totalQuantity += qty;
        existing.totalCost += qty * price;
        if (row.tradeDate > existing.lastBuyDate) existing.lastBuyDate = row.tradeDate;
      } else {
        posMap.set(row.ticker, {
          ticker: row.ticker,
          totalQuantity: qty,
          totalCost: qty * price,
          firstBuyDate: row.tradeDate,
          lastBuyDate: row.tradeDate,
        });
      }
    } else if (existing) {
      existing.totalQuantity = Math.max(0, existing.totalQuantity - qty);
      if (existing.totalQuantity === 0) posMap.delete(row.ticker);
    }
  }

  const positions: PortfolioPosition[] = Array.from(posMap.values())
    .filter((p) => p.totalQuantity > 0)
    .map((p) => {
      const currentPrice = priceMap[p.ticker] ?? null;
      const currentValue = currentPrice != null ? currentPrice * p.totalQuantity : null;
      const unrealizedPnl = currentValue != null ? currentValue - p.totalCost : null;
      const unrealizedPnlPct =
        unrealizedPnl != null && p.totalCost > 0 ? (unrealizedPnl / p.totalCost) * 100 : null;
      return {
        ticker: p.ticker,
        totalQuantity: p.totalQuantity,
        avgBuyPrice: p.totalCost / p.totalQuantity,
        totalCost: p.totalCost,
        currentPrice,
        currentValue,
        unrealizedPnl,
        unrealizedPnlPct,
        firstBuyDate: p.firstBuyDate,
        lastBuyDate: p.lastBuyDate,
      };
    });

  const totalCost = positions.reduce((s, p) => s + p.totalCost, 0);
  return { positions, totalCost };
}

// ─── P&L history ────────────────────────────────────────────────────────────
// realizedPnl is a running total using average-cost accounting: each SELL
// realizes (sellPrice - avgCostAtTheTime) * quantitySold against whatever was
// held for that ticker so far. unrealizedPnl at each date is what's still
// held as of that date, marked at *today's* price from priceMap (there's no
// historical price feed to value it at the price on that past date) minus
// its cost basis — so the curve shows how paper gain/loss on shares
// accumulated over time would look valued at today's market, not a true
// day-by-day mark-to-market. Tickers missing from priceMap (outside the
// scanner's tracked universe) are excluded from unrealizedPnl entirely
// rather than being silently valued at 0.
export function computePnlHistory(
  transactions: StoredTransaction[],
  priceMap: Record<string, number> = {}
): PnlDataPoint[] {
  const sorted = [...transactions].sort((a, b) => a.tradeDate.localeCompare(b.tradeDate));
  if (sorted.length === 0) return [];

  const qtyByTicker = new Map<string, number>();
  const costByTicker = new Map<string, number>();
  let cumulativeRealizedPnl = 0;
  const byDate = new Map<string, { realizedPnl: number; unrealizedPnl: number }>();

  for (const row of sorted) {
    const dateKey = row.tradeDate.slice(0, 10);
    const qty = parseFloat(row.quantity);
    const price = parseFloat(row.price);

    if (row.transactionType === 'BUY') {
      qtyByTicker.set(row.ticker, (qtyByTicker.get(row.ticker) ?? 0) + qty);
      costByTicker.set(row.ticker, (costByTicker.get(row.ticker) ?? 0) + qty * price);
    } else {
      const heldQty = qtyByTicker.get(row.ticker) ?? 0;
      const heldCost = costByTicker.get(row.ticker) ?? 0;
      const avgCost = heldQty > 0 ? heldCost / heldQty : 0;
      const soldQty = Math.min(qty, heldQty);
      cumulativeRealizedPnl += soldQty * (price - avgCost);
      qtyByTicker.set(row.ticker, heldQty - soldQty);
      costByTicker.set(row.ticker, heldCost - soldQty * avgCost);
    }

    let unrealizedPnl = 0;
    for (const [ticker, heldQty] of qtyByTicker) {
      if (heldQty <= 0) continue;
      const currentPrice = priceMap[ticker];
      if (currentPrice == null) continue;
      unrealizedPnl += heldQty * currentPrice - (costByTicker.get(ticker) ?? 0);
    }

    byDate.set(dateKey, { realizedPnl: cumulativeRealizedPnl, unrealizedPnl });
  }

  return Array.from(byDate.entries()).map(([date, v]) => ({
    date,
    realizedPnl: v.realizedPnl,
    unrealizedPnl: v.unrealizedPnl,
  }));
}
