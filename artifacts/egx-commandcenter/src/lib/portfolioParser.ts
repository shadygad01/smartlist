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
};

function normalizeCompanyKey(name: string): string {
  return name
    .toUpperCase()
    .replace(/[.,]/g, '')
    .replace(/\b(LTD|CO|SAE|PLC|CORP|COMPANY)\b/g, '')
    .replace(/\s+/g, ' ')
    .trim();
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
  return key || description.toUpperCase();
}

// Thndr "Customer Account Statement" rows look like:
//   2/2/2026   Buy Eastern Co. (50@39.3800)   -1,974.47   8,333.15
//   19/2/2026  Sell EFG HOLDING (45@27.7000)   1,241.95   7,584.92
// i.e. date, then "Buy/Sell <company name> (<qty>@<price>)", then value and
// running balance (which we don't need — qty/price come from the parens).
// Non-trade rows (transfers, cash deposits) don't match and are skipped.
const statementRowPattern =
  /(\d{1,2}[\/-]\d{1,2}[\/-]\d{2,4})\s+(Buy|Sell|شراء|بيع)\s+([^()]+?)\s*\(\s*([\d,]+(?:\.\d+)?)\s*@\s*([\d,]+(?:\.\d+)?)\s*\)/gi;

function parseStatementText(text: string): ParsedTransaction[] {
  const transactions: ParsedTransaction[] = [];
  // Match across the whole document rather than line-by-line: text extracted
  // from a PDF or via OCR doesn't reliably put one transaction per line.
  const normalized = text.replace(/\s+/g, ' ');

  for (const m of normalized.matchAll(statementRowPattern)) {
    const [, dateStr, typeStr, description, qtyStr, priceStr] = m;

    const qty = parseFloat(qtyStr.replace(/,/g, ''));
    const price = parseFloat(priceStr.replace(/,/g, ''));
    if (!qty || !price) continue;

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

function parseOrdersScreenText(text: string): ParsedTransaction[] {
  const transactions: ParsedTransaction[] = [];
  const normalized = text.replace(/\s+/g, ' ');
  const { section, strict } = ordersSection(normalized);

  const actions = [...section.matchAll(orderActionPattern)];
  if (actions.length === 0) return transactions;

  const ticker = resolveHeaderTicker(text);
  if (!ticker) return transactions;

  const prices = [...section.matchAll(strict ? orderPriceStrictPattern : orderPriceLenientPattern)];
  const dates = [...section.matchAll(orderDatePattern)];
  const statuses = [...section.matchAll(orderStatusPattern)];

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
    if (!priceMatch || !dateMatch || !statusMatch) continue;
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

  return transactions;
}

export function parseThunderText(text: string): ParsedTransaction[] {
  const statementTx = parseStatementText(text);
  if (statementTx.length > 0) return statementTx;
  return parseOrdersScreenText(text);
}
