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
- The `data` branch is created/updated by workflows running on **GitHub**
  (origin, against `secrets.GITHUB_TOKEN`), not from a Replit task environment —
  the isolated env has read-only access to origin and pushes to it hang/timeout.
- Before relying on (or removing seeds for) the data-branch mechanism, verify it
  is actually **deployed to origin/main on GitHub**, not just present locally:
  `git show origin/main:ci/save_data.sh` must exist. If GitHub's `main` still has
  the old "Commit updated DB" style steps (data committed straight to main) then
  the save_data.sh machinery never ran there and no `data` branch will appear no
  matter how many workflows you trigger. The Replit→GitHub sync/push of the
  data-branch code is the true prerequisite; seed removal is blocked until then.
- Fallback when the user's Replit↔GitHub Git-UI sync is broken (UNAUTHENTICATED)
  and no workflow can create the branch: the isolated env's `origin` remote points
  **directly at the user's GitHub repo** — `git fetch origin` works read-only, but
  push hangs. A healthy GitHub **connector** token (`listConnections('github')[0]
  .settings.access_token`) has full admin/push, so the `data` branch can be seeded
  via the GitHub **Git Data API**: read `main`'s recursive tree, reuse the existing
  blob SHAs for every path matching `ci/data_files.txt` (no re-upload of the 2.3MB
  DBs), then create tree → orphan commit (empty `parents`) → `refs/heads/data`.
  After this, `git fetch origin +refs/heads/data:...` and `restore_data.sh` work
  from the isolated env.
- Testing `restore_data.sh` locally re-stages the artifacts into the index
  (`git checkout origin/data -- <path>` writes index + worktree), which would undo
  the `git rm --cached` untracking. After verifying restore, re-run `git rm
  --cached` for the `ci/data_files.txt` patterns so the final index is clean; the
  new `.gitignore` block keeps a platform `git add -A` from re-tracking them.
