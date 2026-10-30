# Start the Wraith desktop after logging in on the first console (tty1).
# Set WRAITH_NO_DESKTOP=1 to stay on the text console.
if [ -z "${WAYLAND_DISPLAY:-}" ] && [ -z "${DISPLAY:-}" ] && [ -z "${WRAITH_NO_DESKTOP:-}" ] \
   && [ "$(tty 2>/dev/null)" = /dev/tty1 ] && command -v start-hyprland >/dev/null 2>&1; then
    mkdir -p "$HOME/.cache"
    [ -f "$HOME/.config/hypr/hyprland.conf" ] || { mkdir -p "$HOME/.config/hypr"; cp /etc/skel/.config/hypr/hyprland.conf "$HOME/.config/hypr/"; }
    _wraith_start=$(date +%s)
    start-hyprland >"$HOME/.cache/wraith-desktop.log" 2>&1
    if [ $(( $(date +%s) - _wraith_start )) -lt 10 ]; then
        printf '\n  The Wraith desktop could not start.\n'
        printf '  In a virtual machine, turn on 3D acceleration for the display and reboot.\n'
        printf '  Details: ~/.cache/wraith-desktop.log    Try again: log out, or run start-hyprland\n\n'
    fi
    unset _wraith_start
fi
