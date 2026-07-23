#!/usr/bin/env bash
set -uo pipefail

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

run_verifier() {
    rm -f /app/bin/tunnelguard
    if ! (cd /app && cargo build --release && install -m 0755 target/release/tunnelguard /app/bin/tunnelguard); then
        echo "Rust build failed" >&2
        return 1
    fi

    (cd /tests && python3 -I -m pytest -o cache_dir=/tmp/pytest_cache --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA)
}

run_verifier
rc=$?
if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
