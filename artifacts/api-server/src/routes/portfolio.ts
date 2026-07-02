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
const pdfParse = _require("pdf-parse") as (buf: Buffer) => Promise<{ text: string; numpages: number }>;

const router: IRouter = Router();
const objectStorageService = new ObjectStorageService();

// ─── Thunder brokerage PDF/text parser ────────────────────────────────────────
// Handles text extracted from Thunder Securities transaction reports
function parseThunderText(text: string): Array<{
  ticker: string;
  transactionType: "BUY" | "SELL";
  quantity: number;
  price: number;
  tradeDate: Date;
}> {
  const transactions: Array<{
    ticker: string;
    transactionType: "BUY" | "SELL";
    quantity: number;
    price: number;
    tradeDate: Date;
  }> = [];

  const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);

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

    const qty = parseFloat(qtyStr.replace(/,/g, ""));
    const price = parseFloat(priceStr.replace(/,/g, ""));
    if (!qty || !price) continue;

    const isBuy = /شراء|buy/i.test(typeStr);
    const tradeDate = parseDate(dateStr);
    if (!tradeDate) continue;

    transactions.push({
      ticker: ticker.toUpperCase(),
      transactionType: isBuy ? "BUY" : "SELL",
      quantity: qty,
      price,
      tradeDate,
    });
  }

  return transactions;
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
  const { objectPath, fileName, contentType, fileHash } = req.body ?? {};

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

    if (isPdf) {
      const parsed = await pdfParse(buffer);
      rawText = parsed.text;
    } else {
      // For images: try to extract any embedded text, else use filename hint
      // Full AI vision parsing requires Gemini (enabled after phone verification)
      // For now, store the upload and return a pending status for images
      await db
        .update(portfolioUploadsTable)
        .set({ status: "failed", errorMessage: "Image parsing requires AI — enable Gemini integration first" })
        .where(eq(portfolioUploadsTable.id, upload.id));

      res.json({
        uploadId: upload.id,
        status: "failed",
        transactionCount: 0,
        message: "الصور محتاجة تفعيل Gemini AI — الـ PDF يشتغل عادي",
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
