import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import Fastify from 'fastify';
import { canonicalJson } from './canonical.js';
import { loadConfig, loadKeyring } from './config.js';
import { TrustCatalog } from './catalog/trust-catalog.js';
import { verifyBundle } from './verify.js';

const BUNDLE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

function sendCanonical(reply, statusCode, body) {
  reply.code(statusCode).header('content-type', 'application/json').send(`${canonicalJson(body)}\n`);
}

export async function buildServer(env = process.env) {
  const config = loadConfig(env);

  if (!existsSync(config.catalogPath)) {
    throw new Error(`trust catalog not found at ${config.catalogPath}`);
  }
  const keyring = loadKeyring(config.keyringPath);
  const catalog = await TrustCatalog.open(config.catalogPath);

  const app = Fastify({ logger: false });
  app.addHook('onClose', async () => catalog.close());

  app.get('/healthz', async (_request, reply) => {
    sendCanonical(reply, 200, { status: 'ok' });
  });

  app.post('/audit-bundles/:bundleId/verify', async (request, reply) => {
    const { bundleId } = request.params;
    if (!BUNDLE_ID.test(bundleId)) {
      sendCanonical(reply, 400, { error: 'invalid_bundle_id' });
      return;
    }

    const path = join(config.bundleDir, `${bundleId}.akb`);
    if (!existsSync(path)) {
      sendCanonical(reply, 404, { error: 'bundle_not_found' });
      return;
    }

    const result = await verifyBundle({
      bundleId,
      archive: readFileSync(path),
      catalog,
      keyring,
    });
    sendCanonical(reply, 200, result);
  });

  app.setErrorHandler((error, _request, reply) => {
    process.stderr.write(`audit error: ${error && error.stack ? error.stack : error}\n`);
    sendCanonical(reply, 500, { error: 'internal_error' });
  });

  return app;
}
