"""Reference primitives for the release-attestation verifier.

Implements the Ed25519 signature scheme (RFC 8032), the canonical JSON encoding used as the
signing preimage, and a PNG badge writer that embeds an attestation payload in private ancillary
``atSt`` chunks.  Kept dependency-free so the verifier runs with no network access.
"""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from typing import Any

# ---------------------------------------------------------------------------
# Ed25519 (RFC 8032), reference implementation over the twisted Edwards curve.
# ---------------------------------------------------------------------------

_P = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493
_D = (-121665 * pow(121666, _P - 2, _P)) % _P
_SQRT_MINUS_1 = pow(2, (_P - 1) // 4, _P)

_IDENTITY = (0, 1, 1, 0)


def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def _recover_x(y: int) -> int:
    numerator = (y * y - 1) % _P
    denominator = (_D * y * y + 1) % _P
    xx = (numerator * pow(denominator, _P - 2, _P)) % _P
    x = pow(xx, (_P + 3) // 8, _P)
    if (x * x - xx) % _P != 0:
        x = (x * _SQRT_MINUS_1) % _P
    if x % 2 != 0:
        x = _P - x
    return x


_BASE_Y = (4 * pow(5, _P - 2, _P)) % _P
_BASE_X = _recover_x(_BASE_Y)
_BASE = (_BASE_X, _BASE_Y, 1, (_BASE_X * _BASE_Y) % _P)


def _point_add(p: tuple[int, int, int, int], q: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x1, y1, z1, t1 = p
    x2, y2, z2, t2 = q
    a = ((y1 - x1) * (y2 - x2)) % _P
    b = ((y1 + x1) * (y2 + x2)) % _P
    c = (2 * _D * t1 * t2) % _P
    d = (2 * z1 * z2) % _P
    e = (b - a) % _P
    f = (d - c) % _P
    g = (d + c) % _P
    h = (b + a) % _P
    return ((e * f) % _P, (g * h) % _P, (f * g) % _P, (e * h) % _P)


def _scalar_mult(point: tuple[int, int, int, int], scalar: int) -> tuple[int, int, int, int]:
    result = _IDENTITY
    addend = point
    while scalar > 0:
        if scalar & 1:
            result = _point_add(result, addend)
        addend = _point_add(addend, addend)
        scalar >>= 1
    return result


def _encode_point(point: tuple[int, int, int, int]) -> bytes:
    x, y, z, _ = point
    z_inverse = pow(z, _P - 2, _P)
    x = (x * z_inverse) % _P
    y = (y * z_inverse) % _P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _secret_scalar(seed: bytes) -> int:
    digest = _sha512(seed)
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    return scalar


def public_key(seed: bytes) -> bytes:
    """Return the 32-byte Ed25519 public key for a 32-byte seed."""
    return _encode_point(_scalar_mult(_BASE, _secret_scalar(seed)))


def sign(seed: bytes, message: bytes) -> bytes:
    """Return the 64-byte Ed25519 signature of ``message`` under the key derived from ``seed``."""
    digest = _sha512(seed)
    scalar = _secret_scalar(seed)
    encoded_public = _encode_point(_scalar_mult(_BASE, scalar))

    nonce = int.from_bytes(_sha512(digest[32:] + message), "little") % _L
    encoded_nonce = _encode_point(_scalar_mult(_BASE, nonce))

    challenge = int.from_bytes(_sha512(encoded_nonce + encoded_public + message), "little") % _L
    signature_scalar = (nonce + challenge * scalar) % _L
    return encoded_nonce + signature_scalar.to_bytes(32, "little")


def verify(raw_public_key: bytes, message: bytes, signature: bytes) -> bool:
    """Return whether ``signature`` is a valid Ed25519 signature of ``message`` under the key."""
    if len(signature) != 64 or len(raw_public_key) != 32:
        return False
    try:
        point_a = _decode_point(raw_public_key)
    except ValueError:
        return False

    encoded_nonce = signature[:32]
    signature_scalar = int.from_bytes(signature[32:], "little")
    if signature_scalar >= _L:
        return False

    challenge = int.from_bytes(_sha512(encoded_nonce + raw_public_key + message), "little") % _L
    left = _scalar_mult(_BASE, signature_scalar)
    right = _point_add(_decode_point(encoded_nonce), _scalar_mult(point_a, challenge))
    return _encode_point(left) == _encode_point(right)


def _decode_point(encoded: bytes) -> tuple[int, int, int, int]:
    value = int.from_bytes(encoded, "little")
    sign = (value >> 255) & 1
    y = value & ((1 << 255) - 1)
    if y >= _P:
        raise ValueError("y coordinate out of range")
    x = _recover_x(y)
    if x == 0 and sign:
        raise ValueError("invalid point encoding")
    if (x & 1) != sign:
        x = _P - x
    return (x, y, 1, (x * y) % _P)


_SPKI_ED25519_PREFIX = bytes.fromhex("302a300506032b6570032100")


def spki_der(raw_public_key: bytes) -> bytes:
    """Wrap a raw 32-byte Ed25519 public key in a SubjectPublicKeyInfo DER structure."""
    return _SPKI_ED25519_PREFIX + raw_public_key


# ---------------------------------------------------------------------------
# Canonical JSON: recursively key-sorted, compact, UTF-8, no trailing newline.
# ---------------------------------------------------------------------------


def _encode_value(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(_encode_value(item) for item in value) + "]"
    if isinstance(value, dict):
        members = [
            json.dumps(key, ensure_ascii=False) + ":" + _encode_value(value[key])
            for key in sorted(value)
        ]
        return "{" + ",".join(members) + "}"
    raise TypeError(f"value of type {type(value).__name__} is not JSON serializable")


def canonical_json(value: Any) -> bytes:
    """Serialize ``value`` to canonical JSON bytes (sorted keys, compact, no trailing newline)."""
    return _encode_value(value).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Attestation payloads and PNG badges.
# ---------------------------------------------------------------------------

ATTESTATION_CHUNK_TYPE = b"atSt"

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def build_attestation(statement: dict[str, Any], seed: bytes) -> dict[str, Any]:
    """Sign ``statement`` with ``seed`` and return the full attestation document."""
    import base64

    signature = sign(seed, canonical_json(statement))
    return {"signature": base64.b64encode(signature).decode("ascii"), "statement": statement}


def _png_chunk(chunk_type: bytes, data: bytes, *, corrupt_crc: bool = False) -> bytes:
    checksum = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    if corrupt_crc:
        checksum ^= 0x00000001
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", checksum)


def _split(payload: bytes, segments: int) -> list[bytes]:
    if segments < 1:
        raise ValueError("segments must be at least 1")
    size = max(1, (len(payload) + segments - 1) // segments)
    parts = [payload[index : index + size] for index in range(0, len(payload), size)]
    while len(parts) < segments:
        parts.append(b"")
    return parts


def build_badge_png(
    payload: bytes,
    *,
    segments: int = 2,
    corrupt_crc: bool = False,
    omit_payload: bool = False,
) -> bytes:
    """Return a valid 1x1 PNG carrying ``payload`` across ``segments`` ``atSt`` chunks."""
    header = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    scanline = b"\x00\x7f\x7f\x7f"
    image = zlib.compress(scanline, 9)

    parts = [_PNG_MAGIC, _png_chunk(b"IHDR", header)]
    if not omit_payload:
        for index, segment in enumerate(_split(payload, segments)):
            parts.append(
                _png_chunk(
                    ATTESTATION_CHUNK_TYPE,
                    segment,
                    corrupt_crc=corrupt_crc and index == 0,
                )
            )
    parts.append(_png_chunk(b"IDAT", image))
    parts.append(_png_chunk(b"IEND", b""))
    return b"".join(parts)
