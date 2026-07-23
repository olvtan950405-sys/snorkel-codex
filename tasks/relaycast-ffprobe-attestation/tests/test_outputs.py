from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import pytest

APP = Path(os.environ.get("APP_DIR", "/app"))


def compact(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def normalize(media: str, path: Path):
    args = ["ffprobe", "-v", "error", "-show_entries",
            "format=format_name,duration:stream=index,codec_type,codec_name,time_base,width,height,sample_rate,channels",
            "-of", "json", str(path)]
    raw = json.loads(subprocess.check_output(args))
    micros = int((raw["format"]["duration"] + ".000000").split(".")[0]) * 1_000_000
    frac = raw["format"]["duration"].partition(".")[2]
    micros += int((frac + "000000")[:6])
    streams = []
    for item in raw["streams"]:
        f = Fraction(item["time_base"])
        row = {"index": int(item["index"]), "type": item["codec_type"],
               "codec": item["codec_name"], "time_base": f"{f.numerator}/{f.denominator}"}
        if row["type"] == "video":
            row.update(width=int(item["width"]), height=int(item["height"]))
        else:
            row.update(sample_rate=int(item["sample_rate"]), channels=int(item["channels"]))
        streams.append(row)
    streams.sort(key=lambda x: x["index"])
    formats = ",".join(sorted(set(x.strip() for x in raw["format"]["format_name"].split(","))))
    record = {"media": media, "format": formats, "duration_us": micros, "streams": streams}
    return record, hashlib.sha256(compact(record)).hexdigest()


def edge_message(edge):
    fields = ["relaycast-edge-v1", edge["id"], edge["source"], edge["target"],
              edge["media"], edge["probe_digest"]]
    return "\0".join(fields).encode()


def merkle(edges):
    level = [hashlib.sha256(b"relaycast-leaf-v1\0" + compact(e)).digest() for e in edges]
    while len(level) > 1:
        level = [hashlib.sha256(b"relaycast-node-v1\0" + level[i] +
                                (level[i + 1] if i + 1 < len(level) else level[i])).digest()
                 for i in range(0, len(level), 2)]
    return level[0].hex()


def sign(key: Path, message: bytes, tmp: Path):
    msg = tmp / "message.bin"
    sig = tmp / "signature.bin"
    msg.write_bytes(message)
    subprocess.run(["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(key),
                    "-in", str(msg), "-out", str(sig)], check=True, capture_output=True)
    return base64.b64encode(sig.read_bytes()).decode()


def make_graph(base: Path, media_root: Path, names=("zeta.ts", "nested/alpha.ts", "middle.ts")):
    key = base / "key.pem"
    subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(key)], check=True,
                   capture_output=True)
    der = subprocess.check_output(["openssl", "pkey", "-in", str(key), "-pubout", "-outform", "DER"])
    pub = base64.b64encode(der[-32:]).decode()
    ns = "http://graphml.graphdrawing.org/xmlns"
    ET.register_namespace("", ns)
    root = ET.Element(f"{{{ns}}}graphml")
    for kid, target, name in [("pk", "graph", "public_key"), ("m", "edge", "media"),
                              ("d", "edge", "probe_digest"), ("s", "edge", "signature")]:
        ET.SubElement(root, f"{{{ns}}}key", id=kid, **{"for": target, "attr.name": name,
                                                       "attr.type": "string"})
    graph = ET.SubElement(root, f"{{{ns}}}graph", id="incident-fresh", edgedefault="directed")
    ET.SubElement(graph, f"{{{ns}}}data", key="pk").text = pub
    for node in ("ingest", "relay", "egress"):
        ET.SubElement(graph, f"{{{ns}}}node", id=node)
    edges = []
    for pos, media in enumerate(names):
        record, digest = normalize(media, media_root / media)
        edge = {"id": ["edge-z", "edge-a", "edge-m"][pos],
                "source": ["ingest", "relay", "ingest"][pos],
                "target": ["relay", "egress", "egress"][pos],
                "media": media, "probe_digest": digest}
        edge["signature"] = sign(key, edge_message(edge), base)
        edges.append(edge)
        xe = ET.SubElement(graph, f"{{{ns}}}edge", id=edge["id"], source=edge["source"],
                           target=edge["target"])
        for kid, name in [("m", "media"), ("d", "probe_digest"), ("s", "signature")]:
            ET.SubElement(xe, f"{{{ns}}}data", key=kid).text = edge[name]
    path = base / "topology.graphml"
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    edges.sort(key=lambda x: x["id"])
    expected = {"schema": "relaycast.provenance/v1", "graph_id": "incident-fresh",
                "public_key": pub, "edges": edges, "merkle_root": merkle(edges)}
    return path, expected


def request(port, route, body):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{route}", data=compact(body),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return res.status, json.load(res)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


@pytest.fixture(scope="session")
def harness(tmp_path_factory):
    base = tmp_path_factory.mktemp("relay")
    media = base / "media"
    (media / "nested").mkdir(parents=True)
    seed = media / "zeta.ts"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=160x96:rate=5", "-t", "1", "-c:v", "mpeg2video", "-f", "mpegts",
                    str(seed)], check=True)
    shutil.copyfile(seed, media / "nested/alpha.ts")
    shutil.copyfile(seed, media / "middle.ts")
    graph, expected = make_graph(base, media)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
    env = os.environ.copy(); env.update(MEDIA_ROOT=str(media), LISTEN_ADDR=f"127.0.0.1:{port}")
    proc = subprocess.Popen([str(APP / "bin/relaycast")], env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    for _ in range(60):
        if proc.poll() is not None: pytest.fail("relaycast server exited")
        try:
            request(port, "/v1/probe", {"media": "zeta.ts"}); break
        except OSError: time.sleep(.1)
    yield base, media, graph, expected, port, env
    proc.terminate(); proc.wait(timeout=5)


def test_probe_is_canonical_and_digest_bound(harness):
    _, media, _, _, port, _ = harness
    status, body = request(port, "/v1/probe", {"media": "nested/alpha.ts"})
    record, digest = normalize("nested/alpha.ts", media / "nested/alpha.ts")
    assert status == 200
    assert body == {"record": record, "digest": digest}


def test_attestation_matches_independent_merkle_oracle(harness):
    _, _, graph, expected, port, _ = harness
    status, body = request(port, "/v1/attest", {"graphml": str(graph)})
    assert status == 200
    assert body == expected
    assert [e["id"] for e in body["edges"]] == ["edge-a", "edge-m", "edge-z"]


def test_offline_reproduce_is_byte_deterministic(harness, tmp_path):
    _, _, graph, expected, _, env = harness
    out = tmp_path / "deep/out/report.json"
    result = subprocess.run([str(APP / "bin/relaycast"), "reproduce", "--graph", str(graph),
                             "--out", str(out)], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert out.read_bytes() == compact(expected) + b"\n"
    assert not (Path(str(out) + ".tmp")).exists()


def test_tampering_is_atomic_and_rejected(harness, tmp_path):
    _, _, graph, _, port, env = harness
    bad = tmp_path / "tampered.graphml"
    text = graph.read_text().replace("edge-z", "edge-x", 1)
    bad.write_text(text)
    status, body = request(port, "/v1/attest", {"graphml": str(bad)})
    assert status == 422 and body["error"]["code"] == "invalid_evidence"
    out = tmp_path / "must-not-exist.json"
    result = subprocess.run([str(APP / "bin/relaycast"), "reproduce", "--graph", str(bad),
                             "--out", str(out)], env=env, capture_output=True)
    assert result.returncode != 0 and not out.exists()


def test_request_strictness_and_path_defenses(harness, tmp_path):
    _, media, _, _, port, _ = harness
    status, body = request(port, "/v1/probe", {"media": "../topology.graphml"})
    assert status == 422 and set(body) == {"error"}
    status, body = request(port, "/v1/probe", {"media": "zeta.ts", "extra": True})
    assert status == 400 and body["error"]["code"] == "bad_request"
    outside = tmp_path / "outside.ts"; shutil.copyfile(media / "zeta.ts", outside)
    (media / "link.ts").symlink_to(outside)
    status, _ = request(port, "/v1/probe", {"media": "link.ts"})
    assert status == 422
