// Wraith App Manager - Kali's toolbox: browse, search, install, remove, open.
import { call, on, initTheme, h, icon, appIcon, dialog, askAdmin, snack, windowFrame, IN_OS, useMock } from "../common/app.js";

if (!IN_OS) useMock((await import("./mock.js")).default);
await initTheme();

const { content } = windowFrame("App Manager");
const nav = h("nav.nav"), main = h("main.content");
content.append(nav, main);

let cat = { tools: [], categories: [] };
let view = "discover", chip = "All", query = "", job = null;   // job: {pkg, kind, pct}
const NAV = [["discover", "Discover", "explore"], ["installed", "Installed", "inventory_2"], ["updates", "Updates", "system_update"]];
for (const [id, label, ic] of NAV)
  nav.append(h("button", { "data-v": id, onclick: () => go(id) }, icon(ic), h("span", label), id === "installed" ? h("span.badge.inst", "") : null));

function go(v) {
  if (v === "updates") { call("openSettings"); if (!IN_OS) snack("Opens Settings › System update"); return; }
  view = v; render();
}

async function load() {
  cat = await call("catalog");
  render();
}

function button(t) {
  if (job && job.pkg === t.pkg)
    return h("div.busy", h("span.ring", { style: { "--p": (job.pct || 0) / 100 } }), job.kind === "remove" ? "Removing…" : `Installing ${Math.round(job.pct || 0)}%`);
  if (t.installed) return [
    t.desktop ? h("button.btn.tonal", { onclick: (e) => { e.stopPropagation(); call("launch", { desktop: t.desktop }); } }, "Open") : null,
    h("button.btn.text", { onclick: (e) => { e.stopPropagation(); remove(t); } }, "Remove")];
  return h("button.btn", { onclick: (e) => { e.stopPropagation(); install(t); } }, icon("download"), "Install");
}

function card(t, i) {
  return h("div.acard", { style: { animationDelay: Math.min(i, 30) * 18 + "ms" }, onclick: () => details(t) },
    appIcon(t.icon, 56, t.terminal ? "terminal" : "apps"),
    h("div.meta", h("b", t.name), h("span", t.comment || t.pkg)),
    h("div.act", button(t)));
}

function render() {
  for (const b of nav.children) b.classList.toggle("on", b.dataset.v === view);
  const instCount = cat.tools.filter((t) => t.installed).length;
  nav.querySelector(".inst").textContent = instCount;
  const page = h("div.page", { style: { maxWidth: "1100px" } });
  const input = h("input", { placeholder: "Search tools and apps", value: query });
  input.oninput = () => { query = input.value; clearTimeout(input._t); input._t = setTimeout(render, 160); };
  page.append(h("div.searchbar", icon("search"), input));
  if (view === "discover" && !query) {
    page.append(h("div.banner", h("b", "Kali's toolbox"), h("span", "Every Kali tool, sorted the way attackers work. Installs and updates go through Tor."),
      h("div.stats", h("div", h("b", cat.tools.length), " tools"), h("div", h("b", instCount), " installed"), h("div", h("b", cat.categories.length), " categories"))));
    page.append(h("div.chips", ["All", ...cat.categories].map((c) => h("button.chip" + (c === chip ? ".on" : ""), { onclick: () => { chip = c; render(); } }, c))));
  }
  const list = h("div.list");
  page.append(list);
  main.replaceChildren(page);
  renderList(list);
  if (!query) input.blur(); else { input.focus(); input.setSelectionRange(query.length, query.length); }
}

async function renderList(list = main.querySelector(".list")) {
  const q = query.trim().toLowerCase();
  let tools = cat.tools;
  if (view === "installed") tools = tools.filter((t) => t.installed);
  if (view === "discover" && chip !== "All" && !q) tools = tools.filter((t) => t.cats.includes(chip));
  if (q) tools = tools.filter((t) => (t.name + " " + t.pkg + " " + t.comment).toLowerCase().includes(q));
  list.replaceChildren();
  if (q) list.append(h("div.section-title", `Kali tools matching “${query}”`));
  list.append(tools.length ? h("div.cards", tools.slice(0, 240).map(card)) : h("div.empty", icon("search_off"), h("div", "No Kali tools match")));
  if (q.length >= 2 && view === "discover") {
    const other = h("div");
    list.append(other);
    const r = await call("search", { q });
    if (query.trim().toLowerCase() !== q) return;     // typed on
    const known = new Set(cat.tools.map((t) => t.pkg));
    const extra = (r?.results ?? []).filter((x) => !known.has(x.pkg));
    if (extra.length) other.append(h("div.section-title", "Other packages"), h("div.cards", extra.map(card)));
  }
}

async function details(t) {
  const info = await call("details", { pkg: t.pkg }) ?? {};
  const close = () => scrim.remove();
  const acts = h("div.acts",
    h("button.btn.text", { onclick: close }, "Close"),
    t.installed ? h("button.btn.text", { onclick: () => { close(); remove(t); } }, "Remove") : null,
    t.installed && t.desktop ? h("button.btn", { onclick: () => { close(); call("launch", { desktop: t.desktop }); } }, icon("open_in_new"), "Open")
      : !t.installed ? h("button.btn", { onclick: () => { close(); install(t); } }, icon("download"), "Install") : null);
  const dlg = h("div.dialog.wide",
    h("div.detail", appIcon(t.icon, 96, t.terminal ? "terminal" : "apps"), h("div", h("b", t.name), h("div.muted", info.summary || t.comment))),
    h("div.facts", info.version && h("span", "Version " + info.version), info["installed-size"] && h("span", Math.round(info["installed-size"] / 1024) + " MB"),
      t.cats?.length && h("span", t.cats.join(" · ")), h("span", "Package: " + t.pkg)),
    info.description && h("div.desc", info.description), acts);
  const scrim = h("div.scrim", { onclick: (e) => e.target === scrim && close() }, dlg);
  document.body.append(scrim);
}

async function install(t) {
  if (job) return snack("Wait for the current install to finish");
  if (!(await askAdmin(`Installing ${t.name} needs the admin password.`))) return;
  job = { pkg: t.pkg, kind: "install", pct: 0 };
  render();
  const r = await call("install", { pkgs: [t.pkg] });
  if (r?.ok === false) { job = null; snack(r.error || "Couldn't start"); render(); }
}
async function remove(t) {
  const ok = await dialog({ icon: "delete", title: `Remove ${t.name}?`, text: "You can install it again any time.", actions: [["Cancel", false], ["Remove", true, "danger"]] });
  if (!ok || !(await askAdmin(`Removing ${t.name} needs the admin password.`))) return;
  job = { pkg: t.pkg, kind: "remove", pct: 0 };
  render();
  const r = await call("remove", { pkgs: [t.pkg] });
  if (r?.ok === false) { job = null; snack(r.error || "Couldn't start"); render(); }
}
on("job", (j) => {
  if (!job) return;
  if (j.done) {
    const t = cat.tools.find((x) => x.pkg === job.pkg);
    if (j.ok && t) t.installed = job.kind === "install";
    snack(j.ok ? `${t?.name ?? job.pkg} ${job.kind === "install" ? "installed" : "removed"}` : (j.errors?.at(-1) || "That didn't work"));
    job = null; render(); return;
  }
  job.pct = j.pct;
  const ring = main.querySelector(".ring");
  if (ring) { ring.style.setProperty("--p", j.pct / 100); ring.parentElement.lastChild.textContent = job.kind === "remove" ? "Removing…" : `Installing ${Math.round(j.pct)}%`; }
});

load();
