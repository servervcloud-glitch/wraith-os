#!/usr/bin/python3
"""Tell the Wraith boot screen how far Tor has got.

Sends `plymouth update --status=wraith:tor:<0-100>` while Tor bootstraps,
so the progress bar only reaches 100% once Tor is really connected.
Never holds up the boot for long: with no wired connection (Wi-Fi is chosen
later on the desktop) it reports that and exits at once, and it gives up
after 60 seconds whatever happens.
"""
import os, subprocess, sys, time

def plymouth(status):
    subprocess.run(["plymouth", "update", f"--status={status}"], check=False)

def tor_mode_on():
    r = subprocess.run(["/usr/local/sbin/wraith-tor", "status"], capture_output=True, text=True)
    return r.stdout.strip() != "off"

def wired_link_up():
    for dev in os.listdir("/sys/class/net"):
        if dev == "lo" or os.path.exists(f"/sys/class/net/{dev}/wireless"):
            continue
        try:
            if open(f"/sys/class/net/{dev}/carrier").read().strip() == "1":
                return True
        except OSError:
            pass
    return False

def main():
    if subprocess.run(["plymouth", "--ping"]).returncode != 0:
        return
    if not tor_mode_on():
        plymouth("wraith:tor:off")
        return
    if not wired_link_up():
        plymouth("wraith:tor:later")
        return

    from stem.control import Controller
    deadline = time.monotonic() + 60
    last = -1
    while time.monotonic() < deadline:
        try:
            with Controller.from_port(port=9051) as c:
                c.authenticate()
                while time.monotonic() < deadline:
                    phase = c.get_info("status/bootstrap-phase")
                    pct = int(phase.split("PROGRESS=")[1].split()[0])
                    if pct != last:
                        plymouth(f"wraith:tor:{pct}")
                        last = pct
                    if pct >= 100:
                        return
                    time.sleep(0.25)
        except Exception:
            time.sleep(0.5)   # Tor not listening yet
    plymouth("wraith:tor:later")

if __name__ == "__main__":
    sys.exit(main())
