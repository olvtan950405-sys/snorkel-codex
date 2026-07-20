import { canonicalJson, sha256Hex } from './canonical.js';
import { normalizeInventory } from './normalize.js';

function violation(row, code, severity, subject, evidence) {
  return {
    code,
    evidence,
    gateway_id: row.gateway_id,
    service_id: row.service_id,
    severity,
    subject,
  };
}

/** Evaluate the subset of policy rules implemented by the starter. */
export function evaluateViolations(inventory, policy, _auditAt) {
  const violations = [];

  for (const service of inventory.services) {
    if (service.rate_limit_enabled === false) {
      violations.push(violation(
        service,
        'RATE_LIMIT_DISABLED',
        'high',
        'rate_limit',
        { enabled: false },
      ));
    }

    if (policy.require_circuit_breaker && service.circuit_breaker_enabled === false) {
      violations.push(violation(
        service,
        'CIRCUIT_BREAKER_REQUIRED',
        'medium',
        'circuit_breaker',
        { enabled: false },
      ));
    }
  }

  // TODO: RETRY_BUDGET_EXCEEDED, UPSTREAM_TIMEOUT_UNBOUNDED and
  // ROUTE_RATE_LIMIT_EXCEEDS are not implemented yet.
  violations.sort((a, b) => a.code.localeCompare(b.code));
  return violations;
}

/** Build the public success payload and its (currently incomplete) digest. */
export function buildAuditResult(bundle, policy) {
  const inventory = normalizeInventory(bundle);
  const violations = evaluateViolations(inventory, policy, bundle.audit_at);
  const policyEvidence = {
    policy_version: policy.policy_version,
    max_requests_per_minute: policy.max_requests_per_minute,
    max_timeout_ms: policy.max_timeout_ms,
    max_retry_attempts: policy.max_retry_attempts,
    require_circuit_breaker: policy.require_circuit_breaker,
    exempt_route_paths: [...policy.exempt_route_paths],
  };

  // TODO: inventory belongs in this preimage, and the preimage must use the
  // fully recursive canonical serializer including its trailing newline.
  const digestPreimage = canonicalJson({
    audit_at: bundle.audit_at,
    bundle_id: bundle.bundle_id,
    policy: policyEvidence,
    violations,
  });

  return {
    audit_at: bundle.audit_at,
    bundle_id: bundle.bundle_id,
    evidence_digest: sha256Hex(Buffer.from(digestPreimage, 'utf8')),
    policy_version: policy.policy_version,
    service_count: inventory.services.length,
    violations,
  };
}
