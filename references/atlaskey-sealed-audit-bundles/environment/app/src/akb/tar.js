// Minimal ustar reader. Sealed bundles are plain uncompressed tars written by the
// signing stations, so this is all the tar support the service needs.

const BLOCK = 512;

function field(header, offset, length) {
  const raw = header.subarray(offset, offset + length);
  const end = raw.indexOf(0);
  return raw.subarray(0, end === -1 ? raw.length : end).toString('ascii');
}

function octal(header, offset, length) {
  const text = field(header, offset, length).trim();
  if (text === '') return 0;
  const value = parseInt(text, 8);
  if (!Number.isFinite(value)) throw new Error('malformed tar numeric field');
  return value;
}

export function readTar(buf) {
  const members = new Map();
  let off = 0;

  while (off + BLOCK <= buf.length) {
    const header = buf.subarray(off, off + BLOCK);
    if (header.every((byte) => byte === 0)) break; // end-of-archive marker

    const name = field(header, 0, 100);
    if (name === '') throw new Error('tar member has no name');
    const size = octal(header, 124, 12);
    const typeflag = String.fromCharCode(header[156]);

    const dataStart = off + BLOCK;
    const dataEnd = dataStart + size;
    if (dataEnd > buf.length) throw new Error(`tar member ${name} is truncated`);

    if (typeflag === '0' || typeflag === '\0') {
      members.set(name, buf.subarray(dataStart, dataEnd));
    }

    off = dataEnd;
  }

  if (members.size === 0) throw new Error('archive contains no regular files');
  return members;
}
