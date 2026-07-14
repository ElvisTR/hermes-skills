#!/usr/bin/env python3
"""Fetch per-vendor (bank / exchange-office) prices for a doviz.com item.

Each currency and gold product on doviz.com has a "Banka Kurları" table listing
every vendor that quotes it, with that vendor's own Alış (bid) / Satış (ask).
One HTTP GET returns the whole table, so both "one vendor" and "all vendors"
queries come from the same page. No API key, token, or login required.

Examples
--------
    python fetch_vendors.py CAD                 # all vendors for CAD/TRY
    python fetch_vendors.py CAD --vendor Akbank # just Akbank
    python fetch_vendors.py CAD --best          # cheapest ask
    python fetch_vendors.py gram-altin --gold   # gold vendor table
    python fetch_vendors.py USD --live          # snapshot, then live socket stream
    python fetch_vendors.py --list currencies   # what you can ask for

Default output is a JSON array; the snapshot path uses only the stdlib.
`--live` additionally needs `websocket-client` (see requirements.txt).
"""
import argparse
import json
import os
import re
import sys
import urllib.request

# doviz.com content is Turkish; force UTF-8 so Windows consoles don't choke.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
FX_PAGE = "https://kur.doviz.com/serbest-piyasa/{slug}"
GOLD_PAGE = "https://altin.doviz.com/{key}"
MAIN_FX = "https://kur.doviz.com/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# 19 gold / precious-metal product keys (slug == socket item token).
GOLD_KEYS = {
    "ons", "gram-altin", "gram-has-altin", "ceyrek-altin", "yarim-altin",
    "tam-altin", "cumhuriyet-altini", "ata-altin", "14-ayar-altin",
    "18-ayar-altin", "22-ayar-bilezik", "ikibucuk-altin", "besli-altin",
    "gremse-altin", "resat-altin", "hamit-altin", "gumus", "gram-platin",
    "gram-paladyum",
}


def _load(name):
    try:
        with open(os.path.join(HERE, name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


SLUGS = _load("slugs.json")        # {"CAD": "kanada-dolari", ...}
VENDORS = _load("vendors.json")    # {"1": "Akbank", ...}


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", "replace")


def tr_num(text):
    """Parse a Turkish-locale number ('40.329,81' -> 40329.81)."""
    text = text.strip().replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def refresh_slugs():
    """Rebuild the code->slug map from the live main FX page.

    Pair code<->slug *within each table row* — menus and the header ticker also
    contain `serbest-piyasa/<slug>` links and `data-socket-key` codes, so a
    document-wide regex would misalign them.
    """
    html = http_get(MAIN_FX)
    out = {}
    for row in re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL):
        code = re.search(r'data-socket-key="([A-Z]{3})"', row)
        slug = re.search(r'serbest-piyasa/([a-z0-9-]+)', row)
        if code and slug:
            out.setdefault(code.group(1), slug.group(1))
    return out


def resolve_url(item, force_gold):
    """Map a user-supplied item to (page_url, human_label)."""
    raw = item.strip()
    if force_gold or raw in GOLD_KEYS:
        if raw not in GOLD_KEYS:
            sys.exit("Unknown gold product: %s (see --list gold)" % raw)
        return GOLD_PAGE.format(key=raw), raw
    code = raw.upper()
    if code in SLUGS:                       # ISO code, e.g. CAD
        return FX_PAGE.format(slug=SLUGS[code]), code
    if raw.lower() in SLUGS.values():       # already a slug, e.g. kanada-dolari
        return FX_PAGE.format(slug=raw.lower()), raw.lower()
    sys.exit("Unknown item: %s (try an ISO code like CAD, a gold key like "
             "gram-altin, or see --list)" % raw)


# One vendor row: name inside the <a>, then bid / ask cells keyed <id>-<ITEM>.
_ROW = re.compile(
    r'<tr[^>]*>(?P<row>.*?)</tr>', re.DOTALL)
_NAME = re.compile(r'<a\b[^>]*>(?:\s*<img[^>]*>)?\s*([^<]+?)\s*</a>', re.DOTALL)
_CELL = re.compile(
    r'data-socket-key="(\d+)-([^"]+)"\s+data-socket-attr="(bid|ask)"[^>]*>'
    r'([^<]+)<', re.DOTALL)


def parse_vendors(html):
    """Return [{vendor_id, vendor, item, bid, ask, makas, makas_pct}, ...]."""
    rows = []
    for m in _ROW.finditer(html):
        chunk = m.group("row")
        cells = _CELL.findall(chunk)
        if not cells:
            continue
        vid = cells[0][0]
        item = cells[0][1]
        prices = {attr: tr_num(val) for _id, _it, attr, val in cells}
        bid, ask = prices.get("bid"), prices.get("ask")
        if bid is None or ask is None:
            continue
        name_m = _NAME.search(chunk)
        vendor = (name_m.group(1).strip() if name_m
                  else VENDORS.get(vid, "vendor-%s" % vid))
        makas = round(ask - bid, 6)
        makas_pct = round(makas / bid * 100, 4) if bid else None
        rows.append({
            "vendor_id": int(vid),
            "vendor": vendor,
            "item": item,
            "bid": bid,
            "ask": ask,
            "makas": makas,
            "makas_pct": makas_pct,
        })
    return rows


def stream_live(keys, duration=30):
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
                 "see requirements.txt for the install command, then retry.")
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
    id2name = {k.split("-", 1)[0]: VENDORS.get(k.split("-", 1)[0], k) for k in keys}
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
                    help="ISO code (CAD), FX slug (kanada-dolari), or gold key (gram-altin)")
    ap.add_argument("--gold", action="store_true", help="treat item as a gold product")
    ap.add_argument("--vendor", help="filter to one vendor (case-insensitive substring)")
    ap.add_argument("--vendor-id", type=int,
                    help="filter to one vendor by numeric id (see --list vendors)")
    ap.add_argument("--best", action="store_true", help="print only the lowest-ask vendor")
    ap.add_argument("--live", action="store_true", help="stream live updates after snapshot")
    ap.add_argument("--live-seconds", type=int, default=30,
                    help="how long --live streams before exiting (0 = until Ctrl-C)")
    ap.add_argument("--list", choices=["currencies", "gold", "vendors"],
                    help="list what can be queried, then exit")
    ap.add_argument("--refresh-slugs", action="store_true",
                    help="rewrite slugs.json from the live site, then exit")
    args = ap.parse_args()

    if args.refresh_slugs:
        data = refresh_slugs()
        with open(os.path.join(HERE, "slugs.json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=False)
        print("wrote %d currency slugs" % len(data))
        return
    if args.list:
        if args.list == "currencies":
            out = SLUGS
        elif args.list == "gold":
            out = sorted(GOLD_KEYS)
        else:
            out = VENDORS
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    if not args.item:
        ap.error("item is required (or use --list)")

    url, _label = resolve_url(args.item, args.gold)
    rows = parse_vendors(http_get(url))
    if not rows:
        sys.exit("No vendor table found at %s" % url)

    if args.vendor_id is not None:
        rows = [r for r in rows if r["vendor_id"] == args.vendor_id]
        if not rows:
            sys.exit("No vendor with id %d for this item" % args.vendor_id)
    elif args.vendor:
        needle = args.vendor.lower()
        rows = [r for r in rows if needle in r["vendor"].lower()]
        if not rows:
            sys.exit("No vendor matching %r for this item" % args.vendor)

    rows.sort(key=lambda r: r["ask"])
    if args.best:
        rows = rows[:1]

    print(json.dumps(rows, ensure_ascii=False, indent=2))

    if args.live:
        stream_live(["%d-%s" % (r["vendor_id"], r["item"]) for r in rows],
                    duration=args.live_seconds)


if __name__ == "__main__":
    main()
