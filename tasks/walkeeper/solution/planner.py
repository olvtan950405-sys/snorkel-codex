import csv, json, re
from pathlib import Path

WAL_RE = re.compile(r"^[0-9A-F]{24}$")
LSN_RE = re.compile(r"^([0-9A-F]+)/([0-9A-F]+)$")

def rows(path, fields):
    with path.open(newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        if not reader.fieldnames or not set(fields) <= set(reader.fieldnames):
            raise ValueError(f"missing columns in {path.name}")
        return list(reader)

def lsn(value):
    m = LSN_RE.fullmatch(value)
    if not m: raise ValueError("invalid LSN")
    return (int(m.group(1),16)<<32) + int(m.group(2),16)

def wal_name(timeline, pos, size):
    log, off = divmod(pos, 1<<32)
    seg = off // size
    return f"{timeline:08X}{log:08X}{seg:08X}"

def segment_valid(s, size):
    try:
        name=s["name"]
        if not WAL_RE.fullmatch(name) or s["state"] != "complete": return False
        tl=int(s["timeline"]); start=lsn(s["start_lsn"]); end=lsn(s["end_lsn"])
        return (int(name[:8],16)==tl and start % size == 0 and
                name==wal_name(tl,start,size) and end-start==size and
                int(s["size"])==size and bool(re.fullmatch(r"[0-9a-f]{64}",s["sha256"])))
    except (ValueError,KeyError): return False

def plan(root: Path, output: Path):
    backups=rows(root/"backups.tsv",["backup_id","started_at","timeline","start_lsn","start_wal","target_lsn"])
    segs=rows(root/"segments.tsv",["name","timeline","start_lsn","end_lsn","size","sha256","state"])
    histories=rows(root/"history.tsv",["timeline","parent","switch_lsn"])
    policy=json.loads((root/"policy.json").read_text())
    size=int(policy["segment_size"])
    hist={}
    duplicate=set()
    for h in histories:
        try: key=int(h["timeline"]); value=(int(h["parent"]),lsn(h["switch_lsn"]))
        except ValueError: continue
        if key in hist: duplicate.add(key)
        hist[key]=value
    byname={s["name"]:s for s in segs}

    def history_ok(tl):
        seen=set()
        while tl != 1:
            if tl in seen or tl in duplicate or tl not in hist: return False
            seen.add(tl); parent,sw=hist[tl]
            if parent>=tl or sw%size: return False
            tl=parent
        return True
    def timeline_at(tl,pos):
        while tl != 1 and pos < hist[tl][1]: tl=hist[tl][0]
        return tl

    verdicts=[]
    for b in backups:
        reason=None; required=[]
        try:
            tl=int(b["timeline"]); start=lsn(b["start_lsn"]); target=lsn(b["target_lsn"])
            if not WAL_RE.fullmatch(b["start_wal"]): reason="invalid_backup"
        except (ValueError,KeyError): reason="invalid_backup"; tl=1; start=target=0
        if not reason and tl != 1 and tl not in hist: reason="unknown_timeline"
        if not reason and not history_ok(tl): reason="invalid_history"
        start_tl=timeline_at(tl,start) if not reason else 1
        if not reason and b["start_wal"] != wal_name(start_tl,(start//size)*size,size): reason="start_segment_mismatch"
        if not reason and target < start: reason="target_before_start"
        if not reason:
            names=[]; missing=False; invalid=False
            pos=(start//size)*size
            while pos < target:
                name=wal_name(timeline_at(tl,pos),pos,size); names.append(name)
                s=byname.get(name)
                if s is None: missing=True
                elif not segment_valid(s,size): invalid=True
                pos += size
            if missing: reason="wal_gap"
            elif invalid: reason="invalid_segment"
            else: reason="ok"; required=names
        verdicts.append({"backup_id":b["backup_id"],"recoverable":reason=="ok","reason":reason,"required_segments":required,"_start":b.get("started_at",""),"_target":target})

    good=[v for v in verdicts if v["recoverable"]]
    selected=min(good,key=lambda v:(-v["_target"],v["_start"],v["backup_id"]))["backup_id"] if good else None
    # Correct the time tie: greatest time, then smallest id.
    if good:
        mt=max(v["_target"] for v in good); same=[v for v in good if v["_target"]==mt]
        ms=max(v["_start"] for v in same); selected=min(v["backup_id"] for v in same if v["_start"]==ms)
    keep=set(policy["protected_backup_ids"])
    if selected: keep.add(selected)
    newest=sorted(good,key=lambda v:(v["_start"],v["backup_id"]),reverse=True)
    keep.update(v["backup_id"] for v in newest[:int(policy["keep_newest"])])
    for v in newest:
        if sum(x["recoverable"] and x["backup_id"] in keep for x in verdicts)>=int(policy["minimum_recoverable"]): break
        keep.add(v["backup_id"])
    keep_seg=set()
    kept_good=[v for v in good if v["backup_id"] in keep]
    for v in kept_good: keep_seg.update(v["required_segments"])
    if kept_good:
        frontier=max(v["_target"] for v in kept_good)
        for s in segs:
            if segment_valid(s,size) and lsn(s["start_lsn"])>=frontier: keep_seg.add(s["name"])
    all_b={b["backup_id"] for b in backups}; all_s={s["name"] for s in segs}
    clean=[{k:v[k] for k in ("backup_id","reason","recoverable","required_segments")} for v in sorted(verdicts,key=lambda x:x["backup_id"])]
    report={"schema_version":1,"selected_backup":selected,"backups":clean,"retention":{"keep_backups":sorted(keep & all_b),"delete_backups":sorted(all_b-keep),"keep_segments":sorted(keep_seg),"delete_segments":sorted(all_s-keep_seg)}}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,sort_keys=True,separators=(",",":"))+"\n")
