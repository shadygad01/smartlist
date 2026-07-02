---
name: Scanner data-branch persistence
description: Why CI runtime data artifacts live on a separate `data` branch and how the restore/save scripts keep the code branch (main) clean.
---

# Scanner data-branch persistence

CI-generated runtime state (SQLite DBs, per-ticker CSVs, JSON/HTML snapshots)
is persisted to a dedicated git branch named `data`, **never** to the code
branch (main). Two reusable scripts drive this:

- `ci/restore_data.sh` — run right after checkout, before the scanner. Fetches
  `data` and checks out the listed artifacts into the working tree. No-op (uses
  seed copies) if the branch does not exist yet.
- `ci/save_data.sh "<msg>"` — run where a job used to `git add/commit/push` to
  main. Builds the commit in an isolated git worktree, copies only the listed
  artifacts, and pushes to `data` with a reset-and-reapply retry loop (avoids
  binary rebase conflicts). Creates the branch as an orphan on first run.

The canonical artifact list is `ci/data_files.txt` (globs/dirs allowed); both
scripts read it, so add new persisted files there once, not per workflow.

**Why:** the scheduled scanner used to commit constantly-changing data straight
to main, so every human/agent code push diverged and hit binary merge conflicts
(notably `notification_delivery.db`). Splitting refs means code pushes and
scanner data pushes never touch the same branch.

**How to apply:**
- Jobs that WRITE state call `save_data.sh`; jobs that only READ state (e.g.
  `dashboard_refresh`, `watchdog`) still need `restore_data.sh` or they run on
  stale seed copies frozen on main.
- Fetch remote-tracking refs with an explicit refspec
  (`+refs/heads/data:refs/remotes/origin/data`) — `actions/checkout` may set a
  narrow refspec so a plain `git fetch origin data` won't update `origin/data`.
- The old data files remain tracked on main as a one-time seed/fallback; do not
  re-point any workflow's data commit back at main. Untracking those seeds is a
  safe follow-up only after the `data` branch is confirmed healthy.
