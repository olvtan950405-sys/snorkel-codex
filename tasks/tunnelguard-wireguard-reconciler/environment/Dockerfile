FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CARGO_NET_OFFLINE=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip sqlite3 rustc cargo tmux asciinema \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.lock /tmp/requirements.lock
RUN python3 -m pip install --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock

COPY app/ /app/
RUN sqlite3 /app/data/gateway.db < /app/data/seed.sql \
    && mkdir -p /app/bin \
    && cargo build --release \
    && cp /app/target/release/tunnelguard /app/bin/tunnelguard \
    && rm -rf /app/target
