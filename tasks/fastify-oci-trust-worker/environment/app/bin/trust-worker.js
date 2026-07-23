#!/usr/bin/env node
import { start, runCli } from '../src/server.js';

const args = process.argv.slice(2);
if (args[0] === 'verify') process.exitCode = await runCli(args.slice(1));
else if (args[0] === '--port' && args[1] && args.length === 2) await start(Number(args[1]));
else { console.error('usage: trust-worker.js verify --request FILE --out DIR | --port PORT'); process.exitCode = 2; }
