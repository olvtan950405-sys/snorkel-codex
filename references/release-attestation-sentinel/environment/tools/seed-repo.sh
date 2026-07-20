#!/usr/bin/env bash
# Builds the deterministic release repository that ReleaseSentinel reconciles badges against.
set -euo pipefail

REPO="${1:-/app/repo}"

export GIT_AUTHOR_NAME="Release Engineering"
export GIT_AUTHOR_EMAIL="release-eng@northwind.example"
export GIT_COMMITTER_NAME="Release Engineering"
export GIT_COMMITTER_EMAIL="release-eng@northwind.example"

rm -rf "$REPO"
mkdir -p "$REPO"
git -C "$REPO" init -q -b main

commit() {
    local date="$1"
    local message="$2"
    export GIT_AUTHOR_DATE="$date"
    export GIT_COMMITTER_DATE="$date"
    git -C "$REPO" add -A
    git -C "$REPO" commit -q -m "$message"
}

cat > "$REPO/README.md" <<'EOF'
# northwind-platform

Monorepo for the payments, orders and search services.  Release branches are cut from `main` and
tagged once the release candidate has been signed off.  Every tag has an entry in `CHANGELOG.md`
naming the branch it was cut from.
EOF

mkdir -p "$REPO/services"
echo "payments-api" > "$REPO/services/payments-api.txt"
echo "orders-api" > "$REPO/services/orders-api.txt"
echo "search-api" > "$REPO/services/search-api.txt"

cat > "$REPO/CHANGELOG.md" <<'EOF'
# Changelog

## v8.5.0 (release/8.5)

- search-api: incremental index rebuilds
- payments-api: settlement retries are idempotent

## v8.4.1 (hotfix/8.4.1)

- payments-api: fix double capture on retried authorisations

## v8.4.0 (release/8.4)

- orders-api: partial fulfilment
- payments-api: 3DS step-up flow

## v8.3.4 (release/8.3)

- search-api: relevance tuning for long-tail queries

## v8.2.1 (release/8.2)

- orders-api: correct tax rounding for split shipments
EOF

commit "2026-01-06T09:00:00+00:00" "Initial platform import"

cut_release() {
    local branch="$1"
    local tag="$2"
    local date="$3"
    local note="$4"

    git -C "$REPO" checkout -q main
    git -C "$REPO" checkout -q -b "$branch"
    echo "$note" > "$REPO/services/RELEASE_NOTES.txt"
    commit "$date" "Cut $tag on $branch"
    GIT_AUTHOR_DATE="$date" GIT_COMMITTER_DATE="$date" git -C "$REPO" tag "$tag"
}

cut_release "release/8.2" "v8.2.1" "2026-02-17T10:00:00+00:00" "8.2.1 maintenance release"
cut_release "release/8.3" "v8.3.4" "2026-03-24T10:00:00+00:00" "8.3.4 maintenance release"
cut_release "release/8.4" "v8.4.0" "2026-05-04T10:00:00+00:00" "8.4.0 feature release"
cut_release "hotfix/8.4.1" "v8.4.1" "2026-05-18T10:00:00+00:00" "8.4.1 hotfix"
cut_release "release/8.5" "v8.5.0" "2026-06-15T10:00:00+00:00" "8.5.0 feature release"

git -C "$REPO" checkout -q main
