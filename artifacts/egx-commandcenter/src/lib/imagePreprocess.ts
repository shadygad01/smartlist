// Client-side image preprocessing before handing a screenshot to Tesseract.
//
// Tesseract's default binarization is luminance-based, which fails on light
// pastel text: Thndr's "Fulfilled"/"Cancelled" status labels are a light
// green (e.g. rgb(76,175,80)-ish) whose grayscale luminance is close enough
// to a white background that Tesseract's automatic page segmentation drops
// the text entirely rather than misreading it — confirmed by OCR runs where
// the status column is silently absent from the output even though every
// other column (including a low-contrast case) comes through.
//
// Thresholding on distance-from-white per channel (rather than converting to
// grayscale first) keeps any sufficiently saturated/dark text visible
// regardless of hue, at the cost of turning the image into stark black-on-
// white — which OCR handles far better anyway.
export async function preprocessForOcr(file: File): Promise<HTMLCanvasElement> {
  const bitmap = await createImageBitmap(file);
  const canvas = document.createElement('canvas');
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const ctx = canvas.getContext('2d');
  if (!ctx) return canvas;

  ctx.drawImage(bitmap, 0, 0);
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const data = imageData.data;

  const THRESHOLD = 40;
  for (let i = 0; i < data.length; i += 4) {
    const distFromWhite = 255 - Math.min(data[i], data[i + 1], data[i + 2]);
    const v = distFromWhite > THRESHOLD ? 0 : 255;
    data[i] = v;
    data[i + 1] = v;
    data[i + 2] = v;
  }
  ctx.putImageData(imageData, 0, 0);
  return canvas;
}

// ─── Row-isolated Orders-screen segmentation ────────────────────────────────
// The flat-text Orders parser (parseOrdersScreenText) pairs each Buy/Sell
// action with the nearest status label by position in the OCR'd text — but
// Tesseract doesn't reliably preserve top-to-bottom order for the screen's
// two-lines-per-row layout, so a status can land in the wrong row's pairing
// window (real observed failure: a Cancelled 25-share ORHD order counted as
// Fulfilled, inflating the position by exactly 25). Slicing the screenshot
// into one image per order row *before* OCR makes cross-row mispairing
// geometrically impossible: whatever text comes out of a slice belongs to
// that row, full stop.
//
// Geometry, validated against real Thndr screenshots (1179px-wide iPhone
// captures): the body is light-background with two text lines per order row
// (action+price, then date+status), ~36px apart, while consecutive rows are
// separated by ~120px + a hairline divider. That 3x contrast between
// within-row and between-row gaps is what groupRowBands keys on — no fixed
// pixel sizes, so it holds across resolutions.
export interface OrderRowSlice {
  // Thresholded black-on-white crop of one order row, ready for OCR.
  canvas: HTMLCanvasElement;
  // Status read from pixel *color* rather than OCR: Thndr renders Fulfilled
  // in saturated green and Cancelled/Rejected in saturated red, and reading
  // a color is far more robust than OCRing a small-font word (the exact
  // failure above came from a misread status word). null when neither color
  // is present in meaningful quantity (e.g. a Pending row, or a non-row
  // slice like the screen title) — the caller then falls back to the OCR'd
  // status word for that row.
  colorStatus: 'fulfilled' | 'cancelled' | null;
}

// Same distance-from-white measure as preprocessForOcr above.
const INK_THRESHOLD = 40;

export async function segmentOrderRows(file: File): Promise<OrderRowSlice[]> {
  const bitmap = await createImageBitmap(file);
  const src = document.createElement('canvas');
  src.width = bitmap.width;
  src.height = bitmap.height;
  const ctx = src.getContext('2d');
  if (!ctx) return [];
  ctx.drawImage(bitmap, 0, 0);
  const w = src.width;
  const h = src.height;
  const data = ctx.getImageData(0, 0, w, h).data;

  const minChannel = (x: number, y: number) => {
    const i = (y * w + x) * 4;
    return Math.min(data[i], data[i + 1], data[i + 2]);
  };

  // 1. Find where the light-background body starts: the app header above it
  // is dark. A screenshot with no light body at all (e.g. full dark mode,
  // which none of the observed captures use) yields no rows — the caller
  // falls back to the flat-text parser rather than failing the upload.
  let bodyStart = -1;
  const xSamples = Math.ceil(w / 8);
  for (let y = 0; y < h; y++) {
    let light = 0;
    for (let x = 0; x < w; x += 8) {
      if (minChannel(x, y) > 200) light++;
    }
    if (light / xSamples > 0.85) {
      bodyStart = y;
      break;
    }
  }
  if (bodyStart < 0) return [];

  // 2. Ink profile: which scanlines contain text. Sampled every 4px
  // horizontally; a line counts as text once ~24px worth of ink shows up,
  // which comfortably clears hairline row dividers and anti-aliasing noise.
  const isTextLine: boolean[] = new Array(h).fill(false);
  for (let y = bodyStart; y < h; y++) {
    let ink = 0;
    for (let x = 0; x < w; x += 4) {
      if (255 - minChannel(x, y) > INK_THRESHOLD) ink++;
      if (ink >= 6) break;
    }
    isTextLine[y] = ink >= 6;
  }

  // 3. Consecutive text scanlines form bands (one band ≈ one text line).
  // Bands under 6px tall are divider lines/noise, not text.
  const bands: Array<{ top: number; bottom: number }> = [];
  let bandStart = -1;
  for (let y = bodyStart; y <= h; y++) {
    const text = y < h && isTextLine[y];
    if (text && bandStart < 0) bandStart = y;
    else if (!text && bandStart >= 0) {
      if (y - bandStart >= 6) bands.push({ top: bandStart, bottom: y });
      bandStart = -1;
    }
  }
  if (bands.length === 0) return [];

  // 4. Group bands into order rows. Real screenshots show within-row gaps
  // (~36px between a row's two lines) and between-row gaps (~120px) with no
  // overlap, so a threshold anywhere between them works; 1.8x the smallest
  // gap, floored at 80% of the midpoint, lands safely inside that window
  // and degrades gracefully when a capture has only one row (all gaps
  // small → nothing splits).
  const groups: Array<Array<{ top: number; bottom: number }>> = [[bands[0]]];
  if (bands.length > 1) {
    const gaps = bands.slice(1).map((b, i) => b.top - bands[i].bottom);
    const minGap = Math.min(...gaps);
    const maxGap = Math.max(...gaps);
    const threshold = Math.max(minGap * 1.8, ((minGap + maxGap) / 2) * 0.8);
    for (let i = 0; i < gaps.length; i++) {
      if (gaps[i] > threshold) groups.push([]);
      groups[groups.length - 1].push(bands[i + 1]);
    }
  }

  // 5. One slice per group: thresholded crop for OCR + color-derived status.
  const slices: OrderRowSlice[] = [];
  for (const group of groups) {
    const top = Math.max(bodyStart, group[0].top - 10);
    const bottom = Math.min(h, group[group.length - 1].bottom + 10);
    if (bottom - top < 20) continue; // too short to be a real row

    // Status color scan, right 45% of the row where the status label sits.
    // Thresholds picked off real captures: Fulfilled green ≈ rgb(60,170,80),
    // Cancelled red ≈ rgb(240,70,60); black/gray body text triggers neither.
    // 30+ matching pixels required so a stray anti-aliased edge can't
    // decide a status (real labels measure in the hundreds).
    let green = 0;
    let red = 0;
    for (let y = top; y < bottom; y++) {
      for (let x = Math.floor(w * 0.55); x < w; x += 2) {
        const i = (y * w + x) * 4;
        const r = data[i];
        const g = data[i + 1];
        const b = data[i + 2];
        if (g > r + 30 && g > b + 30 && g > 100) green++;
        else if (r > g + 40 && r > b + 40 && r > 120) red++;
      }
    }
    const colorStatus = green > Math.max(red, 30) ? 'fulfilled' : red > Math.max(green, 30) ? 'cancelled' : null;

    const rowCanvas = document.createElement('canvas');
    rowCanvas.width = w;
    rowCanvas.height = bottom - top;
    const rowCtx = rowCanvas.getContext('2d');
    if (!rowCtx) continue;
    rowCtx.drawImage(src, 0, top, w, bottom - top, 0, 0, w, bottom - top);
    const rowImage = rowCtx.getImageData(0, 0, w, bottom - top);
    const rowData = rowImage.data;
    for (let i = 0; i < rowData.length; i += 4) {
      const distFromWhite = 255 - Math.min(rowData[i], rowData[i + 1], rowData[i + 2]);
      const v = distFromWhite > INK_THRESHOLD ? 0 : 255;
      rowData[i] = v;
      rowData[i + 1] = v;
      rowData[i + 2] = v;
    }
    rowCtx.putImageData(rowImage, 0, 0);

    slices.push({ canvas: rowCanvas, colorStatus });
  }

  return slices;
}

// The ticker code + company name in the Thndr app's header sits on the same
// visual row as a back arrow and bell/heart icons. Confirmed across multiple
// real screenshots: full-page OCR consistently drops that text (not
// misreads — drops), apparently confused by the icons, even though the same
// text OCRs correctly in isolation. Cropping to just that band (and
// excluding the icon column on the right) recovers it reliably. The header
// background is dark with light text in every sample seen, so this crop is
// left at native colors rather than run through the white-background
// threshold above.
export async function cropHeaderBand(file: File): Promise<HTMLCanvasElement> {
  const bitmap = await createImageBitmap(file);
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * 0.8);
  canvas.height = Math.round(bitmap.height * 0.3);
  const ctx = canvas.getContext('2d');
  if (!ctx) return canvas;
  ctx.drawImage(bitmap, 0, 0);
  return canvas;
}
