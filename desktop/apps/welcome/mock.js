// Preview-only stand-in for backend.py (plain browser).
import settings from "../settings/mock.js";
let boot = null, t0 = 0;
export default {
  ...settings,
  state: () => {
    if (t0) boot = Math.min(100, Math.round((performance.now() - t0) / 60));
    return { live: true, user: "wraith", torBootstrap: boot, needsPassword: true };
  },
  setPassword: ({ password }) => (password.length < 8 ? { ok: false, error: "Use at least 8 characters" } : { ok: true }),
  async wifiConnect(a) { const r = await settings.wifiConnect(a); t0 = performance.now(); return r; },
  finish: () => ({ ok: true }),
};
