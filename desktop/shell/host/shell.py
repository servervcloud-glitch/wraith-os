#!/usr/bin/python3
"""Wraith Shell host.

Shows the shell UI (desktop/shell/ui, plain HTML/CSS/JS) on Wayland layer-shell
surfaces and connects it to the system:

  wallpaper   one per monitor, on the BACKGROUND layer, painted natively with
              cairo from the colours the page computes (WebKit only gives the
              first web view in a process its size, and this is cheaper anyway)
  ui          bar + dock + drawer + quick settings, a full-screen transparent
              surface on the TOP layer; only the bar and dock (or an open panel)
              take clicks, everything else passes through to the windows below
  spacers     two empty surfaces that reserve room for the bar and dock, so
              maximised windows don't go under them

The page talks to us with window.wraith.call(name, args) -> Promise; see
`Backend` for the calls. `wraith-shell-ctl drawer|qs|close` (bound to the
Super key in Hyprland) reaches us over a UNIX socket.

Must start with libgtk4-layer-shell preloaded (the wraith-shell launcher does
that): the library has to load before libwayland-client.
"""
import configparser
import glob
import json
import mimetypes
import os
import re
import shlex
import socket
import subprocess
import sys
import threading
import urllib.parse
import xml.etree.ElementTree as ET

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("WebKit", "6.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, WebKit  # noqa: E402
from gi.repository import Gtk4LayerShell as LayerShell  # noqa: E402
import cairo  # noqa: E402  (python3-gi-cairo: input regions)

UI_DIR = os.environ.get("WRAITH_SHELL_UI", "/usr/share/wraith/shell/ui")
CONF_DIR = os.path.join(GLib.get_user_config_dir(), "wraith")
CONF_FILE = os.path.join(CONF_DIR, "shell.json")
SOCK = os.path.join(GLib.get_user_runtime_dir(), "wraith-shell.sock")
BAR_H, DOCK_ZONE = 40, 92          # reserved space at the top and bottom (px)
TERMINAL = ["foot"]                 # terminal for Terminal=true apps (Wraith Terminal later)

DEFAULT_DOCK = [  # first existing id of each group
    ["foot", "org.codeberg.dnkl.foot"],
    ["torbrowser", "torbrowser-launcher", "torbrowser.desktop"],
    ["org.gnome.Nautilus", "thunar"],
    ["kali-nmap"],
    ["kali-burpsuite"],
    ["kali-metasploit-framework"],
    ["org.wireshark.Wireshark", "kali-wireshark", "wireshark"],
    ["wraith-settings"],
]
RENAME = {"foot": "Terminal", "org.codeberg.dnkl.foot": "Terminal", "org.gnome.Nautilus": "Files",
          "kali-metasploit-framework": "Metasploit", "kali-burpsuite": "Burp Suite"}
HIDE = {"footclient", "foot-server", "org.codeberg.dnkl.footclient", "org.codeberg.dnkl.foot-server",
        "org.freedesktop.Xwayland", "root-terminal", "display-im7.q16", "python3.14", "texdoctk"}
KALI_MENU = "/etc/xdg/menus/applications-merged/kali-applications.menu"


def run(cmd, timeout=8):
    """Run a command, return (ok, stdout)."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode == 0, (p.stdout or p.stderr).strip()
    except Exception as e:  # missing tool, timeout...
        return False, str(e)


def load_conf():
    try:
        with open(CONF_FILE) as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_conf(conf):
    os.makedirs(CONF_DIR, exist_ok=True)
    tmp = CONF_FILE + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(conf, fh, indent=1)
    os.replace(tmp, CONF_FILE)


# --------------------------------------------------------------------------- apps
class Apps:
    """Installed apps from .desktop files, grouped by Kali's menu categories."""

    def __init__(self):
        self.icons = {}
        self.allowed_icon_files = set()
        self.apps = {}
        self.categories = []

    def _index_icons(self):
        # name -> best file. Scalable SVG wins, otherwise the largest PNG.
        best = {}
        roots = [os.path.expanduser("~/.local/share/icons"), "/usr/local/share/icons", "/usr/share/icons"]
        prefer = ["hicolor", "Flat-Remix-Blue-Dark", "Adwaita"]
        themes = []
        for r in roots:
            if os.path.isdir(r):
                names = sorted(os.listdir(r), key=lambda n: (prefer.index(n) if n in prefer else 99, n))
                themes += [os.path.join(r, n) for n in names]
        for rank, theme in enumerate(themes):
            for dirpath, _, files in os.walk(theme):
                if "/apps" not in dirpath and "/categories" not in dirpath and "/places" not in dirpath:
                    continue
                m = re.search(r"/(\d+)x\1(?:@\d)?/", dirpath + "/")
                size = 1024 if "scalable" in dirpath else int(m.group(1)) if m else 0
                for f in files:
                    stem, ext = os.path.splitext(f)
                    if ext not in (".svg", ".png"):
                        continue
                    score = (-rank, size)
                    if stem not in best or score > best[stem][0]:
                        best[stem] = (score, os.path.join(dirpath, f))
        for f in glob.glob("/usr/share/pixmaps/*.png") + glob.glob("/usr/share/pixmaps/*.svg"):
            stem = os.path.splitext(os.path.basename(f))[0]
            best.setdefault(stem, ((-999, 0), f))
        self.icons = {k: v[1] for k, v in best.items()}

    def _icon_url(self, name):
        if not name:
            return None
        path = name if os.path.isabs(name) and os.path.isfile(name) else self.icons.get(name)
        if not path or not path.endswith((".svg", ".png")):
            return None
        self.allowed_icon_files.add(path)
        return "wraith://icon" + urllib.parse.quote(path)

    def _kali_categories(self):
        """category -> [top-level menu names], plus the top-level order."""
        cat_map, order = {}, []
        try:
            root = ET.parse(KALI_MENU).getroot()
        except Exception:
            return cat_map, order
        for top in root.findall("Menu"):
            title = top.findtext("Name") or ""
            d = top.findtext("Directory")
            if d:
                cp = configparser.ConfigParser(interpolation=None, strict=False)
                try:
                    cp.read(os.path.join("/usr/share/desktop-directories", d))
                    title = cp.get("Desktop Entry", "Name", fallback=title)
                except Exception:
                    pass
            title = re.sub(r"^\d+\s*-\s*", "", title).strip()
            if not title:
                continue
            order.append(title)
            for c in top.iter("Category"):
                cat_map.setdefault(c.text, [])
                if title not in cat_map[c.text]:
                    cat_map[c.text].append(title)
        return cat_map, order

    def load(self):
        self._index_icons()
        cat_map, order = self._kali_categories()
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "Hyprland").split(":")
        dirs = ["/usr/share/applications", "/usr/local/share/applications",
                os.path.expanduser("~/.local/share/applications")]
        apps, used = {}, []
        for d in dirs:  # later dirs override earlier ones (user entries win)
            for f in sorted(glob.glob(os.path.join(d, "*.desktop"))):
                app_id = os.path.basename(f)[:-8]
                cp = configparser.ConfigParser(interpolation=None, strict=False)
                try:
                    cp.read(f, encoding="utf-8")
                    e = cp["Desktop Entry"]
                except Exception:
                    continue
                if (e.get("Type") != "Application" or e.get("NoDisplay", "").lower() == "true"
                        or e.get("Hidden", "").lower() == "true" or app_id in HIDE or not e.get("Exec")):
                    apps.pop(app_id, None)
                    continue
                only = [x for x in e.get("OnlyShowIn", "").split(";") if x]
                notin = [x for x in e.get("NotShowIn", "").split(";") if x]
                if (only and not set(only) & set(desktop)) or set(notin) & set(desktop):
                    continue
                cats = []
                for c in e.get("Categories", "").split(";"):
                    for top in cat_map.get(c, []):
                        if top not in cats:
                            cats.append(top)
                if not cats:
                    cats = ["Apps"]
                for c in cats:
                    if c not in used:
                        used.append(c)
                apps[app_id] = {
                    "id": app_id,
                    "name": RENAME.get(app_id, e.get("Name", app_id)),
                    "comment": e.get("Comment", ""),
                    "exec": e.get("Exec"),
                    "terminal": e.get("Terminal", "").lower() == "true",
                    "icon": self._icon_url(e.get("Icon")),
                    "cats": cats,
                }
        self.apps = apps
        self.categories = (["Apps"] if "Apps" in used else []) + [c for c in order if c in used]
        return self

    def payload(self, conf):
        dock = conf.get("dock") or [next((i for i in grp if i in self.apps), None) for grp in DEFAULT_DOCK]
        public = [{k: v for k, v in a.items() if k != "exec"}
                  for a in sorted(self.apps.values(), key=lambda a: a["name"].lower())]
        return {"apps": public, "categories": self.categories, "dock": [d for d in dock if d in self.apps]}

    def command(self, app_id):
        a = self.apps.get(app_id)
        if not a:
            return None
        # drop the %f/%U/... field codes from Exec
        argv = [x for x in shlex.split(a["exec"]) if not re.fullmatch(r"%[a-zA-Z]", x)]
        argv = [re.sub(r"%[a-zA-Z]", "", x) for x in argv]
        return TERMINAL + ["--title", a["name"], "--"] + argv if a["terminal"] else argv


# --------------------------------------------------------------------------- system
class Backend:
    """Everything the page can ask for. Each method gets the call's args dict."""

    def __init__(self, host):
        self.host = host
        self.conf = load_conf()
        self.apps = Apps()

    # ---- status -------------------------------------------------------------
    def status(self, _):
        st = {"live": "boot=live" in open("/proc/cmdline").read().split(),
              "dark": self.conf.get("dark", True), "source": self.conf.get("source")}
        try:
            st["tor"] = open("/etc/wraith/tor-mode").read().strip() != "off"
        except OSError:
            st["tor"] = True
        ok, out = run(["nmcli", "-t", "radio", "wifi"])
        if ok:
            st["wifi"] = out.strip() == "enabled"
            ok2, devs = run(["nmcli", "-t", "-f", "TYPE,STATE", "device"])
            st["wifiConnected"] = ok2 and "wifi:connected" in devs
        rf = self._rfkill()
        st["bluetooth"] = None if "bluetooth" not in rf else not rf["bluetooth"]
        st["airplane"] = bool(rf) and all(rf.values())
        st["mac"] = not os.path.exists("/etc/NetworkManager/conf.d/91-wraith-mac-off.conf")
        ok, out = run(["usbguard", "get-parameter", "ImplicitPolicyTarget"])
        st["usbguard"] = (out.strip() != "allow") if ok else True
        bats = glob.glob("/sys/class/power_supply/BAT*")
        if bats:
            try:
                st["battery"] = int(open(bats[0] + "/capacity").read())
                st["charging"] = open(bats[0] + "/status").read().strip() in ("Charging", "Full")
            except (OSError, ValueError):
                st["battery"] = None
        else:
            st["battery"] = None
        ok, out = run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"])
        m = re.search(r"([\d.]+)", out) if ok else None
        st["volume"] = round(float(m.group(1)) * 100) if m else None
        ok, out = run(["brightnessctl", "-c", "backlight", "-m"])
        m = re.search(r",(\d+)%,", out) if ok else None
        st["brightness"] = int(m.group(1)) if m else None
        return st

    @staticmethod
    def _rfkill():
        """{type: soft_blocked} for every radio."""
        out = {}
        for d in glob.glob("/sys/class/rfkill/rfkill*"):
            try:
                t = open(d + "/type").read().strip()
                out[t] = open(d + "/soft").read().strip() == "1" or out.get(t, False)
            except OSError:
                pass
        return out

    # ---- switches -----------------------------------------------------------
    def toggle(self, a):
        tid, on = a.get("id"), bool(a.get("on"))
        if tid == "dark":
            return self.theme({"dark": on, "source": self.conf.get("source")})
        if tid == "tor":
            return self._ctl("tor", "on" if on else "off")
        if tid == "usbguard":
            return self._ctl("usb", "lock" if on else "unlock")
        if tid == "mac":
            return self._ctl("mac", "on" if on else "off")
        if tid == "wifi":
            ok, out = run(["nmcli", "radio", "wifi", "on" if on else "off"])
        elif tid == "bluetooth":
            ok, out = run(["rfkill", "unblock" if on else "block", "bluetooth"])
        elif tid == "airplane":
            ok, out = run(["rfkill", "block" if on else "unblock", "all"])
        else:
            return {"ok": False, "error": "Unknown switch"}
        return {"ok": ok, "error": None if ok else "Not allowed"}

    @staticmethod
    def _ctl(*args):
        ok, out = run(["sudo", "-n", "/usr/local/sbin/wraith-ctl", *args], timeout=30)
        if ok:
            return {"ok": True}
        if "Wraith Live" in out:
            return {"ok": False, "error": "Always on in Wraith Live"}
        return {"ok": False, "error": "Needs an admin account"}

    def set(self, a):
        key, v = a.get("key"), max(0, min(100, int(a.get("value", 0))))
        if key == "volume":
            run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{v / 100:.2f}"])
        elif key == "brightness":
            run(["brightnessctl", "-q", "-c", "backlight", "set", f"{max(v, 3)}%"])
        return {"ok": True}

    def theme(self, a):
        dark = bool(a.get("dark", True))
        self.conf["dark"] = dark
        if a.get("source"):
            self.conf["source"] = a["source"]
        save_conf(self.conf)
        cursor = "Wraith" if dark else "Wraith-Black"
        run(["hyprctl", "setcursor", cursor, os.environ.get("XCURSOR_SIZE", "24")])
        # GTK / libadwaita apps follow too
        run(["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", "prefer-dark" if dark else "default"])
        run(["gsettings", "set", "org.gnome.desktop.interface", "cursor-theme", cursor])
        if isinstance(a.get("wallpaper"), dict):
            self.conf["wallpaper"] = a["wallpaper"]
        save_conf(self.conf)
        GLib.idle_add(self.host.relay_theme, self.conf.get("wallpaper"))
        return {"ok": True}

    # ---- apps ---------------------------------------------------------------
    def apps_(self, _):
        return self.apps.load().payload(self.conf)

    def launch(self, a):
        argv = self.apps.command(a.get("id"))
        if not argv:
            return {"ok": False}
        try:
            subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=os.path.expanduser("~"))
            return {"ok": True}
        except OSError as e:
            return {"ok": False, "error": str(e)}

    def power(self, a):
        act = a.get("action")
        cmd = {"lock": ["hyprlock"], "logout": ["hyprctl", "dispatch", "exit"],
               "reboot": ["systemctl", "reboot"], "poweroff": ["systemctl", "poweroff"]}.get(act)
        if cmd:
            subprocess.Popen(cmd, start_new_session=True)
        return {"ok": bool(cmd)}

    def inputRegion(self, a):
        GLib.idle_add(self.host.set_input, a.get("rects") or [], bool(a.get("keyboard")))
        return {"ok": True}

    CALLS = {"status": status, "toggle": toggle, "set": set, "theme": theme, "apps": apps_,
             "launch": launch, "power": power, "inputRegion": inputRegion}

    def call(self, name, args):
        fn = self.CALLS.get(name)
        if not fn:
            return None
        try:
            return fn(self, args or {})
        except Exception as e:
            print(f"wraith-shell: {name} failed: {e}", file=sys.stderr)
            return {"ok": False, "error": str(e)}


# --------------------------------------------------------------------------- wallpaper
DEFAULT_WP = {"base": "#141218", "c1": "#4a3fb8", "c2": "#8a2a63", "c3": "#1f4d7a"}
# the same soft colour fields as the CSS: (colour, centre x, centre y, radius x, radius y)
WP_FIELDS = (("c1", .18, .14, .60, .70), ("c2", .88, .42, .55, .65), ("c3", .46, 1.08, .60, .60))


def _rgb(hexcol):
    h = hexcol.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


class Wallpaper(Gtk.DrawingArea):
    """Wallpaper drawn with cairo; cross-fades when the colours change."""

    def __init__(self, colours):
        super().__init__()
        self.cur = self.target = {k: _rgb(v) for k, v in {**DEFAULT_WP, **(colours or {})}.items() if k in DEFAULT_WP}
        self.set_draw_func(self._draw)
        self._tick = None

    def set_colours(self, colours):
        new = {k: _rgb(v) for k, v in {**DEFAULT_WP, **(colours or {})}.items() if k in DEFAULT_WP}
        start, t0 = dict(self.cur), GLib.get_monotonic_time()

        def step(_w, _clock):
            u = min(1.0, (GLib.get_monotonic_time() - t0) / 600000)   # 0.6 s
            e = 1 - (1 - u) ** 3
            self.cur = {k: tuple(a + (b - a) * e for a, b in zip(start[k], new[k])) for k in new}
            self.queue_draw()
            if u >= 1:
                self._tick = None
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE
        if self._tick:
            self.remove_tick_callback(self._tick)
        self._tick = self.add_tick_callback(step)

    def _draw(self, _area, cr, w, h):
        cr.set_source_rgb(*self.cur["base"])
        cr.paint()
        for key, cx, cy, rx, ry in WP_FIELDS:
            r, g, b = self.cur[key]
            cr.save()
            cr.translate(cx * w, cy * h)
            cr.scale(rx * w, ry * h)
            grad = cairo.RadialGradient(0, 0, 0, 0, 0, 1)
            for stop, alpha in ((0, 1), (.25, .82), (.5, .45), (.7, 0)):
                grad.add_color_stop_rgba(stop, r, g, b, alpha)
            cr.set_source(grad)
            cr.arc(0, 0, 1, 0, 6.2832)
            cr.fill()
            cr.restore()


# --------------------------------------------------------------------------- host
BRIDGE_JS = """
window.wraith = {
  _n: 0, _p: {},
  call(name, args) {
    return new Promise((res) => {
      const id = ++this._n; this._p[id] = res;
      window.webkit.messageHandlers.wraith.postMessage(JSON.stringify({ id, name, args: args ?? {} }));
    });
  },
  _reply(id, value) { const r = this._p[id]; delete this._p[id]; if (r) r(value); },
};
"""


class Host:
    def __init__(self, app):
        self.app = app
        self.backend = Backend(self)
        self.views = []          # every webview (for theme relays)
        self.wallpapers = []
        self.ui_win = self.ui_view = None
        self._register_scheme()

    # ---- wraith:// scheme: the UI files and app icons ------------------------
    def _register_scheme(self):
        ctx = WebKit.WebContext.get_default()
        ctx.register_uri_scheme("wraith", self._serve)
        sec = ctx.get_security_manager()
        sec.register_uri_scheme_as_secure("wraith")
        sec.register_uri_scheme_as_cors_enabled("wraith")

    def _serve(self, req):
        uri = GLib.Uri.parse(req.get_uri(), GLib.UriFlags.NONE)
        host, path = uri.get_host(), urllib.parse.unquote(uri.get_path() or "/")
        if host == "ui":
            fp = os.path.realpath(os.path.join(UI_DIR, path.lstrip("/") or "index.html"))
            ok = fp.startswith(os.path.realpath(UI_DIR) + os.sep) and os.path.isfile(fp)
        elif host == "icon":
            fp = path
            ok = fp in self.backend.apps.allowed_icon_files and os.path.isfile(fp)
        else:
            ok = False
        if not ok:
            req.finish_error(GLib.Error.new_literal(Gio.io_error_quark(), "not found", int(Gio.IOErrorEnum.NOT_FOUND)))
            return
        mime = mimetypes.guess_type(fp)[0] or "application/octet-stream"
        if fp.endswith(".js"):
            mime = "text/javascript"
        stream = Gio.File.new_for_path(fp).read(None)
        req.finish(stream, os.path.getsize(fp), mime)

    # ---- windows -------------------------------------------------------------
    def _view(self, surface):
        ucm = WebKit.UserContentManager()
        ucm.add_script(WebKit.UserScript.new(BRIDGE_JS, WebKit.UserContentInjectedFrames.TOP_FRAME,
                                             WebKit.UserScriptInjectionTime.START, None, None))
        ucm.register_script_message_handler("wraith", None)
        view = WebKit.WebView(user_content_manager=ucm)
        ucm.connect("script-message-received::wraith", self._on_message, view)
        s = view.get_settings()
        debug = os.environ.get("WRAITH_SHELL_DEBUG") == "1"
        s.set_enable_developer_extras(debug)
        s.set_enable_write_console_messages_to_stdout(debug)
        s.set_hardware_acceleration_policy(WebKit.HardwareAccelerationPolicy.ALWAYS
                                           if os.environ.get("WRAITH_SHELL_SOFTWARE") != "1"
                                           else WebKit.HardwareAccelerationPolicy.NEVER)
        view.set_background_color(Gdk.RGBA(red=0, green=0, blue=0, alpha=0))
        view.connect("context-menu", lambda *a: True)   # no "Reload / Inspect" menu
        view.load_uri(f"wraith://ui/index.html?surface={surface}")
        self.views.append(view)
        return view

    def _layer_window(self, layer, namespace, monitor=None, anchors="tblr", zone=-1, keyboard=False):
        win = Gtk.Window(application=self.app)
        win.add_css_class("wraith-layer")
        LayerShell.init_for_window(win)
        LayerShell.set_layer(win, layer)
        LayerShell.set_namespace(win, namespace)
        if monitor is not None:
            LayerShell.set_monitor(win, monitor)
        for ch, edge in zip("tblr", (LayerShell.Edge.TOP, LayerShell.Edge.BOTTOM, LayerShell.Edge.LEFT, LayerShell.Edge.RIGHT)):
            LayerShell.set_anchor(win, edge, ch in anchors)
        LayerShell.set_exclusive_zone(win, zone)
        LayerShell.set_keyboard_mode(win, LayerShell.KeyboardMode.EXCLUSIVE if keyboard else LayerShell.KeyboardMode.NONE)
        return win

    def build(self):
        css = Gtk.CssProvider()
        css.load_from_string("window.wraith-layer, window.wraith-layer > * { background: none; }")
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        monitors = Gdk.Display.get_default().get_monitors()
        for i in range(monitors.get_n_items()):
            mon = monitors.get_item(i)
            w = self._layer_window(LayerShell.Layer.BACKGROUND, "wraith-wallpaper", mon)
            w.set_child(Wallpaper(self.backend.conf.get("wallpaper")))
            w.present()
            self.wallpapers.append(w)

        # reserve room for the bar and the dock
        for anchors, h, zone in (("tlr", BAR_H, BAR_H), ("blr", 1, DOCK_ZONE)):
            sp = self._layer_window(LayerShell.Layer.BOTTOM, "wraith-spacer", anchors=anchors, zone=zone)
            sp.set_default_size(1, h)
            sp.connect("map", lambda w: GLib.idle_add(lambda: w.get_surface().set_input_region(cairo.Region()) or False))
            sp.present()

        self.ui_win = self._layer_window(LayerShell.Layer.TOP, "wraith-shell")
        self.ui_view = self._view("ui")
        self.ui_win.set_child(self.ui_view)
        # click-through until the page reports its bar/dock (set after mapping:
        # changing the surface during realize leaves the layer surface unsized)
        self.ui_win.connect("map", lambda w: GLib.idle_add(self.set_input, [], False))
        self.ui_win.present()
        self._start_socket()

    # ---- page <-> host -------------------------------------------------------
    def _on_message(self, _ucm, value, view):
        try:
            msg = json.loads(value.to_string())
        except Exception:
            return
        # system calls can be slow (sudo, nmcli...): answer from a worker thread
        def work():
            result = self.backend.call(msg.get("name"), msg.get("args"))
            GLib.idle_add(self._reply, view, msg.get("id"), result)
        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _js(view, script):
        view.evaluate_javascript(script, -1, None, None, None, None, None)

    def _reply(self, view, call_id, result):
        self._js(view, f"window.wraith._reply({int(call_id or 0)}, {json.dumps(result)})")
        return False

    def relay_theme(self, colours):
        for w in self.wallpapers:
            w.get_child().set_colours(colours)
        return False

    def set_input(self, rects, keyboard):
        surf = self.ui_win.get_surface() if self.ui_win else None
        if surf is None:
            return False
        region = cairo.Region([cairo.RectangleInt(int(x), int(y), max(1, int(w)), max(1, int(h)))
                               for x, y, w, h in rects]) if rects else cairo.Region()
        surf.set_input_region(region)
        LayerShell.set_keyboard_mode(self.ui_win, LayerShell.KeyboardMode.EXCLUSIVE if keyboard
                                     else LayerShell.KeyboardMode.NONE)
        if keyboard:
            self.ui_view.grab_focus()
        return False

    # ---- wraith-shell-ctl ----------------------------------------------------
    def _start_socket(self):
        try:
            os.unlink(SOCK)
        except FileNotFoundError:
            pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(SOCK)
        os.chmod(SOCK, 0o600)
        srv.listen(4)

        def loop():
            while True:
                conn, _ = srv.accept()
                with conn:
                    cmd = conn.recv(64).decode(errors="ignore").strip()
                js = {"drawer": "shell.openDrawer()", "qs": "shell.openQS()", "close": "shell.closeAll()",
                      "refresh": "shell.refreshStatus()"}.get(cmd)
                if js:
                    GLib.idle_add(lambda s=js: (self._js(self.ui_view, f"window.shell && {s}"), False)[1])
        threading.Thread(target=loop, daemon=True).start()


def main():
    app = Gtk.Application(application_id="os.wraith.Shell", flags=Gio.ApplicationFlags.NON_UNIQUE)
    holder = {}

    def activate(a):
        if "host" not in holder:
            holder["host"] = Host(a)
            holder["host"].build()

    app.connect("activate", activate)
    app.hold()  # layer windows only: keep running even if none is "focused"
    return app.run([sys.argv[0]])


if __name__ == "__main__":
    sys.exit(main())
