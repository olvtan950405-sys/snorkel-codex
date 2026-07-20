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
 * credential and route expansions are still placeholders which retain only the
 * first nested item. A complete implementation should model those lists as
 * Polars columns and explode each of them independently, including empty-list
 * handling, before applying the required composite sorts.
 */
export function normalizeInventory(bundle) {
  if (bundle.gateways.length === 0) {
    return { services: [], credentials: [], routes: [] };
  }

  // JSON strings are used as list values because nodejs-polars' JavaScript
  // constructor cannot infer a List<Struct> when the struct itself has nested
  // lists. The explode operation still owns the cardinality transformation.
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
  const credentials = [];
  const routes = [];

  for (const { gateway_id: gatewayId, service } of explodedServices) {
    services.push({
      gateway_id: gatewayId,
      service_id: service.service_id,
      // TODO: de-duplicate and sort cipher_suites before emitting evidence.
      cipher_suites: [...service.tls.cipher_suites],
      mutual_tls: service.tls.mutual_tls,
      tls_minimum_version: service.tls.minimum_version,
    });

    // TODO: replace these first-element shortcuts with Polars explode calls.
    const firstCredential = (service.credentials || [])[0];
    if (firstCredential) {
      credentials.push({
        gateway_id: gatewayId,
        service_id: service.service_id,
        credential_id: firstCredential.credential_id,
        key_type: firstCredential.key_type,
        key_bits: firstCredential.key_bits,
        secret_ref: firstCredential.secret_ref,
        inline: firstCredential.inline,
      });
    }

    const firstRoute = (service.routes || [])[0];
    if (firstRoute) {
      routes.push({
        gateway_id: gatewayId,
        service_id: service.service_id,
        path: firstRoute.path,
        methods: [...(firstRoute.methods || [])],
        authentication: firstRoute.authentication,
      });
    }
  }

  services.sort((a, b) => compareText(a.service_id, b.service_id));
  credentials.sort((a, b) => compareText(a.credential_id, b.credential_id));
  routes.sort((a, b) => compareText(a.path, b.path));

  return { services, credentials, routes };
}
