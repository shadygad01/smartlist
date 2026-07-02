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

// Pattern: date  ticker  buy/sell  qty  price
// Thunder format examples:
//   15/01/2026  COMI  شراء  1000  45.50
//   2026-01-15  EKHW  Buy   500   12.30
//   15-01-2026  HRHO  بيع   200   8.75
const rowPattern =
  /(\d{1,2}[\/-]\d{1,2}[\/-]\d{2,4}|\d{4}[\/-]\d{1,2}[\/-]\d{1,2})\s+([A-Z]{2,6})\s+(شراء|بيع|buy|sell|BUY|SELL)\s+([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)/i;

// Also handle table rows with different ordering
const rowPattern2 =
  /([A-Z]{2,6})\s+(\d{1,2}[\/-]\d{1,2}[\/-]\d{2,4}|\d{4}[\/-]\d{1,2}[\/-]\d{1,2})\s+(شراء|بيع|buy|sell|BUY|SELL)\s+([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)/i;

export function parseThunderText(text: string): ParsedTransaction[] {
  const transactions: ParsedTransaction[] = [];
  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);

  for (const line of lines) {
    let m = rowPattern.exec(line);
    let dateStr: string, ticker: string, typeStr: string, qtyStr: string, priceStr: string;

    if (m) {
      [, dateStr, ticker, typeStr, qtyStr, priceStr] = m;
    } else {
      m = rowPattern2.exec(line);
      if (m) {
        [, ticker, dateStr, typeStr, qtyStr, priceStr] = m;
      } else {
        continue;
      }
    }

    const qty = parseFloat(qtyStr.replace(/,/g, ''));
    const price = parseFloat(priceStr.replace(/,/g, ''));
    if (!qty || !price) continue;

    const isBuy = /شراء|buy/i.test(typeStr);
    const tradeDate = parseDate(dateStr);
    if (!tradeDate) continue;

    transactions.push({
      ticker: ticker.toUpperCase(),
      transactionType: isBuy ? 'BUY' : 'SELL',
      quantity: qty,
      price,
      tradeDate,
    });
  }

  return transactions;
}
