FROM public.ecr.aws/docker/library/python:3.13-slim-bookworm@sha256:01f42367a0a94ad4bc17111776fd66e3500c1d87c15bbd6055b7371d39c124fb

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema ca-certificates git git-lfs lua-socket lua5.4 openssl tmux \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock

WORKDIR /app
COPY app/ /app/
RUN chmod +x /app/bin/model-attestor /app/tools/seed-release.sh \
    && /app/tools/seed-release.sh \
    && rm -rf /app/config/private

ENV LUA_PATH="/app/?.lua;;"
