FROM public.ecr.aws/docker/library/node:22-bookworm-slim@sha256:f3a68cf41a855d227d1b0ab832bed9749469ef38cf4f58182fb8c893bc462383

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NPM_CONFIG_FUND=false \
    NPM_CONFIG_AUDIT=false \
    NODE_ENV=production

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip tmux asciinema \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Verifier tooling and the native Node dependencies live in stable layers.
COPY requirements.lock /tmp/requirements.lock
RUN python3 -m pip install --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY app/ /app/

# The development trust catalog is built from its schema rather than shipped as a binary.
RUN node /app/tools/seed-catalog.mjs /app/data/trust-catalog.sql /app/data/trust-catalog.duckdb
