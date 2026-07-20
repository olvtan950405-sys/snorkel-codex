import { TLS_VERSIONS } from './policy.js';

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function nonEmptyString(value) {
  return typeof value === 'string' && value.length > 0;
}

/**
 * Lightweight bundle guard used by the starter service.
 *
 * It checks enough shape to keep the partial pipeline runnable, but it does not
 * yet enforce the `audit_at` timestamp grammar, enum membership (`key_type`,
 * `authentication`), integer bounds (`key_bits`), booleans (`mutual_tls`,
 * `inline`), Unicode-scalar strings, or identifier uniqueness. Those omissions
 * are deliberate repair points for the task.
 */
export function validateBundle(bundle) {
  if (!isObject(bundle)) return false;
  if (!nonEmptyString(bundle.bundle_id) || !nonEmptyString(bundle.audit_at)) return false;
  if (!Array.isArray(bundle.gateways)) return false;

  return bundle.gateways.every((gateway) => {
    if (!isObject(gateway) || !nonEmptyString(gateway.gateway_id)) return false;
    if (!Array.isArray(gateway.services)) return false;

    return gateway.services.every((service) => {
      if (!isObject(service) || !nonEmptyString(service.service_id)) return false;
      if (!isObject(service.tls) || !Array.isArray(service.tls.cipher_suites)) return false;
      if (!TLS_VERSIONS.includes(service.tls.minimum_version)) return false;
      if (service.credentials !== undefined && !Array.isArray(service.credentials)) return false;
      if (service.routes !== undefined && !Array.isArray(service.routes)) return false;
      return true;
    });
  });
}
