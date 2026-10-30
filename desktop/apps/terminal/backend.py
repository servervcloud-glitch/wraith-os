"""Wraith Terminal backend: one pseudo-terminal (pty) per tab, output streamed to the page."""
import base64
import fcntl
import os
import pty
import pwd
import select
import signal
import struct
import subprocess
import termios
import threading
import time


class Tab:
    def __init__(self, tid, run, cols, rows, on_output, on_exit):
        self.tid = tid
        shell = os.environ.get("SHELL") or pwd.getpwuid(os.getuid()).pw_shell or "/bin/bash"
        argv = ["/bin/bash", "-c", run] if run else [shell, "-l"]
        pid, fd = pty.fork()
        if pid == 0:        # child: the shell
            os.chdir(os.path.expanduser("~"))
            env = dict(os.environ, TERM="xterm-256color", COLORTERM="truecolor", TERM_PROGRAM="WraithTerminal")
            try:
                os.execvpe(argv[0], argv, env)
            finally:
                os._exit(127)
        self.pid, self.fd = pid, fd
        self.resize(cols, rows)
        self.alive = True
        threading.Thread(target=self._read, args=(on_output, on_exit), daemon=True).start()

    def _read(self, on_output, on_exit):
        buf, last = b"", time.monotonic()
        while True:
            try:
                r, _, _ = select.select([self.fd], [], [], 0.016)
            except OSError:
                break
            if r:
                try:
                    chunk = os.read(self.fd, 65536)
                except OSError:
                    chunk = b""
                if not chunk:
                    break
                buf += chunk
            # batch output: at most ~60 updates a second, or when 64 KB pile up
            if buf and (not r or len(buf) > 65536 or time.monotonic() - last > 0.016):
                on_output(self.tid, buf)
                buf, last = b"", time.monotonic()
        if buf:
            on_output(self.tid, buf)
        self.alive = False
        try:
            os.waitpid(self.pid, 0)
        except ChildProcessError:
            pass
        on_exit(self.tid)

    def write(self, data):
        if self.alive:
            os.write(self.fd, data.encode())

    def resize(self, cols, rows):
        try:
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", max(2, rows), max(2, cols), 0, 0))
        except OSError:
            pass

    def close(self):
        if self.alive:
            try:
                os.killpg(os.getpgid(self.pid), signal.SIGHUP)
            except OSError:
                pass

    def cwd(self):
        try:
            # the foreground process's working directory (new tabs start there)
            fg = os.tcgetpgrp(self.fd)
            return os.readlink(f"/proc/{fg}/cwd")
        except OSError:
            return None


class Backend:
    def __init__(self, emit):
        self.emit = emit
        self.tabs = {}
        self.next = 1

    def open(self, a):
        tid = self.next
        self.next += 1
        self.tabs[tid] = Tab(tid, a.get("run"), int(a.get("cols", 80)), int(a.get("rows", 24)), self._out, self._exit)
        return {"id": tid}

    def _out(self, tid, data):
        self.emit("out", {"id": tid, "b64": base64.b64encode(data).decode()})

    def _exit(self, tid):
        self.tabs.pop(tid, None)
        self.emit("exit", {"id": tid})

    def write(self, a):
        t = self.tabs.get(a.get("id"))
        if t:
            t.write(a.get("data", ""))
        return True

    def resize(self, a):
        t = self.tabs.get(a.get("id"))
        if t:
            t.resize(int(a.get("cols", 80)), int(a.get("rows", 24)))
        return True

    def closeTab(self, a):
        t = self.tabs.get(a.get("id"))
        if t:
            t.close()
        return True

    def title(self, a):
        """Name for a tab: the program running in it (e.g. "nmap"), or the folder."""
        t = self.tabs.get(a.get("id"))
        if not t:
            return None
        try:
            fg = os.tcgetpgrp(t.fd)
            name = open(f"/proc/{fg}/comm").read().strip()
            if name in ("bash", "zsh", "sh", "fish"):
                cwd = t.cwd() or ""
                home = os.path.expanduser("~")
                return "~" + cwd[len(home):] if cwd.startswith(home) else cwd or name
            return name
        except OSError:
            return None

    def copy(self, a):
        try:
            subprocess.run(["wl-copy"], input=a.get("text", ""), text=True, timeout=3)
        except (OSError, subprocess.SubprocessError):
            pass
        return True

    def paste(self, _):
        try:
            return subprocess.run(["wl-paste", "-n"], capture_output=True, text=True, timeout=3).stdout
        except (OSError, subprocess.SubprocessError):
            return ""

    def shutdown(self):
        for t in list(self.tabs.values()):
            t.close()
