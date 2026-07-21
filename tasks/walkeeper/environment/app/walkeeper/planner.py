"""Incomplete migration: the output looks useful, but recovery semantics are wrong."""
import csv, json
from pathlib import Path

def _rows(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))

def plan(root: Path, output: Path):
    backups = _rows(root / "backups.tsv")
    segments = _rows(root / "segments.tsv")
    policy = json.loads((root / "policy.json").read_text())
    # BUGS: ignores history ancestry, accepts partial segments, compares WAL names
    # lexically, and protects only the selected backup rather than its WAL chain.
    complete = {s["name"] for s in segments if s["state"] != "missing"}
    verdicts = []
    for b in backups:
        target = int(b["target_lsn"].split("/")[1], 16)
        target_wal = f"{int(b['timeline']):08X}00000000{max(0, target // policy['segment_size'] - 1):08X}"
        needed = [s for s in complete if b["start_wal"] <= s <= target_wal]
        ok = b["start_wal"] in complete and target_wal in complete
        verdicts.append({"backup_id": b["backup_id"], "recoverable": ok,
                         "reason": "ok" if ok else "wal_gap", "required_segments": sorted(needed)})
    valid = [v for v in verdicts if v["recoverable"]]
    selected = max(valid, key=lambda v: v["backup_id"])["backup_id"] if valid else None
    keep = {selected} if selected else set()
    report = {"schema_version": 1, "selected_backup": selected,
              "backups": sorted(verdicts, key=lambda x: x["backup_id"]),
              "retention": {"keep_backups": sorted(keep), "delete_backups": sorted(set(b["backup_id"] for b in backups)-keep),
                            "keep_segments": [], "delete_segments": sorted(complete)}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n")
