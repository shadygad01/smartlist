// Thunder brokerage transaction-report parser — ported from
// artifacts/api-server/src/routes/portfolio.ts so it can run entirely in the
// browser (no server round-trip needed to parse a statement).

export interface ParsedTransaction {
  ticker: string;
  transactionType: 'BUY' | 'SELL';
  quantity: number;
  price: number;
  tradeDate: Date;
}

function parseDate(str: string): Date | null {
  const clean = str.replace(/\//g, '-');
  // dd-mm-yyyy
  let m = /^(\d{1,2})-(\d{1,2})-(\d{4})$/.exec(clean);
  if (m) return new Date(`${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`);
  // yyyy-mm-dd
  m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(clean);
  if (m) return new Date(`${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`);
  // dd-mm-yy
  m = /^(\d{1,2})-(\d{1,2})-(\d{2})$/.exec(clean);
  if (m) return new Date(`20${m[3]}-${m[2].padStart(2, '0')}-${m[1].padStart(2, '0')}`);
  return null;
}

// Known EGX ticker symbols for companies that show up under their full name
// (rather than a ticker code) in Thndr's "Description" column, e.g.
// "Buy Eastern Co. (50@39.3800)". Matched after normalizing away punctuation
// and common corporate suffixes, so "Orascom construction Ltd." and
// "Orascom Construction PLC" both resolve to the same entry.
const COMPANY_TICKER_MAP: Record<string, string> = {
  'EASTERN': 'EAST',
  'ORIENTAL WEAVERS': 'ORWE',
  'EFG HOLDING': 'HRHO',
  'EFG HERMES': 'HRHO',
  'ARABIAN CEMENT': 'ARCC',
  'ORASCOM CONSTRUCTION': 'ORAS',
  'CANAL SHIPPING AGENCIES': 'CSAG',
  'TALAAT MOUSTAFA GROUP': 'TMGH',
  'TALAAT MOUSTAFA': 'TMGH',
  'TMG HOLDING': 'TMGH',
  'EGYPTIAN INTERNATIONAL PHARMACEUTICALS': 'PHAR',
  'EGYPTIAN INTERNATIONAL PHARMACEUTICAL': 'PHAR',
  'COMMERCIAL INTERNATIONAL BANK': 'COMI',
  'MEDINET MASR HOUSING': 'MASR',
  'MADINET MASR': 'MASR',
  'DELTA SUGAR': 'SUGR',
  'ORASCOM DEVELOPMENT EGYPT': 'ORHD',
  'SIDI KERIR PETROCHEMICALS': 'SKPC',
  'ABU QIR FERTILIZERS': 'ABUK',
};

// Thndr statements also include non-stock instruments (its own savings/money
// market product, and internal transfer sweeps) that are not EGX-listed
// tickers and must never be tracked as stock positions — confirmed absent
// from the user's real Thndr "Stocks" list (they live under "Funds" instead).
const NON_STOCK_INSTRUMENTS = new Set(['THNDRSAVINGS', 'AZG']);

function titleCase(s: string): string {
  return s.replace(/\w\S*/g, (w) => w.charAt(0) + w.slice(1).toLowerCase());
}

// Canonical display name per ticker, derived from the first-declared alias
// in COMPANY_TICKER_MAP for that ticker — keeps the "one name per stock"
// rule enforced by a single source (this map) rather than duplicated.
const CANONICAL_NAMES: Record<string, string> = {};
for (const [name, ticker] of Object.entries(COMPANY_TICKER_MAP)) {
  if (!(ticker in CANONICAL_NAMES)) CANONICAL_NAMES[ticker] = titleCase(name);
}

export function canonicalNameForTicker(ticker: string): string {
  return CANONICAL_NAMES[ticker] ?? ticker;
}

export function normalizeCompanyKey(name: string): string {
  return name
    .toUpperCase()
    .replace(/[.,]/g, '')
    .replace(/\b(LTD|CO|SAE|PLC|CORP|COMPANY)\b/g, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function levenshtein(a: string, b: string): number {
  const dp: number[][] = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0));
  for (let i = 0; i <= a.length; i++) dp[i][0] = i;
  for (let j = 0; j <= b.length; j++) dp[0][j] = j;
  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      dp[i][j] =
        a[i - 1] === b[j - 1] ? dp[i - 1][j - 1] : 1 + Math.min(dp[i - 1][j - 1], dp[i - 1][j], dp[i][j - 1]);
    }
  }
  return dp[a.length][b.length];
}

// OCR sometimes garbles a letter or two inside an otherwise-recognizable
// company name (seen in practice: "INTERNATIONAL" -> "INTEMATIONAL",
// "ORIENTAL" -> "ORLENTAL"). Compares the leading slice of key (company
// names appear at the start of the description) against each known name,
// tolerant of a small number of character-level edits proportional to
// length, so a couple of misread letters don't produce a whole separate
// fallback "ticker" for a company that's actually already mapped.
export function fuzzyMatchTicker(key: string): string | null {
  for (const [name, ticker] of Object.entries(COMPANY_TICKER_MAP)) {
    const candidate = key.slice(0, name.length);
    if (candidate.length < name.length * 0.7) continue;
    const threshold = Math.max(2, Math.floor(name.length * 0.15));
    if (levenshtein(candidate, name) <= threshold) return ticker;
  }
  return null;
}

// Resolves a Description-column company name to a ticker symbol, falling
// back to the normalized company name itself when it isn't in the map above
// (better an unmapped-but-consistent label than a guessed, possibly wrong,
// ticker).
function resolveTicker(description: string): string {
  const key = normalizeCompanyKey(description);
  if (COMPANY_TICKER_MAP[key]) return COMPANY_TICKER_MAP[key];
  for (const [name, ticker] of Object.entries(COMPANY_TICKER_MAP)) {
    if (key.startsWith(name) || name.startsWith(key)) return ticker;
  }
  const fuzzy = fuzzyMatchTicker(key);
  if (fuzzy) return fuzzy;
  return key || description.toUpperCase();
}

// Thndr "Customer Account Statement" rows look like:
//   2/2/2026   Buy Eastern Co. (50@39.3800)   -1,974.47   8,333.15
//   19/2/2026  Sell EFG HOLDING (45@27.7000)   1,241.95   7,584.92
// i.e. date, then "Buy/Sell <company name> (<qty>@<price>)", then value and
// running balance (which we don't need — qty/price come from the parens).
// Non-trade rows (transfers, cash deposits, cash dividends) don't match and
// are skipped. The company name itself can contain its own parenthetical,
// e.g. "Commercial International Bank (Egypt)" or "...Pharmaceuticals
// (EIPICO)" — the description group allows (and skips past) parens instead
// of excluding them, so it keeps looking until it finds the one that's
// actually "<qty>@<price>". Bounded to 80 chars so a malformed row without
// a real qty@price group can't run on and swallow the next row's data.
// Image/screenshot uploads of a statement go through OCR, which sometimes
// misreads "(" as "{" — a real observed failure: the strict ")" requirement
// then fails to close the *real* qty@price group, so the match runs on
// across the row boundary and (worse than cosmetic) steals the next row's
// values while its own real transaction is silently never recorded. Both
// bracket flavors are accepted on either side to avoid that.
// Some rows spell out the currency inside the parens too, e.g.
// "Buy AZG (6@22.32101 EGP)" or "Buy thndrsavings (16415@1.21834 EGP)" —
// an optional "EGP" is allowed right before the closing bracket.
// The trailing group captures the row's "Value" column (the actual amount
// debited/credited), which is optional so old callers/tests without it still
// match — see below for why it's used instead of qty * printed price.
const statementRowPattern =
  /(\d{1,2}[\/-]\d{1,2}[\/-]\d{2,4})\s+(Buy|Sell|شراء|بيع)\s+(.{1,80}?)\s*[(\{\[]\s*([\d,]+(?:\.\d+)?)\s*@\s*([\d,]+(?:\.\d+)?)\s*(?:EGP\s*)?[)\}\]](?:\s*(-?[\d,]+(?:\.\d+)?))?/gi;

function parseStatementText(text: string): ParsedTransaction[] {
  const transactions: ParsedTransaction[] = [];
  // Match across the whole document rather than line-by-line: text extracted
  // from a PDF or via OCR doesn't reliably put one transaction per line.
  const normalized = text.replace(/\s+/g, ' ');

  for (const m of normalized.matchAll(statementRowPattern)) {
    const [, dateStr, typeStr, description, qtyStr, priceStr, valueStr] = m;

    if (NON_STOCK_INSTRUMENTS.has(normalizeCompanyKey(description))) continue;

    const qty = parseFloat(qtyStr.replace(/,/g, ''));
    let price = parseFloat(priceStr.replace(/,/g, ''));
    if (!qty || !price) continue;

    // The printed per-share price doesn't include brokerage commission, but
    // the actual amount debited/credited (the Value column) does — confirmed
    // against the real Thndr app's own cost/P&L figures, e.g. a statement row
    // "Buy Arabian Cement (42@47.4700) -1,999.23" costs 1,999.23 in Thndr,
    // not 42 * 47.47 = 1,993.74. Deriving an effective per-share price from
    // Value keeps quantity * price (used everywhere downstream) equal to
    // what was actually paid/received.
    if (valueStr) {
      const value = Math.abs(parseFloat(valueStr.replace(/,/g, '')));
      if (value > 0) price = value / qty;
    }

    const tradeDate = parseDate(dateStr);
    if (!tradeDate) continue;

    const isBuy = /buy|شراء/i.test(typeStr);

    transactions.push({
      ticker: resolveTicker(description.trim()),
      transactionType: isBuy ? 'BUY' : 'SELL',
      quantity: qty,
      price,
      tradeDate,
    });
  }

  return transactions;
}

// ─── Format 2: Thndr app "Orders" screen (screenshot) ──────────────────────
// A per-stock order history screen looks like (ticker/company shown once in
// the header, not per row):
//   ORAS
//   Orascom Construction PLC
//   ...
//   Buy • 3 shares          @ EGP 448.000
//   11 Feb 26 – 11:00AM      Fulfilled
//   Sell • 17 shares        @ EGP 253.128
//   20 Aug 24 – 10:07AM      Fulfilled
// Screenshots go through OCR (Tesseract), which doesn't reliably preserve
// row order for a two-column layout like this — it may read row-by-row or
// column-by-column. So instead of one regex per row, each field (action+qty,
// price, date, status) is matched independently in document order and the
// per-row values are recombined afterward (see parseOrdersScreenText).
const MONTH_MAP: Record<string, number> = {
  jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6,
  jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
};

// OCR at this font/resolution confuses a few characters when they appear in
// numbers: "O" for "0", and "T"/"I"/lowercase-"l" for "1" (most visibly when
// "11" renders as "Tl"). Safe to blanket-replace within a digit run we
// already know is numeric from context.
function normalizeDigits(s: string): string {
  return s.replace(/[Oo]/g, '0').replace(/[TIl]/g, '1');
}

// Thndr always renders prices with exactly 3 decimals (e.g. "76.500"), but
// OCR sometimes reads the decimal point as a comma. Whatever separator
// precedes the final 3 digits is the decimal point; an earlier comma (rare
// for share prices) is a thousands separator.
function parsePrice(raw: string): number {
  const m = /^([\d,]*\d)[.,](\d{3})$/.exec(raw.trim());
  if (m) return parseFloat(`${m[1].replace(/,/g, '')}.${m[2]}`);
  return parseFloat(raw.replace(/,/g, ''));
}

function parseShortDate(str: string): Date | null {
  // "11 Feb 26" / "20 Aug 24" -> 2026-02-11 / 2024-08-20
  const m = /^([\dOoTIl]{1,3})\s+([A-Za-z]{3,9})\s+([\dOo]{2,4})$/.exec(str.trim());
  if (!m) return null;
  const day = parseInt(normalizeDigits(m[1]), 10);
  const month = MONTH_MAP[m[2].slice(0, 3).toLowerCase()];
  if (!month) return null;
  let year = parseInt(normalizeDigits(m[3]), 10);
  if (year < 100) year += 2000;
  return new Date(Date.UTC(year, month - 1, day));
}

const NON_TICKER_WORDS = new Set(['EGP', 'PLC', 'LTD', 'SAE', 'ALL', 'USD', 'GBP', 'EUR']);

// The header shows the ticker code and, below it, the full company name.
// Prefer matching the company name against the known map (more OCR-robust
// than a 2-6 letter ticker code rendered in small text); fall back to the
// first plausible all-caps ticker-looking token.
function resolveHeaderTicker(text: string): string | null {
  const head = text.slice(0, 400);
  const key = normalizeCompanyKey(head);
  for (const [name, ticker] of Object.entries(COMPANY_TICKER_MAP)) {
    if (key.includes(name)) return ticker;
    // The app's own header truncates long company names with "…", so the
    // OCR'd text may only contain a prefix of the full name — match on
    // that prefix too rather than requiring the whole name.
    const prefixLen = Math.min(name.length, 15);
    if (prefixLen >= 8 && key.includes(name.slice(0, prefixLen))) return ticker;
  }
  const candidates = head.match(/\b[A-Z]{2,6}\b/g) ?? [];
  for (const c of candidates) {
    if (!NON_TICKER_WORDS.has(c)) return c;
  }
  return null;
}

const ALL_ORDERS_MARKER = /all\s*orders/i;

// OCR isn't reliable about symbols/separators (the "@" before a price, the
// dash between a date and a time). Once we're past the "All orders" heading,
// the only "EGP <number>" occurrences left are per-row prices — nothing else
// on that part of the screen mentions EGP — so it's safe to match "EGP
// <number>" without requiring "@" too. Before that heading (header fields
// like "Last trade price EGP 730.00") we don't have that guarantee, so stay
// strict and require "@" there.
function ordersSection(text: string): { section: string; strict: boolean } {
  const idx = text.search(ALL_ORDERS_MARKER);
  if (idx >= 0) return { section: text.slice(idx), strict: false };
  return { section: text, strict: true };
}

// Bullet between "Buy/Sell" and the quantity OCRs inconsistently (•, *, «,
// or dropped entirely) — accept up to two non-digit, non-space characters
// instead of a fixed set of glyphs. Digits must never be swallowed by this
// gap, so digits are explicitly excluded from the class.
const orderActionPattern = /(Buy|Sell|شراء|بيع)\s*[^\s\d]{0,2}\s*([\d,TIl]+(?:\.\d+)?)\s*shares?/gi;
const orderPriceStrictPattern = /@\s*EGP\s*([\d,]+(?:[.,]\d+)?)/gi;
const orderPriceLenientPattern = /@?\s*EGP\s*([\d,]+(?:[.,]\d+)?)/gi;
// Allow up to a few stray characters between date and time instead of
// requiring a specific dash glyph, since OCR renders "–" inconsistently.
const orderDatePattern = /([\dOoTIl]{1,3}\s+[A-Za-z]{3,9}\s+[\dOo]{2,4})[^0-9A-Za-z]{0,4}[\dOoTIl]{1,2}:\d{2}\s*[AP]M/gi;
const orderStatusPattern = /\b(Fulf\w*|Pending|Cancel\w*|Rejected|Expired)\b/gi;

export interface ThunderParseResult {
  transactions: ParsedTransaction[];
  // Count of order rows where an action (Buy/Sell • N shares) was detected
  // but its price/date/status couldn't be matched — meaning the row was
  // silently dropped rather than genuinely absent from the screenshot. OCR
  // quality varies run to run (confirmed: the exact same real screenshot
  // parsed cleanly in one run and lost a row's fields in another), so this
  // makes that failure visible to the user instead of a transaction quietly
  // vanishing with no indication anything went wrong.
  incompleteRowCount: number;
  // Orders-screen format only: how many "Fulfilled" status labels were found
  // anywhere in the raw OCR text, independent of whether each one could be
  // successfully paired to an action/price/date. A cross-check that doesn't
  // care *why* a row failed (missed pairing, failed qty/price/date
  // validation, or anything else) — if this is higher than
  // transactions.length, something visibly marked "Fulfilled" in the
  // screenshot didn't make it into the parsed result. 0 for the statement
  // format, which has no such labels.
  fulfilledStatusCount: number;
}

function parseOrdersScreenText(text: string): ThunderParseResult {
  const transactions: ParsedTransaction[] = [];
  let incompleteRowCount = 0;
  const normalized = text.replace(/\s+/g, ' ');
  const { section, strict } = ordersSection(normalized);

  const actions = [...section.matchAll(orderActionPattern)];
  if (actions.length === 0) return { transactions, incompleteRowCount, fulfilledStatusCount: 0 };

  const ticker = resolveHeaderTicker(text);
  if (!ticker || NON_STOCK_INSTRUMENTS.has(ticker.toUpperCase())) {
    return { transactions, incompleteRowCount, fulfilledStatusCount: 0 };
  }

  const prices = [...section.matchAll(strict ? orderPriceStrictPattern : orderPriceLenientPattern)];
  const dates = [...section.matchAll(orderDatePattern)];
  const statuses = [...section.matchAll(orderStatusPattern)];
  const fulfilledStatusCount = statuses.filter((s) => /^fulf/i.test(s[1])).length;

  // Pair each action with the nearest price/date/status that falls between
  // it and the next action, instead of a strict positional zip — an OCR miss
  // on a single row's field (a genuinely observed failure mode) then only
  // drops that one incomplete row instead of misaligning every row after it.
  for (let i = 0; i < actions.length; i++) {
    const start = actions[i].index ?? 0;
    const end = i + 1 < actions.length ? (actions[i + 1].index ?? Infinity) : Infinity;
    const priceMatch = prices.find((p) => (p.index ?? -1) >= start && (p.index ?? -1) < end);
    const dateMatch = dates.find((d) => (d.index ?? -1) >= start && (d.index ?? -1) < end);
    const statusMatch = statuses.find((s) => (s.index ?? -1) >= start && (s.index ?? -1) < end);
    if (!priceMatch || !dateMatch || !statusMatch) {
      incompleteRowCount += 1;
      continue;
    }
    if (!/^fulf/i.test(statusMatch[1])) continue; // skip pending/cancelled orders

    const qty = parseFloat(normalizeDigits(actions[i][2]).replace(/,/g, ''));
    const price = parsePrice(priceMatch[1]);
    if (!qty || !price) continue;

    const tradeDate = parseShortDate(dateMatch[1]);
    if (!tradeDate) continue;

    const isBuy = /buy|شراء/i.test(actions[i][1]);

    transactions.push({
      ticker,
      transactionType: isBuy ? 'BUY' : 'SELL',
      quantity: qty,
      price,
      tradeDate,
    });
  }

  return { transactions, incompleteRowCount, fulfilledStatusCount };
}

export function parseThunderText(text: string): ThunderParseResult {
  const statementTx = parseStatementText(text);
  if (statementTx.length > 0) return { transactions: statementTx, incompleteRowCount: 0, fulfilledStatusCount: 0 };
  return parseOrdersScreenText(text);
}

// A statement can legitimately be a real Thndr document with zero buy/sell
// trades in the period it covers (e.g. a month with only deposits, transfers,
// and bank fees). That's different from a file that isn't a Thndr document
// at all, so callers can show a less alarming message in that case.
export function looksLikeThunderDocument(text: string): boolean {
  return /customer account statement|thndr/i.test(text);
}

// ─── Format 3: Thndr app "My position" screen (ground-truth verification) ──
// A per-stock position summary screenshot, e.g.:
//   ORHD
//   Orascom Development Egypt
//   Last trade price   EGP 38.20
//   My current position
//   Units                74
//   Average cost          EGP 23.73
//   Purchase Value        EGP 1,756.02
//   Market value           2,826.80
// This is the broker's own record of what's actually held — used as a
// ground-truth check against whatever the parsed transaction statement
// computes, never the other way around. Detected independently of the
// statement/orders formats above so it's never mistaken for a trade record.
export interface PositionVerification {
  ticker: string;
  companyName: string;
  units: number;
  avgCost: number | null;
  capturedAt: string;
}

export function looksLikePositionVerification(text: string): boolean {
  return /my\s+current\s+position/i.test(text) && /units/i.test(text) && /average\s*cost/i.test(text);
}

// The four stat cards (Units, Average cost, Purchase Value, Market value)
// render as a 2-column grid in that fixed order. Tesseract doesn't reliably
// preserve a consistent scan order across a grid like this (same caveat as
// the Orders screen above) — it may read a card's label directly followed by
// its own value, or all four labels first and then all four values. Either
// way, the four *values* still surface in the same left-to-right,
// top-to-bottom order as their cells regardless of how the labels get
// grouped, so — instead of an earlier approach that searched near each
// individual label and could latch onto a neighboring cell's number (e.g.
// "Units Average cost 177 EGP 22.20" reading Units' own "177" as Average
// cost's value when the two labels sit adjacent) — this pulls every number
// after "Units" in document order and assigns them positionally: 1st is
// Units, 2nd is Average cost, and so on.
function numbersAfter(section: string, label: RegExp): string[] {
  const m = label.exec(section);
  if (!m) return [];
  const rest = section.slice(m.index + m[0].length);
  // Must start with a real digit (0-9) — unlike the date/price parsing
  // above, this scans through ordinary prose (other labels' text) looking
  // for numbers, and the O/T/I/l digit-noise substitutes are common letters
  // that would otherwise match *inside real words* (e.g. the "o" in "cost")
  // before ever reaching an actual value.
  const numPattern = /\d[\d,OoTIl]*(?:[.,]\d+)?/g;
  return [...rest.matchAll(numPattern)].map((mm) => mm[0]);
}

export function parsePositionVerification(text: string): PositionVerification | null {
  const normalized = text.replace(/\s+/g, ' ');
  const ticker = resolveHeaderTicker(text);
  if (!ticker) return null;

  // Scope to the position card itself, stopping before "Earned Cash
  // Dividends" (which has its own EGP-prefixed numbers that must never be
  // mistaken for Units/Average cost/etc.) when that section is present.
  const startIdx = normalized.search(/my\s+current\s+position/i);
  const section = startIdx >= 0 ? normalized.slice(startIdx) : normalized;
  const endIdx = section.search(/earned\s+cash\s+dividends/i);
  const scoped = endIdx >= 0 ? section.slice(0, endIdx) : section;

  const numbers = numbersAfter(scoped, /units/i);
  if (numbers.length === 0) return null;
  const units = parseFloat(normalizeDigits(numbers[0]).replace(/,/g, ''));
  if (!units) return null;

  const avgCost = numbers[1] != null ? parseFloat(normalizeDigits(numbers[1]).replace(/,/g, '')) : null;

  return {
    ticker,
    companyName: canonicalNameForTicker(ticker),
    units,
    avgCost,
    capturedAt: new Date().toISOString(),
  };
}
