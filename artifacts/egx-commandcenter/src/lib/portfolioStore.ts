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

export function findUploadByHash(fileHash: string): StoredUpload | undefined {
  return load().uploads.find((u) => u.fileHash === fileHash);
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
  parsed: ParsedTransaction[]
): { status: 'parsed' | 'failed' | 'duplicate'; transactionCount: number; newCount: number; duplicateCount: number } {
  const state = load();
  const upload = state.uploads.find((u) => u.id === uploadId);
  if (!upload) return { status: 'failed', transactionCount: 0, newCount: 0, duplicateCount: 0 };

  if (parsed.length === 0) {
    upload.status = 'failed';
    upload.errorMessage = "No transactions found in the file. Make sure it's a Thunder report.";
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

// ─── Positions (FIFO-ish quantity aggregation) ─────────────────────────────
// Ported as-is from the server route: SELL reduces quantity but does not
// reduce totalCost, matching prior behavior exactly.
export function computePositions(transactions: StoredTransaction[]): {
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
    .map((p) => ({
      ticker: p.ticker,
      totalQuantity: p.totalQuantity,
      avgBuyPrice: p.totalCost / p.totalQuantity,
      totalCost: p.totalCost,
      currentPrice: null,
      currentValue: null,
      unrealizedPnl: null,
      unrealizedPnlPct: null,
      firstBuyDate: p.firstBuyDate,
      lastBuyDate: p.lastBuyDate,
    }));

  const totalCost = positions.reduce((s, p) => s + p.totalCost, 0);
  return { positions, totalCost };
}

// ─── P&L history (cumulative invested capital by day) ──────────────────────
export function computePnlHistory(transactions: StoredTransaction[]): PnlDataPoint[] {
  const sorted = [...transactions].sort((a, b) => a.tradeDate.localeCompare(b.tradeDate));
  if (sorted.length === 0) return [];

  const byDate = new Map<string, number>();
  let cumulative = 0;
  for (const row of sorted) {
    const dateKey = row.tradeDate.slice(0, 10);
    const qty = parseFloat(row.quantity);
    const price = parseFloat(row.price);
    if (row.transactionType === 'BUY') cumulative += qty * price;
    byDate.set(dateKey, cumulative);
  }

  return Array.from(byDate.entries()).map(([date]) => ({
    date,
    realizedPnl: 0, // will be calculated when sell transactions are tracked
    unrealizedPnl: 0, // requires current prices — enriched by frontend from snapshot
  }));
}
