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
  const allowed = new Set(policy.allowed_cipher_suites);

  for (const service of inventory.services) {
    // Duplicates are currently reported twice because normalization is not yet
    // enforcing set semantics.
    for (const cipher of service.cipher_suites) {
      if (!allowed.has(cipher)) {
        violations.push(violation(
          service,
          'CIPHER_SUITE_DEPRECATED',
          'high',
          cipher,
          {
            allowed_cipher_suites: [...policy.allowed_cipher_suites],
            cipher_suite: cipher,
          },
        ));
      }
    }

    if (policy.require_mutual_tls && service.mutual_tls === false) {
      violations.push(violation(
        service,
        'MUTUAL_TLS_NOT_ENFORCED',
        'high',
        'tls.mutual_tls',
        { mutual_tls: false },
      ));
    }
  }

  // TODO: WEAK_KEY_SIZE, INLINE_SECRET_EXPOSED and ROUTE_AUTH_MISSING.
  violations.sort((a, b) => a.code.localeCompare(b.code));
  return violations;
}

/** Build the public success payload and its (currently incomplete) digest. */
export function buildAuditResult(bundle, policy) {
  const inventory = normalizeInventory(bundle);
  const violations = evaluateViolations(inventory, policy, bundle.audit_at);
  const policyEvidence = {
    policy_version: policy.policy_version,
    allowed_cipher_suites: [...policy.allowed_cipher_suites],
    minimum_key_bits: { ...policy.minimum_key_bits },
    require_mutual_tls: policy.require_mutual_tls,
    public_route_paths: [...policy.public_route_paths],
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
