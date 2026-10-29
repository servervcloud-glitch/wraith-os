#!/bin/bash
# Builds the Wraith OS ISO. Runs inside a privileged kalilinux/kali-rolling
# container (see .github/workflows/build.yml), or on any Kali machine as root.
#
#   /src   this repository (read-only is fine)
#   /cache apt/debootstrap package cache kept between builds
#   /out   finished ISO + SHA256SUMS
set -euo pipefail

SRC=${SRC:-/src}
CACHE=${CACHE:-/cache}
OUT=${OUT:-/out}
WORK=/work

log() { printf '\n\033[1;35m[wraith]\033[0m %s\n' "$*"; }

log "Installing build tools"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq live-build debootstrap kali-archive-keyring \
    xorriso squashfs-tools mtools dosfstools grub-pc-bin grub-efi-amd64-bin \
    grub-common python3 python3-pil python3-fonttools fontconfig >/dev/null

log "Preparing work tree"
rm -rf "$WORK"
mkdir -p "$WORK" "$CACHE" "$OUT"
cp -a "$SRC"/auto "$SRC"/config "$WORK"/
ln -s "$CACHE" "$WORK/cache"
cd "$WORK"

log "Rendering boot menu and boot animation assets"
python3 "$SRC"/branding/render.py --out "$WORK"

# The server has 4 GB RAM: cap squashfs memory and threads, swap covers spikes.
export MKSQUASHFS_OPTIONS="-mem 1024M -processors $(nproc) -b 1M"

log "Configuring"
lb config

log "Building (this takes hours the first time; later builds reuse the cache)"
lb build

ISO=$(ls -1 "$WORK"/*.iso | head -n1)
STAMP=$(date -u +%Y%m%d-%H%M)
NAME="wraith-${STAMP}-amd64.iso"
mv "$ISO" "$OUT/$NAME"
( cd "$OUT" && sha256sum "$NAME" > "$NAME.sha256" )
log "Done: $OUT/$NAME ($(du -h "$OUT/$NAME" | cut -f1))"
