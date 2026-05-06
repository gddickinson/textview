"""Tiny TCP client for the TextView control server.

Usage:
    python tools/control_client.py --port 4242 state
    python tools/control_client.py --port 4242 open_file --path /tmp/x.md
    python tools/control_client.py --port 4242 set_text --text 'hello'
    python tools/control_client.py --port 4242 trigger_action --name action_save
    python tools/control_client.py --port 4242 eval --code 'w.viewer.mode()'

As a Python module:
    from tools.control_client import Client
    c = Client(port=4242)
    print(c.call("state"))
    c.call("open_file", path="/tmp/x.md")
"""
from __future__ import annotations
import argparse, json, socket, sys


class Client:
    def __init__(self, host: str = "127.0.0.1", port: int = 4242, timeout: float = 5.0):
        self._sock = socket.create_connection((host, port), timeout=timeout)
        self._buf = b""

    def close(self):
        try: self._sock.close()
        except Exception: pass

    def __enter__(self): return self
    def __exit__(self, *a): self.close()

    def call(self, op: str, **args) -> dict:
        msg = json.dumps({"op": op, "args": args}).encode("utf-8") + b"\n"
        self._sock.sendall(msg)
        while b"\n" not in self._buf:
            chunk = self._sock.recv(65536)
            if not chunk: raise ConnectionError("server closed")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return json.loads(line.decode("utf-8"))


def _main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=4242)
    p.add_argument("op", help="operation name (e.g. state, open_file)")
    args, extras = p.parse_known_args()
    kw = {}
    it = iter(extras)
    for token in it:
        if not token.startswith("--"):
            print(f"Expected --key, got {token!r}", file=sys.stderr); return 2
        key = token[2:].replace("-", "_")
        try: val = next(it)
        except StopIteration:
            print(f"Missing value for --{key}", file=sys.stderr); return 2
        # Coerce a few common types.
        if val.lower() in ("true", "false"): val = (val.lower() == "true")
        elif val.lstrip("-").isdigit(): val = int(val)
        kw[key] = val
    with Client(host=args.host, port=args.port) as c:
        reply = c.call(args.op, **kw)
    print(json.dumps(reply, indent=2, default=str))
    return 0 if reply.get("ok") else 1


if __name__ == "__main__":
    sys.exit(_main())
