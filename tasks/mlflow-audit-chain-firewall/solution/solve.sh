#!/usr/bin/env bash
set -euo pipefail
target="${APP_DIR:-/app}"
here="$(cd "$(dirname "$0")" && pwd)"
cp "$here/reference_main.go" "$target/cmd/mlflow-audit/main.go"
cp "$here/reference_audit.go" "$target/internal/audit/audit.go"
cd "$target"
gofmt -w cmd/mlflow-audit/main.go internal/audit/audit.go
go build -o bin/mlflow-audit ./cmd/mlflow-audit
