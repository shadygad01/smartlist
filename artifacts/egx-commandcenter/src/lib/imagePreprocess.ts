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
