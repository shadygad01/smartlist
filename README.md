# Smartlist — EGX Constitutional Scanner

Smartlist is an EGX market-scanning and research system that combines a Python production pipeline, SQLite-backed signal tracking, notification delivery, and a Vite/React dashboard built from a presentation snapshot.

## Production capabilities

The system supports a daily Cairo-time scan, intraday market monitoring, email and Telegram notifications, signal outcome tracking, research reports, and a static EGX Command Center dashboard. The production execution authority is `notifications/scan_orchestrator.py`; workflows should not call `main.py` directly.

## Local setup

Use Python 3.11 or newer and install the validated dependency set:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.lock.txt
```

For dependency upgrades, edit `requirements.txt`, validate the full test/build pipeline, and regenerate `requirements.lock.txt`. Do not install unreviewed package versions directly in production workflows.

## Run the production orchestrator

The orchestrator uses Cairo time and protects jobs with a SQLite execution lock:

```bash
python -m notifications.scan_orchestrator morning
python -m notifications.scan_orchestrator market
python -m notifications.scan_orchestrator dashboard
python -m notifications.scan_orchestrator dispatch
```

The legacy `scheduler.py` remains a compatibility entry point for the learning cycle, but delegates the scan to `notifications.scan_orchestrator` and uses `daily_tracker.run_all()` for outcome measurement.

## Environment variables

| Variable | Purpose |
|---|---|
| `EMAIL_USER` | SMTP sender account |
| `EMAIL_PASS` | SMTP password or app password |
| `REPORT_EMAIL_TO` | Report recipient; defaults to `EMAIL_USER` when omitted |
| `TELEGRAM_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Telegram destination |
| `SMTP_HOST` | Optional SMTP host override |
| `SMTP_PORT` | Optional SMTP port override |
| `SMTP_DEBUG` | Set to `1` only for local SMTP troubleshooting |
| `SAVE_EMAIL_ARTIFACTS` | Set to `1` only when a local HTML email artifact is explicitly required |

Credentials and recipients must be supplied through environment variables or CI secrets. They must not be hardcoded in source files.

## Dashboard development

The active frontend is `artifacts/egx-commandcenter`:

```bash
pnpm install --frozen-lockfile
pnpm --filter @workspace/egx-commandcenter run typecheck
pnpm --filter @workspace/egx-commandcenter run test:architecture
PORT=3000 BASE_PATH=/ pnpm --filter @workspace/egx-commandcenter run build
```

The build defaults to `PORT=3000` and `BASE_PATH=/` when run locally. CI may override these values for GitHub Pages deployment.

## Validation

Run the most relevant local checks before opening a pull request:

```bash
python3 -m compileall -q .
pytest -q tests/test_dashboard_architecture.py
pnpm --filter @workspace/egx-commandcenter run typecheck
PORT=3000 BASE_PATH=/ pnpm --filter @workspace/egx-commandcenter run build
```

The repository also contains broader audit scripts under `audit/` and integration tests under `tests/`. Production and research workflows are defined under `.github/workflows/`.

## Documentation map

The architecture and data contracts are documented in `PROJECT_MAP.md`, `SOURCE_OF_TRUTH.md`, `CONSTITUTION_VERSION.md`, and the files under `docs/`. Generated state is managed separately from source code according to the data-branch scripts under `ci/`.
