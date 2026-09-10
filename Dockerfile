# The brain in a container. The image is only the ENVIRONMENT — Python,
# Node, Claude Code, git, a cron runner. The brain itself (code + your data,
# one folder as always) is bind-mounted at /brain by docker-compose.yml, so
# updating the brain is a `git pull` on the host, never an image rebuild.
#
# See docker/README.md for setup, and note this runs the same scripts a Mac
# schedules with launchd — morning.sh and night.sh work under plain bash.

FROM node:22-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 git ca-certificates curl tzdata procps \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code && npm cache clean --force

# supercronic: cron that runs in the foreground and logs to stdout, which is
# what a container wants from a scheduler.
ARG SUPERCRONIC_VERSION=v0.2.49
ARG TARGETARCH
RUN curl -fsSL -o /usr/local/bin/supercronic \
      "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${TARGETARCH:-amd64}" \
    && chmod +x /usr/local/bin/supercronic

# The bind-mounted repo belongs to the host user; without this, every git
# command inside the container refuses with "dubious ownership".
RUN git config --system --add safe.directory /brain

WORKDIR /brain
EXPOSE 7718
CMD ["python3", "brain/tools/serve.py"]
