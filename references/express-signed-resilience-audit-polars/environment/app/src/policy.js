import fs from 'node:fs';

export const DEFAULT_POLICY_PATH = '/app/data/security-policy.json';

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
  // TODO: the integer ceilings (max_requests_per_minute, max_timeout_ms,
  // max_retry_attempts), the require_circuit_breaker boolean, and the
  // exempt_route_paths array are not yet validated or de-duplicated.

  return {
    policy_version: policy.policy_version,
    max_requests_per_minute: policy.max_requests_per_minute,
    max_timeout_ms: policy.max_timeout_ms,
    max_retry_attempts: policy.max_retry_attempts,
    require_circuit_breaker: Boolean(policy.require_circuit_breaker),
    exempt_route_paths: Array.isArray(policy.exempt_route_paths)
      ? [...policy.exempt_route_paths]
      : [],
  };
}
