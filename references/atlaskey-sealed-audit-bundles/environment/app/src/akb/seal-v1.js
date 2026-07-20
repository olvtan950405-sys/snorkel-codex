// Reader for the legacy v1 seal footer (magic "AKB1").
//
// Kept because the archive vault still holds pre-2026 v1 bundles and support needs to be
// able to open them with /app/tools/inspect-seal.mjs. The v1 wire layout is fully described
// in /app/docs/vendor/akb-format.md; the fields it carries mean exactly what they mean in
// the current format, so this file is also the reference for what a seal *is*.
//
// The audit endpoint itself no longer accepts v1 bundles: the fleet was migrated in May.

export const V1_MAGIC = Buffer.from('AKB1', 'ascii');
const MAC_BYTES = 32;

class Cursor {
  constructor(buf) {
    this.buf = buf;
    this.off = 0;
  }

  take(n) {
    if (this.off + n > this.buf.length) throw new Error('seal footer is truncated');
    const slice = this.buf.subarray(this.off, this.off + n);
    this.off += n;
    return slice;
  }

  u8() {
    return this.take(1)[0];
  }

  u16be() {
    return this.take(2).readUInt16BE(0);
  }

  u32be() {
    return this.take(4).readUInt32BE(0);
  }

  i64be() {
    return Number(this.take(8).readBigInt64BE(0));
  }

  lengthPrefixedString() {
    const len = this.u8();
    return this.take(len).toString('utf8');
  }
}

export function parseSealV1(seal) {
  if (seal.length < 4 || !seal.subarray(0, 4).equals(V1_MAGIC)) {
    throw new Error('not a v1 seal');
  }

  const cur = new Cursor(seal);
  cur.take(4); // magic
  const version = cur.u16be();
  if (version !== 1) throw new Error(`unsupported v1 seal version ${version}`);
  const flags = cur.u16be();
  if (flags !== 0) throw new Error(`reserved flag bits are set: ${flags}`);

  const tenantId = cur.lengthPrefixedString();
  const algorithm = cur.lengthPrefixedString();
  const keyEpoch = cur.u32be();
  const sealedAtMs = cur.i64be();
  const gcmIv = Buffer.from(cur.take(12));
  const gcmTag = Buffer.from(cur.take(16));
  const ciphertext = Buffer.from(cur.take(cur.u32be()));

  // The MAC authenticates every byte of the footer that precedes it.
  const macOffset = cur.off;
  const mac = Buffer.from(cur.take(MAC_BYTES));
  if (cur.off !== seal.length) throw new Error('trailing bytes after v1 seal');

  return {
    formatVersion: 1,
    tenantId,
    algorithm,
    keyEpoch,
    sealedAtMs,
    gcmIv,
    gcmTag,
    ciphertext,
    mac,
    macCovered: seal.subarray(0, macOffset),
  };
}
