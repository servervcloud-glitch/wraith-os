// Wraith Settings
import { call, on, initTheme, h, icon, toggle, dialog, askAdmin, snack, wave, windowFrame, IN_OS, useMock } from "../common/app.js";

if (!IN_OS) useMock((await import("./mock.js")).default);
await initTheme();

const PAGES = [
  ["update", "System update", "system_update"],
  ["network", "Wi-Fi", "wifi"],
  ["privacy", "Privacy & Tor", "shield_lock"],
  ["appearance", "Appearance", "palette"],
  ["sound", "Sound & display", "tune"],
  ["account", "Account", "account_circle"],
  ["about", "About Wraith", "info"],
];
const { content } = windowFrame("Settings");
const nav = h("nav.nav"), main = h("main.content");
content.append(nav, main);
let current = null;
for (const [id, label, ic] of PAGES)
  nav.append(h("button", { "data-page": id, onclick: () => show(id) }, icon(ic), h("span", label)));

async function show(id) {
  current = id;
  for (const b of nav.children) b.classList.toggle("on", b.dataset.page === id);
  const page = h("div.page");
  main.replaceChildren(page);
  main.scrollTop = 0;
  await RENDER[id](page);
}

/* ================================================================ System update */
const upd = { state: "idle", data: null, pct: 0, text: "" };   // idle | checking | ready | updating | done | error
const GROUPS = [["Kali tools & system", "terminal", "Hacking tools, the kernel and the base system, from Kali"],
  ["Tor & privacy", "shield_lock", "Tor, Tor Browser, the firewall and hardening - the Tails side"],
  ["Wraith", "auto_awesome", "Wraith's own desktop and apps"]];

function renderUpdate(page) {
  page.append(h("h2", "System update"));
  const d = upd.data;
  const n = d?.packages?.length ?? 0;
  const [ic, title, sub, cls] = {
    idle: ["update", "Check for updates", "See what's new for Kali tools, Tor and Wraith", ""],
    checking: ["sync", "Checking for updates…", upd.text || "Contacting the update servers over Tor", ""],
    ready: n ? ["download", `${n} update${n > 1 ? "s" : ""} available`, d.download ? `${d.download} to download` : "Ready to install", ""]
             : ["check_circle", "You're up to date", "Everything is on the latest version", "ok"],
    updating: ["downloading", "Updating…", upd.text || "Preparing", ""],
    done: ["task_alt", "Updates installed", d?.restart ? "Restart to finish (a new kernel was installed)" : "Everything is on the latest version", "ok"],
    error: ["error", "Something went wrong", (upd.errors ?? []).at(-1) || "Check your connection and try again", ""],
  }[upd.state];
  const bar = wave();
  const hero = h("div.card",
    h("div.hero" + (cls ? "." + cls : ""), h("div.big", icon(ic, true)),
      h("div.t", h("b", title), h("span", sub), (upd.state === "checking" || upd.state === "updating") && bar)),
    h("div.hero-actions",
      upd.state === "ready" && n ? h("button.btn", { onclick: applyUpdates }, icon("download"), "Update now") : null,
      upd.state === "done" && d?.restart ? h("button.btn", { onclick: () => call("restart") }, icon("restart_alt"), "Restart now") : null,
      !["checking", "updating"].includes(upd.state) ? h("button.btn" + (upd.state === "ready" && n ? ".tonal" : ""), { onclick: checkUpdates }, icon("refresh"), "Check for updates") : null,
      upd.state === "updating" ? h("span.muted", "You can keep working - progress also shows in the Dynamic Island") : null));
  if (upd.state === "checking" || upd.state === "updating") bar.set(upd.pct / 100 || null);
  page.append(hero);
  if (d?.live) page.append(h("div.note", icon("info"), h("div", h("b", "Wraith Live: "), "updates last until you shut down. Install Wraith to keep them.")));
  if (upd.state === "ready" && n) {
    const card = h("div.card");
    for (const [g, gic, gsub] of GROUPS) {
      const list = d.packages.filter((p) => p.group === g);
      if (!list.length) continue;
      card.append(h("details.group", { open: list.length <= 6 },
        h("summary", h("div.ic", icon(gic)), h("div.txt", h("b", g), h("span", gsub)), h("span.count", list.length), h("span.ms.chev", "expand_more")),
        h("div.pkgs", list.map((p) => h("div.pkg", h("span", p.name), h("span", p.new ? `new · ${p.to}` : `${p.from} → ${p.to}`))))));
    }
    page.append(card);
  }
  page.append(h("div.card", h("div.row", h("div.ic", icon("lock")), h("div.txt", h("b", "Private and verified"),
    h("span", "Updates download through Tor and are checked against Kali's signing keys before anything is installed.")))));
}
async function checkUpdates() {
  if (!(await askAdmin("Checking for updates needs the admin password."))) return;
  Object.assign(upd, { state: "checking", pct: 0, text: "" });
  rerender("update");
  call("checkUpdates");
}
async function applyUpdates() {
  if (!(await askAdmin("Installing updates needs the admin password."))) return;
  Object.assign(upd, { state: "updating", pct: 0, text: "" });
  rerender("update");
  call("applyUpdates");
}
on("job", (j) => {
  if (j.done) {
    if (j.kind === "upgrade") { Object.assign(upd, { state: j.ok ? "done" : "error", errors: j.errors }); rerender("update"); snack(j.ok ? "Updates installed" : "The update didn't finish"); }
    return;
  }
  upd.pct = j.pct; upd.text = j.text;
  const bar = current === "update" && main.querySelector(".wave");
  if (bar) { bar.set(j.pct / 100); main.querySelector(".hero .t span").textContent = j.text; } else if (current === "update") rerender("update");
});
on("updates", (d) => { Object.assign(upd, { state: d.ok || d.packages?.length ? "ready" : "error", data: d, errors: d.errors }); rerender("update"); });
function rerender(id) { if (current === id) show(id); }

/* ================================================================ Wi-Fi */
const bars = (s) => s > 75 ? "network_wifi" : s > 50 ? "network_wifi_3_bar" : s > 25 ? "network_wifi_2_bar" : "network_wifi_1_bar";
async function renderNetwork(page, rescan) {
  page.append(h("h2", "Wi-Fi"));
  const w = await call("wifi", { rescan });
  if (!w?.available) { page.append(h("div.note", icon("wifi_off"), "No Wi-Fi hardware was found.")); return; }
  page.append(h("div.card", h("div.row", h("div.ic", icon("wifi")), h("div.txt", h("b", "Use Wi-Fi"), h("span", w.enabled ? "On" : "Off")),
    toggle(w.enabled, async (v) => { await call("wifiRadio", { on: v }); setTimeout(() => rerender("network"), 1200); }))));
  if (!w.enabled) return;
  const list = h("div.card", h("h3", "Networks"));
  if (!w.networks.length) list.append(h("div.row", h("div.txt", h("span", "Looking for networks…"))));
  for (const n of w.networks) {
    list.append(h("div.row.click", { onclick: () => (n.connected ? netMenu(n) : connect(n)) },
      h("div.ic", icon(bars(n.signal), n.connected)),
      h("div.txt", h("b", n.ssid), h("span", n.connected ? "Connected · traffic goes through Tor" : n.saved ? "Saved" : n.secure ? "Secured" : "Open network")),
      n.secure ? h("span.sig", icon("lock")) : null));
  }
  page.append(list, h("button.btn.tonal", { onclick: () => { main.firstChild.replaceChildren(); renderNetwork(main.firstChild, true); } }, icon("refresh"), "Scan again"));
}
async function connect(n) {
  let pw = null;
  if (n.secure && !n.saved) {
    const input = h("input.input", { type: "password", placeholder: "Password" });
    pw = await dialog({ icon: "wifi_password", title: n.ssid, body: h("div.field", input), actions: [["Cancel", null], ["Connect", () => input.value, "filled"]] });
    if (pw == null) return;
  }
  snack(`Connecting to ${n.ssid}…`);
  const r = await call("wifiConnect", { ssid: n.ssid, password: pw });
  snack(r?.ok ? `Connected to ${n.ssid}` : r?.error || "Couldn't connect");
  rerender("network");
}
async function netMenu(n) {
  const act = await dialog({ icon: "wifi", title: n.ssid, text: "Connected. All traffic still goes through Tor.", actions: [["Close", null], ["Forget", "forget", "danger"]] });
  if (act === "forget") { await call("wifiForget", { ssid: n.ssid }); rerender("network"); }
}

/* ================================================================ Privacy & Tor */
async function renderPrivacy(page) {
  page.append(h("h2", "Privacy & Tor"));
  const p = await call("privacy");
  const set = async (key, on) => { const r = await call("setPrivacy", { key, on }); if (!r?.ok) { snack(r?.error || "Not allowed"); return false; } };
  page.append(h("div.card",
    h("div.row", h("div.ic", icon("shield_lock", true)),
      h("div.txt", h("b", "Send everything through Tor"),
        h("span", p.live ? "Always on in Wraith Live" : p.tor ? "On - apps can't reach the internet directly" : "Off - direct internet connection")),
      toggle(p.tor, (v) => set("tor", v), p.live)),
    h("div.row", h("div.ic", icon("autorenew")), h("div.txt", h("b", "New Tor identity"), h("span", "New connections use fresh circuits (new exit IP)")),
      h("button.btn.tonal", { onclick: async () => { const r = await call("setPrivacy", { key: "newnym" }); snack(r?.ok ? "New identity - new connections use new circuits" : "Tor isn't ready yet"); } }, "Renew"))));
  if (p.tor && p.torBootstrap != null && p.torBootstrap < 100)
    page.append(h("div.note", icon("hourglass_top"), `Tor is still connecting (${p.torBootstrap}%).`));
  page.append(h("div.card",
    h("div.row", h("div.ic", icon("fingerprint")), h("div.txt", h("b", "Random MAC address"), h("span", "Your network card shows a new hardware address on every connection")),
      toggle(p.mac, (v) => set("mac", v))),
    h("div.row", h("div.ic", icon("usb")), h("div.txt", h("b", "USB guard"), h("span", "Block USB devices plugged in while you're working")),
      toggle(p.usbguard, (v) => set("usbguard", v)))));
  page.append(h("div.note", icon("visibility"), h("div", "The dots in the Dynamic Island show when an app uses your ",
    h("b", { style: { color: "#34c759" } }, "camera"), ", ", h("b", { style: { color: "#d4a800" } }, "microphone"), " or ", h("b", { style: { color: "#0a84ff" } }, "location"), ".")));
}

/* ================================================================ Appearance */
const ACCENTS = ["#6a5ff0", "#d9467f", "#e7782f", "#2f8fd6", "#25a065", "#8c5cd6", "#c43b3b", "#6d6a7c"];
async function renderAppearance(page) {
  page.append(h("h2", "Appearance"));
  const a = await call("appearance");
  const seg = h("div.seg", [["light", "light_mode", "Light"], ["dark", "dark_mode", "Dark"]].map(([k, ic, label]) =>
    h("button" + ((k === "dark") === a.dark ? ".on" : ""), { onclick: async () => { await call("setAppearance", { dark: k === "dark" }); setTimeout(async () => { await initTheme(); rerender("appearance"); }, 150); } }, icon(ic), label)));
  page.append(h("div.card", h("div.row", h("div.ic", icon("contrast")), h("div.txt", h("b", "Theme"), h("span", "Apps, desktop and cursor follow it")), seg)));
  page.append(h("div.card", h("h3", "Accent colour"), h("div.swatches", ACCENTS.map((c) =>
    h("button.sw" + (c.toLowerCase() === a.source.toLowerCase() ? ".on" : ""), { style: { background: c }, title: c,
      onclick: async () => { await call("setAppearance", { source: c }); setTimeout(async () => { await initTheme(); rerender("appearance"); }, 150); } }))),
    h("div.row", h("div.txt", h("span", "The wallpaper, desktop and apps are coloured from this choice.")))));
}

/* ================================================================ Sound & display */
async function renderSound(page) {
  page.append(h("h2", "Sound & display"));
  const l = await call("levels");
  const slider = (key, ic, v) => {
    const r = h("input.range", { type: "range", min: 0, max: 100, value: v });
    const paint = () => r.style.setProperty("--v", r.value + "%");
    r.oninput = () => { paint(); call("setLevel", { key, value: +r.value }); };
    paint();
    return h("div.slider-row", icon(ic), r);
  };
  const card = h("div.card", h("h3", "Levels"));
  card.append(l.volume == null ? h("div.row", h("div.txt", h("span", "No speakers found"))) : slider("volume", "volume_up", l.volume));
  if (l.brightness != null) card.append(slider("brightness", "light_mode", l.brightness));
  page.append(card);
  const scales = [1, 1.25, 1.5, 1.75, 2];
  page.append(h("div.card", h("h3", "Display size"), h("div.row", h("div.txt", h("b", "Scale"), h("span", "Make everything bigger on high-resolution screens")),
    h("div.seg", scales.map((s) => h("button" + (s === l.scale ? ".on" : ""), { onclick: async () => { await call("setScale", { scale: s }); rerender("sound"); } }, `${s * 100}%`))))));
}

/* ================================================================ Account */
function renderAccount(page) {
  page.append(h("h2", "Account"));
  const cur = h("input.input", { type: "password", autocomplete: "current-password" });
  const nw = h("input.input", { type: "password", autocomplete: "new-password" });
  const again = h("input.input", { type: "password", autocomplete: "new-password" });
  const err = h("div.muted");
  page.append(h("div.card.pad", h("div.row", { style: { padding: 0, minHeight: "auto", marginBottom: "14px" } }, h("div.ic", icon("admin_panel_settings")),
    h("div.txt", h("b", "Admin password"), h("span", "Needed for updates, installing apps and system changes"))),
    h("div.field", h("label", "Current password"), cur), h("div.field", h("label", "New password (8+ characters)"), nw),
    h("div.field", h("label", "New password again"), again), err,
    h("button.btn", { onclick: async () => {
      if (nw.value !== again.value) { err.textContent = "The new passwords don't match"; return; }
      const r = await call("changePassword", { current: cur.value, new: nw.value });
      err.textContent = r?.ok ? "" : r?.error || "Couldn't change it";
      if (r?.ok) { snack("Password changed"); cur.value = nw.value = again.value = ""; }
    } }, icon("key"), "Change password")));
}

/* ================================================================ About */
const gb = (b) => b ? (b / 1024 ** 3).toFixed(b > 100 * 1024 ** 3 ? 0 : 1) + " GB" : "-";
async function renderAbout(page) {
  page.append(h("h2", "About Wraith"));
  const a = await call("about");
  page.append(h("div.card.about-hero", h("div.logo", "Wraith"), h("div.by", "CRAFTED BY VIPIN"), h("div.muted", { style: { marginTop: "10px" } }, `Version ${a.version} · ${a.mode}`)));
  const rows = [["Device name", a.hostname], ["Based on", a.base], ["Kernel", a.kernel], ["Processor", a.cpu], ["Memory", gb(a.memory)],
    ["Graphics", a.gpu || "-"], ["Storage", `${gb(a.disk.free)} free of ${gb(a.disk.total)}`]];
  page.append(h("div.card", h("dl.dl", rows.flatMap(([k, v]) => [h("dt", k), h("dd", v || "-")]))));
}

const RENDER = { update: renderUpdate, network: renderNetwork, privacy: renderPrivacy, appearance: renderAppearance, sound: renderSound, account: renderAccount, about: renderAbout };
const start = new URLSearchParams(location.search).get("page");
on("args", (a) => a.page && show(a.page));
show(PAGES.some(([id]) => id === start) ? start : "update");
