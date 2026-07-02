---
name: pdf-parse esbuild externalize
description: How to use pdf-parse in the api-server which bundles with esbuild ESM format.
---

pdf-parse v2 ships an ESM entry point with no default export. esbuild fails with:
`No matching export in "pdf-parse/dist/pdf-parse/esm/index.js" for import "default"`

**Why:** The api-server uses esbuild with `format: "esm"`. pdf-parse's ESM build doesn't export a default function.

**How to apply:**
1. Add `"pdf-parse"` to the `external` array in `artifacts/api-server/build.mjs`.
2. In the route file, load it via createRequire instead of a static import:
```typescript
import { createRequire } from "node:module";
const _require = createRequire(import.meta.url);
const pdfParse = _require("pdf-parse") as (buf: Buffer) => Promise<{ text: string; numpages: number }>;
```
The esbuild banner already sets `globalThis.require = createRequire(import.meta.url)` but using it inline in the file is cleaner for TypeScript typing.
