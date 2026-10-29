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

# The connection can drop on big downloads: make every download retry.
retry() {
    local n=1
    until "$@"; do
        [ $n -ge 5 ] && { log "Failed after $n tries: $*"; return 1; }
        log "Download interrupted, retrying ($n/5) in 15 s..."; sleep 15; n=$((n+1))
    done
}
mkdir -p /etc/apt/apt.conf.d
printf 'Acquire::Retries "10";\nAcquire::http::Timeout "60";\nAcquire::https::Timeout "60";\n' > /etc/apt/apt.conf.d/80-wraith-retries

log "Installing build tools"
export DEBIAN_FRONTEND=noninteractive
retry apt-get update -qq
retry apt-get install -y -qq live-build debootstrap kali-archive-keyring \
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

# Same retries inside the image being built
mkdir -p config/apt
printf 'Acquire::Retries "10";\nAcquire::http::Timeout "60";\n' > config/apt/80-wraith-retries.conf

log "Building (this takes hours the first time; later builds reuse the cache)"
# If a download drops mid-build, run lb build again: finished stages are
# skipped and already-downloaded packages are reused from the cache.
for attempt in 1 2 3 4; do
    if lb build; then break; fi
    [ $attempt -eq 4 ] && { log "Build failed 4 times, see the log above"; exit 1; }
    log "Build stopped (attempt $attempt/4), probably a dropped download - resuming in 30 s"
    sleep 30
    # A half-finished base system cannot be resumed: start that stage clean
    # (its packages are already in the cache, so this is quick).
    [ -f .build/bootstrap ] || { lb clean --chroot 2>/dev/null || rm -rf chroot; }
done

ISO=$(ls -1 "$WORK"/*.iso | head -n1)
STAMP=$(date -u +%Y%m%d-%H%M)
NAME="wraith-${STAMP}-amd64.iso"
mv "$ISO" "$OUT/$NAME"
( cd "$OUT" && sha256sum "$NAME" > "$NAME.sha256" )
log "Done: $OUT/$NAME ($(du -h "$OUT/$NAME" | cut -f1))"
