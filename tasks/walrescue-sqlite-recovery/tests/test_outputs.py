"""Black-box recovery checks using fresh SQLite histories and independently minted WAL files."""

import random
import secrets
import struct

import pytest

from wal_kit import (
    assert_database,
    build_manual_wal,
    build_wal,
    changed,
    checksum,
    expected_report,
    load_report,
    make_database_history,
    run_tool,
    run_tool_paths,
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


def test_duplicate_page_inside_one_transaction_uses_last_frame(tmp_path):
    """Within a committed transaction, a later frame for the same page is the trusted image."""
    rng = random.Random(secrets.randbits(64))
    base, first, _, _ = make_database_history(tmp_path, rng)
    delta = changed(base, first, 1024)
    page_number, final_page = delta[0]
    stale_page = base[(page_number - 1) * 1024 : page_number * 1024]
    frames = [(page_number, 0, stale_page), (page_number, 0, final_page)]
    frames.extend((number, 0, page) for number, page in delta[1:-1])
    last_number, last_page = delta[-1]
    frames.append((last_number, len(first) // 1024, last_page))
    build = build_manual_wal(frames, 1024, "little", rng.getrandbits(32), rng.getrandbits(32))
    result, output, report = run_tool(tmp_path, base, build.blob)
    assert result.returncode == 0, result.stderr
    assert_database(output, first)
    assert load_report(report) == expected_report(build, 1024, standalone(first))


def test_committed_page_one_wins_but_wal_mode_bytes_are_cleared(tmp_path):
    """A trusted page-1 image is preserved except for the two standalone DB version bytes."""
    rng = random.Random(secrets.randbits(64))
    base, first, _, _ = make_database_history(tmp_path, rng)
    frame = first[:1024]
    build = build_manual_wal(
        [(1, len(base) // 1024, frame)],
        1024,
        "big",
        rng.getrandbits(32),
        rng.getrandbits(32),
    )
    result, output, report = run_tool(tmp_path, base, build.blob)
    assert result.returncode == 0, result.stderr
    expected = bytearray(base)
    expected[:1024] = frame
    expected[18:20] = b"\x01\x01"
    assert output.read_bytes() == bytes(expected)
    assert load_report(report) == expected_report(build, 1024, bytes(expected))


def test_supports_sqlite_65536_page_size_encoding(tmp_path):
    """The SQLite/WAL page-size sentinel value 1 represents 65536-byte pages."""
    rng = random.Random(secrets.randbits(64))
    base, first, _, _ = make_database_history(tmp_path, rng, page_size=65536)
    build = build_wal(base, [first], 65536, "little", rng.getrandbits(32), rng.getrandbits(32))
    assert build.blob[8:12] == b"\x00\x00\x00\x01"
    result, output, report = run_tool(tmp_path, base, build.blob)
    assert result.returncode == 0, result.stderr
    assert_database(output, first)
    assert load_report(report) == expected_report(build, 65536, standalone(first))


@pytest.mark.parametrize("fault", ["base_magic", "base_length"])
def test_malformed_base_database_is_fatal_and_cleans_stale_artifacts(tmp_path, fault):
    """Bad base evidence fails before output artifacts can survive from an earlier run."""
    rng = random.Random(secrets.randbits(64))
    base, first, _, _ = make_database_history(tmp_path, rng)
    build = build_wal(base, [first], 1024, "little", rng.getrandbits(32), rng.getrandbits(32))
    bad_base = bytearray(base)
    if fault == "base_magic":
        bad_base[:6] = b"notSQL"
    else:
        bad_base.append(0)
    stale_out = tmp_path / "recovered.db"
    stale_report = tmp_path / "report.json"
    stale_out.write_bytes(b"stale")
    stale_report.write_bytes(b"stale\n")
    result, output, report = run_tool(tmp_path, bytes(bad_base), build.blob)
    assert result.returncode != 0
    assert output == stale_out and report == stale_report
    assert not output.exists()
    assert not report.exists()


def test_output_and_report_paths_must_not_alias_evidence_or_each_other(tmp_path):
    """The recovery gate refuses to overwrite inputs, collapse artifacts, or follow symlink outputs."""
    rng = random.Random(secrets.randbits(64))
    base, first, _, _ = make_database_history(tmp_path, rng)
    build = build_wal(base, [first], 1024, "little", rng.getrandbits(32), rng.getrandbits(32))
    db_path = tmp_path / "input.db"
    wal_path = tmp_path / "input.db-wal"
    report_path = tmp_path / "report.json"
    db_path.write_bytes(base)
    wal_path.write_bytes(build.blob)

    result = run_tool_paths(tmp_path, db_path, wal_path, db_path, report_path)
    assert result.returncode != 0
    assert db_path.read_bytes() == base
    assert not report_path.exists()

    shared = tmp_path / "shared"
    result = run_tool_paths(tmp_path, db_path, wal_path, shared, shared)
    assert result.returncode != 0
    assert not shared.exists()

    symlink_out = tmp_path / "linked-output.db"
    target = tmp_path / "target.db"
    target.write_bytes(b"do-not-touch")
    symlink_out.symlink_to(target)
    result = run_tool_paths(tmp_path, db_path, wal_path, symlink_out, report_path)
    assert result.returncode != 0
    assert target.read_bytes() == b"do-not-touch"
    assert not report_path.exists()


def test_rejects_trailing_cli_arguments_without_artifacts(tmp_path):
    """Unexpected positional arguments are rejected rather than ignored."""
    rng = random.Random(secrets.randbits(64))
    base, first, _, _ = make_database_history(tmp_path, rng)
    build = build_wal(base, [first], 1024, "little", rng.getrandbits(32), rng.getrandbits(32))
    result, output, report = run_tool(tmp_path, base, build.blob, extra_args=["unexpected"])
    assert result.returncode != 0
    assert not output.exists()
    assert not report.exists()
