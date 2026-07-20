"""Create the deterministic, agent-visible ForgeGate example fixture."""

import base64
import hashlib
import json
import subprocess
from pathlib import Path


APP = Path("/app")
LAYOUT = APP / "data" / "layout"
INDEX_MT = "application/vnd.oci.image.index.v1+json"
MANIFEST_MT = "application/vnd.oci.image.manifest.v1+json"
CONFIG_MT = "application/vnd.oci.image.config.v1+json"
LAYER_MT = "application/vnd.oci.image.layer.v1.tar"
PRIVATE_KEYS = {
    "build-example": """-----BEGIN PRIVATE KEY-----
MC4CAQAwBQYDK2VwBCIEIOBrapDO3nFvcOnWZZXUVoT6V66vu26AgJDz3NE3mm+i
-----END PRIVATE KEY-----
""",
    "security-example": """-----BEGIN PRIVATE KEY-----
MC4CAQAwBQYDK2VwBCIEILeKtFYL1sCs9Rf0Fha+G3vbwMzyLpx7rhHINWJ/ckkf
-----END PRIVATE KEY-----
""",
}


def canonical(value):
    """Encode canonical JSON bytes."""
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256(data):
    """Return an OCI digest."""
    return "sha256:" + hashlib.sha256(data).hexdigest()


def blob(value, media_type):
    """Write one deterministic OCI blob and return its descriptor."""
    raw = value if isinstance(value, bytes) else canonical(value)
    identifier = sha256(raw)
    path = LAYOUT / "blobs" / "sha256" / identifier.split(":", 1)[1]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {"mediaType": media_type, "digest": identifier, "size": len(raw)}


def write(path, value):
    """Write readable input JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def public_and_signature(key_id, payload):
    """Derive public PEM and sign one canonical payload with a fixed key."""
    private = Path("/tmp") / f"{key_id}.pem"
    message = Path("/tmp") / f"{key_id}.message"
    private.write_text(PRIVATE_KEYS[key_id])
    message.write_bytes(canonical(payload))
    public = subprocess.run(
        ["openssl", "pkey", "-in", private, "-pubout"],
        capture_output=True, text=True, check=True,
    ).stdout
    signature = subprocess.run(
        ["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", private, "-in", message],
        capture_output=True, check=True,
    ).stdout
    private.unlink()
    message.unlink()
    return public, base64.b64encode(signature).decode()


write(LAYOUT / "oci-layout", {"imageLayoutVersion": "1.0.0"})
config = blob({"architecture": "amd64", "os": "linux", "rootfs": {"diff_ids": [], "type": "layers"}}, CONFIG_MT)
layer = blob(b"deterministic forgegate example layer\n", LAYER_MT)
manifest = blob({"config": config, "layers": [layer], "mediaType": MANIFEST_MT, "schemaVersion": 2}, MANIFEST_MT)
manifest["platform"] = {"architecture": "amd64", "os": "linux"}
(LAYOUT / "index.json").write_bytes(canonical({"manifests": [manifest], "mediaType": INDEX_MT, "schemaVersion": 2}))

payload = {
    "builder_id": "builder://example/forge-v4",
    "build_finished": "2026-06-14T10:05:00.000Z",
    "build_started": "2026-06-14T10:00:00.000Z",
    "commit": "8b719d21b1109c288562a01706431046f00365c7",
    "materials": [{"digest": "sha256:" + "3" * 64, "uri": "https://git.example/release/payments"}],
    "ref": "refs/tags/v4.8.0",
    "source_uri": "https://git.example/release/payments",
    "subject_digest": manifest["digest"],
    "vulnerabilities": [{"advisory": "CVE-2026-4242", "package": "openssl", "severity": "high"}],
}
keys = []
signatures = []
for key_id, role in (("build-example", "builder"), ("security-example", "security")):
    public, signed = public_and_signature(key_id, payload)
    keys.append({
        "key_id": key_id, "builder_id": payload["builder_id"], "role": role,
        "public_key_pem": public, "active_from": "2026-01-01T00:00:00.000Z",
        "active_until": None, "revoked_at": None,
    })
    signatures.append({"key_id": key_id, "signature": signed})

write(LAYOUT / "evidence" / f"{manifest['digest'].split(':')[1]}.provenance.json",
      {"payload": payload, "signatures": signatures})
write(APP / "data" / "keyring.json", {"keys": keys})
write(APP / "data" / "policy.json", {
    "allowed_builders": [{"builder_id": payload["builder_id"],
                          "source_prefix": "https://git.example/release/", "ref_glob": "refs/tags/v*"}],
    "evaluation_time": "2026-06-15T12:00:00.000Z", "image": "registry.example/payments/api",
    "platforms": [{"architecture": "amd64", "os": "linux"}],
    "role_minimums": {"builder": 1, "security": 1}, "signature_threshold": 2,
    "trusted_material_prefixes": ["https://git.example/"],
})
write(APP / "data" / "waivers.json", {"waivers": [{
    "id": "WV-EXAMPLE-42", "image": "registry.example/payments/api", "platform": "linux-amd64",
    "advisory": "CVE-2026-4242", "package": "openssl", "builder_id": payload["builder_id"],
    "source_prefix": payload["source_uri"], "commit": payload["commit"],
    "starts_at": "2026-06-01T00:00:00.000Z", "expires_at": "2026-07-01T00:00:00.000Z",
}]})
