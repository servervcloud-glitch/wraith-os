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
const backend = window.wraith ?? {
  // Preview stand-in; the host replaces this with real system calls.
  async call(name, args) { console.log("[wraith mock]", name, JSON.stringify(args ?? {})); return mock[name]?.(args); },
};
const mock = {
  status: () => ({ tor: true, live: true, wifi: true, bluetooth: false, usbguard: true, battery: 82, volume: 55, brightness: 70 }),
};
const call = (name, args) => backend.call(name, args);

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
  call("setCursorTheme", { name: d ? "Wraith" : "Wraith-Black" });
}

// Dynamic colour from a wallpaper image (Material You)
async function useWallpaper(url) {
  const img = new Image(); img.src = url; await img.decode();
  state.source = hexFromArgb(await sourceColorFromImage(img));
  const wp = $("#wallpaper"); wp.classList.add("image"); wp.style.backgroundImage = `url("${url}")`;
  applyTheme();
}

/* ------------------------------------------------------------------ apps */
const CATS = ["All", "Information Gathering", "Vulnerability Analysis", "Web Apps", "Passwords", "Wireless", "Exploitation", "Sniffing & Spoofing", "Forensics", "Reverse Engineering", "System"];
const G = { v: ["#a79fff", "#5b52e0"], p: ["#ff9ec4", "#d9467f"], o: ["#ffc98a", "#e7782f"], b: ["#8fdcff", "#2f8fd6"], g: ["#8ee6b5", "#25a065"], r: ["#ff9a8f", "#d6453a"], s: ["#c9c6d6", "#6d6a7c"], k: ["#4b4858", "#1d1b24"] };
const APPS = [
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
].map(([name, glyph, col, cat, exec]) => ({ name, glyph, c: G[col], cat, exec }));
const DOCK = ["Terminal", "Tor Browser", "Files", "Nmap", "Burp Suite", "Metasploit", "Wireshark"];

function icon(app, size) {
  const el = document.createElement("span");
  el.className = "icon"; if (size) el.style.setProperty("--s", size + "px");
  el.style.setProperty("--c1", app.c[0]); el.style.setProperty("--c2", app.c[1]);
  el.innerHTML = `<span class="ms fill">${app.glyph}</span>`;
  return el;
}

function buildDock() {
  const box = $("#dock-apps");
  for (const n of DOCK) {
    const app = APPS.find((a) => a.name === n);
    const b = document.createElement("button"); b.className = "app-btn"; b.setAttribute("aria-label", n);
    b.append(icon(app, 52)); b.insertAdjacentHTML("beforeend", `<span class="tip">${n}</span>`);
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
  let mx = null, raf = 0;
  const frame = () => {
    raf = 0; let moving = false;
    for (const el of items()) {
      let target = BASE;
      if (mx !== null) {
        const r = el.getBoundingClientRect(), d = Math.abs(mx - (r.left + r.width / 2));
        if (d < RANGE) target = BASE + (MAX - BASE) * (Math.cos((Math.PI * d) / RANGE) + 1) / 2;
      }
      const now = cur.get(el) ?? BASE, next = now + (target - now) * 0.28;
      const v = Math.abs(target - next) < 0.15 ? target : next;
      if (v !== target) moving = true;
      cur.set(el, v); el.style.setProperty("--s", v.toFixed(2) + "px");
    }
    if (moving) raf = requestAnimationFrame(frame);
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
  const list = APPS.filter((a) => (cat === "All" || a.cat === cat) && (!q || (a.name + " " + a.cat + " " + a.exec).toLowerCase().includes(q)));
  list.forEach((app, i) => {
    const b = document.createElement("button"); b.className = "cell" + (animate ? " enter" : "");
    b.append(icon(app)); b.insertAdjacentHTML("beforeend", `<span class="name">${app.name}</span>`);
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

function openDrawer() {
  if (state.open === "drawer") return closeAll();
  closeAll(true);
  state.open = "drawer"; overlay.classList.add("active"); drawer.hidden = false;
  $("#search").value = ""; fillGrid(true);
  const h = drawer.offsetHeight;
  drawerSpring.to(1, (x) => (drawer.style.transform = `translateY(${(1 - x) * (h + 40)}px)`));
  setTimeout(() => $("#search").focus({ preventScroll: true }), 120);
}
function openQS() {
  if (state.open === "qs") return closeAll();
  closeAll(true);
  state.open = "qs"; overlay.classList.add("active"); qs.hidden = false;
  qsSpring.to(1, (x) => { qs.style.opacity = Math.min(1, x * 1.6); qs.style.transform = `scale(${0.82 + 0.18 * x})`; });
}
function closeAll(instant) {
  const was = state.open; state.open = null; overlay.classList.remove("active");
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
  { id: "dnd", icon: "do_not_disturb_on", title: "Do not disturb", sub: (on) => (on ? "On" : "Off") },
  { id: "mac", icon: "fingerprint", title: "MAC spoofing", sub: (on) => (on ? "Random each connect" : "Off") },
  { id: "night", icon: "nightlight", title: "Night light", sub: (on) => (on ? "On" : "Off") },
];
const tileState = { tor: true, wifi: true, bluetooth: false, dark: state.dark, usbguard: true, dnd: false, mac: true, night: false };

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
  call("toggle", { id, on: tileState[id] });
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
    update();
  }
}

/* ------------------------------------------------------------------ app launch */
// A tile grows out of the tapped icon into the window, like Pixel's app open.
function launch(app, fromEl) {
  call("launch", { exec: app.exec });
  const r = fromEl.getBoundingClientRect();
  const W = innerWidth, H = innerHeight;
  const win = { w: Math.min(980, W * 0.68), h: Math.min(620, H * 0.66) };
  win.x = (W - win.w) / 2; win.y = Math.max(64, (H - win.h) / 2 - 30);
  const ghost = $("#launch-ghost");
  ghost.style.setProperty("--c1", app.c[0]); ghost.style.setProperty("--c2", app.c[1]);
  ghost.innerHTML = `<span class="ms fill">${app.glyph}</span>`;
  ghost.hidden = false; ghost.style.opacity = 1;
  closeAll();
  const s = new Spring({ stiffness: 260, damping: 25 });
  const lerp = (a, b, x) => a + (b - a) * x;
  s.to(1, (x) => {
    ghost.style.left = lerp(r.left, win.x, x) + "px"; ghost.style.top = lerp(r.top, win.y, x) + "px";
    ghost.style.width = Math.max(10, lerp(r.width, win.w, x)) + "px"; ghost.style.height = Math.max(10, lerp(r.height, win.h, x)) + "px";
    ghost.style.borderRadius = lerp(r.width * 0.3, 18, Math.min(1, x)) + "px";
  }, () => {
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

/* ------------------------------------------------------------------ start */
async function start() {
  const st = (await call("status")) ?? {};
  state.tor = st.tor ?? true; state.live = st.live ?? true;
  Object.assign(tileState, { tor: state.tor, wifi: st.wifi ?? true, bluetooth: !!st.bluetooth, usbguard: st.usbguard ?? true });
  $("#qs-mode").textContent = state.live ? "Wraith Live" : "Wraith";
  applyTheme(); setTorChip();
  buildDock(); buildChips(); buildTiles(); buildSliders();
  tick(); setInterval(tick, 1000 * 15);
  $("#drawer-btn").onclick = openDrawer;
  $("#status-pill").onclick = openQS;
  $("#scrim").onclick = () => closeAll();
  $("#search").oninput = () => fillGrid(false);
  addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAll();
    if (e.key === "Meta" || e.key === "Super") openDrawer();
  });
  // Each surface (wallpaper, bar, dock, overlay) is its own layer-shell window in the host
  const surface = params.get("surface");
  if (surface && surface !== "all") for (const el of document.querySelectorAll("[data-surface]")) if (el.dataset.surface !== surface) el.remove();
  if (params.get("wallpaper")) useWallpaper(params.get("wallpaper"));
  window.shell = { openDrawer, openQS, closeAll, toggleTile, launch: (n) => { const a = APPS.find((x) => x.name === n); launch(a, document.querySelector(`.app-btn[aria-label="${n}"] .icon`) ?? $("#drawer-btn")); }, useWallpaper, state };
}
start();
