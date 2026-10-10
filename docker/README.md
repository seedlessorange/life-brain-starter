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
docker compose up -d --build
```

The page is published on the server's own loopback address only
(`127.0.0.1:7718`). The brain has no login, and anyone who can reach the port
can read everything in it and start Claude runs, so it is never opened to the
network directly. To use it from a laptop or phone, put something with a lock
in front of it: `tailscale serve 7718` on the host (only your own devices get
in), or an SSH tunnel (`ssh -L 7718:127.0.0.1:7718 your-server`). A proxy
that forwards a name other than `localhost` needs that name added to
`BRAIN_ALLOWED_HOSTS` (comma-separated) when you start the stack; the server
refuses requests under any other name, the same guard that protects a
desktop brain from malicious web pages.

The containers run as an unprivileged user (uid 1000), not root. On Linux
the brain folder must be writable by uid 1000 — true when your own account
is the first user on the box; otherwise `sudo chown -R 1000 .` in the folder.

Sign Claude Code in once (it persists in a volume across restarts):

```bash
docker exec -it life-brain claude
```

Then open the page (on the server, `http://127.0.0.1:7718`; elsewhere,
through the tunnel or Tailscale name) and run `/onboard` for the first fill.

Upgrading from an image that ran as root: the saved login belongs to root
and the new user cannot read it. Hand it over once with
`docker compose run --rm -u root brain chown -R node:node /home/node/.claude`,
or just sign in again.

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
