// Client-side Portfolio Tracker data layer. Runs entirely in the visitor's
// own browser via localStorage — no server, no shared database, so it works
// on the static GitHub Pages dashboard with zero hosting. Trade-off: data is
// per-browser only (clearing site data or switching devices loses history).
//
// Position/P&L math is ported as-is from artifacts/api-server/src/routes/portfolio.ts
// so behavior matches what the server version would have done.
import type { ParsedTransaction, PositionVerification } from './portfolioParser';
import { normalizeCompanyKey, fuzzyMatchTicker } from './portfolioParser';

export type { PositionVerification } from './portfolioParser';

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
  // Ground-truth check against a "My position" screenshot upload (see
  // PositionVerification below). null when no verification has been
  // uploaded for this ticker — the row is then purely statement-derived,
  // same as before this feature existed.
  verifiedUnits: number | null;
  // The statement-derived quantity before capping — only differs from
  // totalQuantity when quantityMismatch is true, kept so the UI can show
  // "computed 80, broker confirms 74" rather than just hiding the gap.
  rawComputedQuantity: number;
  quantityMismatch: boolean;
  // Set when this ticker's raw label fuzzy-matches a *different* ticker's
  // verified company name — signals the same stock likely got split across
  // two rows because a statement's company name didn't resolve to the
  // canonical ticker (e.g. OCR noise). Points at the canonical ticker.
  duplicateOf: string | null;
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

// Identity for cross-upload dedup: same ticker/date/side/qty already recorded
// from an earlier upload means this row is old news, not a new trade.
// Deliberately excludes price — the same real trade parsed from a statement
// PDF (price derived from the Value column, which includes commission) vs.
// from an Orders-screen screenshot (raw nominal execution price, no Value
// column available) yields two different price numbers for one real trade,
// e.g. "Buy EFG HOLDING (39@26.98) -1,056.54" derives an effective price of
// ~27.09, while the same fulfilled order on its Orders screen reads a plain
// "26.980" — confirmed against a real user statement/screenshot pair that
// was silently double-counted (inflating quantity and cost basis) when price
// was part of the key. Ticker+date+type+qty is a reliable enough proxy for
// "same real trade" across formats. Normalized to fixed decimals so "45.5"
// and "45.50" match. Deliberately NOT used to dedupe rows against each other
// within the same upload — two genuinely identical trades placed the same
// day should both be kept.
function transactionKey(t: {
  ticker: string;
  transactionType: string;
  quantity: number | string;
  tradeDate: string | Date;
}): string {
  const date = t.tradeDate instanceof Date ? t.tradeDate.toISOString() : t.tradeDate;
  return [
    t.ticker,
    date.slice(0, 10),
    t.transactionType,
    Number(t.quantity).toFixed(4),
  ].join('|');
}

// Running BUY-minus-SELL quantity already on record for a ticker — used to
// arbitrate the same-key-looks-like-a-duplicate case below against a
// verified ground truth, so it must reflect state.transactions as it stands
// *at the point of the check*, including any rows already pushed earlier in
// this same completeUpload() call.
function recordedQuantity(transactions: StoredTransaction[], ticker: string): number {
  let qty = 0;
  for (const t of transactions) {
    if (t.ticker !== ticker) continue;
    const q = parseFloat(t.quantity);
    qty = t.transactionType === 'BUY' ? qty + q : Math.max(0, qty - q);
  }
  return qty;
}

export function completeUpload(
  uploadId: number,
  parsed: ParsedTransaction[],
  noTradesMessage = "No transactions found in the file. Make sure it's a Thunder report.",
  verifications: Record<string, PositionVerification> = {}
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
    let looksLikeDuplicate = existingKeys.has(transactionKey(t));

    // A same ticker/date/side/qty match is usually a genuine duplicate row
    // from a re-uploaded/overlapping statement — but it can also be two real
    // trades that happen to share a day, quantity, and (coincidentally)
    // price, e.g. topping up a position twice the same day. When a verified
    // broker unit count exists for the ticker, prefer it over the same-key
    // heuristic here: if what's on record is still short of the verified
    // total, and keeping this BUY wouldn't push the total past it, it's more
    // likely a real second trade than a duplicate. Scoped to BUY only — a
    // wrongly-kept duplicate SELL would understate the position instead,
    // which this ground truth can't help arbitrate the same way.
    if (looksLikeDuplicate && t.transactionType === 'BUY') {
      const verification = verifications[t.ticker];
      if (verification) {
        const recorded = recordedQuantity(state.transactions, t.ticker);
        if (recorded < verification.units && recorded + t.quantity <= verification.units) {
          looksLikeDuplicate = false;
        }
      }
    }

    if (looksLikeDuplicate) {
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

// Manual escape hatch for a bad row (e.g. a parsing glitch from before a fix
// landed) without having to wipe and re-upload everything else.
export function deleteTransaction(transactionId: number): void {
  const state = load();
  state.transactions = state.transactions.filter((t) => t.id !== transactionId);
  save(state);
}

// ─── Position verification (ground truth from a broker "My position" screen) ──
// Stored separately from transactions/uploads — keyed by ticker so it's
// order-independent (a verification screenshot can be uploaded before or
// after the transaction statement it checks) and always reflects the most
// recently uploaded snapshot for that ticker.
const VERIFICATION_KEY = 'egx-portfolio-verifications-v1';

function loadVerifications(): Record<string, PositionVerification> {
  if (typeof localStorage === 'undefined') return {};
  try {
    const raw = localStorage.getItem(VERIFICATION_KEY);
    return raw ? (JSON.parse(raw) as Record<string, PositionVerification>) : {};
  } catch {
    return {};
  }
}

function saveVerifications(v: Record<string, PositionVerification>) {
  if (typeof localStorage === 'undefined') return;
  localStorage.setItem(VERIFICATION_KEY, JSON.stringify(v));
}

export function getPositionVerifications(): Record<string, PositionVerification> {
  return loadVerifications();
}

export function recordPositionVerification(v: PositionVerification): void {
  const all = loadVerifications();
  all[v.ticker] = v;
  saveVerifications(all);
}

export function deletePositionVerification(ticker: string): void {
  const all = loadVerifications();
  delete all[ticker];
  saveVerifications(all);
}

// Live prices come from presentation_snapshot.json's universe_snapshot — the
// same constitutional-scanner pipeline (price_authority.py / main.py's
// yfinance -> Yahoo chart API -> TradingView scanner fallback chain) already
// powers the rest of this dashboard, fetched app-wide by SnapshotProvider.
// Reusing it here means the Portfolio Tracker never needs its own price feed
// and always agrees with the scanner on "today's price" for a ticker.
// Snapshot tickers carry a ".CA" suffix (e.g. "COMI.CA"); parsed transactions
// don't, so this strips it before building the lookup map.
// Callers pass universe_snapshot concatenated with portfolio_extra_prices —
// the latter covers tickers a user holds outside the scanner's trading
// universe (e.g. PHAR, CSAG), fetched from the same TradingView/yfinance
// sources by portfolio_extra_prices.py, without pulling them into
// signals/gates/backtests.
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
  priceMap: Record<string, number> = {},
  verifications: Record<string, PositionVerification> = {}
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

  const verificationList = Object.values(verifications);

  const positions: PortfolioPosition[] = Array.from(posMap.values())
    .filter((p) => p.totalQuantity > 0)
    .map((p) => {
      const verification = verifications[p.ticker];
      // The broker's own position screen is ground truth for units actually
      // held — the displayed/priced quantity must never exceed it, even if a
      // statement-parsing bug (duplicate or misparsed trade) makes the
      // computed total say more. Quantity itself is capped; totalCost/
      // avgBuyPrice are left as literal statement-derived figures (still
      // useful context) rather than guessed at, since we don't know *which*
      // trade in the statement is the bad one.
      const quantityMismatch = verification != null && p.totalQuantity > verification.units;
      const displayQuantity = verification != null ? Math.min(p.totalQuantity, verification.units) : p.totalQuantity;

      // Same stock split across two different ticker labels (e.g. a garbled
      // OCR company name that didn't resolve to the canonical ticker) — flag
      // it against any verification whose canonical name this label
      // fuzzy-matches, so it never silently reads as two separate holdings.
      let duplicateOf: string | null = null;
      for (const v of verificationList) {
        if (v.ticker === p.ticker) continue;
        if (fuzzyMatchTicker(normalizeCompanyKey(p.ticker)) === v.ticker) {
          duplicateOf = v.ticker;
          break;
        }
      }

      const currentPrice = priceMap[p.ticker] ?? null;
      const currentValue = currentPrice != null ? currentPrice * displayQuantity : null;
      const unrealizedPnl = currentValue != null ? currentValue - p.totalCost : null;
      const unrealizedPnlPct =
        unrealizedPnl != null && p.totalCost > 0 ? (unrealizedPnl / p.totalCost) * 100 : null;
      return {
        ticker: p.ticker,
        totalQuantity: displayQuantity,
        rawComputedQuantity: p.totalQuantity,
        verifiedUnits: verification?.units ?? null,
        quantityMismatch,
        duplicateOf,
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
