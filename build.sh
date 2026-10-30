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

# /work lives on the PC (not inside the container), so if the PC restarts or
# the connection drops, the next run picks up where this one stopped -
# as long as the code hasn't changed (same commit).
COMMIT=${WRAITH_COMMIT:-unknown}
mkdir -p "$WORK" "$CACHE" "$OUT"
if [ -f "$WORK/.wraith-commit" ] && [ "$(cat "$WORK/.wraith-commit")" = "$COMMIT" ] && [ -d "$WORK/.build" ]; then
    RESUME=1
    log "Resuming the unfinished build of $COMMIT"
else
    RESUME=0
    log "Preparing a fresh work tree"
    # Unmount anything a crashed run left mounted, then start clean
    grep -o " $WORK/chroot[^ ]*" /proc/mounts | sort -r | xargs -r -n1 umount -lf 2>/dev/null || true
    find "$WORK" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true
    cp -a "$SRC"/auto "$SRC"/config "$WORK"/
    ln -s "$CACHE" "$WORK/cache"
    echo "$COMMIT" > "$WORK/.wraith-commit"
fi
cd "$WORK"

# Low-RAM friendly compression (needed on fresh and resumed runs alike)
export MKSQUASHFS_OPTIONS="-mem 1024M -processors $(nproc) -b 1M"

if [ "$RESUME" = 0 ]; then
log "Rendering boot menu and boot animation assets"
python3 "$SRC"/branding/render.py --out "$WORK"

# Skip any package that this Kali snapshot doesn't have, instead of failing
# the whole build (Kali drops and renames packages over time).
# Installable = has a real version to install, or another package provides it.
# (apt-cache show also "finds" names that are only mentioned by other packages.)
installable() {
    local cand
    cand=$(apt-cache policy "$1" 2>/dev/null | awk '/Candidate:/ {print $2}')
    [ -n "$cand" ] && [ "$cand" != "(none)" ] && return 0
    apt-cache showpkg "$1" 2>/dev/null | sed -n '/^Reverse Provides:/,$p' | tail -n +2 | grep -q .
}
log "Checking the package lists against the Kali archive"
for list in config/package-lists/*.list.chroot; do
    tmp=$(mktemp)
    while IFS= read -r line; do
        pkg=$(printf '%s' "$line" | sed 's/#.*//' | xargs)
        if [ -z "$pkg" ]; then echo "$line" >> "$tmp"; continue; fi
        if installable "$pkg"; then
            echo "$line" >> "$tmp"
        else
            echo "# skipped (not in Kali): $pkg" >> "$tmp"
            log "WARNING: package '$pkg' is not in the Kali archive - skipped"
        fi
    done < "$list"
    mv "$tmp" "$list"
done

log "Configuring"
lb config

# Same retries inside the image being built
mkdir -p config/apt
printf 'Acquire::Retries "10";\nAcquire::http::Timeout "60";\n' > config/apt/80-wraith-retries.conf
fi

# A run cut off mid-install can leave packages half set up: finish them.
if [ "$RESUME" = 1 ] && [ -d chroot/var/lib/dpkg ]; then
    log "Finishing packages left half-installed by the interrupted run"
    mount --bind /proc chroot/proc 2>/dev/null || true
    chroot chroot env DEBIAN_FRONTEND=noninteractive dpkg --configure -a || true
    umount -lf chroot/proc 2>/dev/null || true
fi

log "Building (this takes hours the first time; later builds reuse the cache)"
# If a download drops mid-build, run lb build again: finished stages are
# skipped and already-downloaded packages are reused from the cache.
for attempt in 1 2 3 4; do
    if lb build; then break; fi
    # Missing packages won't appear by retrying: stop now with a clear message.
    if grep -qE "has no installation candidate|Unable to locate package" build.log 2>/dev/null; then
        log "A package in the lists can't be installed:"
        grep -E "has no installation candidate|Unable to locate package" build.log | sort -u
        exit 1
    fi
    [ $attempt -eq 4 ] && { log "Build failed 4 times, see the log above"; exit 1; }
    log "Build stopped (attempt $attempt/4), probably a dropped download - resuming in 30 s"
    sleep 30
    # A half-finished base system cannot be resumed: start that stage clean
    # (its packages are already in the cache, so this is quick).
    [ -f .build/bootstrap ] || { lb clean --chroot 2>/dev/null || rm -rf chroot; }
done

ISO=$(ls -1 "$WORK"/*.iso 2>/dev/null | head -n1)
[ -n "$ISO" ] || { log "No ISO was produced - look for the first error (E:) above"; exit 1; }
STAMP=$(date -u +%Y%m%d-%H%M)
NAME="wraith-${STAMP}-amd64.iso"
mv "$ISO" "$OUT/$NAME"
( cd "$OUT" && sha256sum "$NAME" > "$NAME.sha256" )
log "Done: $OUT/$NAME ($(du -h "$OUT/$NAME" | cut -f1))"

# Free the ~40 GB work tree; the package cache stays for faster next builds.
log "Cleaning up the work tree"
lb clean --chroot --binary 2>/dev/null || true
find "$WORK" -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null || true
