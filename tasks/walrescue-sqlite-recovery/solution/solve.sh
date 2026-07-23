#!/usr/bin/env bash
set -euo pipefail
cd /app
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
install -m 0644 "$SCRIPT_DIR/reference_recover.go" /app/internal/recoverdb/recover.go
gofmt -w /app/internal/recoverdb/recover.go
go test ./...
go build -o /app/bin/walrescue ./cmd/walrescue
