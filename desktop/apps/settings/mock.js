// Preview-only stand-in for backend.py (used when the page runs in a plain browser).
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PK = [["nmap", "7.95+dfsg-1", "7.95+dfsg-2"], ["metasploit-framework", "6.4.40-0kali1", "6.4.52-0kali1"], ["burpsuite", "2026.9.2", "2026.10.1"],
  ["linux-image-amd64", "7.1.5-1kali1", "7.2.1-1kali1"], ["sqlmap", "1.9.8-1", "1.9.10-1"], ["wireshark", "4.4.9-1", "4.4.10-1"], ["hashcat", "7.1.2-1", "7.1.3-1"],
  ["tor", "0.4.9.3-1", "0.4.9.4-1"], ["torbrowser-launcher", "0.3.7-3", "0.3.8-1"], ["apparmor", "4.1.2-1", "4.1.3-1"], ["nftables", "1.1.5-1", "1.1.6-1"]];
const privGroup = (n) => (/^(tor|torbrowser-launcher|apparmor|nftables)$/.test(n) ? "Tor & privacy" : "Kali tools & system");
let wifiOn = true, connected = "Home-5G", authed = false;
const look = { dark: true, source: "#6a5ff0" };
export default {
  auth: ({ check }) => { if (check) return { ok: authed }; authed = true; return { ok: true }; },
  async checkUpdates(_, emit) {
    for (let p = 0; p <= 100; p += 5) { await sleep(70); emit("job", { kind: "refresh", pct: p, text: `Checking: kali-rolling ${p < 60 ? "InRelease" : "Packages"}` }); }
    emit("updates", { ok: true, live: true, download: "412 MB", restart: true, packages: PK.map(([name, from, to]) => ({ name, from, to, group: privGroup(name) })) });
  },
  async applyUpdates(_, emit) {
    for (let p = 0; p <= 100; p += 2) { await sleep(60); emit("job", { kind: "upgrade", pct: p, text: p < 50 ? `Downloading: ${PK[Math.floor(p / 5) % PK.length][0]}` : `Installing: ${PK[Math.floor(p / 4) % PK.length][0]}` }); }
    emit("job", { kind: "upgrade", done: true, ok: true, errors: [] });
  },
  wifi: () => ({ available: true, enabled: wifiOn, networks: !wifiOn ? [] : [
    { ssid: "Home-5G", signal: 92, secure: true, saved: true }, { ssid: "Cafe Lumière", signal: 71, secure: false },
    { ssid: "TELUS-4821", signal: 58, secure: true }, { ssid: "Bell_3F9A", signal: 33, secure: true }, { ssid: "DIRECT-HP-Printer", signal: 22, secure: true }]
    .map((n) => ({ ...n, connected: n.ssid === connected, saved: n.saved || n.ssid === connected }))
    .sort((a, b) => b.connected - a.connected) }),
  wifiRadio: ({ on }) => { wifiOn = on; return { ok: true }; },
  async wifiConnect({ ssid }) { await sleep(900); connected = ssid; return { ok: true }; },
  wifiForget: () => ({ ok: true }),
  privacy: () => ({ tor: true, live: true, torBootstrap: 100, mac: true, usbguard: true }),
  setPrivacy: ({ key }) => (key === "tor" ? { ok: false, error: "Always on in Wraith Live" } : { ok: true }),
  theme: () => ({ ...look }),
  appearance: () => ({ ...look }),
  setAppearance: (a, emit) => { Object.assign(look, a); emit("theme", { ...look }); return { ok: true }; },
  levels: () => ({ volume: 55, brightness: 70, scale: 1 }),
  setLevel: () => ({ ok: true }), setScale: () => ({ ok: true }),
  changePassword: ({ new: n }) => (n.length < 8 ? { ok: false, error: "Use at least 8 characters" } : { ok: true }),
  about: () => ({ version: "1.0", mode: "Wraith Live", kernel: "7.1.5+kali-amd64", base: "Kali rolling", cpu: "AMD Ryzen 7 7840HS w/ Radeon 780M Graphics",
    memory: 32 * 1024 ** 3, gpu: "Advanced Micro Devices [AMD/ATI] Phoenix3", hostname: "wraith", disk: { total: 512e9, free: 401e9 } }),
};
