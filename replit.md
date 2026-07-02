# EGX Constitutional Command Center

A dark-themed algorithmic trading dashboard for the Egyptian Stock Exchange (EGX) that displays constitutional buy signals, re-accumulation events, near-entry candidates, and portfolio analytics from a live JSON snapshot.

## Run & Operate

- `pnpm --filter @workspace/egx-commandcenter run dev` — run the dashboard (port 21744)
- `pnpm --filter @workspace/api-server run dev` — run the API server (port 8080)
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages

## Stack

- pnpm workspaces, Node.js 24, TypeScript 5.9
- Frontend: Vite + React + Tailwind v4 + wouter (routing)
- Data: fetches `/presentation_snapshot.json` every 60s (no backend API needed)
- Fonts: DM Sans (body) + JetBrains Mono (code/labels)
- Icons: lucide-react
- Toasts: sonner

## Where things live

- `artifacts/egx-commandcenter/` — main dashboard artifact
- `artifacts/egx-commandcenter/src/types/snapshot.ts` — canonical snapshot TypeScript types
- `artifacts/egx-commandcenter/src/providers/SnapshotProvider.tsx` — data fetching/refresh context
- `artifacts/egx-commandcenter/src/components/dashboard/` — all dashboard section components
- `artifacts/egx-commandcenter/src/pages/` — DashboardPage + ArchivePage
- `artifacts/egx-commandcenter/src/index.css` — EGX dark theme CSS variables + Tailwind v4
- `.migration-backup/frontend/` — original Next.js source (reference only)

## Architecture decisions

- **No API routes**: All data comes from `presentation_snapshot.json` served as a static file. The Python backend writes this file; the frontend only reads it.
- **Snapshot URL**: Configured via `VITE_SNAPSHOT_URL` env var; falls back to `/presentation_snapshot.json`.
- **Routing**: wouter with `WouterRouter base={import.meta.env.BASE_URL}` — two routes: `/` (dashboard) and `/archive` (signal archive).
- **Next.js → Vite migration**: Removed all `'use client'` directives, `next/link` → wouter `<Link>`, `next/font` → Google Fonts `<link>` tag in index.html, `next/image` → plain `<img>` (AppImage/AppLogo not used in migrated version — lucide icons used instead).
- **CSS**: Tailwind v4 (`@import "tailwindcss"`) with EGX-specific CSS variables in `:root` (dark theme only — `--background`, `--signal-buy`, `--signal-reaccum`, etc.)

## Product

- **Buy Signal Card**: Highlights tickers the constitutional engine marks as READY NOW or READY FOR RE-ACCUMULATION, with entry zone, current price, R² score, valuation, and behavior phase.
- **Near Entry Section**: Tickers approaching the constitutional entry threshold, ranked by proximity.
- **Re-Accumulation Events**: Active/closed re-accumulation events with expandable DNA + valuation panels.
- **Event Timeline**: Real-time event log (buy signals, near-entry alerts, scans, vol spikes).
- **Constitutional Timeline**: Full historical timeline of all FIRST_BUY and RE-ACCUM events.
- **Universe Snapshot**: Full ticker universe with status, price, distance, and R².
- **Stock DNA**: Per-ticker constitutional memory stats (avg return, best/worst, historical hits).
- **Valuation Engine**: Institutional fair-value table (weighted FV, bull/base/bear, analyst consensus).
- **Archive Page**: Filterable table of all re-accumulation events with KPI stats.

## Gotchas

- The dashboard shows "Loading snapshot…" until `presentation_snapshot.json` is placed in the public directory or `VITE_SNAPSHOT_URL` points to a live URL served by the Python backend.
- `vite.config.ts` has `server.fs.strict = false` to allow serving files outside the artifact root.
- All components use inline `style={}` props for brand-specific colors — do NOT replace with Tailwind color utilities, as the theme uses non-standard CSS variables.

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
