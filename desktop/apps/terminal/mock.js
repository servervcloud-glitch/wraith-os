// Preview-only fake shell (plain browser): echoes input and answers a few commands.
const enc = (s) => btoa(unescape(encodeURIComponent(s)));
const P = "\x1b[1;38;2;157;151;255mwraith\x1b[0m\x1b[2m@\x1b[0m\x1b[38;2;111;211;255mwraith\x1b[0m \x1b[1;38;2;255;143;184m~\x1b[0m \x1b[38;2;255;194;122m❯\x1b[0m ";
const OUT = {
  "nmap -sV scanme.nmap.org": "Starting Nmap 7.95 ( https://nmap.org ) at 2026-10-30 14:30 EDT\r\nNmap scan report for scanme.nmap.org (45.33.32.156)\r\nHost is up (0.21s latency).\r\nNot shown: 996 closed tcp ports (reset)\r\nPORT      STATE SERVICE    VERSION\r\n\x1b[32m22/tcp    open  ssh\x1b[0m        OpenSSH 6.6.1p1 Ubuntu 2ubuntu2.13\r\n\x1b[32m80/tcp    open  http\x1b[0m       Apache httpd 2.4.7 ((Ubuntu))\r\n\x1b[32m9929/tcp  open  nping-echo\x1b[0m Nping echo\r\n\x1b[32m31337/tcp open  tcpwrapped\x1b[0m\r\nService Info: OS: Linux; CPE: cpe:/o:linux:linux_kernel\r\n\r\nNmap done: 1 IP address (1 host up) scanned in 24.81 seconds\r\n",
  "sudo wraith-tor status": "\x1b[1;32m●\x1b[0m Tor-only mode: \x1b[1mon\x1b[0m  (all traffic goes through Tor)\r\n",
  "curl -s https://check.torproject.org/api/ip": '{"IsTor":true,"IP":"185.220.101.47"}\r\n',
  "ls": "\x1b[1;34mDesktop\x1b[0m  \x1b[1;34mDocuments\x1b[0m  \x1b[1;34mDownloads\x1b[0m  \x1b[1;34mloot\x1b[0m  \x1b[1;34mscans\x1b[0m  notes.md\r\n",
};
const tabs = {};
let n = 0;
export default {
  open(a, emit) {
    const id = ++n; tabs[id] = "";
    setTimeout(() => emit("out", { id, b64: enc((a.run ? `$ ${a.run}\r\n` : "") + P) }), 50);
    return { id };
  },
  write({ id, data }, emit) {
    let out = "";
    for (const ch of data) {
      if (ch === "\r") { const cmd = tabs[id].trim(); tabs[id] = ""; out += "\r\n" + (OUT[cmd] ?? (cmd ? `${cmd.split(" ")[0]}: done\r\n` : "")) + P; }
      else if (ch === "\x7f") { if (tabs[id]) { tabs[id] = tabs[id].slice(0, -1); out += "\b \b"; } }
      else { tabs[id] += ch; out += ch; }
    }
    emit("out", { id, b64: enc(out) });
    return true;
  },
  resize: () => true, closeTab: () => true, copy: () => true, paste: () => "",
  title: ({ id }) => (tabs[id]?.startsWith("nmap") ? "nmap" : "~"),
};
