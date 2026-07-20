#!/usr/bin/env node
import { createApp } from '../src/app.js';

function parsePort(argv) {
  let port = 8080;
  for (let index = 0; index < argv.length; index += 1) {
    if (argv[index] !== '--port') {
      throw new Error(`unknown argument: ${argv[index]}`);
    }
    if (index + 1 >= argv.length) throw new Error('missing value for --port');
    port = Number(argv[index + 1]);
    index += 1;
  }
  if (!Number.isInteger(port) || port < 0 || port > 65535) {
    throw new Error('port must be an integer from 0 to 65535');
  }
  return port;
}

function main() {
  const port = parsePort(process.argv.slice(2));
  const app = createApp();
  const server = app.listen(port, () => {
    process.stdout.write(`LISTENING ${server.address().port}\n`);
  });
  server.on('error', (error) => {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  });
}

try {
  main();
} catch (error) {
  process.stderr.write(`${error.message}\n`);
  process.exit(1);
}
