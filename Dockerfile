# The brain in a container. The image is only the ENVIRONMENT — Python,
# Node, Claude Code, git, a cron runner. The brain itself (code + your data,
# one folder as always) is bind-mounted at /brain by docker-compose.yml, so
# updating the brain is a `git pull` on the host, never an image rebuild.
#
# See docker/README.md for setup, and note this runs the same scripts a Mac
# schedules with launchd — morning.sh and night.sh work under plain bash.

# An exact tag, not "22": a floating tag means two people building the same
# file get different images, and a bad upstream push lands without anyone
# choosing it. Bump it on purpose.
FROM node:22.20.0-bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 git ca-certificates curl tzdata procps \
    && rm -rf /var/lib/apt/lists/*

# Pinned for the same reason as the base image: Claude Code runs with the
# brain's files in reach, so a new release should arrive by a deliberate bump
# here, not by whatever npm served on the day of the build.
ARG CLAUDE_CODE_VERSION=2.0.76
RUN npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && npm cache clean --force

# supercronic: cron that runs in the foreground and logs to stdout, which is
# what a container wants from a scheduler. The download is checked against
# the release's published sha256 (GitHub's asset digest, confirmed by hashing
# the files) — a swapped binary here would run every night with the brain
# mounted. Bumping the version means updating both hashes from that release.
ARG SUPERCRONIC_VERSION=v0.2.49
ARG SUPERCRONIC_SHA256_AMD64=a53ae236602c7338aba3fbaff40bda6300eae3b9fedb8261eb06cfe3724430c1
ARG SUPERCRONIC_SHA256_ARM64=02aa0cb229ba09050cba6638059dadb9eedc2276632ea43d6a57a2f8c1629dd5
ARG TARGETARCH
RUN arch="${TARGETARCH:-amd64}" \
    && case "$arch" in \
         amd64) sum="$SUPERCRONIC_SHA256_AMD64" ;; \
         arm64) sum="$SUPERCRONIC_SHA256_ARM64" ;; \
         *) echo "no supercronic checksum for $arch" >&2; exit 1 ;; \
       esac \
    && curl -fsSL -o /usr/local/bin/supercronic \
      "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${arch}" \
    && echo "$sum  /usr/local/bin/supercronic" | sha256sum -c - \
    && chmod +x /usr/local/bin/supercronic

# The bind-mounted repo belongs to the host user; without this, every git
# command inside the container refuses with "dubious ownership".
RUN git config --system --add safe.directory /brain

# Run as the image's own unprivileged user (uid 1000), not root: the server
# and every Claude run it launches then cannot touch the container's system
# files. The .claude folder is created here so the login volume mounted over
# it starts out owned by that user.
RUN mkdir -p /home/node/.claude && chown node:node /home/node/.claude
USER node

WORKDIR /brain
EXPOSE 7718
CMD ["python3", "brain/tools/serve.py"]
