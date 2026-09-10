# Running the brain in Docker

Status: experimental — being tested by a friend of the project. The desktop
launchers remain the recommended way to run a brain; use this if you want it
on an always-on Linux box or a home server.

The image holds only the environment (Python, Node, Claude Code, git). Your
brain — code and your data, one folder as always — is bind-mounted into the
container, so an update is a `git pull` on the host followed by a restart.
Nothing needs rebuilding when the brain changes.

## Setup

Clone the brain's repo (or unzip the package you were sent) into a folder on
the server, then from inside that folder:

```bash
BRAIN_ALLOWED_HOSTS=localhost,127.0.0.1,192.168.1.50 docker compose up -d --build
```

Put every name you will reach the page by — LAN IP, hostname, tailnet name —
in `BRAIN_ALLOWED_HOSTS`. The server refuses requests under any other name;
that refusal is the same guard that protects a desktop brain from malicious
web pages, kept on even though a container has to bind 0.0.0.0.

Sign Claude Code in once (it persists in a volume across restarts):

```bash
docker exec -it life-brain claude
```

Then open `http://<your-server>:7718` and run `/onboard` for the first fill.

## What the second container does

`life-brain-cron` runs the same two scheduled jobs a Mac runs with launchd:
the 07:00 morning plan and the 01:00 night shift, in the container's `TZ`.
Both write their logs to `brain/.morning.log` and `brain/.night.log` in your
brain folder. If you change the hours in `docker/crontab`, keep night at
least five hours before morning — the reason is at the top of `night.sh`.

## Updating

```bash
git pull
docker compose restart
```

Rebuild the image only when the Dockerfile itself changed:
`docker compose up -d --build`.

## What does not work in a container

Integrations that read secrets from a desktop keychain — Beeper, the
Telegram bot, bank feeds, email — quietly skip in Docker; the page and the
scheduled jobs run without them. Phone HTTPS via `tailscale serve` needs
Tailscale on the host (or its own container) fronting port 7718.
