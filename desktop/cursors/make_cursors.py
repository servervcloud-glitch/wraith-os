#!/usr/bin/python3
"""Wraith cursor theme: the "Wisp tail" busy cursor.

Writes real Xcursor files (the format Linux desktops load) with every
animation frame drawn at each cursor size, so it is sharp at 100%-400%.

Two themes, solid colour with no outline: "Wraith" (white, dark desktop
theme) and "Wraith-Black" (black, light desktop theme).

  default / left_ptr        plain Wraith arrow
  progress / left_ptr_watch arrow + a small wisp looping with a rainbow tail (app loading)
  wait / watch              the wisp on its own, larger (system busy)
Everything else (text beam, hand, resize arrows) comes from Adwaita.

usage: make_cursors.py ICONS_DIR    (writes ICONS_DIR/Wraith and ICONS_DIR/Wraith-Black)
"""
import math, os, struct, sys
from PIL import Image, ImageDraw, ImageFilter

SIZES = [24, 32, 48, 64, 96]          # nominal cursor sizes (100% .. 400%)
FRAMES, LOOP_MS = 36, 1200            # 36 frames, one lap every 1.2 s
SS = 4
# Solid cursor colour, no outline: white for the dark desktop theme,
# black for the light one (the desktop switches theme with the colour scheme).
INKS = {"Wraith": (255, 255, 255), "Wraith-Black": (0, 0, 0)}

# Arrow outline in a 24-unit box (tip at 2,2)
ARROW = [(2, 2), (2, 19.5), (6.6, 15.4), (9.8, 22.2), (12.6, 20.9), (9.5, 14.2), (15.5, 14.2)]


def arrow(draw, s, k, ink):
    pts = [(x * k * s, y * k * s) for x, y in ARROW]
    draw.polygon(pts, fill=ink + (255,))


# Brand colours along the tail (the head is the cursor colour)
TAIL_COLS = [(157, 151, 255), (255, 143, 184), (255, 194, 122), (111, 211, 255)]


def wisp_colour(u, ink):
    """Colour along the wisp: u = 0 at the head, 1 at the tip of the tail."""
    cols = [ink] + TAIL_COLS
    u = min(max(u, 0.0), 1.0) * (len(cols) - 1)
    i = min(int(u), len(cols) - 2)
    a, b, w = cols[i], cols[i + 1], u - i
    return tuple(round(x + (y - x) * w) for x, y in zip(a, b))


def wisp_angle(t):
    """Head position on the loop (radians) at loop time t in 0..1.
    It surges and glides once per lap, so the tail stretches and shrinks."""
    return 2 * math.pi * (t - 0.11 * math.sin(2 * math.pi * t)) - math.pi / 2


def wisp(canvas, s, cx, cy, radius_units, f, k, ink, weight=1.0):
    """A glowing wisp running round a loop, trailing a tapered rainbow tail."""
    t0 = f / FRAMES
    R = radius_units * k * s
    head = 1.55 * k * s * weight                # head radius
    span = 0.42                                 # tail covers this much loop *time*
    steps = 90
    pts = []
    for i in range(steps + 1):
        u = i / steps                           # 0 head .. 1 tail tip
        a = wisp_angle(t0 - span * u)
        pts.append((cx * s + R * math.cos(a), cy * s + R * math.sin(a), u))
    W, H = canvas.size
    # 1) faint glow around the head
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x, y, _ = pts[0]
    g = head * 1.7
    ImageDraw.Draw(glow).ellipse([x - g, y - g, x + g, y + g], fill=(157, 151, 255, 110))
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(head * 0.5)))
    # 2) the tail, tip first so the head sits on top; tapers and fades out
    body = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(body)
    for x, y, u in reversed(pts):
        r = head * (1 - u) ** 1.3 + 0.12 * k * s
        al = round(255 * (1 - u) ** 0.8)
        bd.ellipse([x - r, y - r, x + r, y + r], fill=wisp_colour(u * 1.15, ink) + (al,))
    canvas.alpha_composite(body)
    # 3) solid head in the cursor colour
    x, y, _ = pts[0]
    c = head * 0.8
    ImageDraw.Draw(canvas).ellipse([x - c, y - c, x + c, y + c], fill=ink + (255,))


def frame(kind, size, f, ink=INKS["Wraith"]):
    """One frame as RGBA at exactly size x size."""
    k = size / 24
    big = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    if kind == "arrow":
        arrow(d, SS, k, ink)
    elif kind == "progress":
        arrow(d, SS, k, ink)
        wisp(big, SS, 17.5 * k, 17.1 * k, 3.1, f, k, ink, weight=0.76)
    elif kind == "wait":
        wisp(big, SS, 12 * k, 12 * k, 6.6, f, k, ink, weight=1.05)
    return big.resize((size, size), Image.LANCZOS)


def premultiplied_argb(img):
    # Xcursor wants premultiplied ARGB, little-endian (bytes B, G, R, A)
    r, g, b, a = img.split()
    rr, gg, bb = (bytes(x * y // 255 for x, y in zip(ch.tobytes(), a.tobytes())) for ch in (r, g, b))
    out = bytearray(len(rr) * 4)
    out[0::4], out[1::4], out[2::4], out[3::4] = bb, gg, rr, a.tobytes()
    return bytes(out)


def write_xcursor(path, kind, ink):
    """Xcursor file: header, table of contents, one image chunk per frame per size."""
    hot = {"arrow": (2, 2), "progress": (2, 2), "wait": (12, 12)}[kind]
    n = FRAMES if kind != "arrow" else 1
    delay = LOOP_MS // FRAMES
    chunks = []
    for size in SIZES:
        hx, hy = round(hot[0] * size / 24), round(hot[1] * size / 24)
        for f in range(n):
            img = frame(kind, size, f, ink)
            data = struct.pack("<9I", 36, 0xFFFD0002, size, 1, size, size, hx, hy, delay) + premultiplied_argb(img)
            chunks.append((size, data))
    header = struct.pack("<4sIII", b"Xcur", 16, 0x10000, len(chunks))
    pos = 16 + 12 * len(chunks)
    toc = b""
    for size, data in chunks:
        toc += struct.pack("<III", 0xFFFD0002, size, pos)
        pos += len(data)
    with open(path, "wb") as fh:
        fh.write(header + toc + b"".join(d for _, d in chunks))


def write_theme(out, name, ink, label):
    cdir = os.path.join(out, name, "cursors")
    os.makedirs(cdir, exist_ok=True)
    for fname, kind in (("default", "arrow"), ("progress", "progress"), ("wait", "wait")):
        write_xcursor(os.path.join(cdir, fname), kind, ink)
    # Every name apps and toolkits use for these three cursors
    links = {"default": ["left_ptr", "arrow", "top_left_arrow"],
             "progress": ["left_ptr_watch", "half-busy",
                          "08e8e1c95fe2fc01f976f1e063a24ccd", "3ecb610c1bf2410f44200f48c40d3599"],
             "wait": ["watch"]}
    for target, names in links.items():
        for n in names:
            p = os.path.join(cdir, n)
            if os.path.lexists(p):
                os.remove(p)
            os.symlink(target, p)
    with open(os.path.join(out, name, "index.theme"), "w") as fh:
        fh.write(f"[Icon Theme]\nName={name}\nComment=Wraith OS cursors ({label}) - Wisp tail busy cursor, crafted by VIPIN\nInherits=Adwaita\n")
    print("wrote", cdir)


def main():
    out = sys.argv[1]
    write_theme(out, "Wraith", INKS["Wraith"], "white, for the dark theme")
    write_theme(out, "Wraith-Black", INKS["Wraith-Black"], "black, for the light theme")


if __name__ == "__main__":
    main()
