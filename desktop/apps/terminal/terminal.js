// Wraith Terminal - tabs around xterm.js, themed from the desktop colours.
import { call, on, initTheme, h, icon, windowButtons, IN_OS, useMock } from "../common/app.js";

if (!IN_OS) useMock((await import("./mock.js")).default);
await initTheme();
const args = new URLSearchParams(location.search);

// ANSI colours tuned to Wraith's palette (dark and light sets)
const PALETTE = {
  dark: { black: "#1b1a22", red: "#ff6b81", green: "#7ee0a1", yellow: "#ffd479", blue: "#8fb7ff", magenta: "#c6a0ff", cyan: "#6fd3ff", white: "#d9d4e6",
    brightBlack: "#5d596b", brightRed: "#ff8fa0", brightGreen: "#a3f0c0", brightYellow: "#ffe2a3", brightBlue: "#b3cdff", brightMagenta: "#dcc2ff", brightCyan: "#9fe3ff", brightWhite: "#ffffff" },
  light: { black: "#2a2733", red: "#c4314b", green: "#1f8a4c", yellow: "#a46a00", blue: "#2f63c9", magenta: "#8a4fd0", cyan: "#0b7fa3", white: "#c9c5d3",
    brightBlack: "#6d6979", brightRed: "#dc4560", brightGreen: "#2aa35e", brightYellow: "#c08310", brightBlue: "#4479e0", brightMagenta: "#a066e6", brightCyan: "#1597bf", brightWhite: "#1c1b22" },
};
function termTheme() {
  const cs = getComputedStyle(document.documentElement);
  const v = (n) => cs.getPropertyValue(n).trim();
  const dark = document.documentElement.style.colorScheme !== "light";
  document.documentElement.style.setProperty("--term-bg", dark ? "#0f0e14" : "#fdfcff");
  return { background: "#00000000", foreground: v("--on-surface"), cursor: v("--primary"), cursorAccent: dark ? "#0f0e14" : "#fdfcff",
    selectionBackground: v("--primary-container") + "cc", selectionForeground: v("--on-primary-container"), ...(dark ? PALETTE.dark : PALETTE.light) };
}

const tabsEl = h("div.tabs"), panes = h("div.panes");
const tbar = h("header.tbar", tabsEl, h("button.add", { title: "New tab (Ctrl+Shift+T)", onclick: () => newTab() }, icon("add")));
tbar.append(windowButtons(tbar));
const frame = h("div.tframe", tbar, panes);
document.body.append(frame);

const tabs = new Map();   // backend id -> {term, fit, tab, pane, title}
let active = null;

async function newTab(run = null, title = null) {
  const term = new Terminal({
    fontFamily: '"JetBrains Mono", "Fira Code", "DejaVu Sans Mono", monospace', fontSize: 14, lineHeight: 1.25, letterSpacing: 0,
    cursorBlink: true, cursorStyle: "bar", cursorWidth: 2, allowTransparency: true, scrollback: 10000, theme: termTheme(),
    macOptionIsMeta: true, rightClickSelectsWord: true, smoothScrollDuration: 90,
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  term.loadAddon(new WebLinksAddon.WebLinksAddon());
  const pane = h("div.pane");
  panes.append(pane);
  term.open(pane);
  fit.fit();
  const { id } = await call("open", { run, cols: term.cols, rows: term.rows });
  const tab = h("button.tab", { onclick: () => select(id) }, icon(run ? "construction" : "terminal"), h("span.tt", title || "Terminal"),
    h("span.x", { title: "Close tab", onclick: (e) => { e.stopPropagation(); closeTab(id); } }, icon("close")));
  tabsEl.append(tab);
  const t = { term, fit, tab, pane, title: title || "Terminal", fixed: !!title };
  tabs.set(id, t);
  term.onData((d) => call("write", { id, data: d }));
  term.onResize(({ cols, rows }) => call("resize", { id, cols, rows }));
  term.attachCustomKeyEventHandler((e) => {
    if (e.type !== "keydown" || !e.ctrlKey || !e.shiftKey) return true;
    const k = e.key.toLowerCase();
    if (k === "c") { const s = term.getSelection(); if (s) call("copy", { text: s }); return false; }
    if (k === "v") { call("paste").then((txt) => txt && term.paste(txt)); return false; }
    if (k === "t") { newTab(); return false; }
    if (k === "w") { closeTab(id); return false; }
    return true;
  });
  select(id);
  return id;
}
function select(id) {
  active = id;
  for (const [tid, t] of tabs) { t.tab.classList.toggle("on", tid === id); t.pane.classList.toggle("on", tid === id); }
  const t = tabs.get(id);
  if (t) { requestAnimationFrame(() => { t.fit.fit(); t.term.focus(); }); document.title = t.title; }
}
function closeTab(id) {
  const t = tabs.get(id);
  if (!t) return;
  call("closeTab", { id });
  removeTab(id);
}
function removeTab(id) {
  const t = tabs.get(id);
  if (!t) return;
  t.term.dispose(); t.pane.remove(); t.tab.remove(); tabs.delete(id);
  if (!tabs.size) { call("close"); return; }
  if (active === id) select([...tabs.keys()].at(-1));
}

const dec = (b64) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
on("out", ({ id, b64 }) => tabs.get(id)?.term.write(dec(b64)));
on("exit", ({ id }) => {
  const t = tabs.get(id);
  if (!t) return;
  t.term.write("\r\n\x1b[2m[session ended - press any key to close the tab]\x1b[0m");
  const sub = t.term.onKey(() => { sub.dispose(); removeTab(id); });
});
on("theme", () => { for (const t of tabs.values()) t.term.options.theme = termTheme(); });
on("args", (a) => { if (a.run) newTab(a.run, a.title); else newTab(); });
addEventListener("resize", () => { const t = tabs.get(active); t && t.fit.fit(); });
addEventListener("keydown", (e) => {
  if (e.ctrlKey && e.key === "Tab") { e.preventDefault(); const ids = [...tabs.keys()]; select(ids[(ids.indexOf(active) + (e.shiftKey ? ids.length - 1 : 1)) % ids.length]); }
});
// live tab titles: the running program (e.g. "nmap") or the folder
setInterval(async () => {
  for (const [id, t] of tabs) {
    if (t.fixed) continue;
    const name = await call("title", { id });
    if (name && name !== t.title) { t.title = name; t.tab.querySelector(".tt").textContent = name; if (id === active) document.title = name; }
  }
}, 1000);

await newTab(args.get("run"), args.get("title"));
