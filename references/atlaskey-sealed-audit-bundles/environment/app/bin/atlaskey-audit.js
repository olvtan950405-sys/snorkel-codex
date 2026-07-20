#!/usr/bin/env node
import { buildServer } from '../src/server.js';

function parsePort(argv) {
  const index = argv.indexOf('--port');
  if (index === -1) return 8080;
  const port = Number(argv[index + 1]);
  if (!Number.isInteger(port) || port < 0 || port > 65535) {
    process.stderr.write('usage: atlaskey-audit --port <n>\n');
    process.exit(2);
  }
  return port;
}

const port = parsePort(process.argv.slice(2));

try {
  const app = await buildServer();
  await app.listen({ port, host: '0.0.0.0' });
  process.stdout.write(`atlaskey audit service listening on ${port}\n`);

  for (const signal of ['SIGTERM', 'SIGINT']) {
    process.on(signal, () => {
      app.close().then(
        () => process.exit(0),
        () => process.exit(1),
      );
    });
  }
} catch (error) {
  process.stderr.write(`failed to start: ${error.message}\n`);
  process.exit(1);
}
