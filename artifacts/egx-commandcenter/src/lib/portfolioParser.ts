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
const rowPattern =
  /(\d{1,2}[\/-]\d{1,2}[\/-]\d{2,4})\s+(Buy|Sell|شراء|بيع)\s+([^()]+?)\s*\(\s*([\d,]+(?:\.\d+)?)\s*@\s*([\d,]+(?:\.\d+)?)\s*\)/gi;

export function parseThunderText(text: string): ParsedTransaction[] {
  const transactions: ParsedTransaction[] = [];
  // Match across the whole document rather than line-by-line: text extracted
  // from a PDF or via OCR doesn't reliably put one transaction per line.
  const normalized = text.replace(/\s+/g, ' ');

  for (const m of normalized.matchAll(rowPattern)) {
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
