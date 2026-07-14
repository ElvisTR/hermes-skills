#!/usr/bin/env python3
"""Obtain the Bearer token that doviz.com's JSON API (api.doviz.com) requires.

Every doviz detail page injects `Authorization: Bearer <token>` into its AJAX
calls. The token is produced by an obfuscated but **fully static** function (no
time/date input) that decodes a value embedded in the page. It is public page
data (served to every visitor) and rotates on site redeploys, so this helper
**derives it live** from a detail page by porting that decoder — no token is
bundled in this repo — and caches the derived value between runs.
"""
import os
import re
import tempfile
import urllib.request

# Cache the derived token OUTSIDE the skill tree so the publishable skill never
# carries a token-looking file.
CACHE = os.path.join(tempfile.gettempdir(), "doviz-com-api.token")
TOKEN_PAGE = "https://kur.doviz.com/akbank/amerikan-dolari"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ+/"
# Matches the IIFE call site:  })( "<payload>", 9, "hHaEDtnYC", 11, 2, 35 )
_IIFE = re.compile(
    r'\}\)\(\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*"([^"]+)"\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)')


def _base_n(digits, in_base, out_base):
    """Port of the site's `_0xe2c`: read `digits` in base `in_base`, emit base `out_base`."""
    src = _ALPHABET[:in_base]
    dst = _ALPHABET[:out_base]
    value = 0
    for power, ch in enumerate(reversed(digits)):
        idx = src.find(ch)
        if idx != -1:
            value += idx * (in_base ** power)
    out = ""
    while value > 0:
        out = dst[value % out_base] + out
        value //= out_base
    return out or "0"


def derive_token(html):
    """Re-derive the Bearer token from a detail page's HTML. None if not found."""
    m = _IIFE.search(html)
    if not m:
        return None
    payload, _u, n, t, e, _r = m.group(1), int(m.group(2)), m.group(3), \
        int(m.group(4)), int(m.group(5)), int(m.group(6))
    delim = n[e]
    out_bytes = []
    i = 0
    while i < len(payload):
        chunk = ""
        while i < len(payload) and payload[i] != delim:
            chunk += payload[i]
            i += 1
        i += 1  # skip the delimiter
        for j, ch in enumerate(n):
            chunk = chunk.replace(ch, str(j))
        out_bytes.append(int(_base_n(chunk, e, 10)) - t)
    try:
        return bytes(out_bytes).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None


def _http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", "replace")


def get_token(refresh=False):
    """Return a usable API token, derived live from a doviz.com detail page.

    Order: cached value (unless refresh) -> derive from the live page. There is no
    bundled token; the value is public page data that rotates, so it is fetched
    fresh and only cached between runs. Raises RuntimeError if it can't be derived.
    """
    if not refresh and os.path.exists(CACHE):
        try:
            with open(CACHE, encoding="utf-8") as fh:
                tok = fh.read().strip()
            if tok:
                return tok
        except OSError:
            pass
    try:
        tok = derive_token(_http_get(TOKEN_PAGE))
    except Exception:
        tok = None
    if not tok:
        raise RuntimeError(
            "Could not derive the doviz.com API token from %s — the page markup "
            "may have changed." % TOKEN_PAGE)
    try:
        with open(CACHE, "w", encoding="utf-8") as fh:
            fh.write(tok)
    except OSError:
        pass
    return tok


if __name__ == "__main__":
    print(get_token(refresh=True))
