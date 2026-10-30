// Wraith Welcome - first login: what Wraith is, admin password (Live), looks, Wi-Fi + Tor, shortcuts.
import { call, on, initTheme, applyTheme, h, icon, snack, wave, dialog, IN_OS, useMock } from "../common/app.js";

if (!IN_OS) useMock((await import("./mock.js")).default);
await initTheme();
const st = await call("state");

const wz = h("div.wz", h("div.top", h("button.wbtn", { title: "Minimise", onclick: () => call("minimize") }, icon("remove"))));
document.body.append(wz);
const steps = [];
const dotsEl = h("div.dots");
const back = h("button.btn.text", { onclick: () => go(cur - 1) }, "Back");
const next = h("button.btn", { onclick: () => advance() }, "Get started", icon("arrow_forward"));
wz.append(h("div.foot", dotsEl, back, next));
let cur = 0;

function step(el, { onNext, label } = {}) { el.classList.add("step", "out-right"); steps.push({ el, onNext, label }); wz.append(el); }

/* 1 - hello */
step(h("div.hero2",
  h("div.bdots", h("span"), h("span"), h("span"), h("span")),
  h("div.wordmark", "Wraith"), h("div.by", "CRAFTED BY VIPIN"),
  h("p.lead", st.live ? "You're running Wraith Live. Let's get you set up - it takes a minute." : "Wraith is installed. Let's make it yours.")), { label: "Get started" });

/* 2 - what Wraith does */
step(h("div",
  h("h2", st.live ? "Private by design" : "Your private toolbox"),
  h("p.lead", "Every Kali tool, inside a system that protects you while you use them."),
  h("div.feats",
    feat("shield_lock", "Everything through Tor", st.live ? "In Wraith Live, all traffic goes through Tor - always." : "On by default; switch it in quick settings."),
    feat("auto_delete", st.live ? "Forgets everything" : "Encrypted & hardened", st.live ? "Shut down and nothing you did is left on this computer." : "AppArmor, a strict firewall and hardened kernel settings."),
    feat("fingerprint", "New identity per network", "A random hardware (MAC) address every time you connect."),
    feat("usb", "USB guard", "New USB devices are blocked while you work - unlock them in one tap."))));
function feat(ic, t, s) { return h("div.feat", h("div.ic", icon(ic)), h("div", h("b", t), h("span", s))); }

/* 3 - admin password (Live only; an installed system already has one) */
if (st.needsPassword) {
  const pw = h("input.input", { type: "password", placeholder: "At least 8 characters" });
  const pw2 = h("input.input", { type: "password", placeholder: "Type it again" });
  const meter = h("i");
  pw.oninput = () => {
    const v = pw.value, score = Math.min(4, (v.length >= 8) + (v.length >= 12) + /[A-Z]/.test(v) + /[0-9]/.test(v) + /[^A-Za-z0-9]/.test(v));
    meter.style.width = (v ? 15 + score * 21 : 0) + "%";
    meter.style.background = ["#ff6b81", "#ff6b81", "#ffd479", "#7ee0a1", "#7ee0a1"][score];
  };
  step(h("div",
    h("h2", "Set an admin password"),
    h("p.lead", "Wraith asks for it before updates, installs and system changes - so nobody can change your system behind your back."),
    h("div.pwbox", h("div.field", h("label", "Admin password"), pw), h("div.strength", meter), h("div.field", h("label", "Confirm"), pw2))),
    { label: "Set password", onNext: async () => {
      if (pw.value.length < 8) { snack("Use at least 8 characters"); return false; }
      if (pw.value !== pw2.value) { snack("The passwords don't match"); return false; }
      const r = await call("setPassword", { password: pw.value });
      if (!r?.ok) { snack(r?.error || "Couldn't set it"); return false; }
      snack("Admin password set");
    } });
}

/* 4 - looks */
const ACCENTS = ["#6a5ff0", "#d9467f", "#e7782f", "#2f8fd6", "#25a065", "#8c5cd6"];
const look = await call("appearance");
function looksStep() {
  const seg = h("div.seg", [["light", "light_mode", "Light"], ["dark", "dark_mode", "Dark"]].map(([k, ic, l]) =>
    h("button" + ((k === "dark") === look.dark ? ".on" : ""), { onclick: () => setLook({ dark: k === "dark" }) }, icon(ic), l)));
  const sws = h("div.looks", ACCENTS.map((c) => h("button.sw" + (c === look.source ? ".on" : ""), { style: { background: c }, onclick: () => setLook({ source: c }) })));
  return h("div", h("h2", "Make it yours"), h("p.lead", "Pick light or dark and a colour. The wallpaper, desktop and apps all follow it."),
    h("div", { style: { marginBottom: "22px" } }, seg), sws);
}
async function setLook(change) {
  Object.assign(look, change);
  await call("setAppearance", change);
  applyTheme(look);
  const el = looksStep(); el.className = steps[lookIdx].el.className; steps[lookIdx].el.replaceWith(el); steps[lookIdx].el = el;
}
step(looksStep());
const lookIdx = steps.length - 1;

/* 5 - connect */
const torBar = wave();
const torText = h("span.muted", "Waiting for a network…");
const nets = h("div.card.nets");
step(h("div", h("h2", "Get connected"), h("p.lead", "Choose a network. Wraith then connects to Tor - nothing leaves this computer outside Tor."),
  h("div.torline", icon("shield_lock", true), torBar, torText), nets), {});
const netIdx = steps.length - 1;
async function loadNets() {
  const w = await call("wifi", {});
  nets.replaceChildren();
  if (!w?.available || !w.networks?.length) { nets.append(h("div.row", h("div.txt", h("span", w?.available ? "Looking for networks… (a cable works too)" : "No Wi-Fi here - plug in a network cable")))); return; }
  for (const n of w.networks.slice(0, 8))
    nets.append(h("div.row.click", { onclick: () => join(n) }, h("div.ic", icon(n.connected ? "wifi" : "wifi", n.connected)),
      h("div.txt", h("b", n.ssid), h("span", n.connected ? "Connected" : n.secure ? "Secured" : "Open")), n.secure ? icon("lock") : null));
}
async function join(n) {
  if (n.connected) return;
  let pw = null;
  if (n.secure && !n.saved) {
    const input = h("input.input", { type: "password", placeholder: "Password" });
    pw = await dialog({ icon: "wifi_password", title: n.ssid, body: h("div.field", input), actions: [["Cancel", null], ["Connect", () => input.value, "filled"]] });
    if (pw == null) return;
  }
  snack(`Connecting to ${n.ssid}…`);
  const r = await call("wifiConnect", { ssid: n.ssid, password: pw });
  snack(r?.ok ? `Connected to ${n.ssid}` : r?.error || "Couldn't connect");
  loadNets();
}
setInterval(async () => {
  const s = await call("state");
  if (s?.torBootstrap == null) { torBar.set(0); return; }
  torBar.set(s.torBootstrap / 100);
  torText.textContent = s.torBootstrap >= 100 ? "Connected to Tor" : `Connecting to Tor… ${s.torBootstrap}%`;
}, 1000);

/* 6 - shortcuts */
const K = (...k) => h("span", k.map((x, i) => [i ? " + " : "", h("kbd", x)]));
step(h("div", h("h2", "You're all set"), h("p.lead", "A few shortcuts worth knowing:"),
  h("div.keys",
    K("Super"), h("span", "All apps and tools"),
    K("Super", "Enter"), h("span", "Terminal"),
    K("Super", "S"), h("span", "Quick settings (Tor, Wi-Fi, USB guard…)"),
    K("Super", "Q"), h("span", "Close a window"),
    K("Super", "L"), h("span", "Lock the screen"),
    K("Super", "I"), h("span", "Settings and updates"))), { label: "Start using Wraith", onNext: async () => { await call("finish"); call("close"); return false; } });

for (let i = 0; i < steps.length; i++) dotsEl.append(h("i"));
async function advance() {
  const s = steps[cur];
  if (s.onNext && (await s.onNext()) === false) return;
  go(cur + 1);
}
function go(i) {
  if (i < 0 || i >= steps.length) return;
  steps.forEach((s, k) => { s.el.classList.toggle("out-left", k < i); s.el.classList.toggle("out-right", k > i); });
  cur = i;
  [...dotsEl.children].forEach((d, k) => d.classList.toggle("on", k === i));
  back.style.visibility = i ? "visible" : "hidden";
  next.replaceChildren(steps[i].label ?? "Next", icon(i === steps.length - 1 ? "check" : "arrow_forward"));
  if (i === netIdx) loadNets();
  steps[i].el.querySelector("input")?.focus();
}
go(0);
