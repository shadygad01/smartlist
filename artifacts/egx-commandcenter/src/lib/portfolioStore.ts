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

// The Portfolio Tracker is scoped to 2026+ (see the "2026+" badge on the
// page) — trades before this date are out of its tracked range and must
// never factor into positions, P&L, or the transactions list, regardless of
// what a statement upload happens to contain. Applied both when accepting
// new uploads (so they're never stored) and when reading back whatever's
// already in localStorage (so pre-existing data from before this cutoff
// existed is excluded too).
export const TRACKING_START_DATE = '2026-01-01';

function isInTrackedRange(tradeDate: string): boolean {
  return tradeDate.slice(0, 10) >= TRACKING_START_DATE;
}

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
  return [...load().transactions]
    .filter((t) => isInTrackedRange(t.tradeDate))
    .sort((a, b) => b.tradeDate.localeCompare(a.tradeDate));
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
// recorded from an earlier upload means this exact row is old news, not a
// new trade. Includes price deliberately — unlike the "possible duplicate"
// grouping below, this is only meant to catch a *literal* re-upload of the
// same statement/screenshot, which always reproduces the same price too.
// Normalized to fixed decimals so "45.5" and "45.50" match. Deliberately NOT
// used to dedupe rows against each other within the same upload — two
// genuinely identical trades placed the same day should both be kept.
function exactTransactionKey(t: {
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

// Looser identity used only to *flag* possible duplicates for the user to
// review (see withDuplicateFlags below) — ticker+date+side+qty, excluding
// price. The same real trade parsed from a statement PDF (price derived
// from the Value column, which includes commission) vs. from an
// Orders-screen screenshot (raw nominal execution price, no commission)
// yields two different price numbers for one real trade, e.g.
// "Buy EFG HOLDING (39@26.98) -1,056.54" derives an effective price of
// ~27.09, while the same fulfilled order on its Orders screen reads a plain
// "26.980". That's indistinguishable, from the data alone, from a genuine
// second same-day trade at a different price — so rather than guessing,
// both get kept and flagged for the user to confirm or delete themselves.
function looseTransactionKey(t: { ticker: string; transactionType: string; quantity: string; tradeDate: string }): string {
  return [t.ticker, t.tradeDate.slice(0, 10), t.transactionType, Number(t.quantity).toFixed(4)].join('|');
}

export interface TransactionWithFlags extends StoredTransaction {
  possibleDuplicate: boolean;
}

// Groups transactions by looseTransactionKey and marks every member of any
// group with 2+ entries — those share a ticker/date/side/qty but (since
// they weren't caught by the exact-key dedup above) differ in price, the
// commission-inclusion ambiguity described above. Purely a read-time
// computed flag, not persisted — so it re-evaluates correctly as rows get
// added or removed instead of going stale.
export function withDuplicateFlags(transactions: StoredTransaction[]): TransactionWithFlags[] {
  const counts = new Map<string, number>();
  for (const t of transactions) {
    const key = looseTransactionKey(t);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return transactions.map((t) => ({ ...t, possibleDuplicate: (counts.get(looseTransactionKey(t)) ?? 0) > 1 }));
}

export function completeUpload(
  uploadId: number,
  parsed: ParsedTransaction[],
  noTradesMessage = "No transactions found in the file. Make sure it's a Thunder report."
): {
  status: 'parsed' | 'failed' | 'duplicate';
  transactionCount: number;
  newCount: number;
  duplicateCount: number;
  outOfRangeCount: number;
} {
  const state = load();
  const upload = state.uploads.find((u) => u.id === uploadId);
  if (!upload) return { status: 'failed', transactionCount: 0, newCount: 0, duplicateCount: 0, outOfRangeCount: 0 };

  if (parsed.length === 0) {
    upload.status = 'failed';
    upload.errorMessage = noTradesMessage;
    save(state);
    return { status: 'failed', transactionCount: 0, newCount: 0, duplicateCount: 0, outOfRangeCount: 0 };
  }

  // Trades before TRACKING_START_DATE are out of the tracker's scope
  // entirely — filtered out before dedup so they never take an "already
  // recorded" slot from a genuinely new in-range trade, and never get
  // stored at all (see isInTrackedRange's doc comment above).
  const inRange = parsed.filter((t) => isInTrackedRange(t.tradeDate.toISOString()));
  const outOfRangeCount = parsed.length - inRange.length;

  if (inRange.length === 0) {
    upload.status = 'failed';
    upload.errorMessage = `All ${outOfRangeCount} transaction(s) in this file are before ${TRACKING_START_DATE}, which is outside the Portfolio Tracker's tracked range.`;
    save(state);
    return { status: 'failed', transactionCount: parsed.length, newCount: 0, duplicateCount: 0, outOfRangeCount };
  }

  const existingExactKeys = new Set(
    state.transactions.filter((t) => isInTrackedRange(t.tradeDate)).map(exactTransactionKey)
  );

  let newCount = 0;
  let duplicateCount = 0;
  for (const t of inRange) {
    if (existingExactKeys.has(exactTransactionKey(t))) {
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
    // Not added to existingExactKeys: duplicates *within this same upload*
    // should still all be kept (see function doc comment above). A same-key
    // different-price row against something already on record is *not*
    // silently rejected or accepted here — see withDuplicateFlags, which
    // surfaces it for the user to resolve instead of guessing.
  }

  upload.status = newCount > 0 ? 'parsed' : 'duplicate';
  upload.transactionCount = newCount;
  if (newCount === 0) {
    upload.errorMessage = `All ${duplicateCount} transaction(s) in this file were already recorded.`;
  }
  save(state);
  return { status: upload.status, transactionCount: parsed.length, newCount, duplicateCount, outOfRangeCount };
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

// Full reset for when a parsing bug is found upstream and every statement
// needs re-uploading from scratch. Deliberately leaves position
// verifications untouched — they're ground truth captured independently
// from a broker screenshot, not something a bad transaction parse should
// invalidate, and re-uploaded statements can immediately be checked against
// them again without having to re-verify every ticker.
export function clearAllTransactions(): void {
  save({ nextUploadId: 1, nextTransactionId: 1, uploads: [], transactions: [] });
}

// Narrower escape hatch for a single ticker whose statement-derived
// transactions turned out wrong (e.g. still unverified and clearly off) —
// clears just that ticker's transactions so it can be re-uploaded without
// touching any other position. Its verification (if any) is left in place
// for the same reason as clearAllTransactions above.
export function clearTransactionsForTicker(ticker: string): void {
  const state = load();
  state.transactions = state.transactions.filter((t) => t.ticker !== ticker);
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
