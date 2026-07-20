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
 * yet enforce the `audit_at` timestamp grammar, integer bounds (`requests_per_minute`,
 * `max_attempts`, `timeout_ms`, `rate_limit_per_minute`), booleans (`enabled`),
 * Unicode-scalar strings, or identifier uniqueness. Those omissions are
 * deliberate repair points for the task.
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
      if (!isObject(service.rate_limit) || !isObject(service.retry)) return false;
      if (!isObject(service.circuit_breaker)) return false;
      if (service.upstreams !== undefined && !Array.isArray(service.upstreams)) return false;
      if (service.routes !== undefined && !Array.isArray(service.routes)) return false;
      return true;
    });
  });
}
