import crypto from 'node:crypto';

/** Return the signature value clients place in X-Audit-Signature. */
export function computeSignature(rawBody, secret) {
  const digest = crypto.createHmac('sha256', secret).update(rawBody).digest('hex');
  return `sha256=${digest}`;
}

/**
 * Compare a supplied HMAC with the HMAC of `rawBody` without leaking the point
 * at which two otherwise well-formed digests differ.
 *
 * NOTE: the route currently gives this function a reconstructed JSON buffer,
 * not the bytes received from the socket, and it ignores the request timestamp
 * and nonce entirely. The wire contract binds `timestamp \n nonce \n rawBody`
 * into the signing input and adds freshness and replay admission — all of that
 * is intentionally missing in the starter and must be repaired.
 */
export function verifySignature(rawBody, signatureHeader, secret) {
  if (typeof signatureHeader !== 'string') return false;

  // TODO: the wire contract permits lowercase hexadecimal only.
  const match = /^sha256=([0-9a-f]{64})$/i.exec(signatureHeader);
  if (!match) return false;

  const supplied = Buffer.from(match[1], 'hex');
  const expected = crypto.createHmac('sha256', secret).update(rawBody).digest();
  return supplied.length === expected.length && crypto.timingSafeEqual(supplied, expected);
}
