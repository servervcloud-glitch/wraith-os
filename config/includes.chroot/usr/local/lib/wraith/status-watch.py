#!/usr/bin/python3
"""Publishes live system state for the desktop's Dynamic Island.

Runs as root (Tor's control port and USBGuard need it) and writes
/run/wraith/desktop-status.json, readable by everyone:
  torBootstrap  0-100 while Tor connects (100 once it's up), null when Tor is off
  torPhase      what Tor is doing ("Connecting to a relay", ...)
  usbBlocked    name of the last USB device USB guard blocked
  usbEvent      counter that goes up with every blocked device
  camera        names of the programs that have a camera open (privacy dot)
"""
import json, os, re, subprocess, threading, time

OUT = "/run/wraith/desktop-status.json"
state = {"torBootstrap": None, "torPhase": "", "usbBlocked": None, "usbEvent": 0, "camera": []}
lock = threading.Lock()


def publish():
    with lock:
        data = json.dumps(state)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"
    with open(tmp, "w") as fh:
        fh.write(data)
    os.chmod(tmp, 0o644)
    os.replace(tmp, OUT)


def tor_mode_on():
    try:
        return open("/etc/wraith/tor-mode").read().strip() != "off"
    except OSError:
        return True


def watch_tor():
    from stem.control import Controller
    while True:
        if not tor_mode_on():
            if state["torBootstrap"] is not None:
                with lock:
                    state.update(torBootstrap=None, torPhase="")
                publish()
            time.sleep(5)
            continue
        try:
            with Controller.from_port(port=9051) as c:
                c.authenticate()
                while tor_mode_on():
                    phase = c.get_info("status/bootstrap-phase")
                    pct = int(re.search(r"PROGRESS=(\d+)", phase).group(1))
                    summary = (re.search(r'SUMMARY="([^"]*)"', phase) or [None, ""])[1]
                    if pct != state["torBootstrap"]:
                        with lock:
                            state.update(torBootstrap=pct, torPhase=summary)
                        publish()
                    time.sleep(0.5 if pct < 100 else 5)
        except Exception:
            time.sleep(2)   # Tor not up yet


def watch_usb():
    while True:
        try:
            p = subprocess.Popen(["usbguard", "watch"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            for line in p.stdout:
                if re.search(r"target(_new)?=block", line):
                    name = (re.search(r'name "([^"]*)"', line) or [None, "USB device"])[1] or "USB device"
                    with lock:
                        state["usbBlocked"] = name
                        state["usbEvent"] += 1
                    publish()
            p.wait()
        except Exception:
            pass
        time.sleep(5)   # usbguard not running yet, try again


def watch_camera():
    """Any process holding /dev/video* open = camera in use (checked from the
    kernel's side, so it covers every program, not just well-behaved apps)."""
    while True:
        users = set()
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                for fd in os.scandir(f"/proc/{pid}/fd"):
                    try:
                        if os.readlink(fd.path).startswith("/dev/video"):
                            users.add(open(f"/proc/{pid}/comm").read().strip())
                            break
                    except OSError:
                        pass
            except OSError:
                pass
        cams = sorted(users)
        if cams != state["camera"]:
            with lock:
                state["camera"] = cams
            publish()
        time.sleep(1.5)


if __name__ == "__main__":
    publish()
    threading.Thread(target=watch_usb, daemon=True).start()
    threading.Thread(target=watch_camera, daemon=True).start()
    watch_tor()
