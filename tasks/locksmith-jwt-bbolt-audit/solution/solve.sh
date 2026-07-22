#!/usr/bin/env bash
set -euo pipefail
cd /app
cp /oracle/main.go cmd/locksmith-audit/main.go
go build -o /app/bin/locksmith-audit ./cmd/locksmith-audit
