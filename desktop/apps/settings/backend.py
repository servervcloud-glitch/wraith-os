"""Settings app backend: updates, Wi-Fi, privacy, appearance, sound/display, account, about."""
import glob
import json
import os
import platform
import re
import subprocess
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from sysutil import Admin, PkgJob, run  # noqa: E402

CONF = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "wraith", "shell.json")
DISPLAY_CONF = os.path.expanduser("~/.config/hypr/wraith-display.conf")


def is_live():
    try:
        return "boot=live" in open("/proc/cmdline").read().split()
    except OSError:
        return False


class Backend:
    def __init__(self, emit):
        self.emit = emit
        self.admin = Admin()
        self.job = PkgJob(self.admin, emit)

    # ---- admin password -------------------------------------------------------
    def auth(self, a):
        return self.admin.auth(a)

    # ---- System update ----------------------------------------------------------
    def checkUpdates(self, _):
        """Refresh package lists (with progress), then report what can be updated."""
        if self.job.busy:
            return {"ok": False, "error": "Busy"}
        self.job.busy = "check"

        def work():
            errors = []

            def line(t):
                if t.startswith("P "):
                    _, pct, msg = (t.split(" ", 2) + [""])[:3]
                    self.emit("job", {"kind": "refresh", "pct": float(pct), "text": msg})
                elif t.startswith("E "):
                    errors.append(t[2:])
            try:
                rc = self.admin.stream(["/usr/local/sbin/wraith-pkg", "refresh"], line)
                rc2, data, errs2 = self.job.run_sync("upgradable")
                data = data or {"packages": [], "removes": [], "download": "", "restart": False}
                data["ok"] = rc == 0 and rc2 == 0
                data["errors"] = (errors + errs2)[-4:]
                data["live"] = is_live()
                self.emit("updates", data)
            finally:
                self.job.busy = None
        threading.Thread(target=work, daemon=True).start()
        return {"ok": True}

    def applyUpdates(self, _):
        return self.job.start("upgrade")

    def restart(self, _):
        subprocess.Popen(["systemctl", "reboot"], start_new_session=True)
        return {"ok": True}

    # ---- Wi-Fi --------------------------------------------------------------------
    def wifi(self, a):
        ok, out = run(["nmcli", "-t", "radio", "wifi"])
        enabled = ok and out.strip() == "enabled"
        nets = []
        if enabled:
            ok, out = run(["nmcli", "-t", "-e", "yes", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "dev", "wifi", "list",
                           "--rescan", "yes" if a.get("rescan") else "auto"], timeout=20)
            seen = set()
            for line in out.splitlines() if ok else []:
                parts = re.split(r"(?<!\\):", line)
                if len(parts) < 4:
                    continue
                inuse, ssid, signal, sec = parts[0], parts[1].replace("\\:", ":"), parts[2], parts[3]
                if not ssid or ssid in seen:
                    continue
                seen.add(ssid)
                nets.append({"ssid": ssid, "signal": int(signal or 0), "secure": bool(sec and sec != "--"),
                             "connected": inuse == "*"})
            nets.sort(key=lambda n: (not n["connected"], -n["signal"]))
        ok, saved = run(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show"])
        known = [l.split(":")[0] for l in saved.splitlines() if l.endswith(":802-11-wireless")] if ok else []
        for n in nets:
            n["saved"] = n["ssid"] in known
        return {"enabled": enabled, "networks": nets, "available": ok}

    def wifiConnect(self, a):
        ssid, pw = a.get("ssid", ""), a.get("password")
        cmd = ["nmcli", "dev", "wifi", "connect", ssid] + (["password", pw] if pw else [])
        ok, out = run(cmd, timeout=45)
        if not ok:
            msg = "Wrong password" if re.search(r"secrets|password|802-1x", out, re.I) else "Couldn't connect"
            return {"ok": False, "error": msg}
        return {"ok": True}

    def wifiForget(self, a):
        ok, _ = run(["nmcli", "connection", "delete", "id", a.get("ssid", "")])
        return {"ok": ok}

    def wifiRadio(self, a):
        ok, _ = run(["nmcli", "radio", "wifi", "on" if a.get("on") else "off"])
        return {"ok": ok}

    # ---- Privacy & Tor ------------------------------------------------------------
    def privacy(self, _):
        try:
            tor = open("/etc/wraith/tor-mode").read().strip() != "off"
        except OSError:
            tor = True
        ok, out = run(["usbguard", "get-parameter", "ImplicitPolicyTarget"])
        try:
            boot = json.load(open("/run/wraith/desktop-status.json")).get("torBootstrap")
        except (OSError, ValueError):
            boot = None
        return {"tor": tor, "live": is_live(), "torBootstrap": boot,
                "mac": not os.path.exists("/etc/NetworkManager/conf.d/91-wraith-mac-off.conf"),
                "usbguard": (out.strip() != "allow") if ok else True}

    def setPrivacy(self, a):
        key, on = a.get("key"), bool(a.get("on"))
        args = {"tor": ["tor", "on" if on else "off"], "mac": ["mac", "on" if on else "off"],
                "usbguard": ["usb", "lock" if on else "unlock"], "newnym": ["tor", "newnym"]}.get(key)
        if not args:
            return {"ok": False}
        ok, out = run(["sudo", "-n", "/usr/local/sbin/wraith-ctl", *args], timeout=30)
        return {"ok": ok, "error": None if ok else ("Always on in Wraith Live" if "Live" in out else "Not allowed")}

    # ---- Appearance ---------------------------------------------------------------
    def _conf(self):
        try:
            with open(CONF) as fh:
                return json.load(fh)
        except Exception:
            return {}

    def appearance(self, _):
        c = self._conf()
        return {"dark": c.get("dark", True), "source": c.get("source") or "#6a5ff0"}

    def setAppearance(self, a):
        c = self._conf()
        if "dark" in a:
            c["dark"] = bool(a["dark"])
        if a.get("source") and re.fullmatch(r"#[0-9a-fA-F]{6}", a["source"]):
            c["source"] = a["source"]
        os.makedirs(os.path.dirname(CONF), exist_ok=True)
        tmp = CONF + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(c, fh, indent=1)
        os.replace(tmp, CONF)          # the desktop sees the change and re-themes
        return {"ok": True}

    # ---- Sound & display ----------------------------------------------------------
    def levels(self, _):
        ok, out = run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
        m = re.search(r"([\d.]+)", out) if ok else None
        vol = round(float(m.group(1)) * 100) if m else None
        ok, out = run(["brightnessctl", "-c", "backlight", "-m"])
        m = re.search(r",(\d+)%,", out) if ok else None
        scale = None
        try:
            m2 = re.search(r",\s*([\d.]+)\s*$", open(DISPLAY_CONF).read().strip().splitlines()[-1])
            scale = float(m2.group(1)) if m2 else None
        except (OSError, IndexError):
            pass
        if scale is None:  # automatic: report what the screen actually uses
            ok2, out2 = run(["hyprctl", "monitors", "-j"])
            try:
                scale = float(json.loads(out2)[0]["scale"]) if ok2 else 1.0
            except (ValueError, IndexError, KeyError):
                scale = 1.0
        return {"volume": vol, "brightness": int(m.group(1)) if m else None, "scale": scale}

    def setLevel(self, a):
        v = max(0, min(100, int(a.get("value", 0))))
        if a.get("key") == "volume":
            run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{v / 100:.2f}"])
        elif a.get("key") == "brightness":
            run(["brightnessctl", "-q", "-c", "backlight", "set", f"{max(v, 3)}%"])
        return {"ok": True}

    def setScale(self, a):
        s = float(a.get("scale", 1))
        if s not in (1.0, 1.25, 1.5, 1.75, 2.0):
            return {"ok": False}
        os.makedirs(os.path.dirname(DISPLAY_CONF), exist_ok=True)
        with open(DISPLAY_CONF, "w") as fh:
            fh.write("# Written by Wraith Settings > Display\nmonitor = , preferred, auto, %s\n" % s)
        run(["hyprctl", "keyword", "monitor", f",preferred,auto,{s}"])
        return {"ok": True}

    # ---- Account --------------------------------------------------------------------
    def changePassword(self, a):
        cur, new = a.get("current", ""), a.get("new", "")
        if len(new) < 8:
            return {"ok": False, "error": "Use at least 8 characters"}
        if "\n" in new or ":" in new:
            return {"ok": False, "error": "The password can't contain ':' or line breaks"}
        if not self.admin.ready():
            if not self.admin.auth({"password": cur})["ok"]:
                return {"ok": False, "error": "Current password is wrong"}
        ok, out = self.admin.run(["/usr/local/sbin/wraith-account", "setpass"], stdin=new + "\n")
        return {"ok": ok, "error": None if ok else (out.strip() or "Couldn't change it")}

    # ---- About ------------------------------------------------------------------------
    def about(self, _):
        mem = 0
        try:
            mem = int(re.search(r"MemTotal:\s+(\d+)", open("/proc/meminfo").read()).group(1)) * 1024
        except (OSError, AttributeError):
            pass
        cpu = ""
        try:
            cpu = re.search(r"model name\s*:\s*(.+)", open("/proc/cpuinfo").read()).group(1).strip()
        except (OSError, AttributeError):
            pass
        st = os.statvfs("/")
        base = ""
        try:
            base = open("/etc/debian_version").read().strip()
        except OSError:
            pass
        ok, gpu = run(["sh", "-c", "lspci 2>/dev/null | grep -iE 'vga|3d|display' | head -1 | cut -d: -f3"])
        return {"version": "1.0", "mode": "Wraith Live" if is_live() else "Installed", "kernel": platform.release(),
                "base": "Kali " + (base.replace("kali-", "") if base else "rolling"), "cpu": re.sub(r"\s+", " ", cpu), "memory": mem,
                "disk": {"total": st.f_blocks * st.f_frsize, "free": st.f_bavail * st.f_frsize},
                "gpu": gpu.strip() if ok else "", "hostname": platform.node()}
