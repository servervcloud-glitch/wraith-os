// Wraith apps - shared helpers: backend bridge, desktop theme, DOM builder,
// dialogs, snackbar and the wavy progress bar.
import { Hct, SchemeTonalSpot, MaterialDynamicColors as MDC, hexFromArgb, argbFromHex } from "../vendor/mcu.js";

export const IN_OS = !!window.wraith;
const listeners = {};
let mockBackend = null;
/** Preview builds (plain browser) register a mock backend here. */
export function useMock(mock) { mockBackend = mock; }

export async function call(name, args = {}) {
  if (IN_OS) return window.wraith.call(name, args);
  if (name === "theme" && !mockBackend?.theme) return { dark: new URLSearchParams(location.search).get("theme") !== "light", source: "#6a5ff0" };
  const fn = mockBackend?.[name];
  return fn ? fn(args, emitLocal) : null;
}
export function on(event, fn) { (listeners[event] ??= []).push(fn); }
function emitLocal(event, data) { for (const fn of listeners[event] ?? []) fn(data); }
window.wraithEvent = emitLocal;

/* ---- theme: same palette as the desktop ---- */
export function applyTheme({ dark = true, source = "#6a5ff0" } = {}) {
  const scheme = new SchemeTonalSpot(Hct.fromInt(argbFromHex(source)), dark, 0);
  const st = document.documentElement.style;
  const roles = ["surface", "onSurface", "onSurfaceVariant", "surfaceContainerLow", "surfaceContainer", "surfaceContainerHigh",
    "surfaceContainerHighest", "outline", "outlineVariant", "primary", "onPrimary", "primaryContainer", "onPrimaryContainer",
    "secondary", "secondaryContainer", "onSecondaryContainer", "tertiaryContainer", "onTertiaryContainer", "error", "onError",
    "errorContainer", "onErrorContainer", "inverseSurface", "inverseOnSurface"];
  for (const r of roles) st.setProperty("--" + r.replace(/[A-Z]/g, (c) => "-" + c.toLowerCase()), hexFromArgb(MDC[r].getArgb(scheme)));
  st.colorScheme = dark ? "dark" : "light";
}
export async function initTheme() {
  applyTheme(await call("theme"));
  on("theme", applyTheme);
}

/* ---- tiny DOM builder: h("div.card", {onclick}, child, "text") ---- */
export function h(tag, props, ...kids) {
  const [name, ...cls] = tag.split(".");
  const el = document.createElement(name || "div");
  if (cls.length) el.className = cls.join(" ");
  if (props && (typeof props !== "object" || props instanceof Node || Array.isArray(props))) { kids.unshift(props); props = null; }
  for (const [k, v] of Object.entries(props ?? {})) {
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const k of kids.flat(Infinity)) if (k != null && k !== false) el.append(k instanceof Node ? k : document.createTextNode(String(k)));
  return el;
}
export const icon = (name, fill) => h("span.ms" + (fill ? ".fill" : ""), name);

/** M3 switch element; onchange(newValue) may return false (or a Promise of false) to refuse. */
export function toggle(value, onchange, disabled) {
  const el = h("button.switch" + (value ? ".on" : ""), { role: "switch", "aria-checked": String(!!value), disabled });
  el.onclick = async () => {
    const nv = !el.classList.contains("on");
    el.classList.toggle("on", nv);
    if ((await onchange?.(nv)) === false) el.classList.toggle("on", !nv);
  };
  return el;
}

/* ---- dialogs ---- */
export function dialog({ icon: ic, title, text, body, actions }) {
  return new Promise((resolve) => {
    const close = (v) => { scrim.remove(); resolve(v); };
    const dlg = h("div.dialog", ic && h("div.dic", icon(ic)), h("h4", title), text && h("p", text), body,
      h("div.acts", (actions ?? [["OK", true]]).map(([label, val, cls]) =>
        h("button.btn" + (cls ? "." + cls : ".text"), { onclick: () => close(typeof val === "function" ? val() : val) }, label))));
    const scrim = h("div.scrim", dlg);
    scrim.addEventListener("keydown", (e) => { if (e.key === "Escape") close(null); });
    document.body.append(scrim);
    dlg.querySelector("input")?.focus();
  });
}

/** Ask for the admin password and check it with the backend's `auth` call. Returns true when accepted. */
export async function askAdmin(reason) {
  const st = await call("auth", { check: true });
  if (st?.ok) return true;                 // no password needed (or still remembered)
  for (;;) {
    const input = h("input.input", { type: "password", placeholder: "Admin password", autocomplete: "off" });
    const err = h("div.err");
    const body = h("div", h("div.field", input), err);
    const pending = dialog({ icon: "admin_panel_settings", title: "Admin password", text: reason, body,
      actions: [["Cancel", null], ["Continue", () => input.value, "filled"]] });
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") body.closest(".dialog").querySelector(".acts .btn:last-child").click(); });
    const pw = await pending;
    if (pw == null) return false;
    const r = await call("auth", { password: pw });
    if (r?.ok) return true;
    snack("Wrong password, try again");
  }
}

export function snack(text, ms = 3200) {
  document.querySelector(".snack")?.remove();
  const el = h("div.snack", text);
  document.body.append(el);
  setTimeout(() => el.remove(), ms);
}

/* ---- wavy progress bar: value 0..1, or null for "working" ---- */
export function wave() {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  const track = document.createElementNS(ns, "path"), bar = document.createElementNS(ns, "path");
  track.setAttribute("class", "track"); bar.setAttribute("class", "bar");
  svg.append(track, bar);
  const el = h("div.wave", svg);
  let value = 0, shown = 0, phase = 0, raf = 0;
  const draw = () => {
    const w = el.clientWidth || 600, mid = 7, amp = 3, len = 26;
    shown += ((value ?? 0.3) - shown) * 0.12;
    phase += 0.06;
    const end = value == null ? w : Math.max(0, Math.min(1, shown)) * w;
    let d = "";
    for (let x = 0; x <= end; x += 2) d += (x ? "L" : "M") + x.toFixed(1) + " " + (mid + amp * Math.sin(x / len * 2 * Math.PI - phase * 2)).toFixed(2);
    bar.setAttribute("d", d || "M0 7");
    if (value == null) bar.setAttribute("stroke-dasharray", "60 40"), bar.setAttribute("stroke-dashoffset", String(-phase * 60));
    else bar.removeAttribute("stroke-dasharray");
    track.setAttribute("d", value == null ? "" : `M${Math.min(w, end + 10)} ${mid} L${w} ${mid}`);
    raf = el.isConnected ? requestAnimationFrame(draw) : 0;
  };
  el.set = (v) => { value = v; if (!raf) raf = requestAnimationFrame(draw); };
  requestAnimationFrame(() => el.set(value));
  return el;
}

/** Standard window frame with title and close button; returns {frame, content}. */
export function windowFrame(title) {
  const content = h("div.body");
  const frame = h("div.frame",
    h("header.titlebar", h("h1", title),
      h("button.wbtn", { title: "Minimise", onclick: () => call("minimize") }, icon("remove")),
      h("button.wbtn.close", { title: "Close", onclick: () => call("close") }, icon("close"))),
    content);
  document.body.append(frame);
  return { frame, content };
}

/** The app's own icon with the 3D finish (or a neutral glyph when it has none). */
export function icon3d(url, size = 56, glyph = "apps") {
  const el = h("span.i3d", { style: { "--s": size + "px" } });
  if (!url) { el.classList.add("glyph"); el.append(icon(glyph, true)); return el; }
  el.style.setProperty("--img", `url("${url}")`);
  const depth = h("span.depth");
  for (let k = 1; k <= 5; k++) { const d = h("img", { src: url, alt: "", draggable: "false" }); d.style.setProperty("--k", k); depth.append(d); }
  const img = h("img", { src: url, alt: "", draggable: "false" });
  img.onerror = () => { el.replaceWith(icon3d(null, size, glyph)); };
  el.append(depth, img, h("i.gloss"));
  return el;
}
// icons lean towards the pointer
let tiltEl = null;
addEventListener("pointermove", (e) => {
  const el = e.target.closest?.(".i3d:not(.glyph)");
  if (el !== tiltEl) { tiltEl?.style.removeProperty("--rx"); tiltEl?.style.removeProperty("--ry"); tiltEl = el; }
  if (!el) return;
  const r = el.getBoundingClientRect();
  el.style.setProperty("--ry", (((e.clientX - r.left) / r.width - 0.5) * 18).toFixed(1) + "deg");
  el.style.setProperty("--rx", ((0.5 - (e.clientY - r.top) / r.height) * 18).toFixed(1) + "deg");
}, { passive: true });
