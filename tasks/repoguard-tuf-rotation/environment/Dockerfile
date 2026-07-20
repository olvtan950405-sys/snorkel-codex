FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends asciinema jq openssl python3 python3-pip rustc sqlite3 tmux \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.lock /tmp/requirements.lock
RUN python3 -m pip install --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock

COPY app/ /app/
RUN python3 /app/tools/seed_repository.py \
    && mkdir -p /app/target /app/bin \
    && rustc --edition=2021 -O /app/src/main.rs -o /app/target/repoguard

RUN chmod +x /app/bin/repoguard
