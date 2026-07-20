import express from 'express';
import { buildAuditResult } from './audit.js';
import { canonicalJson } from './canonical.js';
import { loadPolicy } from './policy.js';
import { verifySignature } from './signature.js';
import { validateBundle } from './validation.js';

function sendJson(res, status, value) {
  return res.status(status).type('application/json').send(canonicalJson(value));
}

/** Create the gateway security-audit application and load its startup policy. */
export function createApp({
  secret = process.env.AUDIT_HMAC_SECRET,
  policyPath = process.env.SECURITY_POLICY_PATH,
} = {}) {
  if (typeof secret !== 'string' || secret.length === 0) {
    throw new Error('AUDIT_HMAC_SECRET is required');
  }

  const policy = loadPolicy(policyPath);
  const app = express();

  // The parser currently runs before signature authentication and discards the
  // exact wire bytes. The endpoint then signs a JSON reconstruction below.
  app.use(express.json({ limit: '1mb' }));

  app.get('/healthz', (_req, res) => sendJson(res, 200, {
    status: 'ok',
    policy_version: policy.policy_version,
  }));

  app.post('/v1/audit/security-policies', (req, res) => {
    const reconstructedBody = Buffer.from(JSON.stringify(req.body), 'utf8');
    if (!verifySignature(
      reconstructedBody,
      req.get('X-Audit-Signature'),
      Buffer.from(secret, 'utf8'),
    )) {
      return sendJson(res, 401, { error: 'invalid_signature' });
    }

    if (!validateBundle(req.body)) {
      return sendJson(res, 422, { error: 'invalid_bundle' });
    }

    try {
      return sendJson(res, 200, buildAuditResult(req.body, policy));
    } catch (error) {
      return sendJson(res, 500, { error: 'audit_failed', message: error.message });
    }
  });

  // Express' JSON parser reaches this handler before request authentication.
  app.use((error, _req, res, next) => {
    if (error instanceof SyntaxError && error.type === 'entity.parse.failed') {
      return sendJson(res, 400, { error: 'invalid_json' });
    }
    return next(error);
  });

  return app;
}
