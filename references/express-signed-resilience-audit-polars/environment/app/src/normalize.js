import pl from 'nodejs-polars';

function compareText(left, right) {
  if (left < right) return -1;
  if (left > right) return 1;
  return 0;
}

/**
 * Turn nested gateways into evidence rows.
 *
 * The first gateway -> service explosion is implemented with Polars. The
 * upstream and route expansions are still placeholders which retain only the
 * first nested item. A complete implementation should model those lists as
 * Polars columns and explode each of them independently, including empty-list
 * handling, before applying the required composite sorts.
 */
export function normalizeInventory(bundle) {
  if (bundle.gateways.length === 0) {
    return { services: [], upstreams: [], routes: [] };
  }

  const gateways = pl.DataFrame({
    gateway_id: bundle.gateways.map((gateway) => gateway.gateway_id),
    service_json: bundle.gateways.map((gateway) => (
      gateway.services.map((service) => JSON.stringify(service))
    )),
  });

  const explodedServices = gateways
    .explode('service_json')
    .toRecords()
    .filter((row) => typeof row.service_json === 'string')
    .map((row) => ({
      gateway_id: row.gateway_id,
      service: JSON.parse(row.service_json),
    }));

  const services = [];
  const upstreams = [];
  const routes = [];

  for (const { gateway_id: gatewayId, service } of explodedServices) {
    services.push({
      gateway_id: gatewayId,
      service_id: service.service_id,
      circuit_breaker_enabled: service.circuit_breaker.enabled,
      rate_limit_enabled: service.rate_limit.enabled,
      rate_limit_requests_per_minute: service.rate_limit.requests_per_minute,
      retry_max_attempts: service.retry.max_attempts,
    });

    // TODO: replace these first-element shortcuts with Polars explode calls.
    const firstUpstream = (service.upstreams || [])[0];
    if (firstUpstream) {
      upstreams.push({
        gateway_id: gatewayId,
        service_id: service.service_id,
        upstream_id: firstUpstream.upstream_id,
        timeout_ms: firstUpstream.timeout_ms,
      });
    }

    const firstRoute = (service.routes || [])[0];
    if (firstRoute) {
      routes.push({
        gateway_id: gatewayId,
        service_id: service.service_id,
        path: firstRoute.path,
        rate_limit_per_minute: firstRoute.rate_limit_per_minute,
      });
    }
  }

  services.sort((a, b) => compareText(a.service_id, b.service_id));
  upstreams.sort((a, b) => compareText(a.upstream_id, b.upstream_id));
  routes.sort((a, b) => compareText(a.path, b.path));

  return { services, upstreams, routes };
}
