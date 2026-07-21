#!/bin/sh
set -eu

work=/tmp/model-seed
remote=/srv/model-remotes/sentence-transformers/all-MiniLM-L6-v2.git
rm -rf "$work" "$remote"
mkdir -p "$work" "$(dirname "$remote")" /app/config
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out /app/config/maintainer-private.pem 2>/dev/null
openssl pkey -in /app/config/maintainer-private.pem -pubout -out /app/config/maintainer-public.pem 2>/dev/null
git init -q "$work/repo"
git -C "$work/repo" config user.name "Model Maintainer"
git -C "$work/repo" config user.email "model@example.invalid"
git -C "$work/repo" lfs install --local >/dev/null
printf '*.bin filter=lfs diff=lfs merge=lfs -text\n' > "$work/repo/.gitattributes"
printf 'example model weights\n' > "$work/repo/model.bin"
printf '{"hidden_size":384}\n' > "$work/repo/config.json"
git -C "$work/repo" lfs track '*.bin' >/dev/null
git -C "$work/repo" add .
git -C "$work/repo" commit -qm "model snapshot"
git clone -q --bare "$work/repo" "$remote"
git -C "$work/repo" remote add origin "$remote"
git -C "$work/repo" lfs push --all origin >/dev/null
commit=$(git -C "$work/repo" rev-parse HEAD)
digest=$(sha256sum "$work/repo/model.bin" | awk '{print $1}')
size=$(wc -c < "$work/repo/model.bin" | tr -d ' ')
printf 'lock-version 1\nmodel sentence-transformers/all-MiniLM-L6-v2\nrevision %s\nartifact model.bin %s %s\n' "$commit" "$digest" "$size" > "$work/prefix"
openssl dgst -sha256 -sign /app/config/maintainer-private.pem -out "$work/sig" "$work/prefix"
base64 -w0 "$work/sig" > "$work/sig.b64"
cp "$work/prefix" /app/deps.lock.valid
printf 'signature %s\n' "$(cat "$work/sig.b64")" >> /app/deps.lock.valid
rm -rf "$work"
