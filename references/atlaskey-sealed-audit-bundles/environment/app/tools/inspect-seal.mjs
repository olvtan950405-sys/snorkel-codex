#!/usr/bin/env node
// Support tool: dump the seal footer of an archived v1 bundle.
// Usage: node /app/tools/inspect-seal.mjs /path/to/bundle.akb
import { readFileSync } from 'node:fs';
import { readTar } from '../src/akb/tar.js';
import { parseSealV1 } from '../src/akb/seal-v1.js';

const path = process.argv[2];
if (!path) {
  process.stderr.write('usage: inspect-seal <bundle.akb>\n');
  process.exit(2);
}

const seal = parseSealV1(readTar(readFileSync(path)).get('seal.bin'));
process.stdout.write(
  `${JSON.stringify(
    {
      format_version: seal.formatVersion,
      tenant_id: seal.tenantId,
      algorithm: seal.algorithm,
      key_epoch: seal.keyEpoch,
      sealed_at: new Date(seal.sealedAtMs).toISOString(),
      ciphertext_bytes: seal.ciphertext.length,
      mac: seal.mac.toString('hex'),
    },
    null,
    2,
  )}\n`,
);
