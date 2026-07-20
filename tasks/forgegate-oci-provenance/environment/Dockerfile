FROM public.ecr.aws/docker/library/ruby:3.3-slim-bookworm@sha256:e76733e94b3a5893e4a141024ef3a583dc10781dc24becebf74f9c9f9a33e3df

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends asciinema openssl python3 python3-pip tmux \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.lock /tmp/requirements.lock
RUN python3 -m pip install --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock

COPY app/ /app/
COPY seed_example.py /tmp/seed_example.py
RUN python3 /tmp/seed_example.py && rm /tmp/seed_example.py
