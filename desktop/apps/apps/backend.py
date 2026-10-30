"""App Manager backend: Kali's tool catalogue (installed or not), search, install, remove."""
import configparser
import glob
import os
import re
import subprocess
import sys
import urllib.parse
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))
from sysutil import Admin, PkgJob, run  # noqa: E402

KALI_APPS = "/usr/share/kali-menu/applications"     # every Kali tool, installed or not
KALI_MENU = "/etc/xdg/menus/applications-merged/kali-applications.menu"
ICON_ROOTS = ["/usr/share/icons/hicolor", "/usr/share/icons/Flat-Remix-Blue-Dark", "/usr/share/icons/Adwaita", "/usr/share/pixmaps"]


def installed_set():
    ok, out = run(["dpkg-query", "-W", "-f", "${Package}\t${db:Status-Abbrev}\n"], timeout=30)
    return {l.split("\t")[0] for l in out.splitlines() if "\t" in l and l.split("\t")[1].startswith("ii")} if ok else set()


class Backend:
    def __init__(self, emit):
        self.emit = emit
        self.admin = Admin()
        self.job = PkgJob(self.admin, emit, activity="apps")
        self._icons = None
        self.icon_files = set()

    def auth(self, a):
        return self.admin.auth(a)

    # ---- icons ------------------------------------------------------------------
    def _icon(self, name):
        if not name:
            return None
        if self._icons is None:
            self._icons = {}
            for root in reversed(ICON_ROOTS):     # earlier roots win
                for f in glob.glob(os.path.join(root, "**", "*.svg"), recursive=True) + glob.glob(os.path.join(root, "**", "*.png"), recursive=True):
                    self._icons[os.path.splitext(os.path.basename(f))[0]] = f
        p = name if os.path.isabs(name) else self._icons.get(name)
        if not p or not os.path.isfile(p):
            return None
        return "wraith://icon" + urllib.parse.quote(p)        # served by the app host

    # ---- catalogue ------------------------------------------------------------------
    def _categories(self):
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
            if not title or title == "Usual Applications":
                continue
            order.append(title)
            for c in top.iter("Category"):
                cat_map.setdefault(c.text, [])
                if title not in cat_map[c.text]:
                    cat_map[c.text].append(title)
        return cat_map, order

    def catalog(self, _):
        cat_map, order = self._categories()
        inst = installed_set()
        tools = {}
        for f in sorted(glob.glob(os.path.join(KALI_APPS, "*.desktop"))):
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cp.read(f, encoding="utf-8")
                e = cp["Desktop Entry"]
            except Exception:
                continue
            pkg = e.get("X-Kali-Package")
            if not pkg or pkg in tools:
                continue
            cats = []
            for c in e.get("Categories", "").split(";"):
                for t in cat_map.get(c, []):
                    if t not in cats:
                        cats.append(t)
            tools[pkg] = {"pkg": pkg, "name": e.get("Name", pkg), "comment": e.get("Comment", ""),
                          "icon": self._icon(e.get("Icon")), "cats": cats, "installed": pkg in inst,
                          "desktop": os.path.basename(f)[:-8], "terminal": e.get("Terminal", "").lower() == "true"}
        return {"tools": sorted(tools.values(), key=lambda t: t["name"].lower()), "categories": order}

    def search(self, a):
        """Any Debian/Kali package, for things that aren't in Kali's tool menu."""
        q = a.get("q", "").strip()
        if len(q) < 2 or not re.fullmatch(r"[\w .+-]+", q):
            return {"results": []}
        ok, out = run(["apt-cache", "search", "--names-only", q], timeout=20)
        inst = installed_set()
        res = []
        for line in (out.splitlines() if ok else [])[:60]:
            name, _, desc = line.partition(" - ")
            res.append({"pkg": name, "name": name, "comment": desc, "installed": name in inst})
        return {"results": res}

    def details(self, a):
        pkg = a.get("pkg", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", pkg):
            return {}
        ok, out = run(["apt-cache", "show", "--no-all-versions", pkg], timeout=15)
        info = {}
        if ok:
            for k in ("Version", "Installed-Size", "Homepage", "Section"):
                m = re.search(rf"^{k}: (.+)$", out, re.M)
                info[k.lower()] = m.group(1) if m else ""
            m = re.search(r"^Description(?:-\w+)?: (.+?)\n((?: .+\n?)*)", out, re.M)
            if m:
                info["summary"] = m.group(1)
                info["description"] = "\n".join(l[1:] if l.strip() != "." else "" for l in m.group(2).splitlines())
        return info

    # ---- actions ------------------------------------------------------------------------
    def install(self, a):
        return self.job.start("install", *a.get("pkgs", []))

    def remove(self, a):
        return self.job.start("remove", *a.get("pkgs", []))

    def openSettings(self, _):
        subprocess.Popen(["wraith-app", "settings", "page=update"], start_new_session=True)
        return {"ok": True}

    def launch(self, a):
        """Open an installed tool (terminal tools open in the Wraith terminal)."""
        d = a.get("desktop", "")
        path = os.path.join("/usr/share/applications", d + ".desktop")
        if not re.fullmatch(r"[\w.+-]+", d) or not os.path.isfile(path):
            return {"ok": False}
        cp = configparser.ConfigParser(interpolation=None, strict=False)
        cp.read(path, encoding="utf-8")
        e = cp["Desktop Entry"]
        import shlex
        argv = [re.sub(r"%[a-zA-Z]", "", x) for x in shlex.split(e.get("Exec", "")) if not re.fullmatch(r"%[a-zA-Z]", x)]
        if e.get("Terminal", "").lower() == "true":
            argv = ["wraith-app", "terminal", "run=" + " ".join(shlex.quote(x) for x in argv), "title=" + e.get("Name", d)]
        subprocess.Popen(argv, start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         cwd=os.path.expanduser("~"))
        return {"ok": True}
