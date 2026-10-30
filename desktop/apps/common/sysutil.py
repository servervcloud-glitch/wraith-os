"""Shared helpers for Wraith app backends: admin (sudo) access and package jobs."""
import json
import subprocess
import threading


def run(cmd, timeout=10, **kw):
    """Run a command; return (ok, output)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
        return p.returncode == 0, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return False, str(e)


class Admin:
    """Runs root commands through sudo with the admin password the user typed.
    The password only lives in this app's memory while the app is open."""

    def __init__(self):
        self.password = None

    def ready(self):
        return run(["sudo", "-n", "true"])[0]

    def auth(self, args):
        if args.get("check"):
            return {"ok": self.ready()}
        pw = args.get("password") or ""
        ok, _ = run(["sudo", "-S", "-p", "", "-v"], input=pw + "\n")
        if ok:
            self.password = pw
        return {"ok": ok}

    def argv(self, cmd):
        """(argv, stdin prefix) to run cmd as root."""
        if self.ready():
            return ["sudo", "-n", *cmd], ""
        return ["sudo", "-S", "-p", "", *cmd], (self.password or "") + "\n"

    def run(self, cmd, stdin="", timeout=60):
        argv, prefix = self.argv(cmd)
        return run(argv, timeout=timeout, input=prefix + stdin)

    def stream(self, cmd, on_line):
        """Run cmd as root, call on_line(text) for each output line; return exit code."""
        argv, prefix = self.argv(cmd)
        p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            p.stdin.write(prefix)
            p.stdin.close()
        except BrokenPipeError:
            pass
        for line in p.stdout:
            on_line(line.rstrip("\n"))
        return p.wait()


class PkgJob:
    """One wraith-pkg run in the background, reporting progress events:
    emit("job", {"kind", "pct", "text", "done", "ok", "errors", "data"})."""

    def __init__(self, admin, emit):
        self.admin, self.emit = admin, emit
        self.busy = None

    def start(self, kind, *args):
        if self.busy:
            return {"ok": False, "error": "Another job is running"}
        self.busy = kind
        threading.Thread(target=self._run, args=(kind, args), daemon=True).start()
        return {"ok": True}

    def run_sync(self, kind, *args):
        """Run and return (exit code, data, errors) - for quick list commands."""
        data, errors = [None], []

        def line(text):
            if text.startswith("J "):
                data[0] = json.loads(text[2:])
            elif text.startswith("E "):
                errors.append(text[2:])
        rc = self.admin.stream(["/usr/local/sbin/wraith-pkg", kind, *args], line)
        return rc, data[0], errors

    def _run(self, kind, args):
        errors, data, rc = [], None, 1
        state = {"pct": 0}

        def line(text):
            nonlocal data
            if text.startswith("P "):
                _, pct, msg = (text.split(" ", 2) + [""])[:3]
                state["pct"] = float(pct)
                self.emit("job", {"kind": kind, "pct": state["pct"], "text": msg})
            elif text.startswith("J "):
                data = json.loads(text[2:])
            elif text.startswith("E "):
                errors.append(text[2:])
        try:
            rc = self.admin.stream(["/usr/local/sbin/wraith-pkg", kind, *args], line)
        finally:
            self.busy = None
            self.emit("job", {"kind": kind, "done": True, "ok": rc == 0, "errors": errors[-5:], "data": data, "pct": 100})
