import { Router, type IRouter, type Request, type Response } from "express";
import { db } from "@workspace/db";
import {
  portfolioUploadsTable,
  portfolioTransactionsTable,
} from "@workspace/db";
import { eq, desc } from "drizzle-orm";
import { ObjectStorageService } from "../lib/objectStorage";
import { createRequire } from "node:module";

const _require = createRequire(import.meta.url);
const { PDFParse } = _require("pdf-parse") as {
  PDFParse: new (opts: { data: Buffer }) => { getText(): Promise<{ text: string }> };
};

const router: IRouter = Router();
const objectStorageService = new ObjectStorageService();

// Known EGX ticker symbols for companies that show up under their full name
// (rather than a ticker code) in Thndr's "Description" column, e.g.
// "Buy Eastern Co. (50@39.3800)". Matched after normalizing away punctuation
// and common corporate suffixes, so "Orascom construction Ltd." and
// "Orascom Construction PLC" both resolve to the same entry.
const COMPANY_TICKER_MAP: Record<string, string> = {
  EASTERN: "EAST",
  "ORIENTAL WEAVERS": "ORWE",
  "EFG HOLDING": "HRHO",
  "EFG HERMES": "HRHO",
  "ARABIAN CEMENT": "ARCC",
  "ORASCOM CONSTRUCTION": "ORAS",
  "CANAL SHIPPING AGENCIES": "CSAG",
  "TALAAT MOUSTAFA GROUP": "TMGH",
  "TALAAT MOUSTAFA": "TMGH",
};

function normalizeCompanyKey(name: string): string {
  return name
    .toUpperCase()
    .replace(/[.,]/g, "")
    .replace(/\b(LTD|CO|SAE|PLC|CORP|COMPANY)\b/g, "")
    .replace(/\s+/g, " ")
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

type ParsedTx = {
  ticker: string;
  transactionType: "BUY" | "SELL";
  quantity: number;
  price: number;
  tradeDate: Date;
};

// ─── Format 1: Thndr "Customer Account Statement" PDF ─────────────────────────
// Rows look like:
//   2/2/2026   Buy Eastern Co. (50@39.3800)   -1,974.47   8,333.15
//   19/2/2026  Sell EFG HOLDING (45@27.7000)   1,241.95   7,584.92
// i.e. date, then "Buy/Sell <company name> (<qty>@<price>)", then value and
// running balance (which we don't need — qty/price come from the parens).
// Non-trade rows (transfers, cash deposits) don't match and are skipped.
function parseStatementText(text: string): ParsedTx[] {
  const transactions: ParsedTx[] = [];

  // Match across the whole document rather than line-by-line: text extracted
  // from a PDF doesn't reliably put one transaction per line.
  const normalized = text.replace(/\s+/g, " ");
  const rowPattern =
    /(\d{1,2}[\/-]\d{1,2}[\/-]\d{2,4})\s+(Buy|Sell|شراء|بيع)\s+([^()]+?)\s*\(\s*([\d,]+(?:\.\d+)?)\s*@\s*([\d,]+(?:\.\d+)?)\s*\)/gi;

  for (const m of normalized.matchAll(rowPattern)) {
    const [, dateStr, typeStr, description, qtyStr, priceStr] = m;

    const qty = parseFloat(qtyStr.replace(/,/g, ""));
    const price = parseFloat(priceStr.replace(/,/g, ""));
    if (!qty || !price) continue;

    const tradeDate = parseDate(dateStr);
    if (!tradeDate) continue;

    const isBuy = /buy|شراء/i.test(typeStr);

    transactions.push({
      ticker: resolveTicker(description.trim()),
      transactionType: isBuy ? "BUY" : "SELL",
      quantity: qty,
      price,
      tradeDate,
    });
  }

  return transactions;
}

// ─── Format 2: Thndr app "Orders" screen (screenshot) ──────────────────────────
// A per-stock order history screen looks like (ticker/company shown once in
// the header, not per row):
//   ORAS
//   Orascom Construction PLC
//   ...
//   Buy • 3 shares          @ EGP 448.000
//   11 Feb 26 – 11:00AM      Fulfilled
//   Sell • 17 shares        @ EGP 253.128
//   20 Aug 24 – 10:07AM      Fulfilled
// Screenshots go through client-side OCR, which doesn't reliably preserve row
// order for a two-column layout like this — it may read row-by-row or
// column-by-column. So instead of one regex per row, each field (action+qty,
// price, date, status) is matched independently in document order and the
// per-row values are recombined by position. That works either way, because
// within a single column the OCR output is still top-to-bottom.
const MONTH_MAP: Record<string, number> = {
  jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6,
  jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12,
};

function parseShortDate(str: string): Date | null {
  // "11 Feb 26" / "20 Aug 24" -> 2026-02-11 / 2024-08-20
  const m = /^(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{2,4})$/.exec(str.trim());
  if (!m) return null;
  const day = parseInt(m[1], 10);
  const month = MONTH_MAP[m[2].slice(0, 3).toLowerCase()];
  if (!month) return null;
  let year = parseInt(m[3], 10);
  if (year < 100) year += 2000;
  return new Date(Date.UTC(year, month - 1, day));
}

const NON_TICKER_WORDS = new Set(["EGP", "PLC", "LTD", "SAE", "ALL", "USD", "GBP", "EUR"]);

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

const orderActionPattern = /(Buy|Sell|شراء|بيع)\s*[•·.]?\s*([\d,]+(?:\.\d+)?)\s*shares?/gi;
const orderPriceStrictPattern = /@\s*EGP\s*([\d,]+(?:\.\d+)?)/gi;
const orderPriceLenientPattern = /@?\s*EGP\s*([\d,]+(?:\.\d+)?)/gi;
// Allow up to a few stray characters between date and time instead of
// requiring a specific dash glyph, since OCR renders "–" inconsistently.
const orderDatePattern = /(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})[^0-9A-Za-z]{0,4}\d{1,2}:\d{2}\s*[AP]M/gi;
const orderStatusPattern = /\b(Fulf\w*|Pending|Cancel\w*|Rejected|Expired)\b/gi;

function parseOrdersScreenText(text: string): ParsedTx[] {
  const transactions: ParsedTx[] = [];
  const normalized = text.replace(/\s+/g, " ");
  const { section, strict } = ordersSection(normalized);

  const actions = [...section.matchAll(orderActionPattern)];
  if (actions.length === 0) return transactions;

  const ticker = resolveHeaderTicker(text);
  if (!ticker) return transactions;

  const prices = [...section.matchAll(strict ? orderPriceStrictPattern : orderPriceLenientPattern)];
  const dates = [...section.matchAll(orderDatePattern)];
  const statuses = [...section.matchAll(orderStatusPattern)];

  const n = Math.min(actions.length, prices.length, dates.length, statuses.length);
  for (let i = 0; i < n; i++) {
    if (!/^fulf/i.test(statuses[i][1])) continue; // skip pending/cancelled orders

    const qty = parseFloat(actions[i][2].replace(/,/g, ""));
    const price = parseFloat(prices[i][1].replace(/,/g, ""));
    if (!qty || !price) continue;

    const tradeDate = parseShortDate(dates[i][1]);
    if (!tradeDate) continue;

    const isBuy = /buy|شراء/i.test(actions[i][1]);

    transactions.push({
      ticker,
      transactionType: isBuy ? "BUY" : "SELL",
      quantity: qty,
      price,
      tradeDate,
    });
  }

  return transactions;
}

function parseThunderText(text: string): ParsedTx[] {
  const statementTx = parseStatementText(text);
  if (statementTx.length > 0) return statementTx;
  return parseOrdersScreenText(text);
}

function parseDate(str: string): Date | null {
  const clean = str.replace(/\//g, "-");
  // dd-mm-yyyy
  let m = /^(\d{1,2})-(\d{1,2})-(\d{4})$/.exec(clean);
  if (m) return new Date(`${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`);
  // yyyy-mm-dd
  m = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(clean);
  if (m) return new Date(`${m[1]}-${m[2].padStart(2, "0")}-${m[3].padStart(2, "0")}`);
  // dd-mm-yy
  m = /^(\d{1,2})-(\d{1,2})-(\d{2})$/.exec(clean);
  if (m) return new Date(`20${m[3]}-${m[2].padStart(2, "0")}-${m[1].padStart(2, "0")}`);
  return null;
}

// ─── GET /portfolio/uploads ────────────────────────────────────────────────────
router.get("/portfolio/uploads", async (req: Request, res: Response) => {
  try {
    const uploads = await db
      .select()
      .from(portfolioUploadsTable)
      .orderBy(desc(portfolioUploadsTable.createdAt));
    res.json(uploads);
  } catch (err) {
    req.log.error({ err }, "Error listing portfolio uploads");
    res.status(500).json({ error: "Failed to list uploads" });
  }
});

// ─── POST /portfolio/uploads ───────────────────────────────────────────────────
// Parse an uploaded file and extract transactions (deduplication via fileHash)
router.post("/portfolio/uploads", async (req: Request, res: Response) => {
  const { objectPath, fileName, contentType, fileHash, extractedText } = req.body ?? {};

  if (!objectPath || !fileName || !contentType || !fileHash) {
    res.status(400).json({ error: "objectPath, fileName, contentType, fileHash required" });
    return;
  }

  // ── Duplicate check ──
  const existing = await db
    .select()
    .from(portfolioUploadsTable)
    .where(eq(portfolioUploadsTable.fileHash, fileHash))
    .limit(1);

  if (existing.length > 0) {
    res.json({
      uploadId: existing[0].id,
      status: "duplicate",
      transactionCount: existing[0].transactionCount ?? 0,
      message: `ملف مكرر — تم رفعه من قبل (${existing[0].fileName})`,
    });
    return;
  }

  // ── Create upload record ──
  const [upload] = await db
    .insert(portfolioUploadsTable)
    .values({ objectPath, fileName, fileHash, contentType, status: "pending" })
    .returning();

  try {
    // ── Download file from object storage ──
    const objectFile = await objectStorageService.getObjectEntityFile(objectPath);
    const dlResponse = await objectStorageService.downloadObject(objectFile, 0);
    const buffer = Buffer.from(await dlResponse.arrayBuffer());

    // ── Extract text based on content type ──
    let rawText = "";
    const isPdf = contentType.includes("pdf") || fileName.toLowerCase().endsWith(".pdf");

    if (extractedText && typeof extractedText === "string" && extractedText.trim().length > 20) {
      // Client already ran OCR (Tesseract.js for images) — use it directly
      rawText = extractedText;
    } else if (isPdf) {
      const parser = new PDFParse({ data: buffer });
      const parsed = await parser.getText();
      rawText = parsed.text;
    } else {
      await db
        .update(portfolioUploadsTable)
        .set({ status: "failed", errorMessage: "No text extracted from image" })
        .where(eq(portfolioUploadsTable.id, upload.id));
      res.json({
        uploadId: upload.id,
        status: "failed",
        transactionCount: 0,
        message: "مفيش نص اتقرأ من الصورة — حاول ترفع PDF بدلاً منها.",
      });
      return;
    }

    // ── Parse transactions ──
    const parsed = parseThunderText(rawText);

    if (parsed.length === 0) {
      await db
        .update(portfolioUploadsTable)
        .set({ status: "failed", errorMessage: "No transactions found in document" })
        .where(eq(portfolioUploadsTable.id, upload.id));

      res.json({
        uploadId: upload.id,
        status: "failed",
        transactionCount: 0,
        message: "مفيش صفقات اتقرأت من الملف. تأكد إنه تقرير Thunder.",
      });
      return;
    }

    // ── Insert transactions ──
    await db.insert(portfolioTransactionsTable).values(
      parsed.map((t) => ({
        uploadId: upload.id,
        ticker: t.ticker,
        transactionType: t.transactionType,
        quantity: String(t.quantity),
        price: String(t.price),
        tradeDate: t.tradeDate,
      }))
    );

    await db
      .update(portfolioUploadsTable)
      .set({ status: "parsed", transactionCount: parsed.length, parsedAt: new Date() })
      .where(eq(portfolioUploadsTable.id, upload.id));

    res.json({
      uploadId: upload.id,
      status: "parsed",
      transactionCount: parsed.length,
      message: `تم استخراج ${parsed.length} صفقة بنجاح`,
    });
  } catch (err) {
    req.log.error({ err }, "Error parsing portfolio upload");
    await db
      .update(portfolioUploadsTable)
      .set({ status: "failed", errorMessage: String(err) })
      .where(eq(portfolioUploadsTable.id, upload.id));
    res.status(500).json({ error: "Failed to parse document" });
  }
});

// ─── GET /portfolio/transactions ───────────────────────────────────────────────
router.get("/portfolio/transactions", async (req: Request, res: Response) => {
  try {
    const txs = await db
      .select()
      .from(portfolioTransactionsTable)
      .orderBy(desc(portfolioTransactionsTable.tradeDate));
    res.json(txs);
  } catch (err) {
    req.log.error({ err }, "Error listing transactions");
    res.status(500).json({ error: "Failed to list transactions" });
  }
});

// ─── GET /portfolio/positions ──────────────────────────────────────────────────
router.get("/portfolio/positions", async (req: Request, res: Response) => {
  try {
    const rows = await db
      .select({
        ticker: portfolioTransactionsTable.ticker,
        transactionType: portfolioTransactionsTable.transactionType,
        quantity: portfolioTransactionsTable.quantity,
        price: portfolioTransactionsTable.price,
        tradeDate: portfolioTransactionsTable.tradeDate,
      })
      .from(portfolioTransactionsTable)
      .orderBy(portfolioTransactionsTable.tradeDate);

    // Build positions (FIFO)
    const posMap = new Map<string, {
      ticker: string;
      totalQuantity: number;
      totalCost: number;
      firstBuyDate: Date;
      lastBuyDate: Date;
    }>();

    for (const row of rows) {
      const qty = parseFloat(row.quantity);
      const price = parseFloat(row.price);
      const existing = posMap.get(row.ticker);

      if (row.transactionType === "BUY") {
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
        // Reduce cost proportionally
        if (existing.totalQuantity === 0) {
          posMap.delete(row.ticker);
        }
      }
    }

    const positions = Array.from(posMap.values())
      .filter((p) => p.totalQuantity > 0)
      .map((p) => ({
        ticker: p.ticker,
        totalQuantity: p.totalQuantity,
        avgBuyPrice: p.totalCost / p.totalQuantity,
        totalCost: p.totalCost,
        currentPrice: null as number | null,
        currentValue: null as number | null,
        unrealizedPnl: null as number | null,
        unrealizedPnlPct: null as number | null,
        firstBuyDate: p.firstBuyDate.toISOString(),
        lastBuyDate: p.lastBuyDate.toISOString(),
      }));

    const totalCost = positions.reduce((s, p) => s + p.totalCost, 0);

    res.json({ positions, totalCost, totalCurrentValue: null, totalUnrealizedPnl: null, totalUnrealizedPnlPct: null });
  } catch (err) {
    req.log.error({ err }, "Error getting positions");
    res.status(500).json({ error: "Failed to get positions" });
  }
});

// ─── GET /portfolio/pnl-history ────────────────────────────────────────────────
router.get("/portfolio/pnl-history", async (req: Request, res: Response) => {
  try {
    // Group transactions by date and compute cumulative cost basis
    const rows = await db
      .select()
      .from(portfolioTransactionsTable)
      .orderBy(portfolioTransactionsTable.tradeDate);

    if (rows.length === 0) {
      res.json([]);
      return;
    }

    // Build daily snapshots of cumulative invested capital
    const byDate = new Map<string, { invested: number }>();

    let cumulative = 0;
    for (const row of rows) {
      const dateKey = row.tradeDate.toISOString().slice(0, 10);
      const qty = parseFloat(row.quantity);
      const price = parseFloat(row.price);
      if (row.transactionType === "BUY") cumulative += qty * price;
      byDate.set(dateKey, { invested: cumulative });
    }

    const points = Array.from(byDate.entries()).map(([date, v]) => ({
      date,
      realizedPnl: 0, // Will be calculated when sell transactions are tracked
      unrealizedPnl: 0, // Requires current prices — enriched by frontend from snapshot
    }));

    res.json(points);
  } catch (err) {
    req.log.error({ err }, "Error getting P&L history");
    res.status(500).json({ error: "Failed to get P&L history" });
  }
});

export default router;
