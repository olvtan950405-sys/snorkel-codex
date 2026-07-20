// Reader for the current seal footer (magic "AKB2").
//
// TODO(ATK-2291): Sealer 2.0 shipped without an updated format specification, so this was
// never finished. seal-v1.js still says what every field means and how the MAC is taken;
// docs/vendor/CHANGELOG.md is all the vendor has given us about the new layout.

export const V2_MAGIC = Buffer.from('AKB2', 'ascii');

export function parseSealV2(seal) {
  if (seal.length < 4 || !seal.subarray(0, 4).equals(V2_MAGIC)) {
    throw new Error('not a v2 seal');
  }
  throw new Error('v2 seal parsing is not implemented');
}
