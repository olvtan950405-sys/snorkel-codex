#!/usr/bin/env bash
set -u

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Expected /app." >&2
    exit 1
fi

mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt
# Test tooling (pytest, pytest-json-ctrf) is pre-installed in the image via
# environment/Dockerfile; tests must not install packages at runtime.
python3 -m pytest -o cache_dir=/tmp/pytest_cache --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
status=$?
if [ "$status" -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
