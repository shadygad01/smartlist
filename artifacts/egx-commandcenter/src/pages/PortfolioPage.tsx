import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'wouter';
import { Upload, FileText, Image, CheckCircle, XCircle, AlertTriangle, ArrowLeft, TrendingUp, Package, Calendar, DollarSign, ScanText } from 'lucide-react';
import DashboardHeader from '@/components/dashboard/DashboardHeader';
import { createWorker } from 'tesseract.js';
import { extractPdfText } from '@/lib/pdfText';
import { parseThunderText } from '@/lib/portfolioParser';
import {
  getUploads,
  getTransactions,
  findUploadByHash,
  recordUpload,
  completeUpload,
  failUpload,
  computePositions,
  type StoredUpload as PortfolioUpload,
  type StoredTransaction as PortfolioTransaction,
  type PortfolioPosition,
} from '@/lib/portfolioStore';

// ─── Helpers ──────────────────────────────────────────────────────────────────
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
    parsed: { color: '#10b981', icon: <CheckCircle size={12} />, label: 'تم' },
    duplicate: { color: '#f59e0b', icon: <AlertTriangle size={12} />, label: 'مكرر' },
    failed: { color: '#ef4444', icon: <XCircle size={12} />, label: 'فشل' },
    pending: { color: '#6b7280', icon: null, label: 'جاري…' },
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
          اسحب ملف PDF أو صورة هنا
        </p>
        <p className="font-mono mt-1" style={{ fontSize: '11px', color: '#4a5070' }}>
          أو اضغط للاختيار · Thunder Securities
        </p>
      </div>
      <div className="flex gap-3">
        <span className="flex items-center gap-1 font-mono" style={{ fontSize: '10px', color: '#6b7280' }}>
          <FileText size={11} /> PDF
        </span>
        <span className="flex items-center gap-1 font-mono" style={{ fontSize: '10px', color: '#6b7280' }}>
          <Image size={11} /> صورة
        </span>
      </div>
    </div>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────
export default function PortfolioPage() {
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
    setPositions(computePositions(txs).positions);
  }, []);

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

        const existing = findUploadByHash(hash);
        if (existing) {
          showToast(`ملف مكرر — تم رفعه من قبل (${existing.fileName})`, false);
          continue;
        }

        // 1. Extract text: OCR for images (Tesseract), pdfjs for PDFs
        let extractedText = '';
        if (isImage) {
          setUploadStatus('جاري قراءة الصورة بـ OCR…');
          const worker = await createWorker(['ara', 'eng'], 1, {
            logger: (m) => {
              if (m.status === 'recognizing text') {
                setUploadStatus(`OCR: ${Math.round((m.progress ?? 0) * 100)}%`);
              }
            },
          });
          const { data } = await worker.recognize(file);
          await worker.terminate();
          extractedText = data.text;
        } else {
          setUploadStatus('جاري قراءة الـ PDF…');
          extractedText = await extractPdfText(buffer);
        }

        const upload = recordUpload({ fileName: file.name, contentType: file.type, fileHash: hash });

        if (!extractedText || extractedText.trim().length < 20) {
          failUpload(upload.id, 'مفيش نص اتقرأ من الملف.');
          showToast('مفيش نص اتقرأ من الملف — حاول ملف تاني.', false);
          continue;
        }

        // 2. Parse transactions
        setUploadStatus('جاري تحليل الصفقات…');
        const parsed = parseThunderText(extractedText);
        const result = completeUpload(upload.id, parsed);

        showToast(
          result.status === 'parsed'
            ? `تم استخراج ${result.transactionCount} صفقة بنجاح`
            : 'مفيش صفقات اتقرأت من الملف. تأكد إنه تقرير Thunder.',
          result.status !== 'failed'
        );
      } catch (e) {
        showToast(`خطأ: ${String(e)}`, false);
      }
    }
    setUploading(false);
    setUploadStatus('');
    loadData();
  }, [loadData, showToast]);

  const totalCost = positions.reduce((s, p) => s + p.totalCost, 0);
  const totalQty = positions.reduce((s, p) => s + p.totalQuantity, 0);

  return (
    <div style={{ backgroundColor: 'var(--background)', minHeight: '100vh' }}>
      <DashboardHeader />

      <main className="px-4 md:px-6 xl:px-10 pb-10" style={{ paddingTop: '88px' }}>
        <div className="flex flex-col gap-4">

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
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {[
              { label: 'POSITIONS', value: positions.length, color: '#10b981', icon: <Package size={14} /> },
              { label: 'TOTAL COST', value: totalCost > 0 ? `${fmt(totalCost)} EGP` : '—', color: '#3b82f6', icon: <DollarSign size={14} /> },
              { label: 'TOTAL SHARES', value: totalQty > 0 ? fmt(totalQty, 0) : '—', color: '#f59e0b', icon: <TrendingUp size={14} /> },
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
            <div className="flex items-center gap-2 mb-3">
              <Upload size={14} color="#9c6fff" />
              <span className="font-mono font-bold" style={{ fontSize: '11px', color: '#c4c9df', letterSpacing: '0.08em' }}>
                رفع كشف معاملات
              </span>
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
                      {uploadStatus || 'جاري المعالجة…'}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <DropZone onFiles={handleFiles} />
            )}
          </div>

          {/* Tabs */}
          <div className="flex gap-1 p-1 rounded-lg" style={{ backgroundColor: '#0e1120', border: '1px solid #1a1e35' }}>
            {([
              ['positions', 'المراكز الحالية'],
              ['transactions', 'الصفقات'],
              ['uploads', 'المستندات'],
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
                    مفيش مراكز — ارفع كشف معاملات الأول
                  </p>
                </div>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr style={{ backgroundColor: '#0e1120', borderBottom: '1px solid #252645' }}>
                      {['TICKER', 'أول شراء', 'آخر شراء', 'الكمية', 'متوسط السعر', 'التكلفة الكلية'].map((h) => (
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
                        </td>
                        <td className="px-4 py-3 font-mono" style={{ fontSize: '11px', color: '#8b8fa8' }}>
                          {fmtDate(pos.firstBuyDate)}
                        </td>
                        <td className="px-4 py-3 font-mono" style={{ fontSize: '11px', color: '#8b8fa8' }}>
                          {fmtDate(pos.lastBuyDate)}
                        </td>
                        <td className="px-4 py-3 font-mono font-bold" style={{ fontSize: '13px', color: '#c4c9df' }}>
                          {fmt(pos.totalQuantity, 0)}
                        </td>
                        <td className="px-4 py-3 font-mono" style={{ fontSize: '12px', color: '#f59e0b' }}>
                          {fmt(pos.avgBuyPrice)} EGP
                        </td>
                        <td className="px-4 py-3 font-mono" style={{ fontSize: '12px', color: '#3b82f6' }}>
                          {fmt(pos.totalCost)} EGP
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
                    مفيش صفقات بعد
                  </p>
                </div>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr style={{ backgroundColor: '#0e1120', borderBottom: '1px solid #252645' }}>
                      {['TICKER', 'النوع', 'التاريخ', 'الكمية', 'السعر', 'القيمة'].map((h) => (
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
                    {transactions.map((tx, i) => {
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
                              {isBuy ? 'شراء' : 'بيع'}
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
                    مفيش مستندات مرفوعة
                  </p>
                </div>
              ) : (
                <table className="w-full">
                  <thead>
                    <tr style={{ backgroundColor: '#0e1120', borderBottom: '1px solid #252645' }}>
                      {['الملف', 'الحالة', 'الصفقات', 'التاريخ'].map((h) => (
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
