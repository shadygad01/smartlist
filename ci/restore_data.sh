#!/usr/bin/env bash
#
# Restore runtime data artifacts from the dedicated `data` branch into the
# current working tree, so a scanner run starts from the latest persisted
# state instead of the (frozen) seed copies on the code branch.
#
# Safe to run before the data branch exists: it simply keeps the seed copies
# that came with the checkout.
#
# Usage: bash ci/restore_data.sh
# Env:   DATA_BRANCH        (default: data)
#        DATA_FILES_LIST    (default: ci/data_files.txt)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_BRANCH="${DATA_BRANCH:-data}"
LIST_FILE="${DATA_FILES_LIST:-$HERE/data_files.txt}"

if [ ! -f "$LIST_FILE" ]; then
    echo "restore_data: list file '$LIST_FILE' not found; nothing to restore."
    exit 0
fi

git fetch origin --depth=1 "+refs/heads/$DATA_BRANCH:refs/remotes/origin/$DATA_BRANCH" >/dev/null 2>&1 || true

if ! git show-ref --verify --quiet "refs/remotes/origin/$DATA_BRANCH"; then
    echo "restore_data: no '$DATA_BRANCH' branch yet; using seed data from checkout."
    exit 0
fi

restored=0
while IFS= read -r pat || [ -n "$pat" ]; do
    case "$pat" in
        ''|\#*) continue ;;
    esac
    # Quote the pattern so git (not the shell) expands it against the data branch.
    if git checkout "origin/$DATA_BRANCH" -- "$pat" >/dev/null 2>&1; then
        restored=$((restored + 1))
    fi
done < "$LIST_FILE"

echo "restore_data: restored $restored artifact pattern(s) from origin/$DATA_BRANCH."
