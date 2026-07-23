FROM public.ecr.aws/docker/library/php:8.4-cli-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
 && apt-get install -y --no-install-recommends asciinema libsqlite3-dev python3 python3-pip sqlite3 tmux \
 && docker-php-ext-install pdo_sqlite \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /tmp/requirements.lock
RUN python3 -m pip install --break-system-packages --require-hashes --no-deps -r /tmp/requirements.lock \
 && rm /tmp/requirements.lock
WORKDIR /app
COPY app/ /app/
RUN chmod +x /app/bin/deployguard && php /app/tools/seed.php /app/data/deployguard.sqlite
