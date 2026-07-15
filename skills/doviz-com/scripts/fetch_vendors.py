#!/usr/bin/env python3
"""Fetch per-vendor (bank / exchange-office) prices for a doviz.com item.

Each currency and gold product on doviz.com is quoted by many vendors (banks &
exchange offices), each with its own Alış (bid) / Satış (ask). doviz.com serves
that whole per-instrument vendor list as JSON, keyed by the bare item code:

    GET https://api.doviz.com/api/v12/assets/<CODE>   ->  data.other_sources[]

So one request returns every vendor for an item, and both "one vendor" and "all
vendors" come from the same call. The item's type (currency vs gold) is detected
automatically. "Serbest Piyasa" is the market reference, not a vendor, so it is
not listed here (use fetch_history.py without --vendor for that series).

Examples
--------
    python fetch_vendors.py CAD                  # all vendors for CAD/TRY
    python fetch_vendors.py CAD --vendor Akbank  # just Akbank
    python fetch_vendors.py CAD --best           # cheapest ask
    python fetch_vendors.py gram-altin           # gold vendor table (type auto-detected)
    python fetch_vendors.py USD --live           # snapshot, then live socket stream
    python fetch_vendors.py --list vendors USD   # id -> name for one instrument

Auth (a static Bearer token) is handled automatically by doviz_token.py.
The snapshot path uses only the stdlib; `--live` additionally needs
'websocket-client' (see scripts/requirements.txt).
"""
import argparse
import json
import os
import sys

# doviz.com content is Turkish; force UTF-8 so Windows consoles don't choke.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doviz_assets  # noqa: E402


def stream_live(keys, id2name, duration=30):
    """Join the socket with the parsed vendor keys and print live ticks.

    Runs for `duration` seconds then exits cleanly (0 = until Ctrl-C / the server
    hangs up). Illiquid items simply tick rarely — a quiet socket is normal, not
    an error, so read timeouts are swallowed rather than raised.
    """
    try:
        from websocket import (create_connection, WebSocketTimeoutException,
                               WebSocketConnectionClosedException)
    except ImportError:
        sys.exit("--live needs the 'websocket-client' package; "
                 "see scripts/requirements.txt for the install command, then retry.")
    import random
    import time
    nick = "webkullanici_%d" % random.randint(0, 999)
    room = "info@" + ",".join(keys) + "/" + nick
    ws = create_connection("wss://socket.doviz.com",
                           subprotocols=["nokta-chat-json"], timeout=15)
    # The custom protocol needs compact JSON (no spaces), like the site's JS.
    ws.send(json.dumps({"action": "auth",
                        "data": {"username": "", "password": "", "joinTo": room}},
                       separators=(",", ":")))
    ws.settimeout(3)  # short poll so we can honor `duration` between ticks
    deadline = time.time() + duration if duration else None
    ticks = 0
    sys.stderr.write("streaming %d vendor keys for %s (Ctrl-C to stop)...\n"
                     % (len(keys), ("%ds" % duration) if duration else "ever"))
    try:
        while deadline is None or time.time() < deadline:
            try:
                raw = ws.recv()
            except WebSocketTimeoutException:
                continue  # no tick in this interval — keep waiting, not an error
            except WebSocketConnectionClosedException:
                break     # server hung up
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                continue
            if msg.get("a") != "m":
                continue
            m = msg["m"]
            vid = str(m["k"]).split("-", 1)[0]
            ticks += 1
            print("%-16s bid=%s ask=%s @%s" %
                  (id2name.get(vid, vid), m.get("bid"), m.get("ask"), m.get("ts")))
    except KeyboardInterrupt:
        pass
    finally:
        try:
            ws.close()
        except Exception:
            pass
    sys.stderr.write("stream ended (%d ticks)\n" % ticks)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("item", nargs="?",
                    help="ISO code (CAD) or gold key (gram-altin)")
    ap.add_argument("--gold", action="store_true",
                    help="accepted for compatibility; the type is auto-detected")
    ap.add_argument("--vendor", help="filter to one vendor (case-insensitive substring)")
    ap.add_argument("--vendor-id", type=int,
                    help="filter to one vendor by numeric id (see --list vendors <item>)")
    ap.add_argument("--best", action="store_true", help="print only the lowest-ask vendor")
    ap.add_argument("--live", action="store_true", help="stream live updates after snapshot")
    ap.add_argument("--live-seconds", type=int, default=30,
                    help="how long --live streams before exiting (0 = until Ctrl-C)")
    ap.add_argument("--list", choices=["currencies", "gold", "vendors"],
                    help="list what can be queried, then exit (vendors needs an item)")
    args = ap.parse_args()

    if args.list:
        if args.list == "currencies":
            print(json.dumps(doviz_assets.CURRENCIES, ensure_ascii=False, indent=2))
        elif args.list == "gold":
            print(json.dumps(sorted(doviz_assets.GOLD_KEYS), ensure_ascii=False, indent=2))
        else:  # vendors — per instrument, so it needs the item
            if not args.item:
                ap.error("--list vendors needs an item, e.g. --list vendors USD")
            data = doviz_assets.get_asset(args.item)
            print(json.dumps(doviz_assets.vendor_map(data), ensure_ascii=False, indent=2))
        return

    if not args.item:
        ap.error("item is required (or use --list)")

    data = doviz_assets.get_asset(args.item)
    rows = doviz_assets.vendors(data)
    if not rows:
        sys.exit("No vendor prices for %s (it may be quoted only as Serbest "
                 "Piyasa; use fetch_history.py without --vendor for that series)"
                 % args.item)

    if args.vendor_id is not None:
        rows = [r for r in rows if r["vendor_id"] == args.vendor_id]
        if not rows:
            sys.exit("No vendor with id %d for %s (see --list vendors %s)"
                     % (args.vendor_id, args.item, args.item))
    elif args.vendor:
        needle = args.vendor.lower()
        rows = [r for r in rows if needle in r["vendor"].lower()]
        if not rows:
            sys.exit("No vendor matching %r for %s (see --list vendors %s)"
                     % (args.vendor, args.item, args.item))

    rows.sort(key=lambda r: r["ask"])
    if args.best:
        rows = rows[:1]

    print(json.dumps(rows, ensure_ascii=False, indent=2))

    if args.live:
        stream_live(["%d-%s" % (r["vendor_id"], r["item"]) for r in rows],
                    doviz_assets.vendor_map(data), duration=args.live_seconds)


if __name__ == "__main__":
    main()
