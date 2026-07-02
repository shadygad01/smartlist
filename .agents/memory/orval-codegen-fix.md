---
name: Orval codegen duplicate exports fix
description: How to prevent TS2308 duplicate export errors after running orval codegen in this project.
---

Orval (zod client mode) regenerates `lib/api-zod/src/index.ts` with:
```
export * from "./generated/api";
export * from './generated/types';
```
Both modules export schemas with the same names (e.g. `RequestUploadUrlBody`), causing TS2308.

**Why:** Orval generates both Zod validators (`generated/api.ts`) and TypeScript interfaces (`generated/types/`) for the same schemas. Removing the `schemas` option from orval config still causes orval to write an index.ts that references the types dir.

**How to apply:** The fix is in `lib/api-spec/package.json` — the codegen script patches the index.ts immediately after orval runs:
```json
"codegen": "orval --config ./orval.config.ts && node -e \"require('fs').writeFileSync('../api-zod/src/index.ts', \\\"export * from './generated/api';\\\\n\\\")\" && pnpm -w run typecheck:libs"
```
Do NOT add `schemas` back to `lib/api-spec/orval.config.ts` zod output config — it makes it worse.
