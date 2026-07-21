FROM public.ecr.aws/docker/library/python:3.12.11-slim-bookworm@sha256:27f90d79cc85e9b7b2560063ef44fa0e9eaae7a7c3f5a9f74563065c5477cc24

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends tmux asciinema \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.lock /tmp/requirements.lock
RUN python3 -m pip install --no-cache-dir --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock
COPY app/ /app/
RUN chmod +x /app/bin/walkeeper
