"""Build the small offline incident fixture; the verifier uses different data."""
import base64, hashlib, json, subprocess
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as E

app = Path("/app")
media = app / "media"
incident = app / "incident"
media.mkdir(exist_ok=True); incident.mkdir(exist_ok=True)
capture = media / "relay-a.ts"
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                "testsrc2=size=128x72:rate=4", "-t", "1", "-c:v", "mpeg2video",
                "-f", "mpegts", str(capture)], check=True)
args = ["ffprobe", "-v", "error", "-show_entries",
        "format=format_name,duration:stream=index,codec_type,codec_name,time_base,width,height,sample_rate,channels",
        "-of", "json", str(capture)]
raw = json.loads(subprocess.check_output(args))
seconds, _, fraction = raw["format"]["duration"].partition(".")
streams = []
for value in raw["streams"]:
    ratio = Fraction(value["time_base"])
    row = {"index": int(value["index"]), "type": value["codec_type"],
           "codec": value["codec_name"], "time_base": f"{ratio.numerator}/{ratio.denominator}"}
    if row["type"] == "video":
        row.update(width=int(value["width"]), height=int(value["height"]))
    else:
        row.update(sample_rate=int(value["sample_rate"]), channels=int(value["channels"]))
    streams.append(row)
record = {"media": "relay-a.ts",
          "format": ",".join(sorted(set(x.strip() for x in raw["format"]["format_name"].split(",")))),
          "duration_us": int(seconds) * 1_000_000 + int((fraction + "000000")[:6]),
          "streams": sorted(streams, key=lambda x: x["index"])}
digest = hashlib.sha256(json.dumps(record, separators=(",", ":")).encode()).hexdigest()
key = incident / "fixture-key.pem"
subprocess.run(["openssl", "genpkey", "-algorithm", "ED25519", "-out", str(key)], check=True)
der = subprocess.check_output(["openssl", "pkey", "-in", str(key), "-pubout", "-outform", "DER"])
public = base64.b64encode(der[-32:]).decode()
message = "\0".join(["relaycast-edge-v1", "e1", "capture", "relay", "relay-a.ts", digest]).encode()
msg = incident / "message.bin"; sig = incident / "signature.bin"; msg.write_bytes(message)
subprocess.run(["openssl", "pkeyutl", "-sign", "-rawin", "-inkey", str(key),
                "-in", str(msg), "-out", str(sig)], check=True)
signature = base64.b64encode(sig.read_bytes()).decode()
ns = "http://graphml.graphdrawing.org/xmlns"; E.register_namespace("", ns)
root = E.Element(f"{{{ns}}}graphml")
for kid, target, name in [("pk", "graph", "public_key"), ("m", "edge", "media"),
                          ("d", "edge", "probe_digest"), ("s", "edge", "signature")]:
    E.SubElement(root, f"{{{ns}}}key", id=kid, **{"for": target, "attr.name": name,
                                                   "attr.type": "string"})
graph = E.SubElement(root, f"{{{ns}}}graph", id="incident-6", edgedefault="directed")
E.SubElement(graph, f"{{{ns}}}data", key="pk").text = public
for node in ("capture", "relay"): E.SubElement(graph, f"{{{ns}}}node", id=node)
edge = E.SubElement(graph, f"{{{ns}}}edge", id="e1", source="capture", target="relay")
for kid, value in [("m", "relay-a.ts"), ("d", digest), ("s", signature)]:
    E.SubElement(edge, f"{{{ns}}}data", key=kid).text = value
E.ElementTree(root).write(incident / "topology.graphml", encoding="utf-8", xml_declaration=True)
for path in (key, msg, sig): path.unlink()
