// Wraith Shell - the Pixel / Material You desktop UI.
// Runs inside the Wraith host (GTK4 + WebKitGTK layer-shell surfaces), which
// exposes window.wraith.call(name, args) for the system side. In a plain
// browser a mock backend is used, so the UI can be previewed anywhere.
import {
  Hct, SchemeTonalSpot, MaterialDynamicColors as MDC, hexFromArgb, argbFromHex, sourceColorFromImage,
} from "./vendor/mcu.js";

const $ = (s, el = document) => el.querySelector(s);
const params = new URLSearchParams(location.search);

/* ------------------------------------------------------------------ bridge */
// Inside the OS the host injects window.wraith (see host/shell.py).
const backend = window.wraith ?? {
  // Preview stand-in; the host replaces this with real system calls.
  async call(name, args) { console.log("[wraith mock]", name, JSON.stringify(args ?? {})); return mock[name]?.(args); },
};
const mock = {
  status: () => ({ tor: true, live: true, wifi: true, bluetooth: false, usbguard: true, battery: 82, volume: 55, brightness: 70 }),
};
const call = (name, args) => backend.call(name, args);
const IN_OS = !!window.wraith;
if (IN_OS) document.body.classList.add("in-os");

/* ------------------------------------------------------------------ spring */
// Damped spring (same feel as Android's SpringAnimation). Animates 0 -> 1 by default.
class Spring {
  constructor({ stiffness = 380, damping = 26, mass = 1 } = {}) { Object.assign(this, { stiffness, damping, mass }); this.x = 0; this.v = 0; this.target = 0; this.raf = 0; }
  to(target, onUpdate, onRest) {
    this.target = target; this.onUpdate = onUpdate; this.onRest = onRest;
    if (this.raf) return this;
    let last = performance.now();
    const step = (now) => {
      let dt = Math.min(0.032, (now - last) / 1000); last = now;
      // integrate in small sub-steps for stability
      for (let i = 0; i < 4; i++) {
        const h = dt / 4, f = -this.stiffness * (this.x - this.target) - this.damping * this.v;
        this.v += (f / this.mass) * h; this.x += this.v * h;
      }
      this.onUpdate?.(this.x);
      if (Math.abs(this.v) < 0.002 && Math.abs(this.x - this.target) < 0.0005) {
        this.x = this.target; this.v = 0; this.raf = 0; this.onUpdate?.(this.x); this.onRest?.(); return;
      }
      this.raf = requestAnimationFrame(step);
    };
    this.raf = requestAnimationFrame(step);
    return this;
  }
  set(x) { this.x = this.target = x; this.v = 0; }
}

/* ------------------------------------------------------------------ theme */
const state = { dark: params.get("theme") !== "light", source: "#6a5ff0", tor: true, live: true, open: null };

function applyTheme() {
  const scheme = new SchemeTonalSpot(Hct.fromInt(argbFromHex(state.source)), state.dark, 0);
  const root = document.documentElement.style;
  const roles = {
    "surface": MDC.surface, "on-surface": MDC.onSurface, "on-surface-variant": MDC.onSurfaceVariant,
    "surface-container-low": MDC.surfaceContainerLow, "surface-container": MDC.surfaceContainer,
    "surface-container-highest": MDC.surfaceContainerHighest, "outline-variant": MDC.outlineVariant,
    "primary": MDC.primary, "on-primary": MDC.onPrimary,
    "primary-container": MDC.primaryContainer, "on-primary-container": MDC.onPrimaryContainer,
    "secondary-container": MDC.secondaryContainer, "on-secondary-container": MDC.onSecondaryContainer,
    "tertiary-container": MDC.tertiaryContainer, "on-tertiary-container": MDC.onTertiaryContainer,
    "error-container": MDC.errorContainer, "on-error-container": MDC.onErrorContainer,
    "inverse-surface": MDC.inverseSurface, "inverse-on-surface": MDC.inverseOnSurface,
  };
  for (const [k, role] of Object.entries(roles)) root.setProperty(`--${k}`, hexFromArgb(role.getArgb(scheme)));
  // Wallpaper blobs: the source hue plus two neighbours, rich but soft
  const d = state.dark, hue = Hct.fromInt(argbFromHex(state.source)).hue;
  const blob = (dh, chroma, tone) => hexFromArgb(Hct.from((hue + dh + 360) % 360, chroma, tone).toInt());
  root.setProperty("--wp-base", hexFromArgb(scheme.neutralPalette.tone(d ? 6 : 96)));
  root.setProperty("--wp-1", blob(0, d ? 60 : 40, d ? 34 : 80));
  root.setProperty("--wp-2", blob(70, d ? 52 : 36, d ? 30 : 86));
  root.setProperty("--wp-3", blob(-60, d ? 46 : 32, d ? 28 : 88));
  root.setProperty("--on-wallpaper", d ? "#f1eefa" : "#1c1b22");
  // Tor chip: calm tertiary when protected, error colours when direct
  root.setProperty("--tor-bg", state.tor ? hexFromArgb(MDC.tertiaryContainer.getArgb(scheme)) : hexFromArgb(MDC.errorContainer.getArgb(scheme)));
  root.setProperty("--tor-fg", state.tor ? hexFromArgb(MDC.onTertiaryContainer.getArgb(scheme)) : hexFromArgb(MDC.onErrorContainer.getArgb(scheme)));
  document.documentElement.style.colorScheme = d ? "dark" : "light";
  const wp = Object.fromEntries([["base", "--wp-base"], ["c1", "--wp-1"], ["c2", "--wp-2"], ["c3", "--wp-3"]].map(([k, v]) => [k, root.getPropertyValue(v)]));
  call("theme", { dark: d, source: state.source, wallpaper: wp });
}

// Dynamic colour from a wallpaper image (Material You)
async function useWallpaper(url) {
  const img = new Image(); img.src = url; await img.decode();
  state.source = hexFromArgb(await sourceColorFromImage(img));
  const wp = $("#wallpaper"); wp.classList.add("image"); wp.style.backgroundImage = `url("${url}")`;
  applyTheme();
}

/* ------------------------------------------------------------------ apps */
let CATS = ["All", "Information Gathering", "Vulnerability Analysis", "Web Apps", "Passwords", "Wireless", "Exploitation", "Sniffing & Spoofing", "Forensics", "Reverse Engineering", "System"];
const G = { v: ["#a79fff", "#5b52e0"], p: ["#ff9ec4", "#d9467f"], o: ["#ffc98a", "#e7782f"], b: ["#8fdcff", "#2f8fd6"], g: ["#8ee6b5", "#25a065"], r: ["#ff9a8f", "#d6453a"], s: ["#c9c6d6", "#6d6a7c"], k: ["#4b4858", "#1d1b24"] };
let APPS = [
  ["Terminal", "terminal", "k", "System", "wraith-terminal"], ["Tor Browser", "travel_explore", "v", "System", "torbrowser-launcher"],
  ["Files", "folder", "b", "System", "files"], ["App Manager", "apps", "g", "System", "wraith-apps"], ["Settings", "settings", "s", "System", "settings"],
  ["Nmap", "radar", "b", "Information Gathering", "nmap"], ["Maltego", "hub", "v", "Information Gathering", "maltego"], ["theHarvester", "mail", "o", "Information Gathering", "theHarvester"],
  ["Recon-ng", "manage_search", "g", "Information Gathering", "recon-ng"], ["Amass", "lan", "p", "Information Gathering", "amass"],
  ["Nikto", "bug_report", "r", "Vulnerability Analysis", "nikto"], ["OpenVAS", "shield", "g", "Vulnerability Analysis", "gvm-start"], ["Lynis", "fact_check", "o", "Vulnerability Analysis", "lynis"],
  ["Burp Suite", "bolt", "o", "Web Apps", "burpsuite"], ["OWASP ZAP", "electric_bolt", "b", "Web Apps", "zaproxy"], ["sqlmap", "database", "v", "Web Apps", "sqlmap"], ["ffuf", "rocket_launch", "p", "Web Apps", "ffuf"],
  ["John the Ripper", "key", "r", "Passwords", "john"], ["Hashcat", "password", "o", "Passwords", "hashcat"], ["Hydra", "account_tree", "p", "Passwords", "hydra"],
  ["Aircrack-ng", "wifi_tethering", "b", "Wireless", "aircrack-ng"], ["Wifite", "wifi_find", "v", "Wireless", "wifite"], ["Kismet", "sensors", "g", "Wireless", "kismet"],
  ["Metasploit", "token", "k", "Exploitation", "msfconsole"], ["SearchSploit", "search_insights", "r", "Exploitation", "searchsploit"], ["BeEF", "phishing", "o", "Exploitation", "beef-xss"],
  ["Wireshark", "graphic_eq", "b", "Sniffing & Spoofing", "wireshark"], ["Bettercap", "settings_input_antenna", "p", "Sniffing & Spoofing", "bettercap"], ["Responder", "cell_tower", "v", "Sniffing & Spoofing", "responder"],
  ["Autopsy", "biotech", "g", "Forensics", "autopsy"], ["Volatility", "memory", "s", "Forensics", "volatility3"], ["Binwalk", "unarchive", "o", "Forensics", "binwalk"],
  ["Ghidra", "code_blocks", "r", "Reverse Engineering", "ghidra"], ["Radare2", "data_object", "k", "Reverse Engineering", "radare2"], ["Cutter", "content_cut", "v", "Reverse Engineering", "cutter"],
].map(([name, glyph, col, cat, exec]) => ({ id: exec, name, glyph, c: G[col], cats: [cat], exec }));
let DOCK = ["wraith-terminal", "torbrowser-launcher", "files", "nmap", "burpsuite", "msfconsole", "wireshark"];

// Real apps from the system (.desktop files, Kali menu categories, real icons)
async function loadApps() {
  const r = await call("apps");
  if (!r?.apps?.length) return;
  const cols = Object.values(G);
  const hash = (s) => [...s].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 7);
  APPS = r.apps.map((a) => ({ ...a, c: cols[hash(a.id) % cols.length], glyph: a.terminal ? "terminal" : "apps" }));
  CATS = ["All", ...r.categories];
  DOCK = r.dock;
}

function icon(app, size) {
  const el = document.createElement("span");
  el.className = "icon"; if (size) el.style.setProperty("--s", size + "px");
  el.style.setProperty("--c1", app.c[0]); el.style.setProperty("--c2", app.c[1]);
  if (app.icon) {
    // real logo on a glassy Soft 3D tile
    el.classList.add("logo");
    const img = new Image(); img.src = app.icon; img.alt = ""; img.draggable = false;
    img.onerror = () => { el.classList.remove("logo"); el.innerHTML = `<span class="ms fill">${app.glyph}</span>`; };
    el.append(img);
  } else el.innerHTML = `<span class="ms fill">${app.glyph}</span>`;
  return el;
}

function buildDock() {
  const box = $("#dock-apps");
  box.innerHTML = "";
  for (const id of DOCK) {
    const app = APPS.find((a) => a.id === id);
    if (!app) continue;
    const b = document.createElement("button"); b.className = "app-btn"; b.setAttribute("aria-label", app.name);
    b.append(icon(app, 52)); b.insertAdjacentHTML("beforeend", `<span class="tip"></span>`);
    b.querySelector(".tip").textContent = app.name;
    b.onclick = () => launch(app, b.firstChild);
    box.append(b);
  }
  magnify();
}

// macOS-style magnification: the icon under the cursor grows the most and its
// neighbours a little less, so the dock swells smoothly around the pointer.
// The icons are re-drawn at the larger size (not scaled), so they stay sharp.
function magnify() {
  const dock = $("#dock"), BASE = 52, MAX = 84, RANGE = 150;
  const items = () => [...dock.querySelectorAll(".app-btn .icon, #drawer-btn")];
  const cur = new Map();
  let mx = null, raf = 0, last = 0;
  const frame = (t) => {
    raf = 0; let moving = false;
    // time-based smoothing: same snappy feel at 60, 120 or 144 Hz (~95% there in 0.1 s)
    const dt = last ? Math.min(50, t - last) : 16.7; last = t;
    const k = 1 - Math.exp(-dt / 34);
    for (const el of items()) {
      let target = BASE;
      if (mx !== null) {
        const r = el.getBoundingClientRect(), d = Math.abs(mx - (r.left + r.width / 2));
        if (d < RANGE) target = BASE + (MAX - BASE) * (Math.cos((Math.PI * d) / RANGE) + 1) / 2;
      }
      const now = cur.get(el) ?? BASE, next = now + (target - now) * k;
      const v = Math.abs(target - next) < 0.15 ? target : next;
      if (v !== target) moving = true;
      cur.set(el, v); el.style.setProperty("--s", v.toFixed(2) + "px");
    }
    if (moving) raf = requestAnimationFrame(frame); else last = 0;
  };
  const kick = () => { if (!raf) raf = requestAnimationFrame(frame); };
  dock.addEventListener("mousemove", (e) => { mx = e.clientX; kick(); });
  dock.addEventListener("mouseleave", () => { mx = null; kick(); });
}

let cat = "All";
function buildChips() {
  const box = $("#chips"); box.innerHTML = "";
  for (const c of CATS) {
    const b = document.createElement("button"); b.className = "chip" + (c === cat ? " on" : ""); b.textContent = c;
    b.onclick = () => { cat = c; for (const x of box.children) x.classList.toggle("on", x === b); fillGrid(true); };
    box.append(b);
  }
}
function fillGrid(animate) {
  const q = $("#search").value.trim().toLowerCase(), grid = $("#grid");
  grid.innerHTML = "";
  const list = APPS.filter((a) => (cat === "All" || a.cats.includes(cat)) && (!q || (a.name + " " + (a.comment ?? "") + " " + a.cats.join(" ") + " " + a.id).toLowerCase().includes(q)));
  list.forEach((app, i) => {
    const b = document.createElement("button"); b.className = "cell" + (animate ? " enter" : "");
    b.append(icon(app)); b.insertAdjacentHTML("beforeend", `<span class="name"></span>`);
    b.lastChild.textContent = app.name; if (app.comment) b.title = app.comment;
    b.onclick = () => launch(app, b.firstChild);
    grid.append(b);
    if (animate) staggerIn(b, i);
  });
}
function staggerIn(el, i) {
  setTimeout(() => {
    const s = new Spring({ stiffness: 420, damping: 24 });
    el.classList.remove("enter");
    el.style.transition = "none";
    s.to(1, (x) => { el.style.opacity = Math.min(1, x * 1.4); el.style.transform = `translateY(${(1 - x) * 22}px) scale(${0.9 + 0.1 * x})`; },
      () => { el.style.transition = ""; el.style.transform = ""; });
  }, Math.min(i, 24) * 14);
}

/* ------------------------------------------------------------------ panels */
const overlay = $("#overlay"), drawer = $("#drawer"), qs = $("#qs");
const drawerSpring = new Spring({ stiffness: 300, damping: 27 }), qsSpring = new Spring({ stiffness: 420, damping: 28 });

// Tell the host which parts of the screen take clicks (the rest passes through
// to the windows underneath) and whether a panel wants the keyboard.
function syncInput() {
  if (!IN_OS) return;
  const rects = [];
  const add = (el, grow = 0) => { if (!el || el.hidden) return; const r = el.getBoundingClientRect(); rects.push([r.left, r.top - grow, r.width, r.height + grow]); };
  if (state.open) rects.push([0, 0, innerWidth, innerHeight]);
  else { add($("#bar")); add($("#dock"), 44); rects.push(island.box); }
  call("inputRegion", { rects: rects.map((r) => r.map(Math.round)), keyboard: !!state.open });
}
addEventListener("resize", syncInput);

function openDrawer() {
  if (state.open === "drawer") return closeAll();
  closeAll(true);
  state.open = "drawer"; overlay.classList.add("active"); drawer.hidden = false; syncInput();
  $("#search").value = ""; fillGrid(true);
  const h = drawer.offsetHeight;
  drawerSpring.to(1, (x) => (drawer.style.transform = `translateY(${(1 - x) * (h + 40)}px)`));
  setTimeout(() => $("#search").focus({ preventScroll: true }), 120);
}
function openQS() {
  if (state.open === "qs") return closeAll();
  closeAll(true);
  state.open = "qs"; overlay.classList.add("active"); qs.hidden = false; syncInput();
  qsSpring.to(1, (x) => { qs.style.opacity = Math.min(1, x * 1.6); qs.style.transform = `scale(${0.82 + 0.18 * x})`; });
}
function closeAll(instant) {
  const was = state.open; state.open = null; overlay.classList.remove("active"); syncInput();
  if (was === "drawer") {
    const h = drawer.offsetHeight;
    if (instant) { drawerSpring.set(0); drawer.hidden = true; }
    else drawerSpring.to(0, (x) => (drawer.style.transform = `translateY(${(1 - x) * (h + 40)}px)`), () => { if (state.open !== "drawer") drawer.hidden = true; });
  }
  if (was === "qs") {
    if (instant) { qsSpring.set(0); qs.hidden = true; }
    else qsSpring.to(0, (x) => { qs.style.opacity = Math.max(0, x * 1.6 - 0.6); qs.style.transform = `scale(${0.82 + 0.18 * x})`; }, () => { if (state.open !== "qs") qs.hidden = true; });
  }
}

/* ------------------------------------------------------------------ quick settings */
const TILES = [
  { id: "tor", icon: "shield_lock", title: "Tor", sub: (on) => (on ? "All traffic through Tor" : "Direct connection"), cls: "tor" },
  { id: "wifi", icon: "wifi", title: "Wi-Fi", sub: (on) => (on ? "Connected" : "Off") },
  { id: "bluetooth", icon: "bluetooth", title: "Bluetooth", sub: (on) => (on ? "On" : "Off") },
  { id: "dark", icon: "dark_mode", title: "Dark theme", sub: (on) => (on ? "On" : "Off") },
  { id: "usbguard", icon: "usb", title: "USB guard", sub: (on) => (on ? "New devices blocked" : "Allowing devices") },
  { id: "mac", icon: "fingerprint", title: "MAC spoofing", sub: (on) => (on ? "Random each connect" : "Off") },
  { id: "airplane", icon: "flight", title: "Airplane mode", sub: (on) => (on ? "All radios off" : "Off") },
];
const tileState = { tor: true, wifi: true, bluetooth: false, dark: state.dark, usbguard: true, mac: true, airplane: false };

function buildTiles() {
  const box = $("#tiles"); box.innerHTML = "";
  for (const t of TILES) {
    const b = document.createElement("button"); b.className = "tile " + (t.cls ?? ""); b.dataset.id = t.id;
    b.innerHTML = `<span class="tic"><span class="ms">${t.icon}</span></span><span class="tt"><b>${t.title}</b><span></span></span>`;
    b.onclick = () => toggleTile(t.id);
    box.append(b);
  }
  renderTiles();
}
function renderTiles() {
  for (const t of TILES) {
    const b = $(`.tile[data-id="${t.id}"]`); if (!b) continue;
    b.classList.toggle("on", !!tileState[t.id]); b.querySelector(".tt span").textContent = t.sub(tileState[t.id]);
  }
  // Wraith Live is always Tor-only: the tile is locked on there.
  $(`.tile[data-id="tor"]`).classList.toggle("locked", state.live);
}
async function toggleTile(id) {
  if (id === "tor" && state.live) { flash($(`.tile[data-id="tor"] .tt span`), "Always on in Wraith Live"); return; }
  tileState[id] = !tileState[id];
  if (id === "dark") { state.dark = tileState.dark; applyTheme(); }
  if (id === "tor") { state.tor = tileState.tor; setTorChip(); applyTheme(); }
  renderTiles();
  const r = await call("toggle", { id, on: tileState[id] });
  if (id === "tor" && r?.ok !== false) island.alert(state.tor ? { icon: "shield_lock", title: "Tor is on", sub: "All traffic goes through Tor", accent: "#9be6b4" }
                                                  : { icon: "public", title: "Direct connection", sub: "Traffic no longer goes through Tor", accent: "#ffb4ab" });
  if (r && r.ok === false) {
    // the system refused: put the tile back and say why
    tileState[id] = !tileState[id];
    if (id === "dark") { state.dark = tileState.dark; applyTheme(); }
    if (id === "tor") { state.tor = tileState.tor; setTorChip(); applyTheme(); }
    renderTiles(); flash($(`.tile[data-id="${id}"] .tt span`), r.error || "Couldn't change that");
  }
}
function flash(el, text) { const old = el.textContent; el.textContent = text; setTimeout(() => (el.textContent = old), 1600); }
function setTorChip() {
  $("#tor-chip .tor-text").textContent = state.tor ? "Tor" : "Direct";
  $("#tor-chip .ms").textContent = state.tor ? "shield_lock" : "public";
}

function buildSliders() {
  for (const lab of document.querySelectorAll(".slider")) {
    const input = lab.querySelector("input");
    const fill = document.createElement("span"); fill.className = "fillbar"; lab.prepend(fill);
    const update = () => {
      fill.style.width = `max(48px, ${input.value}%)`;
      if (lab.dataset.key === "volume") $("#vol-icon").textContent = input.value == 0 ? "volume_off" : input.value < 40 ? "volume_down" : "volume_up";
    };
    input.oninput = () => { update(); call("set", { key: lab.dataset.key, value: +input.value }); };
    input.addEventListener("input", () => { if (!state.open) osd(lab.dataset.key, +input.value); });
    input.addEventListener("sync", update);
    update();
  }
}

/* ------------------------------------------------------------------ app launch */
// A tile grows out of the tapped icon into the window, like Pixel's app open.
function launch(app, fromEl) {
  call("launch", { id: app.id });
  const r = fromEl.getBoundingClientRect();
  const W = innerWidth, H = innerHeight;
  const win = { w: Math.min(980, W * 0.68), h: Math.min(620, H * 0.66) };
  win.x = (W - win.w) / 2; win.y = Math.max(64, (H - win.h) / 2 - 30);
  const ghost = $("#launch-ghost");
  ghost.style.setProperty("--c1", app.c[0]); ghost.style.setProperty("--c2", app.c[1]);
  ghost.innerHTML = ""; ghost.append(icon(app, 64)); ghost.firstChild.classList.add("ghost-icon");
  ghost.hidden = false; ghost.style.opacity = 1;
  closeAll();
  const s = new Spring({ stiffness: 260, damping: 25 });
  const lerp = (a, b, x) => a + (b - a) * x;
  s.to(1, (x) => {
    ghost.style.left = lerp(r.left, win.x, x) + "px"; ghost.style.top = lerp(r.top, win.y, x) + "px";
    ghost.style.width = Math.max(10, lerp(r.width, win.w, x)) + "px"; ghost.style.height = Math.max(10, lerp(r.height, win.h, x)) + "px";
    ghost.style.borderRadius = lerp(r.width * 0.3, 18, Math.min(1, x)) + "px";
  }, () => {
    if (IN_OS) {   // the real window is opening underneath: fade the tile into it
      ghost.style.transition = "opacity .3s"; ghost.style.opacity = 0;
      setTimeout(() => { ghost.hidden = true; ghost.style.transition = ""; }, 320);
      return;
    }
    // Preview only: show the stand-in window, then fade the tile away
    const dw = $("#demo-window");
    Object.assign(dw.style, { left: win.x + "px", top: win.y + "px", width: win.w + "px", height: win.h + "px" });
    dw.querySelector(".win-title span:nth-child(2)").textContent = app.name;
    dw.querySelector(".win-title .ms").textContent = app.glyph;
    dw.hidden = false;
    ghost.style.transition = "opacity .25s";
    ghost.style.opacity = 0;
    setTimeout(() => { ghost.hidden = true; ghost.style.transition = ""; }, 260);
  });
}

/* ------------------------------------------------------------------ bar */
function tick() {
  const now = new Date();
  $("#clock").textContent = now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  $("#date").textContent = now.toLocaleDateString([], { weekday: "short", month: "short", day: "numeric" });
}

/* ------------------------------------------------------------------ dynamic island */
// A black pill in the bar that springs open for live activities (Tor connecting,
// installs, Now Playing), short alerts (USB blocked, battery) and the volume /
// brightness level. Ongoing activities sit compact; hover or click to expand.
//
// How the morph stays smooth: one spring drives the pill's width and height;
// every content layer is laid out at its own final size and centred, so the
// pill just reveals or covers it (no reflow), and layers cross-fade with a
// short delay on the way in and a quick fade on the way out.
const island = (() => {
  const el = $("#island"), q = (s) => el.querySelector(s);
  const layers = { compact: q(".isl-compact"), full: q(".isl-full"), player: q(".isl-player") };
  const sw = new Spring({ stiffness: 380, damping: 30 }), sh = new Spring({ stiffness: 380, damping: 31 });
  sw.set(118); sh.set(30);
  const ongoing = new Map();
  let alertAct = null, alertTimer = 0, hover = false, pinned = false, target = { w: 118, h: 30 }, media = null;
  // privacy dots: camera green, microphone yellow, location blue
  const PRIV = { camera: ["#34c759", "videocam", "Camera"], mic: ["#ffd60a", "mic", "Microphone"], location: ["#0a84ff", "location_on", "Location"] };
  let priv = { camera: [], mic: [], location: [] };
  const dots = () => Object.keys(PRIV).filter((k) => priv[k].length)
    .map((k) => `<span class="isl-pdot" style="background:${PRIV[k][0]};box-shadow:0 0 6px ${PRIV[k][0]}"></span>`).join("");

  const paint = () => {
    el.style.width = sw.x.toFixed(2) + "px"; el.style.height = sh.x.toFixed(2) + "px";
    el.style.borderRadius = Math.min(sh.x / 2, 32).toFixed(2) + "px";
  };
  const morph = (w, h) => {
    if (w === target.w && h === target.h) return;
    target = { w, h };
    sw.to(w, paint); sh.to(h, paint);
    syncInput();
  };
  const showLayer = (name, w, h) => {
    for (const [n, l] of Object.entries(layers)) {
      if (n === name) { l.style.width = w + "px"; if (h) l.style.height = h + "px"; }
      l.classList.toggle("show", n === name);
    }
  };
  const ring = (a) => `<span class="isl-ring" style="--p:${a.progress}"></span>`;
  const fmt = (us) => { const s = Math.max(0, Math.round((us || 0) / 1e6)); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };

  function fillFull(a) {
    layers.full.style.setProperty("--isl-accent", a.accent || "#c6bfff");
    q(".isl-icon").innerHTML = `<span class="ms fill ${a.spin ? "isl-spin" : ""}">${a.icon || "info"}</span>`;
    q(".isl-title").textContent = a.title || ""; q(".isl-sub").textContent = a.sub || "";
    q(".isl-side").textContent = a.side ?? (a.progress != null ? Math.round(a.progress * 100) + "%" : "");
    layers.full.classList.toggle("has-bar", a.progress != null);
    q(".isl-bar i").style.width = ((a.progress ?? 0) * 100) + "%";
  }
  function fillPlayer() {
    const art = q(".pl-art");
    art.style.backgroundImage = media.art ? `url("${media.art}")` : "";
    art.innerHTML = media.art ? "" : '<span class="ms fill">music_note</span>';
    q(".pl-title").textContent = media.title || "Unknown title";
    q(".pl-artist").textContent = media.artist || media.player || "";
    q(".pl-pp .ms").textContent = media.playing ? "pause" : "play_arrow";
    el.classList.toggle("playing", !!media.playing);
    tickMedia();
  }
  function tickMedia() {
    if (!media) return;
    const pos = media.position + (media.playing ? (performance.now() - media.at) * 1000 : 0);
    const len = media.length || 0;
    q(".pl-pos").textContent = fmt(Math.min(pos, len || pos)); q(".pl-len").textContent = len ? fmt(len) : "--:--";
    q(".pl-track i").style.width = len ? Math.min(100, pos / len * 100) + "%" : "0%";
  }
  setInterval(() => { if (media?.playing && target.h > 100) tickMedia(); }, 500);

  function compactFor(a) {
    let lead, trail, label = a.short ?? a.title ?? "";
    if (a.kind === "media") {
      lead = `<span class="isl-thumb" style="${media?.art ? `background-image:url('${media.art}')` : ""}"></span>`;
      trail = `<span class="isl-eq" style="--eq:#c6bfff"><i></i><i></i><i></i><i></i></span>`;
      label = "";
    } else {
      lead = (a.progress != null ? ring(a) : `<span class="ms fill ${a.spin ? "isl-spin" : ""}">${a.icon}</span>`) + `<span>${label}</span>`;
      trail = a.progress != null ? `<span>${Math.round(a.progress * 100)}%</span>` : `<span class="isl-dot"></span>`;
    }
    layers.compact.style.setProperty("--isl-accent", a.accent || "#c6bfff");
    q(".isl-lead").innerHTML = lead; q(".isl-trail").innerHTML = trail + dots();
    // measure the natural width once, then lay the layer out at that size
    layers.compact.style.width = "auto";
    const w = a.kind === "media" ? 150 : Math.max(150, Math.ceil(layers.compact.scrollWidth) + 2);
    return w;
  }

  function render() {
    const ordered = [...ongoing.values()];
    // progress activities (Tor, installs) outrank Now Playing
    const top = alertAct ?? ordered.filter((a) => a.kind !== "media").at(-1) ?? ordered.at(-1);
    const expanded = !!alertAct || ((hover || pinned) && !!top);
    if (expanded && top.kind === "media") {
      fillPlayer(); showLayer("player", 400, 186); morph(400, 186);
    } else if (expanded) {
      fillFull(top);
      const w = top.wide ?? 380, h = top.progress != null ? 92 : 72;
      showLayer("full", w, h); morph(w, h);
    } else if (top) {
      const w = compactFor(top); showLayer("compact", w); morph(w, 30);
    } else {
      // idle: Tor state on the left, a quiet dot on the right
      const c = state.tor ? "#9be6b4" : "#ffb4ab";
      q(".isl-lead").innerHTML = `<span class="ms fill" style="color:${c}">${state.tor ? "shield_lock" : "public"}</span>`;
      const d = dots();
      q(".isl-trail").innerHTML = d || `<span class="isl-dot" style="--isl-accent:${c}"></span>`;
      const w = d ? 118 + 12 * (d.match(/isl-pdot/g).length - 1) : 118;
      showLayer("compact", w); morph(w, 30);
    }
  }
  el.addEventListener("mouseenter", () => { hover = true; render(); });
  el.addEventListener("mouseleave", () => { hover = false; render(); });
  el.addEventListener("click", (e) => {
    const btn = e.target.closest(".pl-ctrl button");
    if (btn) { e.stopPropagation(); call("media", { action: btn.dataset.act }); return; }
    const top = alertAct ?? [...ongoing.values()].at(-1);
    if (top?.onclick) top.onclick(); else { pinned = !pinned; render(); }
  });
  return {
    /** start or update an ongoing activity */
    set(id, act) { ongoing.set(id, { ...(ongoing.get(id) ?? {}), ...act }); render(); },
    /** finish an ongoing activity, optionally with a short alert */
    end(id, doneAlert) { ongoing.delete(id); if (doneAlert) this.alert(doneAlert); else render(); },
    /** show something briefly, expanded */
    alert(act, ms = 2600) {
      alertAct = act; clearTimeout(alertTimer);
      alertTimer = setTimeout(() => { alertAct = null; render(); }, ms);
      render();
    },
    /** Now Playing: {title, artist, art, playing, position (us), length (us), player} or null */
    media(m) {
      if (!m || !m.title) { media = null; el.classList.remove("playing"); this.end("media"); return; }
      media = { ...m, at: performance.now() };
      el.classList.toggle("playing", !!m.playing);
      if (target.h > 100) fillPlayer();
      this.set("media", { kind: "media", title: m.title });
    },
    /** which apps use the camera / microphone / location right now */
    privacy(p) {
      const prev = priv; priv = { camera: p.camera ?? [], mic: p.mic ?? [], location: p.location ?? [] };
      for (const k of Object.keys(PRIV)) {
        if (priv[k].length && !prev[k].length) {      // just turned on: say who
          const [col, ic, label] = PRIV[k];
          this.alert({ icon: ic, title: `${label} on`, sub: priv[k].join(", "), accent: col }, 2600);
          return;
        }
      }
      render();
    },
    render,
    get box() { return [innerWidth / 2 - target.w / 2 - 8, 0, target.w + 16, target.h + 14]; },
  };
})();
function osd(kind, value) {
  const icons = { volume: value == 0 ? "volume_off" : value < 40 ? "volume_down" : "volume_up", brightness: "light_mode" };
  island.alert({ icon: icons[kind], title: kind === "volume" ? "Volume" : "Brightness", progress: value / 100, wide: 320 }, 1400);
}

/* ------------------------------------------------------------------ status */
async function refreshStatus() {
  const st = (await call("status")) ?? {};
  state.live = st.live ?? true;
  if (st.tor !== undefined) state.tor = st.tor;
  if (st.dark !== undefined && st.dark !== state.dark) { state.dark = st.dark; applyTheme(); }
  for (const k of ["wifi", "bluetooth", "usbguard", "mac", "airplane"]) if (st[k] !== undefined) tileState[k] = st[k];
  tileState.tor = state.tor; tileState.dark = state.dark;
  $("#qs-mode").textContent = state.live ? "Wraith Live" : "Wraith";
  $("#wifi-icon").textContent = st.wifi === false ? "wifi_off" : st.wifiConnected === false ? "signal_wifi_statusbar_null" : "wifi";
  const batt = $(".batt");
  if (st.battery === null) batt.hidden = true;
  else if (st.battery !== undefined) {
    batt.hidden = false; $("#batt-pct").textContent = st.battery + "%";
    $("#batt-icon").textContent = st.charging ? "battery_charging_full" : `battery_${Math.min(6, Math.round(st.battery / 16.7))}_bar`;
  }
  for (const [key, v] of [["volume", st.volume], ["brightness", st.brightness]]) {
    const lab = $(`.slider[data-key="${key}"]`);
    if (v === null) lab.hidden = true; else if (v !== undefined && document.activeElement !== lab.querySelector("input")) { lab.querySelector("input").value = v; lab.querySelector("input").dispatchEvent(new Event("sync")); }
  }
  setTorChip();
  if ($("#tiles").children.length) renderTiles();
  // live activities from the system
  if (state.tor && st.torBootstrap != null && st.torBootstrap < 100) {
    island.set("tor", { icon: "shield_lock", title: "Connecting to Tor", short: "Tor", sub: st.torPhase || "Building a private circuit", progress: st.torBootstrap / 100, accent: "#c6bfff" });
    state.torWasConnecting = true;
  } else if (state.torWasConnecting) {
    state.torWasConnecting = false;
    island.end("tor", { icon: "verified_user", title: "Connected to Tor", sub: "You're browsing privately", accent: "#9be6b4" });
  }
  if (st.usbBlocked && st.usbBlocked !== state.lastUsb) {
    state.lastUsb = st.usbBlocked;
    island.alert({ icon: "usb_off", title: "USB device blocked", sub: st.usbBlocked, accent: "#ffb4ab" }, 4000);
  }
  if (st.battery != null && !st.charging && st.battery <= 15 && !state.lowWarned) {
    state.lowWarned = true;
    island.alert({ icon: "battery_alert", title: "Battery low", sub: `${st.battery}% left - plug in soon`, accent: "#ffb4ab" }, 4000);
  }
  if (st.charging && state.wasCharging === false) island.alert({ icon: "battery_charging_full", title: "Charging", side: st.battery + "%", accent: "#9be6b4", wide: 300 }, 2200);
  state.wasCharging = !!st.charging;
  if (st.charging) state.lowWarned = false;
}

/* ------------------------------------------------------------------ start */
async function start() {
  const surface = params.get("surface") ?? "all";
  if (surface === "wallpaper") {
    // background layer: only the wallpaper; the host relays theme changes
    for (const el of document.querySelectorAll("[data-surface]")) if (el.dataset.surface !== "wallpaper") el.remove();
    $("#demo-window")?.remove();
    const st = (await call("status")) ?? {};
    if (st.dark !== undefined) state.dark = st.dark;
    if (st.source) state.source = st.source;
    applyTheme();
    window.shell = { setTheme: (dark, source) => { state.dark = dark; if (source) state.source = source; applyTheme(); } };
    return;
  }
  if (surface === "ui") {
    $("#wallpaper").remove(); $("#demo-window").remove();
    document.body.style.background = "transparent";
  }
  await loadApps();
  await refreshStatus();
  applyTheme(); setTorChip();
  buildDock(); buildChips(); buildTiles(); buildSliders();
  setInterval(refreshStatus, 10000);
  tick(); setInterval(tick, 1000 * 15);
  $("#drawer-btn").onclick = openDrawer;
  $("#status-pill").onclick = openQS;
  $("#scrim").onclick = () => closeAll();
  $("#search").oninput = () => fillGrid(false);
  addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAll();
    if (e.key === "Meta" || e.key === "Super") openDrawer();
  });
  if (params.get("wallpaper")) useWallpaper(params.get("wallpaper"));
  island.render();
  window.shell = { island, osd, media: (m) => island.media(m), privacy: (p) => island.privacy(p), openDrawer, openQS, closeAll, toggleTile, refreshStatus, launch: (n) => { const a = APPS.find((x) => x.name === n); launch(a, document.querySelector(`.app-btn[aria-label="${n}"] .icon`) ?? $("#drawer-btn")); }, useWallpaper, state };
  requestAnimationFrame(syncInput);
}
start();
