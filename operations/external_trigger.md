# External Trigger Configuration
## Constitutional High Availability Scheduler

GitHub Actions cron has known reliability issues (~5–15% miss rate).
These external schedulers fire a `repository_dispatch` to GitHub when the
primary cron is late, ensuring exactly-once delivery via the morning guard
and scan_execution lock.

---

## 1 — Repository Dispatch Endpoint

```
POST https://api.github.com/repos/shadygad01/smartlist/dispatches
Authorization: Bearer <GITHUB_PAT>
Content-Type: application/json

{
  "event_type": "<event_type>",
  "client_payload": {
    "event_type": "<event_type>",
    "triggered_by": "external_scheduler"
  }
}
```

**Supported `event_type` values:**

| event_type          | Description                                      |
|---------------------|--------------------------------------------------|
| `morning_report`    | Morning brief email + Telegram (07:30 Cairo)     |
| `market_scan`       | Intra-day signal scan (10:00–14:30 Cairo)        |
| `dashboard_refresh` | Rebuild presentation snapshot + dashboard        |
| `operations_check`  | Run OperationsMonitor startup check only         |
| `ha_trigger`        | Generic HA — dispatches based on current time    |

**Required GitHub PAT scopes:** `repo` (for repository_dispatch)

---

## 2 — Google Apps Script (PRIMARY — every 5 minutes)

**This is the production scheduler.** GitHub Actions cron is BACKUP ONLY.

Create a new Apps Script project at https://script.google.com

```javascript
const GITHUB_TOKEN = PropertiesService.getScriptProperties().getProperty('GITHUB_PAT');
const REPO         = 'shadygad01/smartlist';
const API_URL      = `https://api.github.com/repos/${REPO}/dispatches`;

function dispatchEvent(eventType) {
  const payload = {
    event_type: eventType,
    client_payload: { event_type: eventType, triggered_by: 'google_apps_script' }
  };
  const options = {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: `Bearer ${GITHUB_TOKEN}` },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
  };
  const resp = UrlFetchApp.fetch(API_URL, options);
  Logger.log(`${eventType} → ${resp.getResponseCode()}`);
}

// ── PRIMARY: every-5-min tick (ha_trigger routes by Cairo time) ──────────
// ha_trigger → external_dispatch.yml → dispatch_from_env()
// dispatch_from_env routes: hour=7 → morning_report; 10≤hour≤14 → market_scan
function tick() { dispatchEvent('ha_trigger'); }
```

**Setup steps:**
1. Open https://script.google.com → New project
2. Paste the script above
3. Project Settings → Script Properties → Add `GITHUB_PAT` = your token
4. Project Settings → Time zone: set to `Africa/Cairo`
5. Triggers (⏰ icon) → Add trigger:

| Function | Event source | Time-based trigger | Schedule |
|----------|-------------|-------------------|---------|
| `tick`   | Time-driven | Minutes timer     | Every 5 minutes |

**That's it — one trigger, fires every 5 minutes 24/7.**
- At 07:xx Cairo → fires morning_report (morning guard ensures exactly-once)
- 10:00–14:30 Cairo → fires market_scan (lock ensures exactly-once)
- Outside windows → dispatch_from_env returns immediately without action
- All deduplication handled by ScanOrchestrator Python-level lock

---

## 3 — cron-job.org (Backup)

Register at https://cron-job.org → Create cronjob:

**URL:** `https://api.github.com/repos/shadygad01/smartlist/dispatches`
**Method:** POST
**Headers:**
```
Authorization: Bearer <GITHUB_PAT>
Content-Type: application/json
Accept: application/vnd.github.v3+json
```

**Schedule and body for each job:**

### Morning Report (07:32 Cairo = 05:32 UTC, Mon–Fri)
```
Cron: 32 5 * * 1-5
Body: {"event_type":"morning_report","client_payload":{"event_type":"morning_report","triggered_by":"cron-job.org"}}
```

### Market Scan — every 5 min during market hours (08:00-12:30 UTC = 10:00-14:30 Cairo)
```
Cron: */5 8-12 * * 0-4
Body: {"event_type":"ha_trigger","client_payload":{"event_type":"ha_trigger","triggered_by":"cron-job.org"}}
```
Note: ha_trigger routes to dispatch_from_env() which only runs market_scan during 10:00-14:30 Cairo.
Outside those hours the dispatcher returns immediately — no duplicate scans.

### Dashboard Refresh (15:05 Cairo = 13:05 UTC)
```
Cron: 5 13 * * 0-4
Body: {"event_type":"dashboard_refresh","client_payload":{"event_type":"dashboard_refresh","triggered_by":"cron-job.org"}}
```

### Operations Check (every 2 hours, 06:00–22:00 UTC)
```
Cron: 0 6,8,10,12,14,16,18,20,22 * * *
Body: {"event_type":"operations_check","client_payload":{"event_type":"operations_check","triggered_by":"cron-job.org"}}
```

---

## 4 — How exactly-once is guaranteed

All external triggers route through `ScanOrchestrator` → same lock table:

```
External Scheduler (Google/cron-job.org)
        │
        ▼
GitHub repository_dispatch
        │
        ▼
.github/workflows/external_dispatch.yml
        │
        ▼
ScanOrchestrator.run_morning_report()
        │
        ├── morning_guard.is_morning_sent() ── already sent? → EXIT
        ├── scan_execution INSERT lock ──────── already running? → EXIT
        ├── daily_scan() ───────────────────── runs exactly once
        └── lock released → COMPLETED
```

Even if GitHub Actions cron AND Google Apps Script AND cron-job.org all
fire at the same time, only one will acquire the lock. The others exit
immediately without sending duplicate notifications.

---

## 5 — Health check endpoint

`operations/public_status.json` (committed to main after every run) exposes:
```json
{
  "system_health": "HEALTHY",
  "last_scan": "2026-06-22T10:12:56+02:00",
  "last_email": "2026-06-22T10:12:46+02:00",
  "last_dashboard": "2026-06-22T10:12:56+02:00",
  "last_telegram": "2026-06-22T10:12:46+02:00",
  "build_hash": "065c0375d2c354e3",
  "commit_sha": "ba3bafc"
}
```

External monitors can poll the raw GitHub URL:
```
https://raw.githubusercontent.com/shadygad01/smartlist/main/operations/public_status.json
```

If `system_health != "HEALTHY"` or `last_scan` is stale → fire `operations_check`.
