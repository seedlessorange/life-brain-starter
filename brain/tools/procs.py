"""Is a process still running, and stop one with what it started.

One answer for every tool that watches a job it launched (a Sessions turn, a
book guide, a meeting transcription), on a Mac and on Windows. On Windows
os.kill(pid, 0) is not a question: signal 0 is CTRL_C_EVENT there, so the
check itself interrupted the job it was asking about, and os.killpg does not
exist, so the Stop button raised instead of stopping (28 Sep audit).
"""
import os
import subprocess
import sys


def alive(pid):
    """Whether pid is a running process. A zombie (finished, not yet
    collected by its parent) counts as gone."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        k = ctypes.windll.kernel32
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k.GetExitCodeProcess.argtypes = [wintypes.HANDLE,
                                         ctypes.POINTER(wintypes.DWORD)]
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        h = k.OpenProcess(0x1000, False, pid)     # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            code = wintypes.DWORD()
            ok = k.GetExitCodeProcess(h, ctypes.byref(code))
            return bool(ok) and code.value == 259  # STILL_ACTIVE
        finally:
            k.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    try:
        st = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)],
                            capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:                                    # noqa: BLE001
        return True
    return bool(st) and not st.startswith("Z")


def kill_tree(pid):
    """Stop pid and everything it started. On a Mac the job leads its own
    process group (start_new_session=True); Windows has taskkill /T."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return
    if sys.platform == "win32":
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, timeout=15)
        except Exception:                                # noqa: BLE001
            pass
        return
    import signal
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
