"""A fake local app for the process-tree probes (tests/local_run_probe.py).

Binds a stdlib HTTP server on 127.0.0.1:<port>, spawns one sleeping grandchild,
and writes its own pid and the grandchild's into --pid-dir (app.txt,
grandchild.txt) once both exist -- so a reader that sees the files knows the
port is already bound. That is the shape local_run has to clean up: a program
that left a descendant behind.

Everything is bounded by --lifetime so a probe that fails to clean up cannot
leave a process running for more than a few minutes.
"""
import argparse
import http.server
import os
import subprocess
import sys
import threading


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def _write(path, text):
    # Rename into place so a reader never sees a half-written pid.
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--pid-dir", required=True)
    ap.add_argument("--lifetime", type=int, default=300)
    args = ap.parse_args(argv)

    server = http.server.HTTPServer(("127.0.0.1", args.port), _Handler)
    grandchild = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(%d)" % args.lifetime])
    _write(os.path.join(args.pid_dir, "grandchild.txt"), str(grandchild.pid))
    _write(os.path.join(args.pid_dir, "app.txt"), str(os.getpid()))
    threading.Timer(args.lifetime, lambda: os._exit(0)).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
