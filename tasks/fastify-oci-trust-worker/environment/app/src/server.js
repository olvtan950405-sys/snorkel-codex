import Fastify from 'fastify';
import fs from 'node:fs';
import { evaluate } from './verifier.js';

function options(args) {
  const out = {};
  for (let i = 0; i < args.length; i += 2) {
    if (!['--request', '--out'].includes(args[i]) || !args[i + 1] || out[args[i]]) return null;
    out[args[i]] = args[i + 1];
  }
  return out['--request'] && out['--out'] && args.length === 4 ? out : null;
}

export async function runCli(args) {
  const o = options(args);
  if (!o) return 2;
  try { evaluate(JSON.parse(fs.readFileSync(o['--request'], 'utf8')), o['--out']); return 0; }
  catch (error) { console.error(error.message); return 2; }
}

export async function start(port) {
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('invalid port');
  const app = Fastify({ logger: false, bodyLimit: 1024 * 1024 });
  app.get('/healthz', async (_request, reply) => reply.type('application/json').send({status:'ok'}));
  app.post('/v1/admissions', async (request, reply) => {
    try {
      const out = request.headers['x-output-directory'];
      if (typeof out !== 'string') return reply.code(400).send({error:'invalid_request'});
      const result = evaluate(request.body, out);
      return reply.code(result.status === 'accepted' ? 200 : 422).send(result);
    } catch { return reply.code(400).send({error:'invalid_request'}); }
  });
  await app.listen({ host: '127.0.0.1', port });
}
