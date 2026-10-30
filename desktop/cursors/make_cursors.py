#!/usr/bin/python3
"""Wraith cursor theme: the "Wisp tail" busy cursor.

Writes real Xcursor files (the format Linux desktops load) with every
animation frame drawn at each cursor size, so it is sharp at 100%-400%.

  default / left_ptr        plain Wraith arrow
  progress / left_ptr_watch arrow + a small wisp looping with a rainbow tail (app loading)
  wait / watch              the wisp on its own, larger (system busy)
Everything else (text beam, hand, resize arrows) comes from Adwaita.

usage: make_cursors.py OUT_DIR [--preview PREFIX]
"""
import math, os, struct, sys
from PIL import Image, ImageDraw, ImageFilter

SIZES = [24, 32, 48, 64, 96]          # nominal cursor sizes (100% .. 400%)
FRAMES, LOOP_MS = 36, 1200            # 36 frames, one lap every 1.2 s
SS = 4
FILL, EDGE = (241, 238, 250), (15, 14, 20)

# Arrow outline in a 24-unit box (tip at 2,2)
ARROW = [(2, 2), (2, 19.5), (6.6, 15.4), (9.8, 22.2), (12.6, 20.9), (9.5, 14.2), (15.5, 14.2)]


def arrow(draw, s, k):
    pts = [(x * k * s, y * k * s) for x, y in ARROW]
    w = max(1, round(1.5 * k * s))
    draw.polygon(pts, fill=FILL + (255,))
    draw.line(pts + [pts[0]], fill=EDGE + (255,), width=w, joint="curve")


# Brand colours, head -> end of tail
WISP_COLS = [(241, 238, 250), (157, 151, 255), (255, 143, 184), (255, 194, 122), (111, 211, 255)]


def wisp_colour(u):
    """Colour along the wisp: u = 0 at the head, 1 at the tip of the tail."""
    u = min(max(u, 0.0), 1.0) * (len(WISP_COLS) - 1)
    i = min(int(u), len(WISP_COLS) - 2)
    a, b, w = WISP_COLS[i], WISP_COLS[i + 1], u - i
    return tuple(round(x + (y - x) * w) for x, y in zip(a, b))


def wisp_angle(t):
    """Head position on the loop (radians) at loop time t in 0..1.
    It surges and glides once per lap, so the tail stretches and shrinks."""
    return 2 * math.pi * (t - 0.11 * math.sin(2 * math.pi * t)) - math.pi / 2


def wisp(canvas, s, cx, cy, radius_units, f, k, weight=1.0):
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
    # 1) thin dark rim (like the arrow's outline) so it reads on white windows
    rim = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(rim)
    for x, y, u in reversed(pts):
        r = head * (1 - u) ** 1.3 + 0.12 * k * s + 0.75 * k * s
        rd.ellipse([x - r, y - r, x + r, y + r], fill=EDGE + (round(210 * (1 - u) ** 1.1),))
    canvas.alpha_composite(rim)
    # 2) faint glow around the head
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    x, y, _ = pts[0]
    g = head * 1.7
    ImageDraw.Draw(glow).ellipse([x - g, y - g, x + g, y + g], fill=(157, 151, 255, 110))
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(head * 0.5)))
    # 3) the tail, tip first so the head sits on top; tapers and fades out
    body = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(body)
    for x, y, u in reversed(pts):
        r = head * (1 - u) ** 1.3 + 0.12 * k * s
        al = round(255 * (1 - u) ** 0.8)
        bd.ellipse([x - r, y - r, x + r, y + r], fill=wisp_colour(u * 1.15) + (al,))
    canvas.alpha_composite(body)
    # 4) bright core
    x, y, _ = pts[0]
    c = head * 0.55
    ImageDraw.Draw(canvas).ellipse([x - c, y - c, x + c, y + c], fill=(255, 255, 255, 235))


def frame(kind, size, f):
    """One frame as RGBA at exactly size x size."""
    k = size / 24
    big = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    if kind == "arrow":
        arrow(d, SS, k)
    elif kind == "progress":
        arrow(d, SS, k)
        wisp(big, SS, 17.5 * k, 17.1 * k, 3.1, f, k, weight=0.76)
    elif kind == "wait":
        wisp(big, SS, 12 * k, 12 * k, 6.6, f, k, weight=1.05)
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
        fh.write("[Icon Theme]\nName=Wraith\nComment=Wraith OS cursors - Wisp tail busy cursor, crafted by VIPIN\nInherits=Adwaita\n")
    if "--preview" in sys.argv:
        prefix = sys.argv[sys.argv.index("--preview") + 1]
        for kind in ("progress", "wait"):
            for size in (32, 96):
                frames = [frame(kind, size, f) for f in range(FRAMES)]
                frames[0].save(f"{prefix}-{kind}-{size}.png")
    print("wrote", cdir)


if __name__ == "__main__":
    main()
