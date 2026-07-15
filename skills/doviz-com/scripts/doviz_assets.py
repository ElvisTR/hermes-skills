#!/usr/bin/env python3
"""Live per-instrument catalog for doviz.com — asset type & vendor list.

doviz.com exposes one JSON endpoint keyed by the *bare* item code (no slug):

    GET https://api.doviz.com/api/v12/assets/<CODE>

`<CODE>` is an ISO currency code (USD, CAD) or a gold product key (gram-altin,
14-ayar-altin). One GET returns, for that single instrument:
  * asset_type      -> "C" currency / "G" gold  (so the type is auto-detected)
  * other_sources[] -> every vendor (bank / exchange office) that quotes it,
        each with asset_key "<vendorId>-<CODE>", source_id, source_name, and a
        live bid/ask/spread.
  * the top-level fields are the "Serbest Piyasa" reference price (source_id 99),
        which is deliberately NOT a vendor and never appears in other_sources.

This replaces the old bundled slugs.json / vendors.json: both the slug and the
vendor list are now derived live, per instrument, so new banks/exchange offices
show up automatically and nothing goes stale. Auth is the same static Bearer
token the archive API uses, handled by doviz_token.py (auto-refreshed on
401/403). Stdlib only.

Standalone (debug):  python doviz_assets.py USD    # type + vendor rows as JSON
"""
import json
import os
import sys
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import doviz_token  # noqa: E402

ASSET = "https://api.doviz.com/api/v12/assets/{code}"
UA = doviz_token.UA

# 19 gold / precious-metal product keys (item token == socket key == slug tail).
GOLD_KEYS = {
    "ons", "gram-altin", "gram-has-altin", "ceyrek-altin", "yarim-altin",
    "tam-altin", "cumhuriyet-altini", "ata-altin", "14-ayar-altin",
    "18-ayar-altin", "22-ayar-bilezik", "ikibucuk-altin", "besli-altin",
    "gremse-altin", "resat-altin", "hamit-altin", "gumus", "gram-platin",
    "gram-paladyum",
}

# ISO codes, for --list currencies discoverability. Any live code works even if
# it is not here; the per-instrument endpoint is the real source of truth, so
# this is only a hint list and needs no slug mapping anymore.
CURRENCIES = (
    "USD EUR GBP CHF CAD RUB AED AUD DKK SEK NOK JPY KWD ZAR BHD LYD SAR IQD "
    "ILS INR MXN HUF NZD BRL IDR CZK PLN RON CNY ARS ALL AZN BAM CLP COP CRC "
    "DZD EGP HKD ISK KRW KZT LBP LKR MAD MDL MKD MYR OMR PEN PHP PKR QAR RSD "
    "SGD SYP THB TWD UAH UYU GEL TND BGN"
).split()

_TYPE = {"C": "currency", "G": "gold"}
_CACHE = {}  # normalized code -> data dict, so each instrument is fetched once per run


def normalize_code(item):
    """Asset-key token: gold keys pass through lowercase, ISO codes upper-case."""
    raw = item.strip()
    if raw.lower() in GOLD_KEYS:
        return raw.lower()
    return raw.upper()


def _http_json(url, token):
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


def _get_json_with_auth(url):
    """GET a token-authed JSON API URL, refreshing the token once on 401/403.

    Returns the decoded body, or None on 404 (unknown asset). Exits with the
    token helper's message if the token can't be derived.
    """
    try:
        token = doviz_token.get_token()
    except RuntimeError as e:
        sys.exit(str(e))
    for attempt in (0, 1):
        try:
            return _http_json(url, token)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None                     # unknown code -> friendly caller message
            if e.code in (401, 403) and attempt == 0:
                try:
                    token = doviz_token.get_token(refresh=True)  # rotated -> re-derive
                except RuntimeError as e2:
                    sys.exit(str(e2))
                continue
            raise


def get_asset(item):
    """Return the live ``data`` dict for one instrument. Cached per run.

    Auto-refreshes the Bearer token once on 401/403 (it rotates on redeploys).
    Exits with an actionable message on an unknown code or unexpected body.
    """
    code = normalize_code(item)
    if code in _CACHE:
        return _CACHE[code]
    data = _get_json_with_auth(ASSET.format(code=code))
    d = (data or {}).get("data")
    if not data or data.get("error") or not d or not d.get("asset_key"):
        sys.exit("Unknown or unavailable item %r (try an ISO code like USD, or a "
                 "gold key like gram-altin; see fetch_vendors.py --list)" % item)
    _CACHE[code] = d
    return d


def asset_type(data):
    """'currency' or 'gold' for a fetched asset dict."""
    return _TYPE.get(data.get("asset_type"), "other")


def vendors(data):
    """Per-vendor rows from other_sources, shaped like fetch_vendors output.

    Returns [{vendor_id, vendor, item, bid, ask, makas, makas_pct}, ...] for
    every bank / exchange office that quotes this instrument. Serbest Piyasa
    (the market reference) is the asset's top level, not a vendor, so it is not
    included here.
    """
    item = data.get("asset_key")
    rows = []
    for e in data.get("other_sources", []):
        bid, ask = e.get("bid"), e.get("ask")
        if bid is None or ask is None:
            continue
        makas = round(ask - bid, 6)
        rows.append({
            "vendor_id": int(e.get("source_id")),
            "vendor": e.get("source_name") or ("vendor-%s" % e.get("source_id")),
            "item": item,
            "bid": bid,
            "ask": ask,
            "makas": makas,
            "makas_pct": round(makas / bid * 100, 4) if bid else None,
        })
    return rows


def vendor_map(data):
    """{id_str: name} for every vendor that quotes this instrument."""
    return {str(e.get("source_id")): (e.get("source_name") or "")
            for e in data.get("other_sources", [])}


if __name__ == "__main__":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    if len(sys.argv) != 2:
        sys.exit("usage: python doviz_assets.py <ISO code | gold key>  (e.g. USD)")
    _d = get_asset(sys.argv[1])
    print(json.dumps({"item": _d.get("asset_key"), "type": asset_type(_d),
                      "vendors": vendors(_d)}, ensure_ascii=False, indent=2))
