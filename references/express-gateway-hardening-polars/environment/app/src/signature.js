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
 * not the bytes received from the socket. That integration bug is intentional
 * in the starter and is the first thing the audit endpoint needs repaired.
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
