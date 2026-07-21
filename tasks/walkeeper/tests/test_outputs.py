"""Black-box behavioral checks for walkeeper's recovery and retention policy."""
import json, os, subprocess
from pathlib import Path

BIN=Path(os.environ.get("WALKEEPER_BIN","/app/bin/walkeeper"))
APP_DATA=Path(os.environ.get("WALKEEPER_DATA","/app/data"))
SIZE=0x1000000
H="a"*64

def name(tl,pos): return f"{tl:08X}{pos>>32:08X}{(pos&0xffffffff)//SIZE:08X}"
def lsn(pos): return f"{pos>>32:X}/{pos&0xffffffff:08X}"
def seg(tl,pos,state="complete",digest=H,size=SIZE):
    return [name(tl,pos),str(tl),lsn(pos),lsn(pos+SIZE),str(size),digest,state]

def write(root, backups, segments, history=(), policy=None):
    root.mkdir()
    (root/"backups.tsv").write_text("backup_id\tstarted_at\ttimeline\tstart_lsn\tstart_wal\ttarget_lsn\n"+"\n".join("\t".join(x) for x in backups)+"\n")
    (root/"segments.tsv").write_text("name\ttimeline\tstart_lsn\tend_lsn\tsize\tsha256\tstate\n"+"\n".join("\t".join(x) for x in segments)+"\n")
    (root/"history.tsv").write_text("timeline\tparent\tswitch_lsn\n"+"\n".join(f"{a}\t{b}\t{lsn(c)}" for a,b,c in history)+"\n")
    (root/"policy.json").write_text(json.dumps(policy or {"segment_size":SIZE,"minimum_recoverable":1,"keep_newest":1,"protected_backup_ids":[]}))

def backup(i,tl,start,target,start_tl=None,when="2026-01-01T00:00:00Z"):
    return [i,when,str(tl),lsn(start),name(start_tl or tl,(start//SIZE)*SIZE),lsn(target)]

def run(root):
    out=root/"plan.json"
    cp=subprocess.run([str(BIN),"--inventory",str(root),"--output",str(out)],text=True,capture_output=True,timeout=20)
    assert cp.returncode==0,cp.stdout+cp.stderr
    raw=out.read_bytes(); obj=json.loads(raw)
    assert raw==json.dumps(obj,sort_keys=True,separators=(",",":")).encode()+b"\n"
    return obj,raw

def verdict(obj,i): return next(x for x in obj["backups"] if x["backup_id"]==i)

def test_timeline_switch_uses_parent_then_child_wal(tmp_path):
    """Recovery changes timeline exactly at an aligned switch and never uses a sibling fork."""
    root=tmp_path/"i"; write(root,[backup("b",2,SIZE,5*SIZE,1)],
        [seg(1,SIZE),seg(1,2*SIZE),seg(2,3*SIZE),seg(2,4*SIZE),seg(3,3*SIZE)],[(2,1,3*SIZE),(3,1,3*SIZE)])
    obj,_=run(root); v=verdict(obj,"b")
    assert v=={"backup_id":"b","recoverable":True,"reason":"ok","required_segments":[name(1,SIZE),name(1,2*SIZE),name(2,3*SIZE),name(2,4*SIZE)]}

def test_partial_corrupt_and_malformed_segments_are_invalid(tmp_path):
    """A present segment must be complete and structurally consistent rather than merely named correctly."""
    for label,row in [("partial",seg(1,SIZE,"partial")),("corrupt",seg(1,SIZE,"corrupt")),("hash",seg(1,SIZE,digest="ABC")),("size",seg(1,SIZE,size=1))]:
        root=tmp_path/label; write(root,[backup(label,1,SIZE,2*SIZE)],[row])
        assert verdict(run(root)[0],label)["reason"]=="invalid_segment"

def test_gap_precedes_an_invalid_present_segment(tmp_path):
    """A missing required WAL record has the documented precedence over another malformed record."""
    root=tmp_path/"i"; write(root,[backup("b",1,SIZE,3*SIZE)],[seg(1,SIZE,"partial")])
    assert verdict(run(root)[0],"b")["reason"]=="wal_gap"

def test_target_boundary_does_not_require_following_segment(tmp_path):
    """A target on a segment boundary requires only segments intersecting the half-open recovery range."""
    root=tmp_path/"i"; write(root,[backup("b",1,SIZE,2*SIZE)],[seg(1,SIZE)])
    assert verdict(run(root)[0],"b")["required_segments"]==[name(1,SIZE)]

def test_history_validation_and_reason_precedence(tmp_path):
    """Unknown, cyclic, descending, and unaligned timeline histories are rejected deterministically."""
    cases=[("unknown",2,[],"unknown_timeline"),("parent",2,[(2,2,2*SIZE)],"invalid_history"),("unaligned",2,[(2,1,2*SIZE+1)],"invalid_history")]
    for label,tl,hist,reason in cases:
        root=tmp_path/label; write(root,[backup(label,tl,SIZE,2*SIZE,1)],[],hist)
        assert verdict(run(root)[0],label)["reason"]==reason

def test_start_wal_and_reverse_target_rejections(tmp_path):
    """The declared start segment must match the ancestral timeline and the target cannot precede it."""
    root=tmp_path/"i"; b1=backup("mismatch",2,SIZE,2*SIZE,2); b2=backup("reverse",1,2*SIZE,SIZE)
    write(root,[b1,b2],[seg(1,SIZE)],[(2,1,3*SIZE)])
    obj,_=run(root)
    assert verdict(obj,"mismatch")["reason"]=="start_segment_mismatch"
    assert verdict(obj,"reverse")["reason"]=="target_before_start"

def test_selection_uses_target_then_time_then_smallest_id(tmp_path):
    """Selection follows recovery target, backup time, and ascending identifier tie breakers."""
    root=tmp_path/"i"; ss=[seg(1,SIZE),seg(1,2*SIZE),seg(1,3*SIZE)]
    bs=[backup("z",1,SIZE,3*SIZE,when="2026-02-01T00:00:00Z"),backup("b",1,SIZE,4*SIZE),backup("a",1,SIZE,4*SIZE)]
    write(root,bs,ss); assert run(root)[0]["selected_backup"]=="a"

def test_retention_preserves_all_kept_chains_and_future_wal(tmp_path):
    """Retention protects policy-selected backups, their complete chains, and valid future recovery WAL."""
    root=tmp_path/"i"; ss=[seg(1,p) for p in range(SIZE,7*SIZE,SIZE)]+[seg(2,6*SIZE)]
    bs=[backup("old",1,SIZE,3*SIZE,when="2026-01-01T00:00:00Z"),backup("new",1,2*SIZE,5*SIZE,when="2026-02-01T00:00:00Z"),backup("bad",1,SIZE,8*SIZE)]
    pol={"segment_size":SIZE,"minimum_recoverable":2,"keep_newest":1,"protected_backup_ids":["bad"]}
    write(root,bs,ss,policy=pol); r=run(root)[0]["retention"]
    assert r["keep_backups"]==["bad","new","old"]
    assert set(r["keep_segments"])=={name(1,p) for p in range(SIZE,7*SIZE,SIZE)}|{name(2,6*SIZE)}

def test_repeat_runs_are_byte_identical_and_input_driven(tmp_path):
    """Repeated inputs are byte-stable while a semantic target change changes the plan."""
    root=tmp_path/"i"; write(root,[backup("b",1,SIZE,2*SIZE)],[seg(1,SIZE),seg(1,2*SIZE)])
    first=run(root)[1]; second=run(root)[1]; assert first==second
    write_target=root/"backups.tsv"; write_target.write_text(write_target.read_text().replace(lsn(2*SIZE),lsn(3*SIZE)))
    assert run(root)[1]!=first

def test_shipped_inventory_has_expected_fork_verdicts():
    """The shipped fixture makes its good fork recoverable and rejects the sibling with partial WAL."""
    obj,_=run(APP_DATA)
    assert obj["selected_backup"]=="fork-good"
    assert verdict(obj,"fork-good")["reason"]=="ok"
    assert verdict(obj,"fork-gap")["reason"]=="wal_gap"
