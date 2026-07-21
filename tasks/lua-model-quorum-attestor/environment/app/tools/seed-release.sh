#!/bin/sh
set -eu
work=/tmp/release-seed
rm -rf "$work" /srv/model-mirrors /app/config/private /app/config/maintainers
mkdir -p "$work" /srv/model-mirrors /app/config/private /app/config/maintainers

for key in alice bob carol; do
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out "/app/config/private/$key.pem" 2>/dev/null
  openssl pkey -in "/app/config/private/$key.pem" -pubout -out "/app/config/maintainers/$key.pem" 2>/dev/null
done

seed_model() {
  name=$1; file=$2; content=$3
  repo="$work/$name"; remote="/srv/model-mirrors/$name.git"
  git init -q "$repo"
  git -C "$repo" config user.name Maintainer
  git -C "$repo" config user.email model@example.invalid
  git -C "$repo" lfs install --local >/dev/null
  printf '*.bin filter=lfs diff=lfs merge=lfs -text\n' > "$repo/.gitattributes"
  printf '%s\n' "$content" > "$repo/$file"
  git -C "$repo" add .
  git -C "$repo" commit -qm snapshot
  git -C "$repo" tag -a v1 -m "approved release"
  git clone -q --bare "$repo" "$remote"
  git -C "$repo" remote add origin "$remote"
  git -C "$repo" lfs push --all origin >/dev/null
}

seed_model encoder model.bin 'encoder artifact'
seed_model retrieval weights.bin 'retrieval artifact'
ecommit=$(git -C "$work/encoder" rev-parse HEAD)
rcommit=$(git -C "$work/retrieval" rev-parse HEAD)
edigest=$(sha256sum "$work/encoder/model.bin" | awk '{print $1}')
rdigest=$(sha256sum "$work/retrieval/weights.bin" | awk '{print $1}')
esize=$(wc -c < "$work/encoder/model.bin" | tr -d ' ')
rsize=$(wc -c < "$work/retrieval/weights.bin" | tr -d ' ')
{
  printf 'release-lock 1\nrelease hf-encoder-pack-2026-07\nquorum 2\n'
  printf 'model intfloat/e5-small-v2 retrieval v1 %s weights.bin %s %s\n' "$rcommit" "$rdigest" "$rsize"
  printf 'model sentence-transformers/all-MiniLM-L6-v2 encoder v1 %s model.bin %s %s\n' "$ecommit" "$edigest" "$esize"
} > "$work/prefix"
cp "$work/prefix" /app/release.lock.valid
for key in alice bob; do
  openssl dgst -sha256 -sign "/app/config/private/$key.pem" -out "$work/$key.sig" "$work/prefix"
  printf 'signer %s %s\n' "$key" "$(base64 -w0 "$work/$key.sig")" >> /app/release.lock.valid
done
rm -rf "$work"
