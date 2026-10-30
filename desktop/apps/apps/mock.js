// Preview-only stand-in for backend.py (plain browser).
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const I = (n) => `/shell/ui/preview/icons/${n}.svg`;
const T = [
  ["nmap", "nmap", "Network exploration tool and security / port scanner", "kali-nmap", ["Reconnaissance", "Discovery"], 1],
  ["metasploit-framework", "Metasploit", "Framework for exploit development and vulnerability research", "kali-metasploit-framework", ["Initial Access", "Execution"], 1],
  ["burpsuite", "Burp Suite", "Platform for security testing of web applications", "kali-burpsuite", ["Reconnaissance", "Initial Access"], 1],
  ["wireshark", "Wireshark", "Network traffic analyzer", "kali-wireshark", ["Discovery", "Collection"], 1],
  ["sqlmap", "sqlmap", "Automatic SQL injection tool", "kali-sqlmap", ["Initial Access"], 1],
  ["hydra", "hydra", "Very fast network logon cracker", "kali-hydra", ["Credential Access"], 1],
  ["john", "John the Ripper", "Active password cracking tool", "kali-john", ["Credential Access"], 1],
  ["hashcat", "hashcat", "World's fastest and most advanced password recovery utility", "kali-hashcat", ["Credential Access"], 1],
  ["aircrack-ng", "aircrack-ng", "Wireless WEP/WPA cracking utilities", "kali-aircrack-ng", ["Reconnaissance", "Credential Access"], 1],
  ["maltego", "Maltego", "Open source intelligence and forensics application", "kali-maltego", ["Reconnaissance"], 0],
  ["ghidra", "Ghidra", "Software reverse engineering framework", "kali-ghidra", ["Forensics"], 0],
  ["autopsy", "Autopsy", "Graphical interface to The Sleuth Kit", "kali-autopsy", ["Forensics"], 1],
  ["bettercap", "bettercap", "Swiss army knife for network attacks and monitoring", "kali-bettercap", ["Credential Access", "Collection"], 1],
  ["responder", "Responder", "LLMNR/NBT-NS/mDNS poisoner", "kali-responder", ["Credential Access"], 1],
  ["nikto", "nikto", "Web server security scanner", "kali-nikto", ["Reconnaissance"], 1],
  ["zaproxy", "ZAP", "Testing tool for finding vulnerabilities in web applications", "kali-zaproxy", ["Reconnaissance"], 0],
  ["recon-ng", "recon-ng", "Web Reconnaissance framework written in Python", "kali-recon-ng", ["Reconnaissance"], 1],
  ["amass", "amass", "In-depth subdomain enumeration", "kali-amass", ["Reconnaissance"], 1],
  ["wifite", "wifite", "Automated wireless attack tool", "kali-wifite", ["Credential Access"], 1],
  ["kismet", "kismet", "Wireless sniffer and monitor", "kali-kismet", ["Reconnaissance"], 0],
  ["radare2", "radare2", "Reverse engineering framework", "kali-radare2", ["Forensics"], 1],
  ["binwalk", "binwalk", "Tool for searching binary images for embedded files", "kali-binwalk", ["Forensics"], 1],
  ["volatility3", "Volatility 3", "Memory forensics framework", "kali-volatility", ["Forensics"], 0],
  ["exploitdb", "SearchSploit", "Command line search tool for Exploit-DB", "kali-searchsploit", ["Initial Access"], 1],
  ["beef-xss", "BeEF", "Browser Exploitation Framework", "kali-beef-xss-start", ["Initial Access"], 0],
  ["ffuf", "ffuf", "Fast web fuzzer written in Go", "kali-ffuf", ["Reconnaissance"], 1],
  ["lynis", "lynis", "Security auditing tool for Unix based systems", "kali-lynis", ["Discovery"], 1],
  ["gvm", "Greenbone (OpenVAS)", "Vulnerability scanning and management", "kali-openvas", ["Reconnaissance"], 0],
];
const tools = T.map(([pkg, name, comment, ic, cats, inst]) => ({ pkg, name, comment, icon: I(ic), cats, installed: !!inst, desktop: "kali-" + pkg, terminal: !/burp|wireshark|maltego|ghidra|zap|autopsy/i.test(name) }));
let authed = false;
export default {
  auth: ({ check }) => { if (check) return { ok: authed }; authed = true; return { ok: true }; },
  catalog: () => ({ tools: tools.map((t) => ({ ...t })), categories: ["Reconnaissance", "Initial Access", "Execution", "Credential Access", "Discovery", "Collection", "Forensics"] }),
  search: ({ q }) => ({ results: [{ pkg: q + "-utils", name: q + "-utils", comment: "Extra utilities (example result from the Kali archive)", installed: false }] }),
  details: ({ pkg }) => ({ version: "1.0.0-1kali1", "installed-size": 48211, summary: tools.find((t) => t.pkg === pkg)?.comment,
    description: "This is the package description from the Kali archive. It explains what the tool does and how it fits into a security assessment.\n\nIt is shown here exactly as the package maintainers wrote it." }),
  async install(_, emit) { for (let p = 0; p <= 100; p += 4) { await sleep(70); emit("job", { kind: "install", pct: p, text: "" }); } emit("job", { kind: "install", done: true, ok: true }); return { ok: true }; },
  async remove(_, emit) { await sleep(900); emit("job", { kind: "remove", done: true, ok: true }); return { ok: true }; },
  launch: () => ({ ok: true }), openSettings: () => ({ ok: true }),
};
