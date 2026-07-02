---
name: EGX snapshot data flow
description: How the EGX CommandCenter gets its data — purely static JSON, no API.
---

The dashboard fetches `presentation_snapshot.json` from a URL configured via `VITE_SNAPSHOT_URL` env var (falls back to `/presentation_snapshot.json`). The Python backend writes this file; the React frontend only reads it every 60 seconds via SnapshotProvider.

**Why:** No Express/API routes are needed for this app. The Next.js original also used static JSON — there were no API route files in the migration backup.

**How to apply:** If someone asks to "add a backend" or "connect to the API", clarify that the data flow is: Python backend → writes JSON file → frontend fetches it. The API server artifact exists for other purposes.
