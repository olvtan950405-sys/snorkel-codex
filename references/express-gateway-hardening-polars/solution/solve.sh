#!/usr/bin/env bash
set -euo pipefail

cd "${APP_DIR:-/app}"

# The service is deliberately split into small modules.  Authentication never
# sees a parsed body, normalization really crosses the nested list boundaries
# with Polars, and the evidence hash is built from the same normalized values
# that drive the response.

cat > src/canonical.js <<'EOF_CANONICAL'
import crypto from 'node:crypto';

function compareStrings(left, right) {
  const leftPoints = [...left];
  const rightPoints = [...right];
  const length = Math.min(leftPoints.length, rightPoints.length);
  for (let index = 0; index < length; index += 1) {
    const difference = leftPoints[index].codePointAt(0) - rightPoints[index].codePointAt(0);
    if (difference !== 0) return difference < 0 ? -1 : 1;
  }
  return leftPoints.length - rightPoints.length;
}

// This exported structural form is useful to callers that need sorted keys.
// canonicalJson uses its own serializer as JavaScript gives integer-looking
// object keys special enumeration order even when they were inserted sorted.
export function canonicalize(value) {
  if (value === null) return null;
  if (Array.isArray(value)) {
    return value.map((item) => {
      const normalized = canonicalize(item);
      return normalized === undefined ? null : normalized;
    });
  }
  if (typeof value === 'number') return Number.isFinite(value) ? value : null;
  if (typeof value !== 'object') return value;

  const result = {};
  for (const key of Object.keys(value).sort(compareStrings)) {
    const normalized = canonicalize(value[key]);
    if (normalized !== undefined) result[key] = normalized;
  }
  return result;
}

function serialize(value, inArray = false) {
  if (value === null) return 'null';

  const kind = typeof value;
  if (kind === 'string' || kind === 'boolean') return JSON.stringify(value);
  if (kind === 'number') return Number.isFinite(value) ? JSON.stringify(value) : 'null';
  if (kind === 'bigint') throw new TypeError('BigInt cannot be serialized as JSON');
  if (kind === 'undefined' || kind === 'function' || kind === 'symbol') {
    return inArray ? 'null' : undefined;
  }

  if (Array.isArray(value)) {
    return `[${value.map((item) => serialize(item, true)).join(',')}]`;
  }

  const members = [];
  for (const key of Object.keys(value).sort(compareStrings)) {
    const encoded = serialize(value[key], false);
    if (encoded !== undefined) members.push(`${JSON.stringify(key)}:${encoded}`);
  }
  return `{${members.join(',')}}`;
}

export function canonicalJson(value) {
  const encoded = serialize(value);
  if (encoded === undefined) throw new TypeError('value is not JSON serializable');
  return `${encoded}\n`;
}

export function sha256Hex(bytes) {
  return crypto.createHash('sha256').update(bytes).digest('hex');
}
EOF_CANONICAL

cat > src/policy.js <<'EOF_POLICY'
import fs from 'node:fs';

export const DEFAULT_POLICY_PATH = '/app/data/security-policy.json';
export const TLS_VERSIONS = Object.freeze(['TLSv1.0', 'TLSv1.1', 'TLSv1.2', 'TLSv1.3']);
export const KEY_TYPES = Object.freeze(['EC', 'Ed25519', 'RSA']);
export const AUTHENTICATION_MODES = Object.freeze(['api_key', 'mtls', 'none', 'oauth2']);

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

// A non-empty string in which every UTF-16 code unit is either a lone BMP
// scalar or part of a well-formed surrogate pair; lone surrogates are rejected.
function isNonEmptyString(value) {
  if (typeof value !== 'string' || value.length === 0) return false;
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false;
      index += 1;
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      return false;
    }
  }
  return true;
}

function isBoundedInteger(value) {
  return Number.isSafeInteger(value) && value >= 0 && value <= 1_000_000;
}

function compareStrings(left, right) {
  const leftPoints = [...left];
  const rightPoints = [...right];
  const length = Math.min(leftPoints.length, rightPoints.length);
  for (let index = 0; index < length; index += 1) {
    const difference = leftPoints[index].codePointAt(0) - rightPoints[index].codePointAt(0);
    if (difference !== 0) return difference < 0 ? -1 : 1;
  }
  return leftPoints.length - rightPoints.length;
}

function uniqueSorted(values) {
  return [...new Set(values)].sort(compareStrings);
}

function normalizePolicy(value) {
  if (!isObject(value)) throw new Error('policy must be a JSON object');
  if (!isNonEmptyString(value.policy_version)) {
    throw new Error('policy_version must be a non-empty scalar string');
  }
  if (
    !Array.isArray(value.allowed_cipher_suites) ||
    !value.allowed_cipher_suites.every(isNonEmptyString)
  ) {
    throw new Error('allowed_cipher_suites must be an array of non-empty scalar strings');
  }

  const minimumKeyBits = value.minimum_key_bits;
  if (!isObject(minimumKeyBits)) {
    throw new Error('minimum_key_bits must be a JSON object');
  }
  const keys = Object.keys(minimumKeyBits);
  if (
    keys.length !== KEY_TYPES.length ||
    !KEY_TYPES.every((keyType) => Object.prototype.hasOwnProperty.call(minimumKeyBits, keyType))
  ) {
    throw new Error('minimum_key_bits must have exactly EC, Ed25519 and RSA');
  }
  for (const keyType of KEY_TYPES) {
    if (!isBoundedInteger(minimumKeyBits[keyType])) {
      throw new Error(`minimum_key_bits.${keyType} must be an integer from 0 through 1000000`);
    }
  }

  if (typeof value.require_mutual_tls !== 'boolean') {
    throw new Error('require_mutual_tls must be a boolean');
  }
  if (
    !Array.isArray(value.public_route_paths) ||
    !value.public_route_paths.every(isNonEmptyString)
  ) {
    throw new Error('public_route_paths must be an array of non-empty scalar strings');
  }

  // Deliberately return exactly the fields that are part of the evidence policy.
  return {
    policy_version: value.policy_version,
    allowed_cipher_suites: uniqueSorted(value.allowed_cipher_suites),
    minimum_key_bits: {
      EC: minimumKeyBits.EC,
      Ed25519: minimumKeyBits.Ed25519,
      RSA: minimumKeyBits.RSA,
    },
    require_mutual_tls: value.require_mutual_tls,
    public_route_paths: uniqueSorted(value.public_route_paths),
  };
}

export function loadPolicy(
  policyPath = process.env.SECURITY_POLICY_PATH || DEFAULT_POLICY_PATH,
) {
  const selectedPath = policyPath || DEFAULT_POLICY_PATH;
  let parsed;
  try {
    parsed = JSON.parse(fs.readFileSync(selectedPath, 'utf8'));
  } catch (error) {
    throw new Error(`unable to load security policy at ${selectedPath}: ${error.message}`);
  }

  try {
    return normalizePolicy(parsed);
  } catch (error) {
    throw new Error(`invalid security policy at ${selectedPath}: ${error.message}`);
  }
}
EOF_POLICY

cat > src/signature.js <<'EOF_SIGNATURE'
import crypto from 'node:crypto';

function secretBytes(secret) {
  return Buffer.isBuffer(secret) ? secret : Buffer.from(String(secret), 'utf8');
}

export function computeSignature(rawBody, secret) {
  const digest = crypto.createHmac('sha256', secretBytes(secret)).update(rawBody).digest('hex');
  return `sha256=${digest}`;
}

export function verifySignature(rawBody, signatureHeader, secret) {
  if (typeof signatureHeader !== 'string') return false;
  // A length check also rules out a trailing line terminator, for which the
  // JavaScript `$` regex assertion can otherwise match just before the end.
  if (signatureHeader.length !== 71 || !/^sha256=[0-9a-f]{64}$/.test(signatureHeader)) {
    return false;
  }

  const supplied = Buffer.from(signatureHeader.slice('sha256='.length), 'hex');
  const expected = crypto.createHmac('sha256', secretBytes(secret)).update(rawBody).digest();
  return supplied.length === 32 && crypto.timingSafeEqual(supplied, expected);
}
EOF_SIGNATURE

cat > src/validation.js <<'EOF_VALIDATION'
import { AUTHENTICATION_MODES, KEY_TYPES, TLS_VERSIONS } from './policy.js';

const UTC_MILLISECOND = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

// A non-empty string with no lone UTF-16 surrogate code units.
function isNonEmptyString(value) {
  if (typeof value !== 'string' || value.length === 0) return false;
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index);
    if (code >= 0xd800 && code <= 0xdbff) {
      const next = value.charCodeAt(index + 1);
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false;
      index += 1;
    } else if (code >= 0xdc00 && code <= 0xdfff) {
      return false;
    }
  }
  return true;
}

function isExactInstant(value) {
  if (typeof value !== 'string' || !UTC_MILLISECOND.test(value)) return false;
  const milliseconds = Date.parse(value);
  return Number.isFinite(milliseconds) && new Date(milliseconds).toISOString() === value;
}

function isStringArray(value) {
  return Array.isArray(value) && value.every(isNonEmptyString);
}

function isBoundedInteger(value) {
  return Number.isSafeInteger(value) && value >= 1 && value <= 1_000_000;
}

function uniqueBy(items, keyFor) {
  const seen = new Set();
  for (const item of items) {
    const key = keyFor(item);
    if (seen.has(key)) return false;
    seen.add(key);
  }
  return true;
}

function validCredential(credential) {
  return (
    isObject(credential) &&
    isNonEmptyString(credential.credential_id) &&
    KEY_TYPES.includes(credential.key_type) &&
    isBoundedInteger(credential.key_bits) &&
    isNonEmptyString(credential.secret_ref) &&
    typeof credential.inline === 'boolean'
  );
}

function validRoute(route) {
  if (!isObject(route) || !isNonEmptyString(route.path)) return false;
  if (!AUTHENTICATION_MODES.includes(route.authentication)) return false;
  if (route.methods !== undefined && !isStringArray(route.methods)) return false;
  return true;
}

function validService(service) {
  if (!isObject(service) || !isNonEmptyString(service.service_id)) return false;
  if (!isObject(service.tls)) return false;
  if (!TLS_VERSIONS.includes(service.tls.minimum_version)) return false;
  if (typeof service.tls.mutual_tls !== 'boolean') return false;
  if (!isStringArray(service.tls.cipher_suites)) return false;

  const credentials = service.credentials === undefined ? [] : service.credentials;
  if (!Array.isArray(credentials) || !credentials.every(validCredential)) return false;
  if (!uniqueBy(credentials, (credential) => credential.credential_id)) return false;

  const routes = service.routes === undefined ? [] : service.routes;
  if (!Array.isArray(routes) || !routes.every(validRoute)) return false;
  if (!uniqueBy(routes, (route) => route.path)) return false;
  return true;
}

function validGateway(gateway) {
  if (!isObject(gateway) || !isNonEmptyString(gateway.gateway_id)) return false;
  if (!Array.isArray(gateway.services) || !gateway.services.every(validService)) return false;
  return uniqueBy(gateway.services, (service) => service.service_id);
}

export function validateBundle(bundle) {
  if (!isObject(bundle)) return false;
  if (!isNonEmptyString(bundle.bundle_id) || !isExactInstant(bundle.audit_at)) return false;
  if (!Array.isArray(bundle.gateways) || !bundle.gateways.every(validGateway)) return false;
  return uniqueBy(bundle.gateways, (gateway) => gateway.gateway_id);
}
EOF_VALIDATION

cat > src/normalize.js <<'EOF_NORMALIZE'
import pl from 'nodejs-polars';

const STRING = pl.String;
const STRING_LIST = pl.List(pl.String);

function compareStrings(left, right) {
  const leftPoints = [...left];
  const rightPoints = [...right];
  const length = Math.min(leftPoints.length, rightPoints.length);
  for (let index = 0; index < length; index += 1) {
    const difference = leftPoints[index].codePointAt(0) - rightPoints[index].codePointAt(0);
    if (difference !== 0) return difference < 0 ? -1 : 1;
  }
  return leftPoints.length - rightPoints.length;
}

function uniqueSorted(values) {
  return [...new Set(values)].sort(compareStrings);
}

function makeFrame(rows, fields, schema) {
  const columns = {};
  for (const field of fields) columns[field] = rows.map((row) => row[field]);
  return pl.DataFrame(columns, { schema });
}

export function normalizeInventory(bundle) {
  // The pinned Polars version rejects a typed zero-row parent frame.  Empty
  // input has no nested cardinality to transform, so its normalized inventory
  // is unambiguously three empty arrays.
  if (bundle.gateways.length === 0) {
    return { services: [], credentials: [], routes: [] };
  }

  // Each nested object is carried through a typed Polars list column as a
  // lossless JSON string so that the three explode operations own the
  // cardinality transformation even when the child objects themselves contain
  // nested lists, and empty lists collapse to nulls that are then dropped.
  const gatewayRows = bundle.gateways.map((gateway) => ({
    gateway_id: gateway.gateway_id,
    services: gateway.services.map((service) => JSON.stringify(service)),
  }));
  const gatewayFrame = makeFrame(
    gatewayRows,
    ['gateway_id', 'services'],
    { gateway_id: STRING, services: STRING_LIST },
  );

  const serviceCarriers = gatewayFrame
    .explode('services')
    .toRecords()
    .filter((row) => typeof row.services === 'string')
    .map((row) => ({ gateway_id: row.gateway_id, service: JSON.parse(row.services) }));

  // A non-empty gateway frame can consist entirely of empty service lists; its
  // required service explosion has already happened above.
  if (serviceCarriers.length === 0) {
    return { services: [], credentials: [], routes: [] };
  }

  const services = serviceCarriers.map(({ gateway_id, service }) => ({
    gateway_id,
    service_id: service.service_id,
    cipher_suites: uniqueSorted(service.tls.cipher_suites),
    mutual_tls: service.tls.mutual_tls,
    tls_minimum_version: service.tls.minimum_version,
  }));

  // Keys and certificates are separate list dimensions; exploding them in
  // separate frames correctly handles different lengths and empty lists.
  const credentialRows = serviceCarriers.map(({ gateway_id, service }) => ({
    gateway_id,
    service_id: service.service_id,
    credentials: (service.credentials ?? []).map((credential) => JSON.stringify(credential)),
  }));
  const credentials = makeFrame(
    credentialRows,
    ['gateway_id', 'service_id', 'credentials'],
    { gateway_id: STRING, service_id: STRING, credentials: STRING_LIST },
  )
    .explode('credentials')
    .toRecords()
    .filter((row) => typeof row.credentials === 'string')
    .map((row) => {
      const credential = JSON.parse(row.credentials);
      return {
        gateway_id: row.gateway_id,
        service_id: row.service_id,
        credential_id: credential.credential_id,
        key_type: credential.key_type,
        key_bits: credential.key_bits,
        secret_ref: credential.secret_ref,
        inline: credential.inline,
      };
    });

  const routeRows = serviceCarriers.map(({ gateway_id, service }) => ({
    gateway_id,
    service_id: service.service_id,
    routes: (service.routes ?? []).map((route) => JSON.stringify(route)),
  }));
  const routes = makeFrame(
    routeRows,
    ['gateway_id', 'service_id', 'routes'],
    { gateway_id: STRING, service_id: STRING, routes: STRING_LIST },
  )
    .explode('routes')
    .toRecords()
    .filter((row) => typeof row.routes === 'string')
    .map((row) => {
      const route = JSON.parse(row.routes);
      return {
        gateway_id: row.gateway_id,
        service_id: row.service_id,
        path: route.path,
        methods: uniqueSorted(route.methods ?? []),
        authentication: route.authentication,
      };
    });

  services.sort(
    (a, b) =>
      compareStrings(a.gateway_id, b.gateway_id) ||
      compareStrings(a.service_id, b.service_id),
  );
  credentials.sort(
    (a, b) =>
      compareStrings(a.gateway_id, b.gateway_id) ||
      compareStrings(a.service_id, b.service_id) ||
      compareStrings(a.credential_id, b.credential_id),
  );
  routes.sort(
    (a, b) =>
      compareStrings(a.gateway_id, b.gateway_id) ||
      compareStrings(a.service_id, b.service_id) ||
      compareStrings(a.path, b.path),
  );

  return { services, credentials, routes };
}
EOF_NORMALIZE

cat > src/audit.js <<'EOF_AUDIT'
import { normalizeInventory } from './normalize.js';
import { canonicalJson, sha256Hex } from './canonical.js';

function compareStrings(left, right) {
  const leftPoints = [...left];
  const rightPoints = [...right];
  const length = Math.min(leftPoints.length, rightPoints.length);
  for (let index = 0; index < length; index += 1) {
    const difference = leftPoints[index].codePointAt(0) - rightPoints[index].codePointAt(0);
    if (difference !== 0) return difference < 0 ? -1 : 1;
  }
  return leftPoints.length - rightPoints.length;
}

function uniqueSorted(values) {
  return [...new Set(values)].sort(compareStrings);
}

function violationOrder(left, right) {
  return (
    compareStrings(left.gateway_id, right.gateway_id) ||
    compareStrings(left.service_id, right.service_id) ||
    compareStrings(left.code, right.code) ||
    compareStrings(left.subject, right.subject)
  );
}

function violation(code, severity, subject, row, evidence) {
  return {
    code,
    evidence,
    gateway_id: row.gateway_id,
    service_id: row.service_id,
    severity,
    subject,
  };
}

export function evaluateViolations(inventory, policy, _auditAt) {
  const violations = [];
  const allowedCiphers = uniqueSorted(policy.allowed_cipher_suites);
  const allowedCipherSet = new Set(allowedCiphers);
  const publicPaths = new Set(policy.public_route_paths);

  for (const service of inventory.services) {
    for (const cipher of service.cipher_suites) {
      if (!allowedCipherSet.has(cipher)) {
        violations.push(
          violation('CIPHER_SUITE_DEPRECATED', 'high', cipher, service, {
            allowed_cipher_suites: allowedCiphers,
            cipher_suite: cipher,
          }),
        );
      }
    }

    if (policy.require_mutual_tls && service.mutual_tls === false) {
      violations.push(
        violation('MUTUAL_TLS_NOT_ENFORCED', 'high', 'tls.mutual_tls', service, {
          mutual_tls: false,
        }),
      );
    }
  }

  for (const credential of inventory.credentials) {
    const minimumBits = policy.minimum_key_bits[credential.key_type];
    // Strictly below the minimum is weak; a key exactly at the minimum is fine.
    if (typeof minimumBits === 'number' && credential.key_bits < minimumBits) {
      violations.push(
        violation('WEAK_KEY_SIZE', 'high', credential.credential_id, credential, {
          key_bits: credential.key_bits,
          key_type: credential.key_type,
          minimum_bits: minimumBits,
        }),
      );
    }

    if (credential.inline === true) {
      violations.push(
        violation('INLINE_SECRET_EXPOSED', 'critical', credential.credential_id, credential, {
          secret_ref: credential.secret_ref,
        }),
      );
    }
  }

  for (const route of inventory.routes) {
    if (route.authentication === 'none' && !publicPaths.has(route.path)) {
      violations.push(
        violation('ROUTE_AUTH_MISSING', 'critical', route.path, route, {
          authentication: 'none',
          methods: route.methods,
        }),
      );
    }
  }

  return violations.sort(violationOrder);
}

export function buildAuditResult(bundle, policy) {
  const normalizedPolicy = {
    policy_version: policy.policy_version,
    allowed_cipher_suites: uniqueSorted(policy.allowed_cipher_suites),
    minimum_key_bits: { ...policy.minimum_key_bits },
    require_mutual_tls: policy.require_mutual_tls,
    public_route_paths: uniqueSorted(policy.public_route_paths),
  };
  const inventory = normalizeInventory(bundle);
  const violations = evaluateViolations(inventory, normalizedPolicy, bundle.audit_at);
  const preimage = {
    audit_at: bundle.audit_at,
    bundle_id: bundle.bundle_id,
    inventory,
    policy: normalizedPolicy,
    violations,
  };

  return {
    audit_at: bundle.audit_at,
    bundle_id: bundle.bundle_id,
    evidence_digest: sha256Hex(Buffer.from(canonicalJson(preimage), 'utf8')),
    policy_version: normalizedPolicy.policy_version,
    service_count: inventory.services.length,
    violations,
  };
}
EOF_AUDIT

cat > src/app.js <<'EOF_APP'
import express from 'express';
import { TextDecoder } from 'node:util';
import { loadPolicy } from './policy.js';
import { verifySignature } from './signature.js';
import { validateBundle } from './validation.js';
import { buildAuditResult } from './audit.js';
import { canonicalJson } from './canonical.js';

const MAX_RAW_BODY_BYTES = 1_048_576;

function sendJson(response, status, value) {
  const body = Buffer.from(canonicalJson(value), 'utf8');
  response.status(status);
  response.set('Content-Type', 'application/json; charset=utf-8');
  response.set('Content-Length', String(body.length));
  response.end(body);
}

async function captureRawBody(request, response, next) {
  try {
    const chunks = [];
    let length = 0;
    let tooLarge = false;
    for await (const chunk of request) {
      const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      length += bytes.length;
      if (length > MAX_RAW_BODY_BYTES) {
        tooLarge = true;
        chunks.length = 0;
      } else if (!tooLarge) {
        chunks.push(bytes);
      }
    }
    if (tooLarge) {
      sendJson(response, 413, { error: 'payload_too_large' });
      return;
    }
    request.rawBody = Buffer.concat(chunks);
    next();
  } catch (error) {
    next(error);
  }
}

function singleSignatureHeader(request) {
  const rawHeaders = request.rawHeaders;
  if (Array.isArray(rawHeaders)) {
    const values = [];
    for (let index = 0; index < rawHeaders.length; index += 2) {
      if (String(rawHeaders[index]).toLowerCase() === 'x-audit-signature') {
        values.push(rawHeaders[index + 1]);
      }
    }
    return values.length === 1 ? values[0] : undefined;
  }

  // This fallback makes the helper usable with lightweight request mocks.
  const value = request.headers?.['x-audit-signature'];
  return typeof value === 'string' ? value : undefined;
}

function hasJsonMediaType(request) {
  const value = request.headers?.['content-type'];
  if (typeof value !== 'string') return false;
  return value.split(';', 1)[0].trim().toLowerCase() === 'application/json';
}

function hasSupportedContentEncoding(request) {
  const value = request.headers?.['content-encoding'];
  return value === undefined || (typeof value === 'string' && value.trim().toLowerCase() === 'identity');
}

function parseJsonBytes(rawBody) {
  // Fatal decoding rejects malformed UTF-8 rather than silently substituting
  // U+FFFD. Keeping a BOM in the decoded text lets JSON.parse reject it too.
  const decoder = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true });
  return JSON.parse(decoder.decode(rawBody));
}

export function createApp({
  secret = process.env.AUDIT_HMAC_SECRET,
  policyPath = process.env.SECURITY_POLICY_PATH,
} = {}) {
  if (typeof secret !== 'string' || secret.length === 0) {
    throw new Error('AUDIT_HMAC_SECRET is required');
  }
  const policy = loadPolicy(policyPath || undefined);
  const app = express();
  app.disable('x-powered-by');

  app.get('/healthz', (_request, response) => {
    sendJson(response, 200, { policy_version: policy.policy_version, status: 'ok' });
  });

  app.post('/v1/audit/security-policies', captureRawBody, (request, response, next) => {
    const signature = singleSignatureHeader(request);
    if (!verifySignature(request.rawBody, signature, secret)) {
      sendJson(response, 401, { error: 'invalid_signature' });
      return;
    }

    if (!hasSupportedContentEncoding(request)) {
      sendJson(response, 415, { error: 'unsupported_content_encoding' });
      return;
    }

    if (!hasJsonMediaType(request)) {
      sendJson(response, 415, { error: 'unsupported_media_type' });
      return;
    }

    let bundle;
    try {
      bundle = parseJsonBytes(request.rawBody);
    } catch {
      sendJson(response, 400, { error: 'invalid_json' });
      return;
    }

    if (!validateBundle(bundle)) {
      sendJson(response, 422, { error: 'invalid_bundle' });
      return;
    }

    try {
      sendJson(response, 200, buildAuditResult(bundle, policy));
    } catch (error) {
      next(error);
    }
  });

  app.use((error, _request, response, _next) => {
    if (response.headersSent) return;
    sendJson(response, 500, { error: 'internal_error' });
  });

  return app;
}
EOF_APP

cat > bin/security-audit.js <<'EOF_CLI'
#!/usr/bin/env node
import { createApp } from '../src/app.js';

function parsePort(argv) {
  let value = process.env.PORT || '8080';
  let sawPort = false;
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] !== '--port' || sawPort || index + 1 >= argv.length) {
      throw new Error('usage: node /app/bin/security-audit.js --port <n>');
    }
    value = argv[index + 1];
    sawPort = true;
    index += 1;
  }
  if (!/^\d+$/.test(value)) {
    throw new Error('port must be an integer between 0 and 65535');
  }
  const port = Number(value);
  if (!Number.isInteger(port) || port < 0 || port > 65535) {
    throw new Error('port must be an integer between 0 and 65535');
  }
  return port;
}

try {
  const app = createApp();
  const port = parsePort(process.argv.slice(2));
  const server = app.listen(port, '0.0.0.0', () => {
    const address = server.address();
    const listeningPort = typeof address === 'object' && address ? address.port : port;
    process.stdout.write(`LISTENING ${listeningPort}\n`);
  });
  server.on('error', (error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
} catch (error) {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
}
EOF_CLI

chmod +x bin/security-audit.js
