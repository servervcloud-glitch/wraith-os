"""Welcome screen backend: reuses Settings for Wi-Fi / looks, plus first-run steps."""
import importlib.util
import json
import os

_spec = importlib.util.spec_from_file_location("wraith_settings_backend",
                                               os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "settings", "backend.py"))
_settings = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_settings)
DONE = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "wraith", "welcome-done")


class Backend(_settings.Backend):
    def state(self, _):
        try:
            boot = json.load(open("/run/wraith/desktop-status.json")).get("torBootstrap")
        except (OSError, ValueError):
            boot = None
        return {"live": _settings.is_live(), "user": os.environ.get("USER", "wraith"), "torBootstrap": boot,
                "needsPassword": _settings.is_live() and self.admin.ready()}

    def setPassword(self, a):
        pw = a.get("password", "")
        if len(pw) < 8 or "\n" in pw or ":" in pw:
            return {"ok": False, "error": "Use at least 8 characters (no ':')"}
        ok, out = self.admin.run(["/usr/local/sbin/wraith-account", "setpass"], stdin=pw + "\n")
        if not ok:
            return {"ok": False, "error": out.strip() or "Couldn't set it"}
        # from now on admin actions ask for this password
        self.admin.run(["/usr/local/sbin/wraith-account", "require-password"])
        self.admin.password = pw
        return {"ok": True}

    def finish(self, _):
        os.makedirs(os.path.dirname(DONE), exist_ok=True)
        open(DONE, "w").close()
        return {"ok": True}
