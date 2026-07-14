#!/usr/bin/env python3
"""Historical (daily) price for a doviz.com item + vendor.

doviz.com detail pages draw their chart from a JSON archive API:

    GET https://api.doviz.com/api/v12/assets/<vendorId>-<CODE>/archive
        ?start=<epoch>&end=<epoch>

The asset key is the same `<vendorId>-<ITEM>` used by the vendor tables
(`1-USD`=Akbank USD, `1-gram-altin`=Akbank gram altın). It returns one point per
day; each point's `close` is that day's price (`update_date` is 00:00 Istanbul).

Examples
--------
    python fetch_history.py USD --vendor Akbank --date 2020-03-16
    python fetch_history.py USD --vendor Akbank --start 2026-07-07 --end 2026-07-13
    python fetch_history.py gram-altin --vendor Akbank --date 2026-07-13
    python fetch_history.py CAD --vendor-id 20 --date 2026-07-10   # Kapalıçarşı

Auth (a static Bearer token) is handled automatically by doviz_token.py.
Stdlib only.
"""
import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doviz_token  # noqa: E402

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
ARCHIVE = "https://api.doviz.com/api/v12/assets/{key}/archive?start={start}&end={end}"
UA = doviz_token.UA
# Turkey is UTC+3 year-round (no DST since 2016); the API's daily update_date is
# 00:00 Europe/Istanbul, so a calendar day D starts at D 00:00 −03:00.
TR = timezone(timedelta(hours=3))
DAY = 86400

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


VENDORS = _load("vendors.json")   # {"1": "Akbank", ...}
SLUGS = _load("slugs.json")       # {"CAD": "kanada-dolari", ...} (for FX validation)


def resolve_vendor_id(name, vendor_id):
    if vendor_id is not None:
        return str(vendor_id)
    needle = name.lower()
    matches = [vid for vid, vn in VENDORS.items() if needle in vn.lower()]
    if not matches:
        sys.exit("Unknown vendor %r (see fetch_vendors.py --list vendors)" % name)
    if len(matches) > 1:
        exact = [vid for vid in matches if VENDORS[vid].lower() == needle]
        if len(exact) == 1:
            return exact[0]
        sys.exit("Ambiguous vendor %r: %s" % (name, ", ".join(VENDORS[v] for v in matches)))
    return matches[0]


def resolve_item(item):
    """Return the ITEM token for the asset key (upper ISO code, or gold slug)."""
    raw = item.strip()
    if raw in GOLD_KEYS:
        return raw
    code = raw.upper()
    if code in SLUGS or len(code) == 3:
        return code
    sys.exit("Unknown item %r (ISO code like USD, or gold key like gram-altin)" % raw)


def day_bounds(d):
    """[start, end) epoch seconds bracketing calendar day d in Istanbul time."""
    start = int(datetime(d.year, d.month, d.day, tzinfo=TR).timestamp())
    return start, start + DAY


def fetch_archive(key, start, end):
    """GET the archive; auto-refresh the token once on 401/403."""
    url = ARCHIVE.format(key=key, start=start, end=end)

    def _call(token):
        hdr = {
            "Authorization": "Bearer " + token,
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": UA,
            "Origin": "https://kur.doviz.com",
            "Referer": "https://kur.doviz.com/",
            "Accept": "application/json, text/plain, */*",
        }
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=25) as r:
            return json.loads(r.read().decode("utf-8", "replace"))

    try:
        token = doviz_token.get_token()
    except RuntimeError as e:
        sys.exit(str(e))
    try:
        data = _call(token)
    except urllib.error.HTTPError as e:
        if e.code not in (401, 403):
            raise
        try:
            token = doviz_token.get_token(refresh=True)  # token rotated → re-derive
        except RuntimeError as e2:
            sys.exit(str(e2))
        data = _call(token)
    archive = (data or {}).get("data", {}).get("archive")
    if archive is None:
        sys.exit("Unexpected response for %s: %s" % (key, json.dumps(data)[:200]))
    return list(archive.values()) if isinstance(archive, dict) else list(archive)


def shape(point):
    ud = point.get("update_date")
    return {
        "date": datetime.fromtimestamp(ud, TR).strftime("%Y-%m-%d") if ud else None,
        "update_date": ud,
        "close": point.get("close"),
        "close_try": point.get("close_try"),
        "close_usd": point.get("close_usd"),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("item", help="ISO code (USD) or gold key (gram-altin)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--vendor", help="vendor name, e.g. Akbank (substring match)")
    g.add_argument("--vendor-id", type=int, help="numeric vendor id")
    ap.add_argument("--date", help="single day, YYYY-MM-DD")
    ap.add_argument("--start", help="range start, YYYY-MM-DD (with --end)")
    ap.add_argument("--end", help="range end, YYYY-MM-DD (inclusive)")
    args = ap.parse_args()

    if not args.vendor and args.vendor_id is None:
        ap.error("a vendor is required (--vendor NAME or --vendor-id N)")
    if not args.date and not (args.start and args.end):
        ap.error("give --date, or both --start and --end")

    vid = resolve_vendor_id(args.vendor, args.vendor_id)
    token_item = resolve_item(args.item)
    key = "%s-%s" % (vid, token_item)

    if args.date:
        try:
            d = datetime.strptime(args.date, "%Y-%m-%d").date()
        except ValueError:
            sys.exit("Bad --date %r (want YYYY-MM-DD)" % args.date)
        start, end = day_bounds(d)
        pts = fetch_archive(key, start, end)
        if not pts:
            # Market closed that day: widen ±3 days, take nearest on/before D.
            wide = fetch_archive(key, start - 3 * DAY, end + 3 * DAY)
            on_or_before = [p for p in wide if p.get("update_date", 0) <= start]
            chosen = max(on_or_before, key=lambda p: p["update_date"]) if on_or_before \
                else (min(wide, key=lambda p: abs(p["update_date"] - start)) if wide else None)
            if not chosen:
                sys.exit("No data near %s for %s" % (args.date, key))
            out = shape(chosen)
            out["requested_date"] = args.date
            out["note"] = "nearest available trading day"
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(shape(pts[0]), ensure_ascii=False, indent=2))
        return

    try:
        s = datetime.strptime(args.start, "%Y-%m-%d").date()
        e = datetime.strptime(args.end, "%Y-%m-%d").date()
    except ValueError:
        sys.exit("Bad --start/--end (want YYYY-MM-DD)")
    if s > e:
        sys.exit("--start must not be after --end")
    start, _ = day_bounds(s)
    _, end = day_bounds(e)
    rows = [shape(p) for p in fetch_archive(key, start, end)]
    # Clip to the requested calendar range (the API may include today's live
    # point or a boundary day just outside [start, end]).
    lo, hi = args.start, args.end
    rows = [r for r in rows if r["date"] and lo <= r["date"] <= hi]
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
