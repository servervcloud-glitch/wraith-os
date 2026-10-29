#!/usr/bin/python3
"""Preview the Wraith boot animation without booting: replays the same timing
and layout as the Plymouth script, compositing the real theme images 1:1.

  preview.py THEME_DIR WIDTH HEIGHT out.mp4      (simulated boot + Tor)
  preview.py THEME_DIR WIDTH HEIGHT out.png --at 12
"""
import json, math, subprocess, sys
from PIL import Image

theme, W, H, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
at = float(sys.argv[6]) if len(sys.argv) > 6 and sys.argv[5] == "--at" else None
L = json.load(open(f"{theme}/layout.json"))
sets = {int(k): v for k, v in L["sets"].items()}
set_h = min(sets)
for h in sorted(sets):
    if h <= H:
        set_h = h
g = sets[set_h]
D = f"{theme}/h{set_h}/"
bg = tuple(L["palette"]["bg"])
U = g["u"]
HZ, NF, NL = 50, 32, 6

cache = {}
def img(n):
    if n not in cache:
        cache[n] = Image.open(D + n).convert("RGBA")
    return cache[n]

def px(v): return int(math.floor(v + 0.5))
def c01(v): return max(0.0, min(1.0, v))
def back(p, s): q = p - 1; return 1 + (s + 1) * q ** 3 + s * q * q

def put(cv, im, x, y, op):
    if op <= 0: return
    if op < 1:
        im = im.copy(); a = im.getchannel("A").point(lambda v: int(v * op)); im.putalpha(a)
    cv.alpha_composite(im, (x, y)) if 0 <= x and 0 <= y and x + im.width <= W and y + im.height <= H else cv.paste(im, (x, y), im)

# simulated boot: systemd progress estimate, then Tor bootstrap reports
def sys_progress(t): return min(1.0, (t / 6.5) ** 0.85 + 0.03 * math.sin(t * 3))
TOR_EVENTS = [(5.6, 0), (6.2, 10), (6.9, 25), (7.4, 45), (8.3, 60), (8.8, 75), (9.6, 90), (10.3, 100)]

state = dict(target=0.0, shown=0.0, sys_p=0.0, tor="none", tor_pct=0, key="", status_t=0.0, done_t=0.0)
CX, WORD_CY = W / 2, H * 0.44
BASE_Y = WORD_CY - g["word_mid"]; WORD_X = CX - g["word_w"] / 2
BAR_CY = H * 0.70; BAR_X = px(CX - g["bar_w"] / 2)

def frame(tick):
    s = state; t = tick / HZ
    s["sys_p"] = max(s["sys_p"], sys_progress(t))
    for et, pct in TOR_EVENTS:
        if t >= et:
            if pct >= 100: s["tor"], s["tor_pct"] = "done", 100
            elif pct >= s["tor_pct"]: s["tor"], s["tor_pct"] = "active", pct
    cv = Image.new("RGBA", (W, H), bg + (255,))

    sp = c01((t - 2.0) / 0.8); se = back(sp, 1.7); scale = 1 - 0.55 * se
    d = max(g["dot_min"], min(g["dot_max"], int(g["dot_big"] * scale + 0.5)))
    space = g["dot_space"] * scale
    for i in range(4):
        p = c01((t - 0.2 - 0.09 * i) / 0.9)
        drop = -150 * U * (1 - back(p, 2.2))
        q = (t - 1.15 - 0.08 * i) / 0.5
        hop = -15 * U * math.sin(math.pi * (q - int(q))) if 0 <= q < 2 else 0
        im = img(f"d{i}-{d}.png")
        put(cv, im, px(CX + (i - 1.5) * space - im.width / 2), px(WORD_CY + 76 * U * se + drop + hop - im.height / 2), c01(p * 4))

    for i in range(NL):
        st = 2.05 + 0.06 * i; p = c01((t - st) / 0.7); op = c01(p * 2.5); c = c01((t - st) / 1.0)
        y = px(BASE_Y + g["ly"][i] + 34 * U * (1 - back(p, 1.56))); x = px(WORD_X + g["lx"][i])
        put(cv, img(f"l{i}w.png"), x, y, op * c)
        put(cv, img(f"l{i}c.png"), x, y, op * (1 - c))

    a = 0.7 * min(s["sys_p"] / 0.9, 1)
    final = s["tor"] in ("done", "later", "off")
    want = 1 if final else (0.7 + 0.3 * s["tor_pct"] / 100 if s["tor"] == "active" else a)
    s["target"] = max(s["target"], want)
    s["shown"] += (s["target"] - s["shown"]) * 0.08
    if s["target"] - s["shown"] < 0.002: s["shown"] = s["target"]
    key = {"done": "desktop", "later": "later", "off": "direct", "active": "tor"}.get(s["tor"]) or \
        ("start" if a < 0.25 else "drivers" if a < 0.5 else "secure")
    if key != s["key"]: s["key"], s["status_t"] = key, t

    ba = c01((t - 3.0) / 0.6); rise = 12 * U * (1 - back(ba, 1.56))
    cy = BAR_CY + rise; top = px(cy - g["bar_h"] / 2)
    fill = g["stroke"] / 2 + s["shown"] * (g["bar_w"] - g["stroke"])
    done = s["shown"] >= 0.999
    if done and s["done_t"] == 0: s["done_t"] = t
    fl = c01((t - s["done_t"]) / 0.4) if done else 0
    k = int(t * NF * 1.1) - int(t * 1.1) * NF
    put(cv, img(f"wave{k}.png"), BAR_X, top, ba * (1 - fl))
    put(cv, img("flat.png"), BAR_X, top, ba * fl)
    put(cv, img("mask.png"), px(BAR_X + fill), top, 1)
    phase = 2 * math.pi * k / NF
    ly = cy + g["amp"] * math.sin(2 * math.pi * fill / g["lam"] - phase) * (1 - fl)
    if fill > g["stroke"]: put(cv, img("lead.png"), px(BAR_X + fill - g["lead"] / 2), px(ly - g["lead"] / 2), ba)
    tx = BAR_X + fill + g["gap"]
    show_track = tx < BAR_X + g["bar_w"] - g["stroke"] and not done
    if show_track: put(cv, img("track.png"), px(tx - g["stroke"] / 2), top, ba)
    put(cv, img("mask.png"), px(BAR_X + g["bar_w"] - g["stroke"] / 2), top, 1)
    if show_track:
        put(cv, img("endcap.png"), px(BAR_X + g["bar_w"] - g["stroke"] / 2 - g["endd"] / 2), px(cy - g["endd"] / 2), ba)
        put(cv, img("stop.png"), px(BAR_X + g["bar_w"] - g["stroke"] / 2 - g["stopd"] / 2), px(cy - g["stopd"] / 2), ba)
    st_im = img(f"s-{s['key']}.png"); sf = c01((t - s["status_t"]) / 0.25)
    put(cv, st_im, px(CX - st_im.width / 2), px(cy + 40 * U - st_im.height / 2), ba * sf)
    cr = img("credit.png")
    put(cv, cr, px(CX - cr.width / 2), px(H - 44 * U - cr.height / 2), c01((t - 3.0) / 1.0))
    return cv.convert("RGB")

if at is not None:
    for tick in range(int(at * HZ) + 1):
        f = frame(tick)
    f.save(out); sys.exit()

ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                       "-s", f"{W}x{H}", "-r", "50", "-i", "-", "-c:v", "libx264", "-preset", "veryfast",
                       "-crf", "14", "-pix_fmt", "yuv420p", "-r", "50", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
for tick in range(int(12.5 * HZ)):
    ff.stdin.write(frame(tick).tobytes())
ff.stdin.close(); ff.wait()
