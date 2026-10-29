# Wraith OS

A Kali + Tails hybrid: every Kali tool, with Tails-style amnesia and Tor.
Crafted by VIPIN.

## Boot options

| Menu entry | What it does |
|---|---|
| **Wraith Live** | Runs from the USB only. Everything goes through Tor (non-Tor traffic, DNS and IPv6 are blocked), new random MAC address, nothing written to any disk, RAM wiped as the system shuts down, and an instant power-off if the USB is pulled out. |
| **Install Wraith** | Installs Wraith to the hard drive (full-disk encryption recommended). The installed system has a Tor on/off switch: `sudo wraith-tor on` / `sudo wraith-tor off`. |
| Advanced options | Safe graphics, copy-to-RAM, UEFI firmware settings. |

## What's inside

- `auto/`, `config/` - the live-build definition of the OS (Kali rolling base, all tools via `kali-linux-everything`)
- `config/includes.chroot/etc/wraith/nft/` - Tor-only and direct firewalls (nftables)
- `config/includes.chroot/usr/local/sbin/` - `wraith-tor`, `wraith-usb`, `wraith-live-guard`, `wraith-display-fit`
- `branding/render.py` - draws the boot menu and boot animation at the exact pixel size of each screen
- `branding/preview.py` - renders a preview video of the boot animation without booting
- `build.sh` - builds the ISO inside a Kali container
- `.github/workflows/build.yml` - runs the build on your own server

## Building

**Windows PC?** Run `tools/setup-windows-builder.ps1` in PowerShell as administrator; it sets up WSL2, Docker and the runner for you.


Builds run on your own server through a self-hosted GitHub Actions runner
labelled `wraith-builder` (needs Docker and about 100 GB free disk).

1. Repo **Settings > Actions > Runners > New self-hosted runner**, Linux x64; run the commands it shows on the server, adding the label `wraith-builder`, then `sudo ./svc.sh install && sudo ./svc.sh start`.
2. **Actions > Build Wraith OS > Run workflow** (or push a tag like `v0.1`).
3. The ISO lands in `~/wraith-builds/` on the server, next to its `.sha256`.

Write it to a 32 GB+ USB stick:

```bash
sha256sum -c wraith-*.iso.sha256
sudo dd if=wraith-*.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

The first build takes several hours; later builds reuse the package cache.
