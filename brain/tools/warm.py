#!/usr/bin/env python3
"""A helper process kept warm between requests.

The voice has two models that are slow to load and quick to use: Whisper
(hear.py) and Kokoro (voice.py). Each runs in its own process, under the
Python that has it installed, and answers one JSON line per request:

    request:  {"...": ...}\\n          ->   reply: {"...": ...}\\n
    first line after start:                 {"ready": true} or {"error": "..."}

The process exits by itself after its idle time (it reads that from its own
argv) and is started again on the next request. One request at a time.
"""
import json
import os
import select
import subprocess
import tempfile
import threading


class Warm:
    def __init__(self, argv, env=None, ready_timeout=240):
        """`argv` is a function returning the command line, so the model
        and idle time are read fresh at each start. It raises ValueError
        with a plain message when the helper cannot run on this Mac."""
        self._argv = argv
        self._env = env or {}
        self._ready_timeout = ready_timeout
        self._lock = threading.Lock()
        self._proc = None

    def alive(self):
        return self._proc is not None and self._proc.poll() is None

    def kill(self):
        if self._proc is not None:
            try:
                self._proc.kill()
            except Exception:
                pass
        self._proc = None

    def _readline(self, timeout):
        ready, _, _ = select.select([self._proc.stdout], [], [], timeout)
        if not ready:
            return None
        return self._proc.stdout.readline()

    def _spawn(self):
        argv = self._argv()
        self._proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True,
            env=dict(os.environ, **self._env), cwd=tempfile.gettempdir())
        line = self._readline(self._ready_timeout)
        try:
            msg = json.loads(line or "{}")
        except ValueError:
            msg = {}
        if not msg.get("ready"):
            self.kill()
            raise ValueError(msg.get("error") or "it did not start")

    def warm(self):
        """Start it in the background, so the next request is quick."""
        def go():
            with self._lock:
                if not self.alive():
                    try:
                        self._spawn()
                    except Exception:
                        pass
        threading.Thread(target=go, daemon=True).start()

    def ask(self, req, timeout=180):
        """One request, one reply (a dict). Raises ValueError."""
        data = json.dumps(req) + "\n"
        with self._lock:
            line = None
            for _attempt in range(2):
                if not self.alive():
                    self._spawn()
                try:
                    self._proc.stdin.write(data)
                    self._proc.stdin.flush()
                except (BrokenPipeError, OSError):
                    self.kill()            # it idled out as we wrote: again
                    continue
                line = self._readline(timeout)
                if line:
                    break
                if line is None:           # timed out: a stuck helper
                    self.kill()
                    raise ValueError("took too long")
                self.kill()                # EOF: it exited mid-request
            if not line:
                raise ValueError("stopped before answering")
        try:
            res = json.loads(line)
        except ValueError:
            raise ValueError("answered with something unreadable")
        if res.get("error"):
            raise ValueError(str(res["error"])[:200])
        return res
