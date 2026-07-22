#!/usr/bin/env bash
set -euo pipefail
cd /app
cp /oracle/auth.ts src/auth.ts
cp /oracle/analyze.ts src/analyze.ts
npm run build
cp dist/cli.js bin/refundguard
chmod +x bin/refundguard
