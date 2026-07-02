#!/usr/bin/env bash
#
# Persist runtime data artifacts to the dedicated `data` branch.
#
# Why: the scanner runs on a schedule and used to commit generated data (SQLite
# DBs, CSVs, JSON/HTML snapshots) straight to the code branch (main). Because
# those files change on every run, they constantly collided with human/agent
# code pushes and produced binary merge conflicts. Writing them to a separate
# `data` branch keeps the code branch clean: code pushes and scanner data
# pushes never touch the same ref.
#
# The commit is built in an isolated git worktree so the current checkout
# (main, with code) is never disturbed. Only the files listed in
# ci/data_files.txt are copied over, so the data branch holds data only.
#
# Usage: bash ci/save_data.sh "commit message [skip ci]"
# Env:   DATA_BRANCH        (default: data)
#        DATA_FILES_LIST    (default: ci/data_files.txt)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_BRANCH="${DATA_BRANCH:-data}"
COMMIT_MSG="${1:-CI: data update [skip ci]}"
LIST_FILE="${DATA_FILES_LIST:-$HERE/data_files.txt}"

if [ ! -f "$LIST_FILE" ]; then
    echo "save_data: list file '$LIST_FILE' not found; nothing to save."
    exit 0
fi

git config user.email "github-actions[bot]@users.noreply.github.com"
git config user.name "github-actions[bot]"

WT="$(mktemp -d)"
cleanup() { git worktree remove --force "$WT" >/dev/null 2>&1 || rm -rf "$WT"; }
trap cleanup EXIT

# Establish a worktree that holds the current data branch (or a fresh orphan).
git fetch origin --depth=1 "+refs/heads/$DATA_BRANCH:refs/remotes/origin/$DATA_BRANCH" >/dev/null 2>&1 || true
if git show-ref --verify --quiet "refs/remotes/origin/$DATA_BRANCH"; then
    git worktree add --force "$WT" "origin/$DATA_BRANCH" >/dev/null 2>&1
    ( cd "$WT" && git checkout -B "$DATA_BRANCH" >/dev/null 2>&1 )
else
    echo "save_data: '$DATA_BRANCH' branch does not exist yet; creating it."
    git worktree add --force --detach "$WT" HEAD >/dev/null 2>&1
    ( cd "$WT" && git checkout --orphan "$DATA_BRANCH" >/dev/null 2>&1 \
        && git rm -rf . >/dev/null 2>&1 || true )
fi

# Copy every listed artifact from the current working tree into the worktree,
# preserving directory structure. Existing data-branch files not produced by
# this run are left untouched.
copy_files() {
    while IFS= read -r pat || [ -n "$pat" ]; do
        case "$pat" in
            ''|\#*) continue ;;
        esac
        for match in $pat; do
            [ -e "$match" ] || continue
            if [ -d "$match" ]; then
                mkdir -p "$WT/$match"
                cp -rf "$match/." "$WT/$match/" 2>/dev/null || true
            else
                mkdir -p "$WT/$(dirname "$match")"
                cp -f "$match" "$WT/$match" 2>/dev/null || true
            fi
        done
    done < "$LIST_FILE"
}

stage_and_commit() {
    ( cd "$WT" && git add -Af . \
        && ( git diff --staged --quiet || git commit -m "$COMMIT_MSG" >/dev/null ) )
}

copy_files
stage_and_commit

# Nothing to push if HEAD matches the remote data branch tip (no new commit).
if git show-ref --verify --quiet "refs/remotes/origin/$DATA_BRANCH" \
   && [ -z "$(cd "$WT" && git log "origin/$DATA_BRANCH"..HEAD --oneline 2>/dev/null)" ]; then
    echo "save_data: no data changes to persist."
    exit 0
fi

pushed=0
for attempt in 1 2 3 4 5; do
    if ( cd "$WT" && git push origin "HEAD:$DATA_BRANCH" ); then
        echo "save_data: pushed data update to '$DATA_BRANCH' (attempt $attempt)."
        pushed=1
        break
    fi
    echo "save_data: push rejected (attempt $attempt); syncing with remote data branch..."
    ( cd "$WT" && git fetch origin --depth=1 "+refs/heads/$DATA_BRANCH:refs/remotes/origin/$DATA_BRANCH" >/dev/null 2>&1 \
        && git reset --hard "origin/$DATA_BRANCH" >/dev/null 2>&1 ) || true
    copy_files
    stage_and_commit
    sleep $((attempt * 3))
done

if [ "$pushed" != 1 ]; then
    echo "save_data: WARNING — could not push data update after retries (non-fatal)."
fi
exit 0
