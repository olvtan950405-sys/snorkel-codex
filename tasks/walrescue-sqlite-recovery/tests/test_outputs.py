"""Black-box recovery checks using fresh SQLite histories and independently minted WAL files."""

import random
import secrets
import struct
from pathlib import Path

import pytest

from wal_kit import (
    assert_database,
    build_wal,
    checksum,
    expected_report,
    load_report,
    make_database_history,
    run_tool,
    standalone,
)


@pytest.mark.parametrize("endian", ["little", "big"])
def test_recovers_multiple_transactions_in_both_checksum_orders(tmp_path, endian):
    """Both WAL magics recover multiple commits with rolling checksums and later page images winning."""
    rng = random.Random(secrets.randbits(64))
    base, first, second, _ = make_database_history(tmp_path, rng)
    build = build_wal(base, [first, second], 1024, endian, rng.getrandbits(32), rng.getrandbits(32))
    result, output, report = run_tool(tmp_path, base, build.blob)
    assert result.returncode == 0, result.stderr
    assert_database(output, second)
    assert load_report(report) == expected_report(build, 1024, standalone(second))


def test_ignores_valid_uncommitted_tail(tmp_path):
    """Checksum-valid frames after the final commit are counted but never applied."""
    rng = random.Random(secrets.randbits(64))
    base, first, second, tail = make_database_history(tmp_path, rng)
    build = build_wal(base, [first, second], 1024, "little", rng.getrandbits(32), rng.getrandbits(32), tail)
    result, output, report = run_tool(tmp_path, base, build.blob)
    assert result.returncode == 0, result.stderr
    assert_database(output, second)
    assert load_report(report) == expected_report(build, 1024, standalone(second))


@pytest.mark.parametrize(
    ("damage", "reason"),
    [("checksum", "checksum_mismatch"), ("salt", "salt_mismatch"), ("page", "zero_page_number")],
)
def test_stops_at_first_invalid_complete_frame(tmp_path, damage, reason):
    """A corrupt complete frame stops scanning and preserves the preceding durable transaction."""
    rng = random.Random(secrets.randbits(64))
    base, first, second, _ = make_database_history(tmp_path, rng)
    build = build_wal(
        base, [first, second], 1024, "little", rng.getrandbits(32), rng.getrandbits(32)
    )
    cut_index = build.committed_frames - 1
    offset = build.frame_offsets[cut_index]
    if damage == "checksum":
        build.blob[offset + 16] ^= 0x40
    elif damage == "salt":
        build.blob[offset + 8] ^= 0x01
    else:
        build.blob[offset : offset + 4] = b"\0\0\0\0"
    result, output, report = run_tool(tmp_path, base, build.blob)
    assert result.returncode == 0, result.stderr
    assert_database(output, first)
    parsed = load_report(report)
    first_frames = len(build_wal(base, [first], 1024, "little", 1, 2).frame_offsets)
    assert parsed == expected_report(
        build, 1024, standalone(first), reason, scanned=cut_index + 1, valid=cut_index
    ) | {
        "committed_frames": first_frames,
        "transactions": 1,
        "database_pages": len(first) // 1024,
        "ignored_tail_frames": cut_index - first_frames,
    }


def test_partial_frame_is_reported_and_prior_commit_survives(tmp_path):
    """Trailing bytes shorter than a frame produce partial_frame without invalidating the last commit."""
    rng = random.Random(secrets.randbits(64))
    base, first, second, tail = make_database_history(tmp_path, rng)
    build = build_wal(base, [first, second], 1024, "big", rng.getrandbits(32), rng.getrandbits(32), tail)
    build.blob += secrets.token_bytes(173)
    result, output, report = run_tool(tmp_path, base, build.blob)
    assert result.returncode == 0, result.stderr
    assert_database(output, second)
    assert load_report(report) == expected_report(build, 1024, standalone(second), "partial_frame")


def test_invalid_commit_size_rejects_the_commit_frame(tmp_path):
    """A commit size below any page in its transaction terminates the scan without committing it."""
    rng = random.Random(secrets.randbits(64))
    base, first, second, _ = make_database_history(tmp_path, rng)
    build = build_wal(base, [first, second], 1024, "little", rng.getrandbits(32), rng.getrandbits(32))
    offset = build.frame_offsets[-1]
    previous = build.frame_offsets[-2]
    state = struct.unpack_from(">II", build.blob, previous + 16)
    struct.pack_into(">I", build.blob, offset + 4, 1)
    page = bytes(build.blob[offset + 24 : offset + 24 + 1024])
    state = checksum(bytes(build.blob[offset : offset + 8]) + page, state, "little")
    struct.pack_into(">II", build.blob, offset + 16, *state)
    result, output, report = run_tool(tmp_path, base, build.blob)
    assert result.returncode == 0, result.stderr
    assert_database(output, first)
    parsed = load_report(report)
    first_frames = len(build_wal(base, [first], 1024, "little", 1, 2).frame_offsets)
    assert parsed["stop_reason"] == "invalid_commit_size"
    assert parsed["frames_scanned"] == len(build.frame_offsets)
    assert parsed["valid_frames"] == len(build.frame_offsets) - 1
    assert parsed["committed_frames"] == first_frames
    assert parsed["transactions"] == 1
    assert parsed["database_pages"] == len(first) // 1024
    assert parsed["ignored_tail_frames"] == len(build.frame_offsets) - 1 - first_frames


def test_commit_size_can_truncate_the_database(tmp_path):
    """The size on a later commit discards pages retained by an earlier larger snapshot."""
    rng = random.Random(secrets.randbits(64))
    base, first, _, _ = make_database_history(tmp_path, rng)
    work = tmp_path / "working.db"
    import sqlite3

    con = sqlite3.connect(work)
    con.execute("DELETE FROM events")
    con.commit()
    con.execute("VACUUM")
    con.commit()
    smaller = work.read_bytes()
    con.close()
    assert len(smaller) < len(first)
    build = build_wal(
        base, [first, smaller], 1024, "little", rng.getrandbits(32), rng.getrandbits(32)
    )
    result, output, report = run_tool(tmp_path, base, build.blob)
    assert result.returncode == 0, result.stderr
    assert_database(output, smaller)
    assert load_report(report)["database_pages"] == len(smaller) // 1024


@pytest.mark.parametrize("fault", ["magic", "header_checksum", "page_size", "no_commit"])
def test_fatal_wal_errors_leave_no_artifacts(tmp_path, fault):
    """Malformed headers, page-size disagreement, and a WAL without a commit fail atomically."""
    rng = random.Random(secrets.randbits(64))
    base, first, _, tail = make_database_history(tmp_path, rng)
    snapshots = [] if fault == "no_commit" else [first]
    build = build_wal(
        base,
        snapshots or [first],
        1024,
        "little",
        rng.getrandbits(32),
        rng.getrandbits(32),
        tail if fault == "no_commit" else None,
    )
    if fault == "magic":
        build.blob[0] = 0
    elif fault == "header_checksum":
        build.blob[24] ^= 1
    elif fault == "page_size":
        build.blob[10] = 8
    else:
        # Turn every commit marker into zero and recompute is deliberately unnecessary:
        # retain only header for the no-valid-commit condition.
        build.blob = build.blob[:32]
    result, output, report = run_tool(tmp_path, base, build.blob)
    assert result.returncode != 0
    assert not output.exists()
    assert not report.exists()


def test_inputs_are_unchanged_and_paths_are_independent(tmp_path):
    """Recovery never mutates either input and works when all four paths have unrelated names."""
    rng = random.Random(secrets.randbits(64))
    base, first, second, _ = make_database_history(tmp_path, rng, page_size=4096)
    build = build_wal(base, [first, second], 4096, "big", rng.getrandbits(32), rng.getrandbits(32))
    original_wal = bytes(build.blob)
    result, output, _ = run_tool(tmp_path, base, original_wal)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "input.db").read_bytes() == base
    assert (tmp_path / "input.db-wal").read_bytes() == original_wal
    assert_database(output, second)
