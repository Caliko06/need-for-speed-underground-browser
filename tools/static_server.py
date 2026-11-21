#!/usr/bin/env python3
"""Plain static server for dist/: files, Range, COOP/COEP/CORP headers, nothing else (no /log, /save, /plan). Test stand-in for a real host.
Usage: python3 tools/static_server.py [port=5181] [dir=dist]
RN_RTT_MS=80: every answer waits that long first, the round trip of a real visit (live 2026-11-16: 75 ms a request; localhost hides it).
RN_MBIT=50: one shared 50 Mbit/s transfer budget for all requests and workers."""
import functools, http.server, io, os, re, sys, time, threading

RTT = float(os.environ.get("RN_RTT_MS", 0)) / 1000
RATE = float(os.environ.get("RN_MBIT", 0)) * 1e6 / 8
rate_lock = threading.Lock()
rate_next = 0

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5181
DIR = os.path.abspath(sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist"))


class H(http.server.SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".wasm": "application/wasm", ".js": "text/javascript"}

    def end_headers(self):
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        super().end_headers()

    def do_GET(self):
        path = self.translate_path(self.path)
        if RTT:
            time.sleep(RTT)
        if path.endswith('.br') and '/data-chunks/' in path and os.path.isfile(path):
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Encoding", "br")
            self.send_header("Content-Length", str(os.path.getsize(path)))
            self.end_headers()
            with open(path, 'rb') as f:
                self.copyfile(f, self.wfile)
            return
        m = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
        if m and os.path.isfile(path):
            size = os.path.getsize(path)
            a, b = int(m[1]), min(int(m[2]) if m[2] else size - 1, size - 1)
            if a >= size or b < a:
                self.send_response(416); self.send_header("Content-Range", f"bytes */{size}"); self.send_header("Content-Length", "0"); self.end_headers()
                return
            with open(path, "rb") as f:
                f.seek(a); body = f.read(b - a + 1)
            self.send_response(206)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.copyfile(io.BytesIO(body), self.wfile)
            return
        super().do_GET()

    def copyfile(self, source, outputfile):
        global rate_next
        while body := source.read(64 << 10):
            if RATE:
                with rate_lock:
                    rate_next = max(time.monotonic(), rate_next) + len(body) / RATE
                    delay = rate_next - time.monotonic()
                time.sleep(max(0, delay))
            outputfile.write(body)

    def log_message(self, *a):
        pass


http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(H, directory=DIR)).serve_forever()
