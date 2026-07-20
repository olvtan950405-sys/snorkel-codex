import { sha256Hex } from '../canonical.js';

// The event table is a Parquet member inside the bundle.
//
// TODO: this is a placeholder. It digests the raw Parquet bytes, which is not what the seal
// commits to, and it does not read a single event row. nodejs-polars is already a dependency.
export function summarizeEvents(parquetBytes) {
  return {
    eventCount: 0,
    highRiskEvents: 0,
    contentDigest: sha256Hex(parquetBytes),
  };
}
