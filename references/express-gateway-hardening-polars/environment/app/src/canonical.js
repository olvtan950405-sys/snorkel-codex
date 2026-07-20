import crypto from 'node:crypto';

/**
 * Sort the keys at the top level of an object.
 *
 * This starter implementation is intentionally shallow. Nested evidence and
 * policy objects still retain insertion order and arrays retain input order.
 */
export function canonicalize(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return value;
  return Object.fromEntries(Object.keys(value).sort().map((key) => [key, value[key]]));
}

/** Compact JSON; recursive sorting and the required final newline are pending. */
export function canonicalJson(value) {
  return JSON.stringify(canonicalize(value));
}

export function sha256Hex(bytes) {
  return crypto.createHash('sha256').update(bytes).digest('hex');
}
