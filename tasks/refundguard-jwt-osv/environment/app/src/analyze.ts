import fs from "node:fs";

export async function analyze(ledger: string, lockfile: string, database: string, report: string): Promise<void> {
  // TODO: import the CSV into SQLite, query suspicious groups, query OSV, and
  // atomically emit the report required by docs/refund-security-contract.md.
  fs.writeFileSync(report, JSON.stringify({ledger_rows: 0, suspicious: [], vulnerabilities: []}) + "\n");
}
