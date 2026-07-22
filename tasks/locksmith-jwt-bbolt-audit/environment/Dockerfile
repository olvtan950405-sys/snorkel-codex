FROM public.ecr.aws/docker/library/golang:1.24-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends asciinema git lsof procps python3 python3-pip strace tmux \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /tmp/requirements.lock
RUN python3 -m pip install --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock && rm /tmp/requirements.lock
WORKDIR /app
COPY app/go.mod ./
RUN go mod download
COPY app/ /app/
RUN go build -o /app/bin/locksmith-api ./fixture && go build -o /app/bin/locksmith-audit ./cmd/locksmith-audit
