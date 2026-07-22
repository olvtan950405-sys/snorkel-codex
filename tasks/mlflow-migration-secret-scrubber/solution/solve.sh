#!/usr/bin/env bash
set -euo pipefail
TARGET_DIR="${APP_DIR:-/app}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp "$SCRIPT_DIR/reference_main.go" "$TARGET_DIR/cmd/mlflow-gateway/main.go"
cp "$SCRIPT_DIR/reference_scrubber.go" "$TARGET_DIR/internal/scrubber/scrubber.go"
cd "$TARGET_DIR"
gofmt -w cmd/mlflow-gateway/main.go internal/scrubber/scrubber.go
go build -o bin/mlflow-gateway ./cmd/mlflow-gateway
