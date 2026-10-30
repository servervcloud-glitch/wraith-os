#!/usr/bin/python3
"""Wraith cursor theme: the "Tile flip" busy cursor.

Writes real Xcursor files (the format Linux desktops load) with every
animation frame drawn at each cursor size, so it is sharp at 100%-400%.

  default / left_ptr        plain Wraith arrow
  progress / left_ptr_watch arrow + a Soft 3D tile flipping in 3D (app loading)
  wait / watch              the flipping tile on its own, larger (system busy)
Everything else (text beam, hand, resize arrows) comes from Adwaita.

usage: make_cursors.py OUT_DIR [--preview PREFIX]
"""
import math, os, struct, sys
from PIL import Image, ImageDraw

SIZES = [24, 32, 48, 64, 96]          # nominal cursor sizes (100% .. 400%)
FRAMES, LOOP_MS = 32, 1600            # 32 frames, one flip cycle per 1.6 s
SS = 4
FILL, EDGE = (241, 238, 250), (15, 14, 20)

# Arrow outline in a 24-unit box (tip at 2,2)
ARROW = [(2, 2), (2, 19.5), (6.6, 15.4), (9.8, 22.2), (12.6, 20.9), (9.5, 14.2), (15.5, 14.2)]


def arrow(draw, s, k):
    pts = [(x * k * s, y * k * s) for x, y in ARROW]
    w = max(1, round(1.5 * k * s))
    draw.polygon(pts, fill=FILL + (255,))
    draw.line(pts + [pts[0]], fill=EDGE + (255,), width=w, joint="curve")


def cubic_bezier(x1, y1, x2, y2):
    """CSS cubic-bezier easing as a function of progress 0..1."""
    def bez(t, a, b):
        return 3 * a * (1 - t) ** 2 * t + 3 * b * (1 - t) * t ** 2 + t ** 3
    def ease(x):
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2
            if bez(mid, x1, x2) < x:
                lo = mid
            else:
                hi = mid
        return bez((lo + hi) / 2, y1, y2)
    return ease


SPRING = cubic_bezier(0.34, 1.56, 0.64, 1)   # same springy curve as the desktop


def tile_texture(px):
    """The Soft 3D icon tile: glossy squircle with gradient, highlight and rim."""
    n = px * SS
    t = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    grad = Image.new("RGBA", (n, n))
    top, bot = (185, 180, 255), (106, 95, 240)
    gd = ImageDraw.Draw(grad)
    for y in range(n):
        u = y / max(1, n - 1)
        gd.line([(0, y), (n, y)], fill=tuple(round(a + (b - a) * u) for a, b in zip(top, bot)) + (255,))
    mask = Image.new("L", (n, n), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, n - 1, n - 1], radius=n * 0.32, fill=255)
    t.paste(grad, (0, 0), mask)
    hl = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse([n * 0.12, n * 0.05, n * 0.88, n * 0.45], fill=(255, 255, 255, 95))
    hl.putalpha(Image.composite(hl.getchannel("A"), Image.new("L", (n, n), 0), mask))
    t.alpha_composite(hl)
    return t


def solve_perspective(dst, src):
    """Coefficients for PIL's PERSPECTIVE transform mapping dst quad -> src quad."""
    import numpy as np
    A, B = [], []
    for (x, y), (u, v) in zip(dst, src):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); B.append(u)
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y]); B.append(v)
    return np.linalg.solve(np.array(A, float), np.array(B, float)).tolist()


def flipping_tile(canvas, s, cx, cy, size_units, f, k):
    """Tile rotates 180 deg around Y (spring), then 180 deg around X (spring)."""
    t = f / FRAMES
    if t < 0.5:
        ry, rx = math.pi * SPRING(t / 0.5), 0.0
    else:
        ry, rx = math.pi, math.pi * SPRING((t - 0.5) / 0.5)
    h = size_units * k * s / 2
    D = h * 2 * 4.0                       # perspective distance (keeps the near edge inside the cursor box)
    corners = [(-h, -h), (h, -h), (h, h), (-h, h)]
    pts = []
    for x, y in corners:
        x1, z1 = x * math.cos(ry), -x * math.sin(ry)          # rotate around Y
        y2, z2 = y * math.cos(rx) - z1 * math.sin(rx), y * math.sin(rx) + z1 * math.cos(rx)  # around X
        f_ = D / (D - z2)
        pts.append((cx * s + x1 * f_, cy * s + y2 * f_))
    area = 0.5 * sum(pts[i][0] * pts[(i + 1) % 4][1] - pts[(i + 1) % 4][0] * pts[i][1] for i in range(4))
    if abs(area) < (h * 0.08) ** 2:
        return                            # edge-on: nothing visible
    tex = tile_texture(round(size_units * k))
    n = tex.width
    if area < 0:                          # back face: mirrored and a touch darker
        tex = tex.transpose(Image.FLIP_LEFT_RIGHT)
        dark = Image.new("RGBA", tex.size, (40, 30, 90, 70))
        dark.putalpha(Image.composite(dark.getchannel("A"), Image.new("L", tex.size, 0), tex.getchannel("A")))
        tex.alpha_composite(dark)
    coeffs = solve_perspective(pts, [(0, 0), (n, 0), (n, n), (0, n)])
    warped = tex.transform(canvas.size, Image.PERSPECTIVE, coeffs, Image.BICUBIC)
    # soft shadow under the tile
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([cx * s - h * 0.8, cy * s + h * 1.02, cx * s + h * 0.8, cy * s + h * 1.32],
                               fill=(0, 0, 0, 70))
    canvas.alpha_composite(sh)
    canvas.alpha_composite(warped)


def frame(kind, size, f):
    """One frame as RGBA at exactly size x size."""
    k = size / 24
    big = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    if kind == "arrow":
        arrow(d, SS, k)
    elif kind == "progress":
        arrow(d, SS, k)
        flipping_tile(big, SS, 17.4 * k, 16.4 * k, 8.4, f, k)
    elif kind == "wait":
        flipping_tile(big, SS, 12 * k, 10.6 * k, 13.0, f, k)
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
        fh.write("[Icon Theme]\nName=Wraith\nComment=Wraith OS cursors - Tile flip busy cursor, crafted by VIPIN\nInherits=Adwaita\n")
    if "--preview" in sys.argv:
        prefix = sys.argv[sys.argv.index("--preview") + 1]
        for kind in ("progress", "wait"):
            for size in (32, 96):
                frames = [frame(kind, size, f) for f in range(FRAMES)]
                frames[0].save(f"{prefix}-{kind}-{size}.png")
    print("wrote", cdir)


if __name__ == "__main__":
    main()
