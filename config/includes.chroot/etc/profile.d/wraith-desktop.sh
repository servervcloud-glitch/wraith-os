# Start the Wraith desktop after logging in on the first console (tty1).
# Set WRAITH_NO_DESKTOP=1 to stay on the text console.
if [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${DISPLAY:-}" ] && [ -z "${WRAITH_NO_DESKTOP:-}" ] \
   && [ "$(tty 2>/dev/null)" = /dev/tty1 ] && command -v start-hyprland >/dev/null 2>&1; then
    mkdir -p "$HOME/.cache"
    mkdir -p "$HOME/.config/hypr"
    for f in hyprland.conf wraith-display.conf; do
        [ -f "$HOME/.config/hypr/$f" ] || cp "/etc/skel/.config/hypr/$f" "$HOME/.config/hypr/"
    done
    if [ "$(cat /sys/class/dmi/id/product_name 2>/dev/null)" = VirtualBox ]; then
        # VirtualBox's display (VMSVGA) starts Hyprland but never shows a
        # window - a black screen with no way out - so don't start it there.
        printf '\n  The Wraith desktop does not work in VirtualBox (its display adapter\n'
        printf '  cannot show the desktop). Use QEMU / virt-manager with virtio-gpu and 3D,\n'
        printf '  VMware, or a real computer. Try anyway: start-hyprland\n\n'
    else
        _wraith_start=$(date +%s)
        start-hyprland >"$HOME/.cache/wraith-desktop.log" 2>&1
        if [ $(( $(date +%s) - _wraith_start )) -lt 10 ]; then
            printf '\n  The Wraith desktop could not start.\n'
            if ! ls /dev/dri/card* >/dev/null 2>&1; then
                printf '  No graphics driver is running (safe graphics / nomodeset?). Boot "Wraith Live" instead.\n'
            else
                printf '  In a virtual machine, use a 3D-capable display (QEMU/virt-manager: virtio-gpu with 3D).\n'
            fi
            printf '  Details: ~/.cache/wraith-desktop.log    Try again: log out, or run start-hyprland\n\n'
        fi
        unset _wraith_start
    fi
fi
