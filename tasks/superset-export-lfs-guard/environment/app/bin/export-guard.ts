#!/usr/bin/env node
// Broken during the migration: this implementation trusts mutable configuration
// and export-supplied hashes. Rebuild the gate according to docs/contracts.md.
import { readFileSync } from "node:fs";

const pos = process.argv.indexOf("--export");
if (pos < 0 || !process.argv[pos + 1]) {
  console.log('{"reasons":["INVALID_EXPORT"],"status":"rejected"}');
  process.exit(1);
}
const value = JSON.parse(readFileSync(process.argv[pos + 1], "utf8"));
console.log(JSON.stringify({charts: value.charts.length, dashboardId: value.dashboardId,
  policyCommit: "FOLLOW_BRANCH", status: "approved"}));
