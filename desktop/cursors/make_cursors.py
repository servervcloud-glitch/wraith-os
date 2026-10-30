#!/usr/bin/python3
"""Wraith cursor theme: the "Orbit" busy cursor.

Writes real Xcursor files (the format Linux desktops load) with every
animation frame drawn at each cursor size, so it is sharp at 100%-400%.

  default / left_ptr        plain Wraith arrow
  progress / left_ptr_watch arrow + four coloured dots orbiting (app loading)
  wait / watch              the orbit on its own, larger (system busy)
Everything else (text beam, hand, resize arrows) comes from Adwaita.

usage: make_cursors.py OUT_DIR [--preview PREFIX]
"""
import math, os, struct, sys
from PIL import Image, ImageDraw

SIZES = [24, 32, 48, 64, 96]          # nominal cursor sizes (100% .. 400%)
FRAMES, LOOP_MS = 32, 1600            # 32 frames, one full orbit per 1.6 s
SS = 4
DOTS = [(157, 151, 255), (255, 143, 184), (255, 194, 122), (111, 211, 255)]
FILL, EDGE = (241, 238, 250), (15, 14, 20)

# Arrow outline in a 24-unit box (tip at 2,2)
ARROW = [(2, 2), (2, 19.5), (6.6, 15.4), (9.8, 22.2), (12.6, 20.9), (9.5, 14.2), (15.5, 14.2)]


def arrow(draw, s, k):
    pts = [(x * k * s, y * k * s) for x, y in ARROW]
    w = max(1, round(1.5 * k * s))
    draw.polygon(pts, fill=FILL + (255,))
    draw.line(pts + [pts[0]], fill=EDGE + (255,), width=w, joint="curve")


def orbit(draw, s, cx, cy, radius, dot_r, phase):
    """Four dots circling, radius breathing in and out once per loop."""
    r = radius * (0.82 + 0.18 * math.sin(phase))
    for i, col in enumerate(DOTS):
        a = phase + i * math.pi / 2
        x, y = (cx + r * math.cos(a)) * s, (cy + r * math.sin(a)) * s
        dr = dot_r * s
        draw.ellipse([x - dr, y - dr, x + dr, y + dr], fill=col + (255,))


def frame(kind, size, f):
    """One frame as RGBA at exactly size x size."""
    k = size / 24
    big = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    phase = 2 * math.pi * f / FRAMES
    if kind == "arrow":
        arrow(d, SS, k)
    elif kind == "progress":
        arrow(d, SS, k)
        orbit(d, SS, 17.6 * k, 17.6 * k, 4.2 * k, 1.55 * k, phase)
    elif kind == "wait":
        orbit(d, SS, 12 * k, 12 * k, 7.0 * k, 2.4 * k, phase)
    return big.resize((size, size), Image.LANCZOS)


def premultiplied_argb(img):
    # Xcursor wants premultiplied ARGB, little-endian (bytes B, G, R, A)
    r, g, b, a = img.split()
    rr, gg, bb = (bytes(x * y // 255 for x, y in zip(ch.tobytes(), a.tobytes())) for ch in (r, g, b))
    out = bytearray(len(rr) * 4)
    out[0::4], out[1::4], out[2::4], out[3::4] = bb, gg, rr, a.tobytes()
    return bytes(out)


def write_xcursor(path, kind):
    """Xcursor file: header, table of contents, one image chunk per frame per size."""
    hot = {"arrow": (2, 2), "progress": (2, 2), "wait": (12, 12)}[kind]
    n = FRAMES if kind != "arrow" else 1
    delay = LOOP_MS // FRAMES
    chunks = []
    for size in SIZES:
        hx, hy = round(hot[0] * size / 24), round(hot[1] * size / 24)
        for f in range(n):
            img = frame(kind, size, f)
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


def main():
    out = sys.argv[1]
    cdir = os.path.join(out, "cursors")
    os.makedirs(cdir, exist_ok=True)
    for name, kind in (("default", "arrow"), ("progress", "progress"), ("wait", "wait")):
        write_xcursor(os.path.join(cdir, name), kind)
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
    with open(os.path.join(out, "index.theme"), "w") as fh:
        fh.write("[Icon Theme]\nName=Wraith\nComment=Wraith OS cursors - Orbit busy cursor, crafted by VIPIN\nInherits=Adwaita\n")
    if "--preview" in sys.argv:
        prefix = sys.argv[sys.argv.index("--preview") + 1]
        for kind in ("progress", "wait"):
            for size in (32, 96):
                frames = [frame(kind, size, f) for f in range(FRAMES)]
                frames[0].save(f"{prefix}-{kind}-{size}.png")
    print("wrote", cdir)


if __name__ == "__main__":
    main()
