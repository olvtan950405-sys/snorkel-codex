FROM public.ecr.aws/docker/library/maven:3.9.9-eclipse-temurin-21@sha256:3a4ab3276a087bf276f79cae96b1af04f53731bec53fb2e651aca79e4b10211e

ENV JAVA_HOME=/opt/java/openjdk \
    APP_HOME=/app \
    MAVEN_OPTS=-Dmaven.artifact.threads=4 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# A C toolchain, make and valgrind stay in the runtime image on purpose: the task requires the agent
# to rebuild the native extractor and to inspect it for memory errors.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        ca-certificates \
        gcc \
        git \
        libc6-dev \
        make \
        python3 \
        python3-pip \
        tmux \
        valgrind \
    && rm -rf /var/lib/apt/lists/*

# The verifier's Python dependencies are fully hash-locked, so every transitive artifact is pinned.
COPY requirements.lock /tmp/requirements.lock
RUN python3 -m pip install --no-cache-dir --break-system-packages \
        --require-hashes --no-deps -r /tmp/requirements.lock \
    && rm /tmp/requirements.lock

WORKDIR /app

# Warm the Maven cache from the manifest first so dependency resolution stays in a stable layer.
COPY app/pom.xml /app/pom.xml
RUN mvn -B -q dependency:go-offline

COPY app/ /app/

# Build once so the worker is runnable as shipped, and so the offline Maven build the agent runs
# afterwards resolves every plugin from the local repository.
RUN chmod +x /app/bin/sentinel \
    && make all \
    && rm -rf /app/target

COPY tools/seed-repo.sh /tmp/seed-repo.sh
RUN bash /tmp/seed-repo.sh /app/repo \
    && rm /tmp/seed-repo.sh
