#!/usr/bin/env bash
set -uo pipefail

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile before running this script." >&2
    mkdir -p /logs/verifier
    echo 0 > /logs/verifier/reward.txt
    exit 0
fi

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

# Rebuild the worker and native library from whatever source the agent left behind, using the
# offline Maven repository and local toolchain baked into the image.  No packages are fetched.
export MVN_FLAGS="-o -B -q"
make -C /app clean >/dev/null 2>&1 || true
make -C /app all

python3 -m pytest -o cache_dir=/tmp/pytest_cache --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
rc=$?

if [ "$rc" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
