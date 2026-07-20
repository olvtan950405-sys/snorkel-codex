import { createDecipheriv, createHmac, timingSafeEqual } from 'node:crypto';

// Algorithm suites the signing stations are able to emit. The suite name is carried in
// the seal and is authenticated; whether a tenant may *use* a suite is a catalog question.
export const SUITES = {
  'AES-256-GCM+HMAC-SHA256': { cipher: 'aes-256-gcm', encKeyBytes: 32 },
  'AES-128-GCM+HMAC-SHA256': { cipher: 'aes-128-gcm', encKeyBytes: 16 },
};

export function suiteFor(algorithm) {
  return Object.prototype.hasOwnProperty.call(SUITES, algorithm) ? SUITES[algorithm] : null;
}

export function macMatches(macKey, covered, tag) {
  const expected = createHmac('sha256', macKey).update(covered).digest();
  return expected.length === tag.length && timingSafeEqual(expected, tag);
}

// Returns the decoded payload object, or null when the payload does not authenticate.
export function openSealedPayload({ suite, encKey, iv, ciphertext, tag, aad }) {
  try {
    const decipher = createDecipheriv(suite.cipher, encKey, iv);
    decipher.setAAD(aad);
    decipher.setAuthTag(tag);
    const plaintext = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
    return JSON.parse(plaintext.toString('utf8'));
  } catch {
    return null;
  }
}
