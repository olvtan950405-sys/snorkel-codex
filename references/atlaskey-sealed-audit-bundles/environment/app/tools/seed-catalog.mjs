#!/usr/bin/env node
// Builds the development trust catalog from data/trust-catalog.sql.
// Usage: node /app/tools/seed-catalog.mjs [sql-file] [duckdb-file]
import { existsSync, readFileSync, rmSync } from 'node:fs';
import { DuckDBInstance } from '@duckdb/node-api';

const sqlPath = process.argv[2] ?? '/app/data/trust-catalog.sql';
const dbPath = process.argv[3] ?? '/app/data/trust-catalog.duckdb';

if (existsSync(dbPath)) rmSync(dbPath);

const instance = await DuckDBInstance.create(dbPath);
const connection = await instance.connect();

const sql = readFileSync(sqlPath, 'utf8')
  .split('\n')
  .filter((line) => !line.trimStart().startsWith('--'))
  .join('\n');

for (const statement of sql.split(';')) {
  if (statement.trim() === '') continue;
  await connection.run(statement);
}

connection.closeSync();
instance.closeSync();
process.stdout.write(`seeded ${dbPath}\n`);
