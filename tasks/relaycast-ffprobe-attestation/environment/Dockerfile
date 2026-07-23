FROM public.ecr.aws/docker/library/golang:1.24-bookworm@sha256:1a6d4452c65dea36aac2e2d606b01b4a029ec90cc1ae53890540ce6173ea77ac

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg make openssl python3 python3-pip tmux asciinema \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /tmp/requirements.lock
RUN python3 -m pip install --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock
WORKDIR /app
COPY app/go.mod /app/go.mod
RUN go mod download
COPY app/ /app/
RUN go build -o /app/bin/relaycast ./cmd/relaycast && chmod +x /app/bin/relaycast
COPY seed_fixture.py /tmp/seed_fixture.py
RUN python3 /tmp/seed_fixture.py && rm /tmp/seed_fixture.py
