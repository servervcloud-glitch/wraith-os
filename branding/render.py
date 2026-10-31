#!/usr/bin/python3
"""Render the Wraith boot menu (GRUB) and boot animation (Plymouth).

Everything is drawn from shapes and the Figtree font at the exact pixel size
of each screen resolution, so nothing is ever stretched or shrunk at boot.

  render.py --out WORK            write themes into a live-build work tree
  render.py --plymouth-only DIR --heights 1440   (installed-system hook)
  render.py --grub DIR --size 2560x1440          (installed-system hook)
"""
import argparse, json, math, os, shutil, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "fonts", "Figtree.ttf")
SS = 4  # shapes are drawn 4x and averaged down once, at render time, for clean edges

# Screen heights that get their own pixel-exact asset set. A screen uses the
# tallest set that fits it; the installed system also renders its own height.
HEIGHTS = [720, 768, 800, 900, 1024, 1050, 1080, 1200, 1440, 1600, 1800, 2160, 2880]

DOTS = [(157, 151, 255), (255, 143, 184), (255, 194, 122), (111, 211, 255)]
THEMES = {
    "wraith": dict(bg=(15, 14, 20), text=(241, 238, 250), status=(143, 137, 156),
                   wave=(198, 191, 255), track=(58, 54, 69), credit=(93, 88, 104),
                   name=(198, 191, 255), field=(37, 35, 45), prompt=(200, 194, 210)),
    "wraith-light": dict(bg=(246, 244, 251), text=(27, 26, 33), status=(95, 90, 107),
                         wave=(91, 85, 214), track=(226, 223, 255), credit=(150, 145, 160),
                         name=(91, 85, 214), field=(234, 231, 243), prompt=(70, 66, 80)),
}
STATUS = {
    "start": "Starting Wraith",
    "drivers": "Loading drivers",
    "secure": "Securing network",
    "tor": "Connecting to Tor",
    "later": "Tor will connect when you’re online",
    "direct": "Direct connection · Tor off",
    "desktop": "Starting desktop",
}
WORD = "Wraith"
WAVE_FRAMES = 32


def font(px, weight=500):
    f = ImageFont.truetype(FONT, max(1, round(px)))
    f.set_variation_by_axes([weight])
    return f


def rgba(c, a=255):
    return tuple(c) + (a,)


def shape(w, h, draw_fn):
    """Draw at SS x and average down: exact w x h output, smooth edges."""
    big = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(big), SS)
    return big.resize((w, h), Image.LANCZOS)


def circle(d, colour):
    n = max(1, math.ceil(d)) + 2
    off = (n - d) / 2
    return shape(n, n, lambda g, s: g.ellipse([off * s, off * s, (off + d) * s, (off + d) * s], fill=rgba(colour)))


def text_img(txt, px, colour, weight=500, tracking=0.0):
    f = font(px, weight)
    if tracking:
        widths = [f.getlength(ch) for ch in txt]
        total = sum(widths) + tracking * (len(txt) - 1)
        asc, desc = f.getmetrics()
        im = Image.new("RGBA", (math.ceil(total) + 4, asc + desc + 4), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        x = 2.0
        for ch, w in zip(txt, widths):
            d.text((x, 2 + asc), ch, font=f, fill=rgba(colour), anchor="ls")
            x += w + tracking
        return im.crop(im.getbbox() or (0, 0, 1, 1))
    l, t, r, b = f.getbbox(txt, anchor="ls")
    im = Image.new("RGBA", (r - l + 4, b - t + 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((2 - l, 2 - t), txt, font=f, fill=rgba(colour), anchor="ls")
    return im


def credit_img(px, c1, c2):
    a = text_img("CRAFTED BY", px, c1, 500, tracking=px * 0.22)
    b = text_img("VIPIN", px, c2, 600, tracking=px * 0.22)
    gap = round(px * 0.6)
    h = max(a.height, b.height)
    im = Image.new("RGBA", (a.width + gap + b.width, h), (0, 0, 0, 0))
    im.alpha_composite(a, (0, h - a.height))
    im.alpha_composite(b, (a.width + gap, h - b.height))
    return im


def wave_img(w, hh, stroke, amp, lam, phase, colour, flat=False):
    cy = hh / 2

    def draw(g, s):
        # Stamp round brush dabs densely along the curve: a perfectly even
        # stroke with round ends, no seams between segments.
        r = stroke * s / 2
        x = stroke / 2
        while x <= w - stroke / 2 + 1e-6:
            y = cy if flat else cy + amp * math.sin(2 * math.pi * x / lam - phase)
            g.ellipse([x * s - r, y * s - r, x * s + r, y * s + r], fill=rgba(colour))
            x += 0.25
    return shape(w, hh, draw)


def line_img(w, hh, stroke, colour):
    return wave_img(w, hh, stroke, 0, 1, 0, colour, flat=True)


def pill(w, h, colour):
    return shape(w, h, lambda g, s: g.rounded_rectangle([0, 0, w * s - 1, h * s - 1], radius=h * s / 2, fill=rgba(colour)))


# ---------------------------------------------------------------- Plymouth

def plymouth_set(H, pal, out):
    """One pixel-exact asset set for screens H pixels tall."""
    u = H / 1080
    os.makedirs(out, exist_ok=True)
    g = {}

    # Wordmark, one image per letter, final colour and its flash colour.
    f = font(76 * u, 500)
    l0, t0, r0, b0 = f.getbbox(WORD, anchor="ls")
    total = f.getlength(WORD)
    g["word_w"] = total
    g["word_mid"] = (t0 + b0) / 2          # baseline-to-visual-centre offset (negative)
    lx, ly = [], []
    for i, ch in enumerate(WORD):
        x = f.getlength(WORD[:i])
        l, t, r, b = f.getbbox(ch, anchor="ls")
        for name, col in (("w", pal["text"]), ("c", DOTS[i % 4])):
            im = Image.new("RGBA", (r - l + 4, b - t + 4), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((2 - l, 2 - t), ch, font=f, fill=rgba(col), anchor="ls")
            im.save(f"{out}/l{i}{name}.png")
        lx.append(round(x + l - 2, 2))
        ly.append(t - 2)
    g["lx"], g["ly"] = lx, ly

    # Dots at every whole-pixel diameter between settled and full size.
    big, small = 22 * u, 10 * u
    dmin, dmax = max(2, math.floor(small * 0.85)), math.ceil(big * 1.05)
    for c, col in enumerate(DOTS):
        for d in range(dmin, dmax + 1):
            circle(d, col).save(f"{out}/d{c}-{d}.png")
    g.update(dot_big=big, dot_min=dmin, dot_max=dmax, dot_space=big + 15 * u)

    # Wavy progress bar.
    bw = round(320 * u)
    stroke = max(2, round(6 * u))
    amp = 4.2 * u
    lam = 44 * u
    hh = math.ceil(2 * amp + stroke) + 4
    for k in range(WAVE_FRAMES):
        wave_img(bw, hh, stroke, amp, lam, 2 * math.pi * k / WAVE_FRAMES, pal["wave"]).save(f"{out}/wave{k}.png")
    line_img(bw, hh, stroke, pal["wave"]).save(f"{out}/flat.png")
    line_img(bw, hh, stroke, pal["track"]).save(f"{out}/track.png")
    gap = round(9 * u)
    Image.new("RGBA", (bw + gap + stroke * 2, hh), rgba(pal["bg"])).save(f"{out}/mask.png")
    circle(stroke, pal["wave"]).save(f"{out}/lead.png")
    circle(stroke, pal["track"]).save(f"{out}/endcap.png")
    circle(max(2, stroke * 0.7), pal["wave"]).save(f"{out}/stop.png")
    g.update(bar_w=bw, bar_h=hh, stroke=stroke, amp=amp, lam=lam, gap=gap,
             lead=Image.open(f"{out}/lead.png").width, stopd=Image.open(f"{out}/stop.png").width,
             endd=Image.open(f"{out}/endcap.png").width)

    # Status lines and credit.
    for key, txt in STATUS.items():
        text_img(txt, 21 * u, pal["status"], 400).save(f"{out}/s-{key}.png")
    credit_img(13 * u, pal["credit"], pal["name"]).save(f"{out}/credit.png")

    # Disk-unlock screen (installed system with full-disk encryption).
    text_img("Enter your passphrase to unlock Wraith", 22 * u, pal["prompt"], 400).save(f"{out}/prompt.png")
    pill(round(380 * u), round(54 * u), pal["field"]).save(f"{out}/field.png")
    circle(10 * u, pal["text"]).save(f"{out}/bullet.png")
    g.update(field_w=round(380 * u), field_h=round(54 * u), bullet_space=18 * u)

    g["u"] = u
    return g


def plymouth_theme(name, heights, out):
    pal = THEMES[name]
    root = os.path.join(out, name)
    os.makedirs(root, exist_ok=True)
    sets = {}
    for H in heights:
        sets[H] = plymouth_set(H, pal, os.path.join(root, f"h{H}"))
    with open(os.path.join(root, "layout.json"), "w") as fh:
        json.dump({"palette": pal, "sets": sets}, fh)
    with open(os.path.join(root, f"{name}.plymouth"), "w") as fh:
        fh.write(f"""[Plymouth Theme]
Name={name}
Description=Wraith OS boot animation, crafted by VIPIN
ModuleName=script

[script]
ImageDir=/usr/share/plymouth/themes/{name}
ScriptFile=/usr/share/plymouth/themes/{name}/{name}.script
""")
    with open(os.path.join(root, f"{name}.script"), "w") as fh:
        fh.write(plymouth_script(pal, sets))
    return root


def plymouth_script(pal, sets):
    hs = sorted(sets)
    lines = []
    for i, H in enumerate(hs):
        g = sets[H]
        body = [f"global.SETH = {H};", f"global.U = {g['u']:.6f};",
                f"global.WORD_W = {g['word_w']:.3f};", f"global.WORD_MID = {g['word_mid']:.3f};",
                f"global.DOT_BIG = {g['dot_big']:.3f};", f"global.DOT_MIN = {g['dot_min']};",
                f"global.DOT_MAX = {g['dot_max']};", f"global.DOT_SPACE = {g['dot_space']:.3f};",
                f"global.BAR_W = {g['bar_w']};", f"global.BAR_H = {g['bar_h']};",
                f"global.STROKE = {g['stroke']};", f"global.AMP = {g['amp']:.4f};",
                f"global.LAM = {g['lam']:.4f};", f"global.GAP = {g['gap']};",
                f"global.LEAD = {g['lead']};", f"global.STOPD = {g['stopd']};", f"global.ENDD = {g['endd']};",
                f"global.FIELD_W = {g['field_w']};", f"global.FIELD_H = {g['field_h']};",
                f"global.BULLET_SPACE = {g['bullet_space']:.3f};"]
        for j, (x, y) in enumerate(zip(g["lx"], g["ly"])):
            body.append(f"LX[{j}] = {x}; LY[{j}] = {y};")
        cond = "if" if i == 0 else "else if"
        lines.append(f"{cond} (set_h == {H}) {{\n    " + "\n    ".join(body) + "\n}")
    set_block = "\n".join(lines)
    heights = "\n".join(f"SETS[{i}] = {H};" for i, H in enumerate(hs))
    bg = pal["bg"]
    statuses = ", ".join(f'"{k}"' for k in STATUS)
    return SCRIPT.replace("@BG@", f"{bg[0]/255:.4f}, {bg[1]/255:.4f}, {bg[2]/255:.4f}") \
                 .replace("@HEIGHTS@", heights).replace("@NSETS@", str(len(hs))) \
                 .replace("@SET_BLOCK@", set_block).replace("@WAVE_FRAMES@", str(WAVE_FRAMES)) \
                 .replace("@NLETTERS@", str(len(WORD))).replace("@STATUSES@", statuses)


SCRIPT = r"""# Wraith OS boot animation - generated by branding/render.py, do not edit.
# Every image was rendered at the exact pixel size of a screen height, so
# nothing is scaled at boot. Animation uses only movement and fades.
#
# Plymouth script notes: there is no clock, so time is counted in refresh
# ticks (about 50 a second); variables changed inside functions need global.

Window.SetBackgroundTopColor(@BG@);
Window.SetBackgroundBottomColor(@BG@);

SW = Window.GetWidth();
SH = Window.GetHeight();
HZ = 50;
NF = @WAVE_FRAMES@;
NL = @NLETTERS@;
PI = Math.Pi;

# ---- pick the tallest asset set that fits this screen ----
@HEIGHTS@
set_h = SETS[0];
i = 0;
while (i < @NSETS@) { if (SETS[i] <= SH) set_h = SETS[i]; i++; }
@SET_BLOCK@
D = "h" + set_h + "/";

fun px(v) { return Math.Int(v + 0.5); }
fun clamp01(v) { return Math.Clamp(v, 0, 1); }
fun back(p, s) { q = p - 1; return 1 + (s + 1) * q * q * q + s * q * q; }

CX = SW / 2;
WORD_CY = SH * 0.44;
BASE_Y = WORD_CY - WORD_MID;
WORD_X = CX - WORD_W / 2;
BAR_CY = SH * 0.70;
BAR_X = px(CX - BAR_W / 2);

# ---- sprites ----
li = 0;
while (li < NL) {
    LW[li] = Sprite(Image(D + "l" + li + "w.png")); LW[li].SetOpacity(0); LW[li].SetZ(30);
    LC[li] = Sprite(Image(D + "l" + li + "c.png")); LC[li].SetOpacity(0); LC[li].SetZ(31);
    li++;
}
di = 0;
while (di < 4) {
    dd = DOT_MIN;
    while (dd <= DOT_MAX) { DOTIMG[di * 1000 + dd] = Image(D + "d" + di + "-" + dd + ".png"); dd++; }
    DS[di] = Sprite(); DS[di].SetZ(32); DS[di].SetOpacity(0);
    di++;
}
k = 0;
while (k < NF) { WAVE[k] = Image(D + "wave" + k + ".png"); k++; }

wave_s = Sprite(WAVE[0]); wave_s.SetZ(10); wave_s.SetOpacity(0);
flat_s = Sprite(Image(D + "flat.png")); flat_s.SetZ(10); flat_s.SetOpacity(0);
mask_s = Sprite(Image(D + "mask.png")); mask_s.SetZ(11);
lead_s = Sprite(Image(D + "lead.png")); lead_s.SetZ(12); lead_s.SetOpacity(0);
track_s = Sprite(Image(D + "track.png")); track_s.SetZ(13); track_s.SetOpacity(0);
cover_s = Sprite(Image(D + "mask.png")); cover_s.SetZ(14);
end_s = Sprite(Image(D + "endcap.png")); end_s.SetZ(15); end_s.SetOpacity(0);
stop_s = Sprite(Image(D + "stop.png")); stop_s.SetZ(16); stop_s.SetOpacity(0);

status_s = Sprite(); status_s.SetZ(20); status_s.SetOpacity(0);
credit_i = Image(D + "credit.png");
credit_s = Sprite(credit_i); credit_s.SetZ(20); credit_s.SetOpacity(0);
credit_s.SetPosition(px(CX - credit_i.GetWidth() / 2), px(SH - 44 * U - credit_i.GetHeight() / 2), 20);

prompt_i = Image(D + "prompt.png");
prompt_s = Sprite(prompt_i); prompt_s.SetOpacity(0);
prompt_s.SetPosition(px(CX - prompt_i.GetWidth() / 2), px(BAR_CY - 70 * U), 40);
field_s = Sprite(Image(D + "field.png")); field_s.SetOpacity(0);
field_s.SetPosition(px(CX - FIELD_W / 2), px(BAR_CY - FIELD_H / 2), 40);
bullet_i = Image(D + "bullet.png");

global.tick = 0;
global.sys_p = 0;
global.tor = "none";
global.tor_pct = 0;
global.target = 0;
global.shown = 0;
global.status_key = "";
global.status_t = 0;
global.mode = "normal";
global.nbullets = 0;
global.done_t = 0;
b = 0;
while (b < 18) { BUL[b] = Sprite(bullet_i); BUL[b].SetOpacity(0); b++; }

fun show_status(key, t) {
    if (key != global.status_key) {
        global.status_key = key;
        global.status_t = t;
        im = Image(D + "s-" + key + ".png");
        status_s.SetImage(im);
        global.status_w = im.GetWidth();
        global.status_h = im.GetHeight();
    }
}

fun refresh_callback() {
    global.tick++;
    t = global.tick / HZ;

    # ---- dots: drop in, hop twice, settle small under the name ----
    sp = clamp01((t - 2.0) / 0.8);
    se = back(sp, 1.7);
    scale = 1 - 0.55 * se;
    d = Math.Clamp(Math.Int(DOT_BIG * scale + 0.5), DOT_MIN, DOT_MAX);
    space = DOT_SPACE * scale;
    i = 0;
    while (i < 4) {
        p = clamp01((t - 0.2 - 0.09 * i) / 0.9);
        drop = -150 * U * (1 - back(p, 2.2));
        hop = 0;
        q = (t - 1.15 - 0.08 * i) / 0.5;
        if (q >= 0 && q < 2) hop = -15 * U * Math.Sin(PI * (q - Math.Int(q)));
        img = DOTIMG[i * 1000 + d];
        DS[i].SetImage(img);
        x = CX + (i - 1.5) * space - img.GetWidth() / 2;
        y = WORD_CY + 76 * U * se + drop + hop - img.GetHeight() / 2;
        DS[i].SetPosition(px(x), px(y), 32);
        DS[i].SetOpacity(clamp01(p * 4));
        i++;
    }

    # ---- letters spring up one by one with a colour flash ----
    i = 0;
    while (i < NL) {
        st = 2.05 + 0.06 * i;
        p = clamp01((t - st) / 0.7);
        op = clamp01(p * 2.5);
        c = clamp01((t - st) / 1.0);
        y = BASE_Y + LY[i] + 34 * U * (1 - back(p, 1.56));
        LW[i].SetPosition(px(WORD_X + LX[i]), px(y), 30);
        LC[i].SetPosition(px(WORD_X + LX[i]), px(y), 31);
        LW[i].SetOpacity(op * c);
        LC[i].SetOpacity(op * (1 - c));
        i++;
    }

    # ---- real progress ----
    a = 0.7 * Math.Min(global.sys_p / 0.9, 1);
    final = (global.tor == "done" || global.tor == "later" || global.tor == "off");
    if (final) want = 1;
    else if (global.tor == "active") want = 0.7 + 0.3 * global.tor_pct / 100;
    else want = a;
    if (want > global.target) global.target = want;
    global.shown = global.shown + (global.target - global.shown) * 0.08;
    if (global.target - global.shown < 0.002) global.shown = global.target;

    if (global.tor == "done") key = "desktop";
    else if (global.tor == "later") key = "later";
    else if (global.tor == "off") key = "direct";
    else if (global.tor == "active") key = "tor";
    else if (a < 0.25) key = "start";
    else if (a < 0.5) key = "drivers";
    else key = "secure";
    show_status(key, t);

    # ---- wavy bar fades in under the name ----
    ba = clamp01((t - 3.0) / 0.6);
    rise = 12 * U * (1 - back(ba, 1.56));
    if (global.mode != "normal") ba = 0;
    cy = BAR_CY + rise;
    top = px(cy - BAR_H / 2);
    fill = STROKE / 2 + global.shown * (BAR_W - STROKE);
    done = global.shown >= 0.999;
    if (done) {
        if (global.done_t == 0) global.done_t = t;
        fl = clamp01((t - global.done_t) / 0.4);
    } else fl = 0;

    k = Math.Int(t * NF * 1.1) - Math.Int(t * 1.1) * NF;
    wave_s.SetImage(WAVE[k]);
    wave_s.SetPosition(BAR_X, top, 10);
    wave_s.SetOpacity(ba * (1 - fl));
    flat_s.SetPosition(BAR_X, top, 10);
    flat_s.SetOpacity(ba * fl);

    mask_s.SetPosition(px(BAR_X + fill), top, 11);
    phase = 2 * PI * k / NF;
    ly = cy + AMP * Math.Sin(2 * PI * fill / LAM - phase) * (1 - fl);
    lead_s.SetPosition(px(BAR_X + fill - LEAD / 2), px(ly - LEAD / 2), 12);
    if (fill > STROKE) lead_s.SetOpacity(ba); else lead_s.SetOpacity(0);

    tx = BAR_X + fill + GAP;
    show_track = (tx < BAR_X + BAR_W - STROKE) && !done;
    track_s.SetPosition(px(tx - STROKE / 2), top, 13);
    cover_s.SetPosition(px(BAR_X + BAR_W - STROKE / 2), top, 14);
    end_s.SetPosition(px(BAR_X + BAR_W - STROKE / 2 - ENDD / 2), px(cy - ENDD / 2), 15);
    stop_s.SetPosition(px(BAR_X + BAR_W - STROKE / 2 - STOPD / 2), px(cy - STOPD / 2), 16);
    if (show_track) { track_s.SetOpacity(ba); end_s.SetOpacity(ba); stop_s.SetOpacity(ba); }
    else { track_s.SetOpacity(0); end_s.SetOpacity(0); stop_s.SetOpacity(0); }

    sf = clamp01((t - global.status_t) / 0.25);
    status_s.SetPosition(px(CX - global.status_w / 2), px(cy + 40 * U - global.status_h / 2), 20);
    status_s.SetOpacity(ba * sf);
    credit_s.SetOpacity(clamp01((t - 3.0) / 1.0));
}

fun progress_callback(duration, progress) {
    if (progress > global.sys_p) global.sys_p = progress;
}

fun parse_pct(s) {
    n = 0;
    while (n <= 100) { if (s == "wraith:tor:" + n) return n; n++; }
    return -1;
}

fun status_callback(s) {
    if (s == "wraith:tor:later") global.tor = "later";
    else if (s == "wraith:tor:off") global.tor = "off";
    else {
        n = parse_pct(s);
        if (n >= 100) { global.tor = "done"; global.tor_pct = 100; }
        else if (n >= 0 && n >= global.tor_pct) { global.tor = "active"; global.tor_pct = n; }
    }
}

fun hide_bullets() {
    b = 0;
    while (b < global.nbullets) { BUL[b].SetOpacity(0); b++; }
}

fun password_callback(prompt, bullets) {
    global.mode = "password";
    prompt_s.SetOpacity(1);
    field_s.SetOpacity(1);
    hide_bullets();
    n = Math.Min(bullets, 18);
    b = 0;
    while (b < n) {
        x = CX + (b - (n - 1) / 2) * BULLET_SPACE - bullet_i.GetWidth() / 2;
        BUL[b].SetPosition(px(x), px(BAR_CY - bullet_i.GetHeight() / 2), 41);
        BUL[b].SetOpacity(1);
        b++;
    }
    global.nbullets = n;
}

fun normal_callback() {
    global.mode = "normal";
    prompt_s.SetOpacity(0);
    field_s.SetOpacity(0);
    hide_bullets();
}

fun message_callback(text) { }

Plymouth.SetRefreshFunction(refresh_callback);
Plymouth.SetBootProgressFunction(progress_callback);
Plymouth.SetUpdateStatusFunction(status_callback);
Plymouth.SetDisplayPasswordFunction(password_callback);
Plymouth.SetDisplayNormalFunction(normal_callback);
Plymouth.SetMessageFunction(message_callback);
"""

# ---------------------------------------------------------------- GRUB

def grub_icon(kind, d, colour, bgc):
    def draw(g, s):
        g.ellipse([0, 0, d * s - 1, d * s - 1], fill=rgba(bgc))
        c = d * s / 2
        k = d * s / 40
        w = max(1, round(2.6 * k))
        if kind == "ghost":
            g.rounded_rectangle([c - 9 * k, c - 11 * k, c + 9 * k, c + 9 * k], radius=9 * k, fill=rgba(colour))
            for j in range(3):
                x0 = c - 9 * k + j * 6 * k
                g.polygon([(x0, c + 7 * k), (x0 + 3 * k, c + 11 * k), (x0 + 6 * k, c + 7 * k)], fill=rgba(colour))
            for ex in (-3.6, 3.6):
                g.ellipse([c + (ex - 1.8) * k, c - 4.5 * k, c + (ex + 1.8) * k, c - 0.5 * k], fill=rgba(bgc))
        elif kind == "install":
            g.line([(c, c - 10 * k), (c, c + 4 * k)], fill=rgba(colour), width=w)
            g.line([(c - 6 * k, c - 2 * k), (c, c + 4.5 * k), (c + 6 * k, c - 2 * k)], fill=rgba(colour), width=w, joint="curve")
            g.line([(c - 10 * k, c + 10 * k), (c + 10 * k, c + 10 * k)], fill=rgba(colour), width=w)
        else:  # sliders
            for j, kx in enumerate((-4, 5, -1)):
                y = c + (j - 1) * 7 * k
                g.line([(c - 10 * k, y), (c + 10 * k, y)], fill=rgba(colour), width=w)
                g.ellipse([c + (kx - 3) * k, y - 3 * k, c + (kx + 3) * k, y + 3 * k], fill=rgba(colour))
    return shape(d, d, draw)


def nine_slice(out, prefix, w, h, colour):
    """Pill split into GRUB's 9 pieces; corners are exact quarter circles."""
    r = h // 2
    full = pill(max(w, 2 * r + 2), h, colour)
    W, H = full.size
    boxes = {"nw": (0, 0, r, r), "n": (r, 0, r + 1, r), "ne": (W - r, 0, W, r),
             "w": (0, r, r, H - r), "c": (r, r, r + 1, H - r), "e": (W - r, r, W, H - r),
             "sw": (0, H - r, r, H), "s": (r, H - r, r + 1, H), "se": (W - r, H - r, W, H)}
    for k, b in boxes.items():
        piece = full.crop(b)
        if piece.width == 0 or piece.height == 0:
            piece = Image.new("RGBA", (max(1, piece.width), max(1, piece.height)), rgba(colour))
        piece.save(f"{out}/{prefix}_{k}.png")


def grub_theme(W, H, out, make_fonts=True):
    pal = THEMES["wraith"]
    u = H / 1080
    os.makedirs(os.path.join(out, "icons"), exist_ok=True)

    # Wordmark with its four dots
    word = text_img(WORD, 58 * u, pal["text"], 500)
    dd, gap = 9 * u, 7 * u
    dots_w = math.ceil(4 * dd + 3 * gap)
    wm = Image.new("RGBA", (max(word.width, dots_w), word.height + round(16 * u) + math.ceil(dd) + 2), (0, 0, 0, 0))
    wm.alpha_composite(word, ((wm.width - word.width) // 2, 0))
    for i, col in enumerate(DOTS):
        dot = circle(dd, col)
        x = round((wm.width - dots_w) / 2 + i * (dd + gap)) - 1
        wm.alpha_composite(dot, (x, word.height + round(16 * u) - 1))
    wm.save(f"{out}/wordmark.png")
    credit_img(12 * u, pal["credit"], pal["name"]).save(f"{out}/credit.png")

    item_h, item_sp = round(66 * u), round(10 * u)
    menu_w = round(560 * u)
    icon = round(42 * u)
    for kind, cls in (("ghost", "ghost"), ("install", "install"), ("sliders", "advanced")):
        grub_icon(kind, icon, (230, 225, 240), (44, 41, 56)).save(f"{out}/icons/{cls}.png")
    shutil.copy(f"{out}/icons/advanced.png", f"{out}/icons/settings.png")
    nine_slice(out, "select", menu_w, item_h, (63, 56, 145))
    bar_h = max(4, round(6 * u))
    nine_slice(out, "bar", round(240 * u), bar_h, pal["track"])
    nine_slice(out, "hl", round(240 * u), bar_h, pal["wave"])

    sizes = {"item": round(25 * u), "hint": round(17 * u)}
    if make_fonts:
        build_grub_fonts(out, sizes)

    # Everything is placed relative to the vertical centre of the screen, so the
    # wordmark, menu, timer and hint stay together and centred whatever mode
    # the firmware actually gives (16:10, 4:3, 1366x768 ... not only 1080p).
    menu_h = 3 * (item_h + item_sp)
    hint_h = round(sizes["hint"] * 1.4)
    gap_wm, gap_bar, gap_hint = round(64 * u), round(34 * u), round(52 * u)
    block = wm.height + gap_wm + menu_h + gap_hint + hint_h
    y0 = -block // 2                      # top of the block, relative to 50%
    y_menu = y0 + wm.height + gap_wm
    y_bar = y_menu + menu_h + gap_bar
    y_hint = y_menu + menu_h + gap_hint

    def at(v):
        return f"50%{'+' if v >= 0 else '-'}{abs(v)}"

    theme = f"""# Wraith OS boot menu - generated for {W}x{H} by branding/render.py
title-text: ""
desktop-color: "#{'%02x%02x%02x' % pal['bg']}"
terminal-font: "Unifont Regular 16"
terminal-left: "10%"
terminal-top: "10%"
terminal-width: "80%"
terminal-height: "80%"
terminal-border: "0"

+ image {{
    left = 50%-{wm.width // 2}
    top = {at(y0)}
    file = "wordmark.png"
}}

+ boot_menu {{
    left = 50%-{menu_w // 2}
    top = {at(y_menu)}
    width = {menu_w}
    height = {menu_h}
    item_font = "WraithMedium Regular {sizes['item']}"
    item_color = "#e6e1f0"
    selected_item_color = "#ffffff"
    item_height = {item_h}
    item_spacing = {item_sp}
    item_padding = {round(12 * u)}
    icon_width = {icon}
    icon_height = {icon}
    item_icon_space = {round(18 * u)}
    selected_item_pixmap_style = "select_*.png"
    scrollbar = false
}}

+ progress_bar {{
    id = "__timeout__"
    left = 50%-{round(120 * u)}
    top = {at(y_bar)}
    width = {round(240 * u)}
    height = {bar_h}
    show_text = false
    bar_style = "bar_*.png"
    highlight_style = "hl_*.png"
}}

+ label {{
    id = "__timeout__"
    left = 0
    width = 100%
    top = {at(y_hint)}
    height = {hint_h}
    align = "center"
    font = "WraithRegular Regular {sizes['hint']}"
    color = "#8f899c"
    text = "Starting in %d s  ·  ↑ ↓ to choose, Enter to start"
}}

+ image {{
    left = 50%-{Image.open(f'{out}/credit.png').width // 2}
    top = 100%-{round(52 * u)}
    file = "credit.png"
}}
"""
    with open(f"{out}/theme.txt", "w") as fh:
        fh.write(theme)
    return dict(item_h=item_h, item_sp=item_sp, menu_w=menu_w, icon=icon, y_menu=y_menu, block=block,
                sizes=sizes, wm=wm.size, bar_h=bar_h)


def build_grub_fonts(out, sizes):
    """Static Figtree instances -> GRUB bitmap fonts at the exact sizes used."""
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont
    tmp = os.path.join(out, ".fonts")
    os.makedirs(tmp, exist_ok=True)
    for name, weight, size in (("WraithMedium", 500, sizes["item"]), ("WraithRegular", 400, sizes["hint"])):
        ttf = os.path.join(tmp, f"{name}.ttf")
        inst = instantiateVariableFont(TTFont(FONT), {"wght": weight})
        # GRUB names the font "<name> <style> <size>"; force style "Regular" so
        # it always matches the names used in theme.txt.
        for rec in inst["name"].names:
            if rec.nameID in (2, 17):
                rec.string = "Regular"
        inst.save(ttf)
        subprocess.run(["grub-mkfont", "-s", str(size), "-n", name, "-o",
                        os.path.join(out, f"{name}-{size}.pf2"), ttf], check=True)
    shutil.rmtree(tmp)
    uni = "/usr/share/grub/unicode.pf2"
    if os.path.exists(uni):
        shutil.copy(uni, out)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="live-build work tree")
    ap.add_argument("--plymouth-only")
    ap.add_argument("--heights", default="")
    ap.add_argument("--extra-height", type=int, default=0, help="also render this exact screen height")
    ap.add_argument("--grub")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--no-fonts", action="store_true")
    a = ap.parse_args()

    heights = [int(h) for h in a.heights.split(",") if h] or HEIGHTS
    if a.extra_height and a.extra_height not in heights:
        heights = sorted(heights + [a.extra_height])
    if a.out:
        ply = os.path.join(a.out, "config/includes.chroot/usr/share/plymouth/themes")
        for name in THEMES:
            plymouth_theme(name, heights, ply)
        lib = os.path.join(a.out, "config/includes.chroot/usr/local/lib/wraith/branding")
        os.makedirs(lib, exist_ok=True)
        shutil.copy(__file__, lib)
        shutil.copytree(os.path.join(HERE, "fonts"), os.path.join(lib, "fonts"), dirs_exist_ok=True)
        # Live USB boot menu: 1920x1080 is asked for first (see grub.cfg), so
        # this set is pixel-exact on the screens most people have.
        grub_theme(1920, 1080, os.path.join(a.out, "config/wraith-grub/themes/wraith"), not a.no_fonts)
    if a.plymouth_only:
        for name in THEMES:
            plymouth_theme(name, heights, a.plymouth_only)
    if a.grub:
        w, h = (int(v) for v in a.size.split("x"))
        grub_theme(w, h, a.grub, not a.no_fonts)


if __name__ == "__main__":
    main()
