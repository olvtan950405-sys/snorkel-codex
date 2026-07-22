FROM public.ecr.aws/docker/library/node:22-bookworm-slim@sha256:f3a68cf41a855d227d1b0ab832bed9749469ef38cf4f58182fb8c893bc462383

# Node is needed for the supplied Express/TypeScript service. This is an official
# digest-pinned image; the Harbor runtime tools and verifier are added below.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends asciinema python3 python3-pip sqlite3 tmux \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock /tmp/requirements.lock
RUN python3 -m pip install --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock

WORKDIR /app
COPY app/package.json app/package-lock.json ./
RUN npm install --no-audit --no-fund
COPY app/ /app/
RUN npm run build && mkdir -p /app/bin && cp /app/dist/cli.js /app/bin/refundguard && chmod +x /app/bin/refundguard
