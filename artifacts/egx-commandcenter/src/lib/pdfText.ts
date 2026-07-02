// Client-side PDF text extraction using pdfjs-dist, so uploaded statements
// never need to leave the browser. Mirrors what pdf-parse did server-side.
import * as pdfjsLib from 'pdfjs-dist';
import pdfjsWorker from 'pdfjs-dist/build/pdf.worker.mjs?url';

pdfjsLib.GlobalWorkerOptions.workerSrc = pdfjsWorker;

export async function extractPdfText(buffer: ArrayBuffer): Promise<string> {
  const doc = await pdfjsLib.getDocument({ data: buffer }).promise;
  const pageTexts: string[] = [];
  for (let i = 1; i <= doc.numPages; i++) {
    const page = await doc.getPage(i);
    const content = await page.getTextContent();
    const text = content.items.map((item) => ('str' in item ? item.str : '')).join(' ');
    pageTexts.push(text);
  }
  return pageTexts.join('\n');
}
