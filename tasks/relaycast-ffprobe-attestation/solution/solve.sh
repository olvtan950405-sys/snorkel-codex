#!/usr/bin/env bash
set -euo pipefail
cp /solution/reference_relaycast.go /app/cmd/relaycast/main.go
cd /app
go build -o /app/bin/relaycast ./cmd/relaycast
