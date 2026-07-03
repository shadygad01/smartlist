import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'wouter';
import { Upload, FileText, Image, CheckCircle, XCircle, AlertTriangle, ArrowLeft, TrendingUp, Package, Calendar, DollarSign, ScanText, Trash2, RotateCcw } from 'lucide-react';
import DashboardHeader from '@/components/dashboard/DashboardHeader';
import { createWorker } from 'tesseract.js';
import { extractPdfText } from '@/lib/pdfText';
import { preprocessForOcr, cropHeaderBand } from '@/lib/imagePreprocess';
import {
  parseThunderText,
  looksLikeThunderDocument,
  looksLikePositionVerification,
  parsePositionVerification,
} from '@/lib/portfolioParser';
import {
  getUploads,
  getTransactions,
  recordUpload,
  completeUpload,
  deleteTransaction,
  clearAllTransactions,
  clearTransactionsForTicker,
  computePositions,
  buildPriceMapFromSnapshot,
  getPositionVerifications,
  recordPositionVerification,
  withDuplicateFlags,
  TRACKING_START_DATE,
  type StoredUpload as PortfolioUpload,
  type StoredTransaction as PortfolioTransaction,
  type PortfolioPosition,
} from '@/lib/portfolioStore';
import { useSnapshot } from '@/providers/SnapshotProvider';

// ─── Helpers ──────────────────────────────────────────────────────────────────

// Runs the header+body two-pass OCR (see cropHeaderBand/preprocessForOcr in
// imagePreprocess.ts) with a given language set and returns the combined text.
async function runOcr(
  languages: string[],
  headerBand: HTMLCanvasElement,
  bodyInput: HTMLCanvasElement,
  onProgress: (status: string) => void
): Promise<string> {
  const worker = await createWorker(languages, 1, {
    logger: (m) => {
      if (m.status === 'recognizing text') {
        onProgress(`OCR: ${Math.round((m.progress ?? 0) * 100)}%`);
      }
    },
  });
  const headerResult = await worker.recognize(headerBand);
  const bodyResult = await worker.recognize(bodyInput);
  await worker.terminate();
  return `${headerResult.data.text}\n${bodyResult.data.text}`;
}

async function sha256Hex(buffer: ArrayBuffer): Promise<string> {
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

function fmt(n: number, dec = 2) {
  return n.toLocaleString('en-US', { minimumFractionDigits: dec, maximumFractionDigits: dec });
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' });
}

// ─── Status badge ─────────────────────────────────────────────────────────────
function UploadStatusBadge({ status }: { status: PortfolioUpload['status'] }) {
  const map = {
    parsed: { color: '#10b981', icon: <CheckCircle size={12} />, label: 'Done' },
    duplicate: { color: '#f59e0b', icon: <AlertTriangle size={12} />, label: 'Duplicate' },
    failed: { color: '#ef4444', icon: <XCircle size={12} />, label: 'Failed' },
    pending: { color: '#6b7280', icon: null, label: 'Processing…' },
  };
  const s = map[status];
  return (
    <span
      className="inline-flex items-center gap-1 font-mono px-2 py-0.5 rounded"
      style={{ fontSize: '10px', color: s.color, backgroundColor: `${s.color}18`, border: `1px solid ${s.color}40` }}
    >
      {s.icon} {s.label}
    </span>
  );
}

// ─── Drop zone ────────────────────────────────────────────────────────────────
function DropZone({ onFiles }: { onFiles: (files: File[]) => void }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    const files = Array.from(e.dataTransfer.files).filter(
      (f) => f.type === 'application/pdf' || f.type.startsWith('image/')
    );
    if (files.length) onFiles(files);
  }, [onFiles]);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (files.length) onFiles(files);
    if (inputRef.current) inputRef.current.value = '';
  }, [onFiles]);

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => inputRef.current?.click()}
      className="cursor-pointer flex flex-col items-center justify-center gap-3 rounded-xl transition-all duration-150"
      style={{
        border: `2px dashed ${dragging ? '#10b981' : '#252645'}`,
        backgroundColor: dragging ? 'rgba(16,185,129,0.05)' : '#0e1120',
        padding: '40px 24px',
        minHeight: '160px',
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,image/*"
        multiple
        className="hidden"
        onChange={handleChange}
      />
      <Upload size={32} color={dragging ? '#10b981' : '#3b4565'} />
      <div className="text-center">
        <p className="font-mono" style={{ fontSize: '13px', color: '#c4c9df' }}>
          Drag a PDF or image here
        </p>
        <p className="font-mono mt-1" style={{ fontSize: '11px', color: '#4a5070' }}>
          or click to choose · Thunder Securities
        </p>
      </div>
      <div className="flex gap-3">
        <span className="flex items-center gap-1 font-mono" style={{ fontSize: '10px', color: '#6b7280' }}>
          <FileText size={11} /> PDF
        </span>
        <span className="flex items-center gap-1 font-mono" style={{ fontSize: '10px', color: '#6b7280' }}>
          <Image size={11} /> Image
        </span>
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function PortfolioPage() {
  const { snapshot } = useSnapshot();
  const [uploads, setUploads] = useState<PortfolioUpload[]>([]);
  const [transactions, setTransactions] = useState<PortfolioTransaction[]>([]);
  const [positions, setPositions] = useState<PortfolioPosition[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string>('');
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const [activeTab, setActiveTab] = useState<'positions' | 'transactions' | 'uploads'>('positions');

  const showToast = useCallback((msg: string, ok: boolean) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 4000);
  }, []);

  const loadData = useCallback(() => {
    setUploads(getUploads());
    const txs = getTransactions();
    setTransactions(txs);
    const priceMap = buildPriceMapFromSnapshot([
      ...(snapshot?.universe_snapshot ?? []),
      ...(snapshot?.portfolio_extra_prices ?? []),
    ]);
    const verifications = getPositionVerifications();
    setPositions(computePositions(txs, priceMap, verifications).positions);
  }, [snapshot]);

  useEffect(() => { loadData(); }, [loadData]);

  // Everything happens in the browser — no server round-trip. The file never
  // leaves the device; only the extracted text is parsed and the resulting
  // transactions are kept in localStorage (see src/lib/portfolioStore.ts).
  const handleFiles = useCallback(async (files: File[]) => {
    setUploading(true);
    for (const file of files) {
      try {
        const isImage = file.type.startsWith('image/');
        const buffer = await file.arrayBuffer();
        const hash = await sha256Hex(buffer);

        // No file-level duplicate check here on purpose: a user tracking many
        // stocks re-uploads updated screenshots of the same stock often (new
        // orders added since last time), and rejecting the whole file by hash
        // would block those. Dedup happens per-transaction instead, below.

        // 1. Extract text: OCR for images (Tesseract), pdfjs for PDFs
        let extractedText = '';
        if (isImage) {
          setUploadStatus('Reading image with OCR…');
          // Two passes: the header (ticker code + company name, next to the
          // back/bell/heart icons) gets silently dropped by full-page OCR —
          // isolating it recovers it. The body gets the white-background
          // threshold since Thndr's light-green status labels are otherwise
          // invisible to Tesseract's default binarization. See
          // imagePreprocess.ts for both.
          const headerBand = await cropHeaderBand(file);
          const bodyInput = await preprocessForOcr(file);

          // English-only first: loading the Arabic model alongside English
          // measurably degrades accuracy on English-language screenshots —
          // confirmed by running the exact same real screenshot through OCR
          // repeatedly: a fulfilled order's timestamp ("01:57PM") was
          // consistently misread as "74" only when both models were loaded
          // together, breaking that row's date match and silently dropping
          // it downstream (english-only read it correctly every time).
          // Arabic is still needed for Arabic-language broker apps, so it's
          // a fallback rather than removed outright — only retried when the
          // English-only pass doesn't look like a document we recognize.
          extractedText = await runOcr(['eng'], headerBand, bodyInput, setUploadStatus);
          if (!looksLikeThunderDocument(extractedText) && !looksLikePositionVerification(extractedText)) {
            setUploadStatus('Retrying with Arabic support…');
            extractedText = await runOcr(['ara', 'eng'], headerBand, bodyInput, setUploadStatus);
          }
        } else {
          setUploadStatus('Reading PDF…');
          extractedText = await extractPdfText(buffer);
        }

        if (!extractedText || extractedText.trim().length < 20) {
          showToast('No text could be read from the file — try another file.', false);
          continue;
        }

        // A "My position" screenshot from the broker app is a ground-truth
        // check, not a trade record — route it separately so it never gets
        // parsed for buy/sell rows (it has none) and never shows up as a
        // near-empty "0 transactions" upload. Checked before the statement
        // parser so it can never be mistaken for one.
        if (looksLikePositionVerification(extractedText)) {
          const verification = parsePositionVerification(extractedText);
          if (!verification) {
            showToast("Recognized a position screen but couldn't read the ticker/units — try a clearer screenshot.", false);
            continue;
          }
          recordPositionVerification(verification);
          showToast(`Verified ${verification.ticker}: ${verification.units} units confirmed from broker.`, true);
          continue;
        }

        const upload = recordUpload({ fileName: file.name, contentType: file.type, fileHash: hash });

        // 2. Parse transactions — dedup happens per-transaction (ticker+date+
        // side+qty+price) against everything already recorded, not just
        // against the whole file, so re-uploading an updated statement that
        // overlaps with a previous one only adds what's genuinely new.
        setUploadStatus('Analyzing transactions…');
        const { transactions: parsed, incompleteRowCount } = parseThunderText(extractedText);
        const noTradesMessage = looksLikeThunderDocument(extractedText)
          ? 'This looks like a valid Thndr statement, but it has no buy/sell trades in this period.'
          : "No transactions found in the file. Make sure it's a Thunder report.";
        const result = completeUpload(upload.id, parsed, noTradesMessage, getPositionVerifications());

        const rangeNote =
          result.outOfRangeCount > 0
            ? ` (${result.outOfRangeCount} before ${TRACKING_START_DATE}, outside the tracked range, skipped)`
            : '';
        // Surfaces a genuinely observed failure mode: an order row whose
        // action (Buy/Sell • N shares) was detected but whose price/date/
        // status couldn't be read — OCR quality varies between runs even on
        // the exact same screenshot, so this row was silently dropped rather
        // than never having existed. Without this note it looks identical to
        // "nothing more to add".
        const incompleteNote =
          incompleteRowCount > 0
            ? ` ⚠ ${incompleteRowCount} order row(s) were detected but couldn't be fully read (missing price/date/status) — try re-uploading a clearer or larger screenshot if a trade seems to be missing.`
            : '';

        let message: string;
        if (result.status === 'failed') {
          message =
            result.outOfRangeCount > 0 && result.outOfRangeCount === result.transactionCount
              ? `All ${result.outOfRangeCount} transaction(s) in this file are before ${TRACKING_START_DATE} — outside the Portfolio Tracker's tracked range.`
              : noTradesMessage;
        } else if (result.status === 'duplicate') {
          message = `All ${result.duplicateCount} transaction(s) in this file were already recorded — nothing new added.${rangeNote}${incompleteNote}`;
        } else if (result.duplicateCount > 0) {
          message = `Added ${result.newCount} new transaction(s) (${result.duplicateCount} already recorded, skipped).${rangeNote}${incompleteNote}`;
        } else {
          message = `Added ${result.newCount} new transaction(s).${rangeNote}${incompleteNote}`;
        }
        showToast(message, result.status !== 'failed' && incompleteRowCount === 0);
      } catch (e) {
        showToast(`Error: ${String(e)}`, false);
      }
    }
    setUploading(false);
    setUploadStatus('');
    loadData();
  }, [loadData, showToast]);

  // Escape hatch for a bad row (e.g. a parsing glitch from before a fix
  // landed) without wiping and re-uploading everything else.
  const handleDeleteTransaction = useCallback((id: number, ticker: string) => {
    if (!window.confirm(`Delete this ${ticker} transaction? This can't be undone.`)) return;
    deleteTransaction(id);
    loadData();
  }, [loadData]);

  // Full reset for when a parsing bug is found and everything needs
  // re-uploading. Verifications are deliberately untouched (see
  // clearAllTransactions's doc comment) so re-uploaded statements can still
  // be checked against them right away.
  const handleClearAll = useCallback(() => {
    if (transactions.length === 0) return;
    if (!window.confirm(`Clear all ${transactions.length} transaction(s) and ${uploads.length} uploaded document(s)? Verified positions are kept. This can't be undone.`)) return;
    clearAllTransactions();
    loadData();
  }, [loadData, transactions.length, uploads.length]);

  // Narrower reset for a single position whose statement-derived numbers
  // look wrong — clears just that ticker's transactions without touching
  // anything else, so it can be re-uploaded cleanly.
  const handleClearPosition = useCallback((ticker: string, count: number) => {
    if (!window.confirm(`Clear all ${count} ${ticker} transaction(s) so you can re-upload them? Its verification (if any) is kept. This can't be undone.`)) return;
    clearTransactionsForTicker(ticker);
    loadData();
  }, [loadData]);

  const totalCost = positions.reduce((s, p) => s + p.totalCost, 0);
  const totalQty = positions.reduce((s, p) => s + p.totalQuantity, 0);
  const pricedPositions = positions.filter((p) => p.unrealizedPnl != null);
  const totalUnrealizedPnl =
    pricedPositions.length > 0 ? pricedPositions.reduce((s, p) => s + (p.unrealizedPnl ?? 0), 0) : null;

  return (
    <div style={{ backgroundColor: 'var(--background)', minHeight: '100vh' }}>
      <DashboardHeader />

      <main className="px-4 md:px-6 xl:px-10 pb-10" style={{ paddingTop: '88px' }}>
        <div className="flex flex-col gap-4 max-w-[1680px] mx-auto">

          {/* Page title */}
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <TrendingUp size={20} color="#10b981" />
              <h1 className="font-mono font-bold" style={{ fontSize: '16px', color: '#e2e6f0', letterSpacing: '0.05em' }}>
                PORTFOLIO TRACKER
              </h1>
              <span
                className="font-mono px-2 py-0.5 rounded"
                style={{ fontSize: '10px', color: '#4a9fff', backgroundColor: 'rgba(74,159,255,0.1)', border: '1px solid rgba(74,159,255,0.25)' }}
              >
                2026+
              </span>
            </div>
            <Link
              href="/"
              className="flex items-center gap-1 font-mono transition-opacity hover:opacity-70"
              style={{ fontSize: '11px', color: '#6b7280' }}
            >
              <ArrowLeft size={12} /> Dashboard
            </Link>
          </div>

          {/* Summary KPIs */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {[
              { label: 'POSITIONS', value: positions.length, color: '#10b981', icon: <Package size={14} /> },
              { label: 'TOTAL COST', value: totalCost > 0 ? `${fmt(totalCost)} EGP` : '—', color: '#3b82f6', icon: <DollarSign size={14} /> },
              { label: 'TOTAL SHARES', value: totalQty > 0 ? fmt(totalQty, 0) : '—', color: '#f59e0b', icon: <TrendingUp size={14} /> },
              {
                label: 'UNREALIZED P&L',
                value: totalUnrealizedPnl != null ? `${totalUnrealizedPnl >= 0 ? '+' : ''}${fmt(totalUnrealizedPnl)} EGP` : '—',
                color: totalUnrealizedPnl == null ? '#6b7280' : totalUnrealizedPnl >= 0 ? '#10b981' : '#ef4444',
                icon: <TrendingUp size={14} />,
              },
              { label: 'UPLOADS', value: uploads.length, color: '#9c6fff', icon: <FileText size={14} /> },
            ].map((kpi) => (
              <div
                key={kpi.label}
                className="flex flex-col gap-1 p-3 rounded-lg"
                style={{ backgroundColor: '#181930', border: '1px solid #252645' }}
              >
                <div className="flex items-center gap-2" style={{ color: '#6b7280' }}>
                  {kpi.icon}
                  <span className="font-mono" style={{ fontSize: '9px', letterSpacing: '0.08em' }}>{kpi.label}</span>
                </div>
                <div className="font-mono font-bold" style={{ fontSize: '18px', color: kpi.color }}>
                  {kpi.value}
                </div>
              </div>
            ))}
          </div>

          {/* Upload zone */}
          <div className="rounded-xl p-4" style={{ backgroundColor: '#181930', border: '1px solid #252645' }}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Upload size={14} color="#9c6fff" />
                <span className="font-mono font-bold" style={{ fontSize: '11px', color: '#c4c9df', letterSpacing: '0.08em' }}>
                  Upload transaction statement
                </span>
              </div>
              {transactions.length > 0 && (
                <button
                  onClick={handleClearAll}
                  className="flex items-center gap-1 font-mono transition-opacity hover:opacity-70"
                  style={{ fontSize: '10px', color: '#ef4444' }}
                  title="Clear all transactions and uploaded documents (verified positions are kept) so you can re-upload from scratch"
                >
                  <RotateCcw size={11} /> Clear all
                </button>
              )}
            </div>
            {uploading ? (
              <div className="flex items-center justify-center py-10">
                <div className="flex flex-col items-center gap-2">
                  <div
                    className="animate-spin rounded-full"
                    style={{ width: 28, height: 28, border: '2px solid #252645', borderTopColor: '#10b981' }}
                  />
                  <div className="flex items-center gap-1.5">
                    <ScanText size={13} color="#10b981" />
                    <span className="font-mono" style={{ fontSize: '11px', color: '#10b981' }}>
                      {uploadStatus || 'Processing…'}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <DropZone onFiles={handleFiles} />
            )}
            <p className="font-mono mt-3" style={{ fontSize: '10px', color: '#4a5070' }}>
              Tip: also upload a screenshot of a stock's "My position" screen (Units / Average cost) —
              it's auto-detected and used to verify that stock's quantity, capping it if a statement ever computes more than the broker actually shows.
            </p>
          </div>

          {/* Tabs */}
          <div className="flex gap-1 p-1 rounded-lg" style={{ backgroundColor: '#0e1120', border: '1px solid #1a1e35' }}>
            {([
              ['positions', 'Current Positions'],
              ['transactions', 'Transactions'],
              ['uploads', 'Documents'],
            ] as const).map(([tab, label]) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className="flex-1 font-mono py-2 rounded-md transition-all duration-150"
                style={{
                  fontSize: '11px',
                  letterSpacing: '0.03em',
                  color: activeTab === tab ? '#e2e6f0' : '#4a5070',
                  backgroundColor: activeTab === tab ? '#252645' : 'transparent',
                  border: activeTab === tab ? '1px solid #353768' : '1px solid transparent',
                }}
              >
                {label}
                {tab === 'positions' && positions.length > 0 && (
                  <span className="ml-1" style={{ color: '#10b981' }}>({positions.length})</span>
                )}
                {tab === 'transactions' && transactions.length > 0 && (
                  <span className="ml-1" style={{ color: '#3b82f6' }}>({transactions.length})</span>
                )}
              </button>
            ))}
          </div>

          {/* Positions tab */}
          {activeTab === 'positions' && (
            <div className="rounded-xl overflow-hidden" style={{ border: '1px solid #252645' }}>
              {positions.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 gap-3">
                  <Package size={32} color="#252645" />
                  <p className="font-mono" style={{ fontSize: '12px', color: '#4a5070' }}>
                    No positions yet — upload a statement first
                  </p>
                </div>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr style={{ backgroundColor: '#0e1120', borderBottom: '1px solid #252645' }}>
                      {['TICKER', 'First Buy', 'Last Buy', 'Quantity', 'Avg Price', 'Total Cost', 'Current Price', 'Unrealized P&L', ''].map((h) => (
                        <th
                          key={h}
                          className="font-mono text-left px-4 py-2"
                          style={{ fontSize: '9px', color: '#4a5070', letterSpacing: '0.08em' }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {positions.map((pos, i) => (
                      <tr
                        key={pos.ticker}
                        style={{
                          backgroundColor: i % 2 === 0 ? '#181930' : '#141526',
                          borderBottom: '1px solid #1a1e35',
                        }}
                      >
                        <td className="px-4 py-3">
                          <span className="font-mono font-bold" style={{ fontSize: '13px', color: '#10b981' }}>
                            {pos.ticker}
                          </span>
                          {pos.duplicateOf && (
                            <div
                              className="flex items-center gap-1 mt-1 font-mono"
                              style={{ fontSize: '9px', color: '#ef4444' }}
                              title={`This row's label didn't resolve to a known ticker but looks like the same stock as ${pos.duplicateOf} — likely a duplicate from an unresolved company name in a statement upload.`}
                            >
                              <AlertTriangle size={10} /> possible duplicate of {pos.duplicateOf}
                            </div>
                          )}
                          {pos.verifiedUnits != null && !pos.quantityMismatch && !pos.quantityShortfall && (
                            <div
                              className="flex items-center gap-1 mt-1 font-mono"
                              style={{ fontSize: '9px', color: '#10b981' }}
                              title="Quantity matches a broker 'My position' screenshot exactly."
                            >
                              <CheckCircle size={10} /> verified
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 font-mono" style={{ fontSize: '11px', color: '#8b8fa8' }}>
                          {fmtDate(pos.firstBuyDate)}
                        </td>
                        <td className="px-4 py-3 font-mono" style={{ fontSize: '11px', color: '#8b8fa8' }}>
                          {fmtDate(pos.lastBuyDate)}
                        </td>
                        <td className="px-4 py-3 font-mono font-bold" style={{ fontSize: '13px', color: pos.quantityMismatch || pos.quantityShortfall ? '#ef4444' : '#c4c9df' }}>
                          {fmt(pos.totalQuantity, 0)}
                          {pos.quantityMismatch && (
                            <div
                              className="flex items-center gap-1 mt-1 font-mono font-normal"
                              style={{ fontSize: '9px', color: '#ef4444' }}
                              title={`Statement math computes ${fmt(pos.rawComputedQuantity, 0)} units, but the broker's own position screen confirms only ${fmt(pos.verifiedUnits ?? 0, 0)} — quantity capped to the verified number. Check your uploaded transactions for a duplicate or misparsed trade.`}
                            >
                              <AlertTriangle size={10} /> computed {fmt(pos.rawComputedQuantity, 0)}, capped
                            </div>
                          )}
                          {pos.quantityShortfall && (
                            <div
                              className="flex items-center gap-1 mt-1 font-mono font-normal"
                              style={{ fontSize: '9px', color: '#ef4444' }}
                              title={`Statement math computes only ${fmt(pos.rawComputedQuantity, 0)} units, but the broker's own position screen confirms ${fmt(pos.verifiedUnits ?? 0, 0)} — some transactions are likely missing. Re-check your uploaded Orders/statement screenshots for gaps (e.g. rows below the fold that weren't captured) and re-upload.`}
                            >
                              <AlertTriangle size={10} /> short {fmt((pos.verifiedUnits ?? 0) - pos.rawComputedQuantity, 0)} vs. broker
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 font-mono" style={{ fontSize: '12px', color: '#f59e0b' }}>
                          {fmt(pos.avgBuyPrice)} EGP
                        </td>
                        <td className="px-4 py-3 font-mono" style={{ fontSize: '12px', color: '#3b82f6' }}>
                          {fmt(pos.totalCost)} EGP
                        </td>
                        <td className="px-4 py-3 font-mono" style={{ fontSize: '12px', color: '#c4c9df' }}>
                          {pos.currentPrice != null ? `${fmt(pos.currentPrice)} EGP` : '—'}
                        </td>
                        <td className="px-4 py-3 font-mono" style={{ fontSize: '12px', color: pos.unrealizedPnl == null ? '#4a5070' : pos.unrealizedPnl >= 0 ? '#10b981' : '#ef4444' }}>
                          {pos.unrealizedPnl != null
                            ? `${pos.unrealizedPnl >= 0 ? '+' : ''}${fmt(pos.unrealizedPnl)} EGP (${pos.unrealizedPnlPct! >= 0 ? '+' : ''}${pos.unrealizedPnlPct!.toFixed(1)}%)`
                            : '—'}
                        </td>
                        <td className="px-4 py-3">
                          <button
                            onClick={() => handleClearPosition(pos.ticker, transactions.filter((t) => t.ticker === pos.ticker).length)}
                            className="transition-opacity hover:opacity-70"
                            title={`Clear ${pos.ticker}'s transactions so you can re-upload them (its verification, if any, is kept)`}
                          >
                            <RotateCcw size={13} color="#ef4444" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {/* Transactions tab */}
          {activeTab === 'transactions' && (
            <div className="rounded-xl overflow-hidden" style={{ border: '1px solid #252645' }}>
              {transactions.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 gap-3">
                  <Calendar size={32} color="#252645" />
                  <p className="font-mono" style={{ fontSize: '12px', color: '#4a5070' }}>
                    No transactions yet
                  </p>
                </div>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr style={{ backgroundColor: '#0e1120', borderBottom: '1px solid #252645' }}>
                      {['TICKER', 'Type', 'Date', 'Quantity', 'Price', 'Value', ''].map((h) => (
                        <th
                          key={h}
                          className="font-mono text-left px-4 py-2"
                          style={{ fontSize: '9px', color: '#4a5070', letterSpacing: '0.08em' }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {withDuplicateFlags(transactions).map((tx, i) => {
                      const qty = parseFloat(tx.quantity);
                      const price = parseFloat(tx.price);
                      const isBuy = tx.transactionType === 'BUY';
                      return (
                        <tr
                          key={tx.id}
                          style={{
                            backgroundColor: i % 2 === 0 ? '#181930' : '#141526',
                            borderBottom: '1px solid #1a1e35',
                          }}
                        >
                          <td className="px-4 py-2.5">
                            <span className="font-mono font-bold" style={{ fontSize: '12px', color: '#c4c9df' }}>
                              {tx.ticker}
                            </span>
                            {tx.possibleDuplicate && (
                              <div
                                className="flex items-center gap-1 mt-1 font-mono"
                                style={{ fontSize: '9px', color: '#ef4444' }}
                                title={`Same ticker/date/side/quantity as another transaction at a different price — likely the same real trade uploaded twice (once with commission folded into the price, once without). This is the ${isBuy ? 'lower' : 'higher'}-priced one, the side more likely to be the raw no-commission duplicate. Confirm it's a genuine second trade, or delete it.`}
                              >
                                <AlertTriangle size={10} /> possible duplicate
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-2.5">
                            <span
                              className="font-mono px-2 py-0.5 rounded"
                              style={{
                                fontSize: '10px',
                                color: isBuy ? '#10b981' : '#ef4444',
                                backgroundColor: isBuy ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                                border: `1px solid ${isBuy ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}`,
                              }}
                            >
                              {isBuy ? 'BUY' : 'SELL'}
                            </span>
                          </td>
                          <td className="px-4 py-2.5 font-mono" style={{ fontSize: '11px', color: '#6b7280' }}>
                            {fmtDate(tx.tradeDate)}
                          </td>
                          <td className="px-4 py-2.5 font-mono" style={{ fontSize: '12px', color: '#c4c9df' }}>
                            {fmt(qty, 0)}
                          </td>
                          <td className="px-4 py-2.5 font-mono" style={{ fontSize: '12px', color: '#f59e0b' }}>
                            {fmt(price)}
                          </td>
                          <td className="px-4 py-2.5 font-mono" style={{ fontSize: '12px', color: '#8b8fa8' }}>
                            {fmt(qty * price)}
                          </td>
                          <td className="px-4 py-2.5">
                            <button
                              onClick={() => handleDeleteTransaction(tx.id, tx.ticker)}
                              className="transition-opacity hover:opacity-70"
                              title="Delete this transaction"
                            >
                              <Trash2 size={13} color="#ef4444" />
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          )}

          {/* Uploads tab */}
          {activeTab === 'uploads' && (
            <div className="rounded-xl overflow-hidden" style={{ border: '1px solid #252645' }}>
              {uploads.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 gap-3">
                  <FileText size={32} color="#252645" />
                  <p className="font-mono" style={{ fontSize: '12px', color: '#4a5070' }}>
                    No documents uploaded
                  </p>
                </div>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr style={{ backgroundColor: '#0e1120', borderBottom: '1px solid #252645' }}>
                      {['File', 'Status', 'Transactions', 'Date'].map((h) => (
                        <th
                          key={h}
                          className="font-mono text-left px-4 py-2"
                          style={{ fontSize: '9px', color: '#4a5070', letterSpacing: '0.08em' }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {uploads.map((u, i) => (
                      <tr
                        key={u.id}
                        style={{
                          backgroundColor: i % 2 === 0 ? '#181930' : '#141526',
                          borderBottom: '1px solid #1a1e35',
                        }}
                      >
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            {u.fileName.toLowerCase().endsWith('.pdf') ? (
                              <FileText size={13} color="#9c6fff" />
                            ) : (
                              <Image size={13} color="#3b82f6" />
                            )}
                            <span className="font-mono" style={{ fontSize: '12px', color: '#c4c9df' }}>
                              {u.fileName}
                            </span>
                          </div>
                          {u.errorMessage && (
                            <p className="font-mono mt-0.5" style={{ fontSize: '10px', color: '#ef4444' }}>
                              {u.errorMessage}
                            </p>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <UploadStatusBadge status={u.status} />
                        </td>
                        <td className="px-4 py-3 font-mono font-bold" style={{ fontSize: '13px', color: '#10b981' }}>
                          {u.transactionCount ?? 0}
                        </td>
                        <td className="px-4 py-3 font-mono" style={{ fontSize: '11px', color: '#6b7280' }}>
                          {fmtDate(u.createdAt)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}

        </div>
      </main>

      {/* Toast */}
      {toast && (
        <div
          className="fixed bottom-6 left-1/2 -translate-x-1/2 flex items-center gap-2 px-4 py-3 rounded-xl font-mono z-50"
          style={{
            fontSize: '12px',
            color: toast.ok ? '#10b981' : '#ef4444',
            backgroundColor: '#181930',
            border: `1px solid ${toast.ok ? '#10b981' : '#ef4444'}50`,
            boxShadow: '0 4px 24px rgba(0,0,0,0.5)',
          }}
        >
          {toast.ok ? <CheckCircle size={14} /> : <XCircle size={14} />}
          {toast.msg}
        </div>
      )}
    </div>
  );
}
