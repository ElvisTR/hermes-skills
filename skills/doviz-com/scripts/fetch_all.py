#!/usr/bin/env python3
"""One-shot snapshot of the whole doviz.com market (Serbest Piyasa).

This is the "market summary" counterpart to fetch_vendors.py: instead of every
vendor for one item, it returns the single reference price for *every* item both
sites expose (all currencies + all gold/metal products + the index/crypto/
commodity ticker widgets).

How it works (exactly what the site does):
  1. GET both landing pages and collect every unique `data-socket-key` — this is
     the full catalog, discovered from an HTML attribute (no number parsing).
  2. Open one WebSocket to wss://socket.doviz.com (subprotocol nokta-chat-json),
     join a room with all those keys. On join the server pushes a current tick
     for every key. Collect one per key, then close.

Verified: ~85 keys, full snapshot in a few seconds. Needs `websocket-client`.

    python fetch_all.py                 # everything
    python fetch_all.py --currencies    # type == currency only
    python fetch_all.py --gold          # type == gold only
    python fetch_all.py --timeout 12
"""
import argparse
import json
import os
import random
import re
import sys
import urllib.request
from datetime import datetime, timezone

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

PAGES = ("https://kur.doviz.com/", "https://altin.doviz.com/")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HERE = os.path.dirname(os.path.abspath(__file__))
_KEY = re.compile(r'data-socket-key="([^"]+)"')
_TYPE = {"C": "currency", "G": "gold"}


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", "replace")


def discover_keys():
    # The two landing pages carry only summary items (no per-vendor "1-CAD"
    # rows — those live on per-item detail pages), so every key here is a
    # market item, including gold products whose slug starts with a number
    # (14-ayar-altin, 18-ayar-altin, 22-ayar-bilezik).
    keys = set()
    for url in PAGES:
        for k in _KEY.findall(http_get(url)):
            if k:
                keys.add(k)
    return sorted(keys)


def snapshot(keys, timeout):
    from websocket import create_connection
    nick = "webkullanici_%d" % random.randint(0, 999)
    room = "info@" + ",".join(keys) + "/" + nick
    ws = create_connection("wss://socket.doviz.com",
                           subprotocols=["nokta-chat-json"], timeout=timeout)
    # The custom protocol needs compact JSON (no spaces), like the site's JS.
    ws.send(json.dumps({"action": "auth",
                        "data": {"username": "", "password": "", "joinTo": room}},
                       separators=(",", ":")))
    ws.settimeout(timeout)
    wanted, got = set(keys), {}
    try:
        while wanted - set(got):
            msg = json.loads(ws.recv())
            if msg.get("a") != "m":
                continue
            m = msg["m"]
            got.setdefault(m["k"], m)
    except Exception:                       # timeout / socket close ends collection
        pass
    finally:
        ws.close()
    return got


def normalize(m):
    ts = m.get("ts")
    return {
        "code": m.get("k"),
        "type": _TYPE.get(m.get("t"), "other"),
        "last": m.get("sn"),
        "bid": m.get("bid"),
        "ask": m.get("ask"),
        "high": m.get("hn"),
        "low": m.get("ln"),
        "change_pct": m.get("cn"),
        "change_amount": m.get("an"),
        "prefix": m.get("p") or "",
        "ts": (datetime.fromtimestamp(ts, timezone.utc).isoformat()
               if isinstance(ts, (int, float)) else None),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--currencies", action="store_true", help="only type == currency")
    ap.add_argument("--gold", action="store_true", help="only type == gold")
    ap.add_argument("--timeout", type=float, default=10.0,
                    help="socket read timeout in seconds (default 10)")
    args = ap.parse_args()

    try:
        from websocket import create_connection  # noqa: F401
    except ImportError:
        sys.exit("fetch_all needs the 'websocket-client' package; "
                 "see requirements.txt for the install command, then retry.")

    keys = discover_keys()
    got = snapshot(keys, args.timeout)
    items = [normalize(got[k]) for k in keys if k in got]

    if args.currencies:
        items = [i for i in items if i["type"] == "currency"]
    if args.gold:
        items = [i for i in items if i["type"] == "gold"]

    missing = [k for k in keys if k not in got]
    if missing:
        sys.stderr.write("warning: %d keys did not return: %s\n"
                         % (len(missing), ", ".join(missing)))
    print(json.dumps(items, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
