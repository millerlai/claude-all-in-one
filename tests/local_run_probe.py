"""Probe driver for local_run's process-tree mechanics (unit 1, P1-P6).

  python tests/local_run_probe.py --pid-dir DIR --sleep 60 [--mode wait|stop|env]

Starts tests/fake_app.py through local_run.start_tree, writes port.txt next to
the app's pid files in DIR, then:
  wait (default)  sleeps --sleep seconds waiting to be ended from outside
                  (P2, P3, P5), then stops the tree and exits
  stop            stops the tree normally and exits (P1)
  env             only prints whether BASH_DEFAULT_TIMEOUT_MS and
                  BASH_MAX_TIMEOUT_MS are in the environment (P6)

It installs the same safety nets the real runner will: J0 on Windows, the
SIGTERM/SIGINT/SIGHUP handlers on POSIX.
"""
import argparse
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "plugins", "cai", "scripts"))

import local_run  # noqa: E402

READY_WAIT = 30  # seconds to wait for the fake app's pid files


def _env_report():
    for name in ("BASH_DEFAULT_TIMEOUT_MS", "BASH_MAX_TIMEOUT_MS"):
        print("%s %s" % (name, "set=" + os.environ[name] if name in os.environ
                         else "not in environment"), flush=True)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid-dir", required=True)
    ap.add_argument("--sleep", type=float, default=60)
    ap.add_argument("--mode", choices=("wait", "stop", "env"), default="wait")
    args = ap.parse_args(argv)

    _env_report()
    if args.mode == "env":
        return 0

    try:
        local_run.install_safety_net()
    except OSError as e:
        print("safety net not installed: %s" % e, flush=True)
        return 2
    print("J0 installed" if sys.platform == "win32" else "signal handlers installed",
          flush=True)

    port = local_run.free_port()
    with open(os.path.join(args.pid_dir, "port.txt"), "w") as f:
        f.write(str(port))
    tree = local_run.start_tree(
        [sys.executable, os.path.join(HERE, "fake_app.py"), "--port", str(port),
         "--pid-dir", args.pid_dir],
        cwd=args.pid_dir, out_path=os.path.join(args.pid_dir, "app.log"))

    end = time.monotonic() + READY_WAIT
    names = ("app.txt", "grandchild.txt")
    while time.monotonic() < end and not all(
            os.path.exists(os.path.join(args.pid_dir, n)) for n in names):
        time.sleep(0.1)
    print("READY port=%d" % port, flush=True)

    if args.mode == "wait":
        time.sleep(args.sleep)
    left = local_run.stop_tree(tree)
    print("stopped; alive=%s survivors=%s" % (left, local_run.survivors()), flush=True)
    return 0 if not left else local_run.EXIT_TREE_LEFT


if __name__ == "__main__":
    sys.exit(main())
