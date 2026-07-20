import fs from 'node:fs';

export const DEFAULT_POLICY_PATH = '/app/data/security-policy.json';
export const TLS_VERSIONS = ['TLSv1.0', 'TLSv1.1', 'TLSv1.2', 'TLSv1.3'];
export const KEY_TYPES = ['EC', 'Ed25519', 'RSA'];
export const AUTHENTICATION_MODES = ['api_key', 'mtls', 'none', 'oauth2'];

function fail(message) {
  throw new Error(`invalid security policy: ${message}`);
}

/** Read the selected policy once during process startup. */
export function loadPolicy(
  policyPath = process.env.SECURITY_POLICY_PATH || DEFAULT_POLICY_PATH,
) {
  let policy;
  try {
    policy = JSON.parse(fs.readFileSync(policyPath, 'utf8'));
  } catch (error) {
    throw new Error(`unable to load security policy ${policyPath}: ${error.message}`);
  }

  if (!policy || typeof policy !== 'object' || Array.isArray(policy)) {
    fail('expected a JSON object');
  }
  if (typeof policy.policy_version !== 'string' || policy.policy_version.length === 0) {
    fail('policy_version is required');
  }
  if (
    !Array.isArray(policy.allowed_cipher_suites)
    || policy.allowed_cipher_suites.some((value) => typeof value !== 'string' || value.length === 0)
  ) {
    fail('allowed_cipher_suites must be an array of non-empty strings');
  }
  // TODO: minimum_key_bits must be an object holding an integer bound
  // (0..1000000) for exactly EC, Ed25519 and RSA; the starter only checks that
  // it is an object.
  if (!policy.minimum_key_bits || typeof policy.minimum_key_bits !== 'object') {
    fail('minimum_key_bits must be an object');
  }
  // TODO: require_mutual_tls must be a strict boolean and public_route_paths a
  // de-duplicated array of non-empty Unicode-scalar strings.

  return {
    policy_version: policy.policy_version,
    allowed_cipher_suites: [...policy.allowed_cipher_suites],
    minimum_key_bits: { ...policy.minimum_key_bits },
    require_mutual_tls: Boolean(policy.require_mutual_tls),
    public_route_paths: Array.isArray(policy.public_route_paths)
      ? [...policy.public_route_paths]
      : [],
  };
}
