#!/usr/bin/env bash
set -euo pipefail

# Rewrites the four incomplete modules so ffguard resolves each FFmpeg service
# from the host-state inventory, queries the OSV advisory API, applies Debian
# version ordering to advisory ranges, and emits the hardening artifacts at the
# paths the contract requires. The remaining modules are already correct.

cd "${APP_DIR:-/app}"

cat > src/debver.ts <<'EOF_debver'
// Debian package version comparison (dpkg semantics).
//
// A version is [epoch:]upstream[-revision]. Epochs compare as integers; the
// upstream and revision parts compare with the dpkg verrevcmp algorithm where
// digit runs compare numerically and non-digit runs compare by a modified
// ordering in which '~' sorts before everything (even the empty string) and
// letters sort before all other punctuation.

function order(character: string): number {
  if (character === '') return 0;
  if (character >= '0' && character <= '9') return 0;
  const code = character.charCodeAt(0);
  if ((character >= 'a' && character <= 'z') || (character >= 'A' && character <= 'Z')) return code;
  if (character === '~') return -1;
  return code + 256;
}

function isDigit(character: string | undefined): boolean {
  return character !== undefined && character >= '0' && character <= '9';
}

function verrevcmp(left: string, right: string): number {
  let i = 0;
  let j = 0;
  while (i < left.length || j < right.length) {
    let firstDifference = 0;
    while ((i < left.length && !isDigit(left[i])) || (j < right.length && !isDigit(right[j]))) {
      const leftOrder = order(i < left.length ? left[i] : '');
      const rightOrder = order(j < right.length ? right[j] : '');
      if (leftOrder !== rightOrder) return leftOrder - rightOrder;
      i += 1;
      j += 1;
    }
    while (left[i] === '0') i += 1;
    while (right[j] === '0') j += 1;
    while (isDigit(left[i]) && isDigit(right[j])) {
      if (firstDifference === 0) firstDifference = left.charCodeAt(i) - right.charCodeAt(j);
      i += 1;
      j += 1;
    }
    if (isDigit(left[i])) return 1;
    if (isDigit(right[j])) return -1;
    if (firstDifference !== 0) return firstDifference;
  }
  return 0;
}

function parse(version: string): { epoch: number; upstream: string; revision: string } {
  let epoch = 0;
  let rest = version;
  const colon = version.indexOf(':');
  if (colon >= 0) {
    epoch = Number.parseInt(version.slice(0, colon), 10);
    rest = version.slice(colon + 1);
  }
  let upstream = rest;
  let revision = '';
  const dash = rest.lastIndexOf('-');
  if (dash >= 0) {
    upstream = rest.slice(0, dash);
    revision = rest.slice(dash + 1);
  }
  return { epoch, upstream, revision };
}

export function compareDeb(left: string, right: string): number {
  const a = parse(left);
  const b = parse(right);
  if (a.epoch !== b.epoch) return a.epoch < b.epoch ? -1 : 1;
  const upstream = verrevcmp(a.upstream, b.upstream);
  if (upstream !== 0) return upstream < 0 ? -1 : 1;
  const revision = verrevcmp(a.revision, b.revision);
  return revision < 0 ? -1 : revision > 0 ? 1 : 0;
}
EOF_debver

cat > src/osv.ts <<'EOF_osv'
// OSV advisory client and version-range containment.
//
// Advisories are fetched from an OSV-compatible API with POST /v1/query and a
// {package:{name,ecosystem}} body. Containment follows OSV ECOSYSTEM range
// semantics over Debian version ordering: events form (introduced, fixed |
// last_affected | open) intervals in sequence; a version is affected if it
// falls in one of those intervals, and a "fixed" interval reports the version
// that clears it.

import { compareDeb } from './debver.js';

export interface OsvEvent {
  introduced?: string;
  fixed?: string;
  last_affected?: string;
}

export interface OsvRange {
  type?: string;
  events?: OsvEvent[];
}

export interface OsvAffected {
  package?: { name?: string; ecosystem?: string };
  ranges?: OsvRange[];
}

export interface OsvVuln {
  id: string;
  withdrawn?: string;
  affected?: OsvAffected[];
  database_specific?: { severity?: string };
}

type Interval = { introduced: string; kind: 'fixed' | 'last_affected' | 'open'; end: string | null };

function intervals(events: OsvEvent[]): Interval[] {
  const result: Interval[] = [];
  let introduced: string | null = null;
  for (const event of events) {
    if (event.introduced !== undefined) {
      introduced = event.introduced;
    } else if (event.fixed !== undefined) {
      result.push({ introduced: introduced ?? '0', kind: 'fixed', end: event.fixed });
      introduced = null;
    } else if (event.last_affected !== undefined) {
      result.push({ introduced: introduced ?? '0', kind: 'last_affected', end: event.last_affected });
      introduced = null;
    }
  }
  if (introduced !== null) result.push({ introduced, kind: 'open', end: null });
  return result;
}

function rangeHit(events: OsvEvent[], version: string): { hit: boolean; fixed: string | null } {
  for (const interval of intervals(events)) {
    const atOrAbove = interval.introduced === '0' || compareDeb(version, interval.introduced) >= 0;
    if (!atOrAbove) continue;
    if (interval.kind === 'open') return { hit: true, fixed: null };
    if (interval.kind === 'fixed') {
      if (compareDeb(version, interval.end as string) < 0) return { hit: true, fixed: interval.end };
    } else if (compareDeb(version, interval.end as string) <= 0) {
      return { hit: true, fixed: null };
    }
  }
  return { hit: false, fixed: null };
}

// Whether an advisory applies to package@version, and the fixed version of the
// containing interval when one exists. Withdrawn advisories, non-ECOSYSTEM
// ranges, and affected blocks for other packages or ecosystems never apply.
export function advisoryHit(vuln: OsvVuln, packageName: string, version: string): { hit: boolean; fixed: string | null } {
  if (vuln.withdrawn !== undefined) return { hit: false, fixed: null };
  for (const affected of vuln.affected ?? []) {
    if (affected.package?.name !== packageName || affected.package?.ecosystem !== 'Debian') continue;
    for (const range of affected.ranges ?? []) {
      if (range.type !== 'ECOSYSTEM') continue;
      const result = rangeHit(range.events ?? [], version);
      if (result.hit) return result;
    }
  }
  return { hit: false, fixed: null };
}

export async function queryOsv(base: string, packageName: string): Promise<OsvVuln[]> {
  const response = await fetch(`${base}/v1/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ package: { name: packageName, ecosystem: 'Debian' } }),
  });
  if (!response.ok) {
    throw new Error(`OSV query for ${packageName} failed with status ${response.status}`);
  }
  const data = (await response.json()) as { vulns?: OsvVuln[] };
  return data.vulns ?? [];
}
EOF_osv

cat > src/inventory.ts <<'EOF_inventory'
// Host-state inventory access.
//
// The inventory is a SQLite database with packages(name, version, ecosystem),
// binaries(path, package) and services(unit, exec_path, enabled). An FFmpeg
// service is a unit whose executable basename is one of the FFmpeg tools; its
// installed version is resolved exec_path -> binaries.package -> packages.version.
// A path with no binaries row, a NULL package, or a package missing from
// packages is unresolvable and leaves the version null.

import { readFileSync } from 'node:fs';
import { basename } from 'node:path';
import initSqlJs, { type Database } from 'sql.js';

export const FFMPEG_TOOLS = new Set(['ffmpeg', 'ffprobe']);

export interface ServiceRecord {
  unit: string;
  exec_path: string;
  enabled: boolean;
  package: string | null;
  version: string | null;
}

function rows(db: Database, sql: string, params: (string | number)[] = []): Record<string, unknown>[] {
  const statement = db.prepare(sql);
  statement.bind(params);
  const out: Record<string, unknown>[] = [];
  while (statement.step()) out.push(statement.getAsObject());
  statement.free();
  return out;
}

export async function loadInventory(dbPath: string): Promise<ServiceRecord[]> {
  const SQL = await initSqlJs();
  const db = new SQL.Database(readFileSync(dbPath));
  try {
    const services = rows(db, 'SELECT unit, exec_path, enabled FROM services ORDER BY unit').filter(
      (service) => FFMPEG_TOOLS.has(basename(String(service.exec_path))),
    );
    const records: ServiceRecord[] = [];
    for (const service of services) {
      const execPath = String(service.exec_path);
      let packageName: string | null = null;
      let version: string | null = null;
      const binary = rows(db, 'SELECT package FROM binaries WHERE path = ?', [execPath]);
      if (binary.length > 0 && binary[0].package !== null && binary[0].package !== undefined) {
        const candidate = String(binary[0].package);
        const pkg = rows(db, 'SELECT version FROM packages WHERE name = ?', [candidate]);
        if (pkg.length > 0) {
          packageName = candidate;
          version = String(pkg[0].version);
        }
      }
      records.push({
        unit: String(service.unit),
        exec_path: execPath,
        enabled: Number(service.enabled) === 1,
        package: packageName,
        version,
      });
    }
    return records;
  } finally {
    db.close();
  }
}
EOF_inventory

cat > src/report.ts <<'EOF_report'
// Artifact rendering.
//
// Writes, under the output directory:
//   apt/preferences.d/ffguard-<package>.pref   (APT pin, one per pinned package)
//   systemd/system/<unit>.d/override.conf      (drop-in per blocked unit)
//   hardening-report.json                      (canonical JSON report)
//   ffmpeg-hardening-audit.md                  (Markdown audit note)

import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { canonicalJson, compareCodePoints } from './canonical.js';
import { compareDeb } from './debver.js';
import type { ServiceDecision } from './policy.js';

export interface Pin {
  package: string;
  version: string;
}

function writeFile(outDir: string, relative: string, contents: string): void {
  const full = join(outDir, relative);
  mkdirSync(dirname(full), { recursive: true });
  writeFileSync(full, contents);
}

export function pinsFor(decisions: ServiceDecision[]): Pin[] {
  const targets = new Map<string, string>();
  for (const decision of decisions) {
    if (decision.decision === 'pin' && decision.package !== null && decision.pin_version !== null) {
      const current = targets.get(decision.package);
      if (current === undefined || compareDeb(decision.pin_version, current) > 0) {
        targets.set(decision.package, decision.pin_version);
      }
    }
  }
  return [...targets.keys()]
    .sort(compareCodePoints)
    .map((name) => ({ package: name, version: targets.get(name) as string }));
}

function renderMarkdown(decisions: ServiceDecision[]): string {
  const pinned = decisions.filter((d) => d.decision === 'pin').length;
  const blocked = decisions.filter((d) => d.decision === 'block').length;
  const compliant = decisions.filter((d) => d.decision === 'ok').length;
  const lines = [
    '# FFmpeg transcode hardening audit',
    '',
    `Services scanned: ${decisions.length}`,
    `Pinned: ${pinned}`,
    `Blocked: ${blocked}`,
    `Compliant: ${compliant}`,
    '',
  ];
  for (const decision of decisions) {
    const pkg = decision.package !== null ? decision.package : 'untracked';
    const version = decision.installed_version !== null ? decision.installed_version : 'unknown';
    let verdict: string;
    if (decision.decision === 'pin') verdict = `PINNED to ${decision.pin_version}`;
    else if (decision.decision === 'block') verdict = `BLOCKED (${decision.reason})`;
    else verdict = 'COMPLIANT';
    const advisories = decision.advisories.length > 0 ? decision.advisories.join(', ') : 'none';
    lines.push(
      `## ${decision.unit}`,
      '',
      `- Executable: ${decision.exec_path}`,
      `- Package: ${pkg}`,
      `- Installed version: ${version}`,
      `- Decision: ${verdict}`,
      `- Advisories: ${advisories}`,
      '',
    );
  }
  return lines.join('\n');
}

export function writeArtifacts(outDir: string, decisions: ServiceDecision[]): void {
  const ordered = [...decisions].sort((a, b) => compareCodePoints(a.unit, b.unit));
  const pins = pinsFor(ordered);
  const blocked = ordered.filter((d) => d.decision === 'block').map((d) => d.unit).sort(compareCodePoints);

  const report = {
    generated_by: 'ffguard',
    report_version: '1',
    services: ordered,
    pins,
    blocked_units: blocked,
  };
  writeFile(outDir, 'hardening-report.json', canonicalJson(report));

  for (const pin of pins) {
    writeFile(
      outDir,
      `apt/preferences.d/ffguard-${pin.package}.pref`,
      `Package: ${pin.package}\nPin: version ${pin.version}\nPin-Priority: 1001\n`,
    );
  }

  for (const decision of ordered) {
    if (decision.decision === 'block') {
      writeFile(
        outDir,
        `systemd/system/${decision.unit}.d/override.conf`,
        '[Service]\nExecStart=\nExecStart=/bin/false\nNoNewPrivileges=yes\nProtectSystem=strict\n',
      );
    }
  }

  writeFile(outDir, 'ffmpeg-hardening-audit.md', renderMarkdown(ordered));
}
EOF_report

# Recompile so /app/dist reflects the repaired sources.
npm run build
