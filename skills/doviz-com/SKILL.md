---
name: doviz-com
description: "Live, vendor & historical doviz.com FX & gold prices."
version: 1.2.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    category: research
    tags: [finance, forex, fx, gold, altin, doviz, live-prices]
    related_skills: [financial-data-queries]
---

# doviz.com Skill

doviz.com publishes live Turkish-market foreign-exchange and gold prices across
two sibling sites — `kur.doviz.com` (FX) and `altin.doviz.com` (gold). This skill
ships Python scripts that pull three things: the single **Serbest Piyasa**
reference price, every **vendor's** (bank / exchange-office) buy/sell for an item,
and **historical daily** prices. There is no clean public REST price API; the
scripts wrap doviz.com's HTML tables, a live WebSocket, and a semi-private archive
API for you. See **Reference** below for how each source works.

## When to Use

- User wants live USD/EUR/GBP (or any) currency rate against the Turkish Lira
- User wants live gold prices (Gram Altın, Çeyrek, Ons, Has, Bilezik, etc.)
- User wants a specific vendor's price ("Akbank USD") or all vendors for an item
- User wants historical prices for an item + vendor (a single day or a range)
- User wants the full catalog / a whole-market snapshot of everything doviz tracks
- User pastes a doviz.com URL and asks how to pull its numbers programmatically

For casual "what's X worth" questions without doviz.com specifically, see
`financial-data-queries`. This skill is for doviz.com's structured feeds.

## Bundled Files

- `scripts/fetch_vendors.py` — per-vendor bid/ask for one item (all vendors, one vendor, or cheapest)
- `scripts/fetch_history.py` — historical daily close for an item + vendor (single day or range)
- `scripts/fetch_all.py` — one-shot snapshot of every currency + gold item
- `scripts/doviz_token.py` — shared helper; derives the archive API's Bearer token
- `scripts/slugs.json`, `scripts/vendors.json` — bundled item/vendor catalogs
- `scripts/requirements.txt` — optional deps for the live-socket paths
- `templates/starter.js` — WebSocket starter template

## Procedure

All scripts live in `scripts/`. The default snapshot paths use only the Python
stdlib; the live-socket paths (`scripts/fetch_all.py`, `scripts/fetch_vendors.py`
with `--live`) need `websocket-client`. Install it with **uv** — the Hermes agent
venv has no `pip`:

```bash
uv pip install -r scripts/requirements.txt   # NOT `pip install` — pip is not on PATH
```

**Invoking the scripts — always quote the path and use forward slashes.** The
terminal is a POSIX shell even on Windows, so unquoted backslashes are eaten
(`C:\Users\…\x.py` → `C:Users…x.py`, "can't open file"). Forward slashes work on
every platform, and each script resolves its own bundled data (`slugs.json`,
`vendors.json`) via `__file__`, so it runs from any working directory:

```bash
# Set once to this skill's folder, e.g. on Hermes/Windows:
#   C:/Users/<you>/AppData/Local/hermes/skills/research/doviz-com
python "$SKILL_DIR/scripts/fetch_vendors.py" CAD --vendor Akbank
```

**Which tool answers which question:**
- *"Current / today's price"* → `fetch_vendors.py` snapshot (its bid/ask is live).
  Do **not** use `--live` for a one-shot value.
- *"Price on date D"* (including today) → `fetch_history.py … --date D`.
- *"Cheapest vendor"* → `fetch_vendors.py <item> --best`.
- *"Everything at once"* → `fetch_all.py`.
- *"Watch it change"* → `fetch_vendors.py <item> --live --live-seconds N` — a
  bounded monitor that streams N seconds (default 30) then exits.

```bash
# Vendor / current prices (stdlib only)
python ".../scripts/fetch_vendors.py" CAD                  # all vendors, CAD/TRY
python ".../scripts/fetch_vendors.py" CAD --vendor Akbank  # one vendor by name
python ".../scripts/fetch_vendors.py" CAD --vendor-id 20   # one vendor by id
python ".../scripts/fetch_vendors.py" CAD --best           # lowest ask
python ".../scripts/fetch_vendors.py" gram-altin --gold    # gold vendor table
python ".../scripts/fetch_vendors.py" --list currencies    # discoverability
python ".../scripts/fetch_vendors.py" CAD --live --live-seconds 20  # watch, then exit

# Whole-market snapshot via one socket join (needs websocket-client)
python ".../scripts/fetch_all.py"                    # every item
python ".../scripts/fetch_all.py" --currencies       # or --gold : filter by type

# Historical daily prices: Serbest Piyasa (no vendor) or a specific vendor (stdlib only)
python ".../scripts/fetch_history.py" EUR --date 2026-07-13                   # Serbest Piyasa
python ".../scripts/fetch_history.py" USD --vendor Akbank --date 2020-03-16
python ".../scripts/fetch_history.py" USD --vendor Akbank --start 2026-07-07 --end 2026-07-13
python ".../scripts/fetch_history.py" gram-altin --vendor Akbank --date 2026-07-13
python ".../scripts/fetch_history.py" CAD --vendor-id 20 --date 2026-07-10
```

Items are ISO codes (`USD`, `CAD`) or gold product keys (`gram-altin`); vendors are
a name (`--vendor Akbank`, case-insensitive substring) or an id (`--vendor-id 1`).
In `fetch_history.py`, omitting both `--vendor` and `--vendor-id` fetches the
**Serbest Piyasa** reference series instead of a bank's — the only history source
that also has real `open`/`high`/`low` (vendor points leave them `0`).
A `--date` on a market-closed day returns the nearest prior trading day, flagged
with a `note`. All scripts print JSON and exit non-zero with an actionable message
on bad input.

## Pitfalls

- **Quote script paths / use forward slashes.** A POSIX shell strips unquoted
  Windows backslashes, so `python C:\…\fetch_vendors.py` becomes `C:…fetch_vendors.py`
  and fails with "can't open file". Use `python "C:/…/fetch_vendors.py"`.
- **`uv pip install`, never `pip`.** The Hermes agent venv has no pip/pip3 on PATH.
- **`--live` is a monitor, not a price read.** For "current price" use the plain
  snapshot; `--live` streams and only exits after `--live-seconds`.
- **Compact JSON on the socket.** Spaces in the auth frame → join `failed`.
- **Numeric-slug gold keys are not vendor keys.** `14-ayar-altin`,
  `18-ayar-altin`, `22-ayar-bilezik` start with digits but are items, not
  `<vendorId>-<ITEM>`. Landing pages contain no vendor keys, so don't filter by a
  leading-number rule there.
- **Archive API is picky.** It needs the Bearer token **and** `Origin`/`Referer:
  https://kur.doviz.com` — miss either and it's 401/403, not an empty result. The
  token rotates, so re-derive on 401/403 (`doviz_token.get_token(refresh=True)`).
- **Archive days are Istanbul-midnight.** Bracket a day as `[00:00+03:00, +24h)`
  and label points in UTC+3; a naive UTC date is off by one.
- **The subprotocol is mandatory.** A WebSocket opened without `"nokta-chat-json"`
  fails the handshake. It is the second argument.
- **You must join a room or you get nothing.** The socket only pushes keys named in
  `joinTo`. There is no wildcard — enumerate keys from the HTML first.
- **Formatted vs numeric fields.** `s`,`c`,`a` are TR-locale display strings;
  always compute on `sn`,`cn`,`an`,`bid`,`ask`,`hn`,`ln`.
- **`ts` is in seconds, not milliseconds.**
- **Cross-vendor prices genuinely differ.** Some banks quote an item ~20% above
  others; when comparing vendors historically, compare each vendor's own trajectory
  and don't assume one clean market price.

## Verification

Run from any directory with the Hermes venv python (replace `.../` with the skill
path). Each should print JSON and exit 0:

```bash
python ".../scripts/fetch_vendors.py" CAD --vendor Akbank
#   → one row: {"vendor":"Akbank","vendor_id":1,"item":"CAD","bid":…,"ask":…,…}
python ".../scripts/fetch_vendors.py" gram-altin --gold --best
#   → single lowest-ask gold vendor row (key like 1-gram-altin)
python ".../scripts/fetch_history.py" USD --vendor Akbank --date 2020-03-16
#   → {"date":"2020-03-16", … ,"close":6.598}   (Istanbul-midnight close)
python ".../scripts/fetch_history.py" EUR --date 2026-07-13
#   → {"date":"2026-07-13","source":"Serbest Piyasa","open":…,"high":…,"low":…,"close":…}
python ".../scripts/fetch_all.py" --currencies   # needs websocket-client
#   → JSON array of ~63 currency items with numeric bid/ask/last
```

If `fetch_all.py`/`--live` reports a missing module, run the `uv pip install` line
above. If the archive returns 401/403, it self-heals by re-deriving the token.

## Reference

### How the data flows
```
GET https://kur.doviz.com/      ──▶  HTML with data-socket-key cells   (catalog + seed)
GET https://altin.doviz.com/    ──▶  HTML with data-socket-key cells   (catalog + seed)
                                        │  collect unique data-socket-key values
wss://socket.doviz.com  (subprotocol nokta-chat-json)
        join room "info@<key1>,<key2>,.../<nick>"
                                        ▼  server streams price ticks
        {"a":"m","m":{ "k":"USD","bid":..,"ask":..,"ts":.. }}   (live)
```
Price cells: `data-socket-key` = item code, `data-socket-attr` = which field
(`s` headline value, `bid` Alış/buy, `ask` Satış/sell, `c` change %, `a` change
amount). The HTML gives *what exists* + seed values; the socket gives *live* ticks.
No API key, login, or cookie for the HTML or socket.

### Item catalogs
Discovered by collecting every unique `data-socket-key` from the page HTML.

**kur.doviz.com — 63 currencies** (ISO codes = socket keys):
```
USD EUR GBP CHF CAD RUB AED AUD DKK SEK NOK JPY KWD ZAR BHD LYD SAR IQD ILS
INR MXN HUF NZD BRL IDR CZK PLN RON CNY ARS ALL AZN BAM CLP COP CRC DZD EGP
HKD ISK KRW KZT LBP LKR MAD MDL MKD MYR OMR PEN PHP PKR QAR RSD SGD SYP THB
TWD UAH UYU GEL TND BGN
```

**altin.doviz.com — 19 gold / precious-metal products** (`key` → name):
```
ons                Ons Altın           gram-altin       Gram Altın
gram-has-altin     Gram Has Altın      ceyrek-altin     Çeyrek Altın
yarim-altin        Yarım Altın         tam-altin        Tam Altın
cumhuriyet-altini  Cumhuriyet Altını   ata-altin        Ata Altın
14-ayar-altin      14 Ayar Bilezik     18-ayar-altin    18 Ayar Bilezik
22-ayar-bilezik    22 Ayar Bilezik     ikibucuk-altin   İkibuçuk Altın
besli-altin        Beşli Altın         gremse-altin     Gremse Altın
resat-altin        Reşat Altın         hamit-altin      Hamit Altın
gumus              Gram Gümüş          gram-platin      Gram Platin
gram-paladyum      Gram Paladyum
```
Header ticker keys (`XU100`=BIST100, `d-bitcoin`, `BRENT`) are widgets, not tables.
`scripts/slugs.json` maps each currency code → detail-page slug (CAD →
`kanada-dolari`); `fetch_vendors.py --refresh-slugs` rebuilds it from the live site.

### Vendor (bank) prices
Each item has a **"Banka Kurları"** table listing every vendor's own Alış/Satış, on
per-item detail pages:
- **Currency:** `https://kur.doviz.com/serbest-piyasa/<slug>` (CAD → `kanada-dolari`)
- **Gold:** `https://altin.doviz.com/<product-key>` (`gram-altin`)

Each vendor row carries the vendor name plus `data-socket-key="<vendorId>-<ITEM>"`
and two priced cells `data-socket-attr="bid"` (Alış) / `="ask"` (Satış). One GET
returns all vendors. Vendor IDs are **global/consistent** across items (`1`=Akbank,
`20`=Kapalıçarşı, `23`=Harem, `11`=Merkez Bankası, …); full map in
`scripts/vendors.json`. `Makas` = `ask − bid`; `Makas%` = `makas / bid × 100`.

### WebSocket protocol
| Property | Value |
|----------|-------|
| URL | `wss://socket.doviz.com` |
| Subprotocol | `nokta-chat-json` (**required**, second WS arg) |
| Auth | None — anonymous, no cookie/token |
| Transport | Push. One subscribe frame, then receive only. |

On open, send an auth+join frame as **compact JSON** (no spaces, or the server
returns `{"a":"j","response":{"status":"failed"}}`):
```js
ws = new WebSocket("wss://socket.doviz.com", "nokta-chat-json");
ws.onopen = () => ws.send(JSON.stringify({action:"auth",data:{username:"",password:"",
  joinTo:"info@USD,EUR,gram-altin,ons/webkullanici_"+(Math.random()*1000|0)}}));
```
Ack: `{"a":"a","response":{"status":"ok",…}}`. Tick: `{"a":"m","m":{…}}`, one per
item. `templates/starter.js` is a runnable client. Tick (`m`) fields:

```json
{"t":"C","k":"USD","c":"0,02","cn":0.02,"s":"47,0009","sn":47.0009,"a":"0,0094",
 "an":0.0094,"cnw":0.39,"cnm":1.58,"cny":17,"d":4,"p":"","ts":1783973453,
 "bid":46.9947,"ask":47.0072,"ln":46.719,"hn":47.0039,"v":604748}
```
| Field | Meaning |
|-------|---------|
| `t` | Type: `"C"` currency, `"G"` gold/metal |
| `k` | Item key (matches `data-socket-key`) |
| `s`/`sn` | Headline price — formatted (TR locale) / **numeric** |
| `bid` / `ask` | **Alış** (buy) / **Satış** (sell), numeric |
| `hn` / `ln` | Day high (Yüksek) / low (Düşük), numeric |
| `c`/`cn`, `a`/`an` | Daily change % / amount — formatted / numeric |
| `cnw` `cnm` `cny` | Weekly / monthly / yearly change % (with `anw`/`anm`/`any`) |
| `d` | Decimals to render (4 FX, 2 gold) |
| `p` | Prefix symbol (`""` TRY, `"$"` ons) |
| `ts` | Timestamp, Unix epoch **seconds** |
| `v` | Volume (some FX items) |

### Historical archive API
```
GET https://api.doviz.com/api/v12/assets/<vendorId>-<CODE>/archive?start=<epoch>&end=<epoch>
```
- Asset key is either `<vendorId>-<ITEM>` for a bank/exchange (`1-USD`, `1-gram-altin`,
  `20-CAD`), or the **bare `<ITEM>` code** for the **Serbest Piyasa** reference series
  (`USD`, `gram-altin`) — the same key the chart on `kur.doviz.com/serbest-piyasa/<slug>`
  uses in the background, with no vendor id at all.
- `start`/`end` are Unix **seconds**; returns **one point per day** (a 10-year range
  → ~2996 points). `update_date` = **00:00 Europe/Istanbul** (UTC+3, fixed since 2016).
- Response: `{"error":false,"data":{"archive":[{update_date, open, highest, lowest,
  close, close_try, close_usd, volume}, …]}}`. For vendor keys only **`close`** (and
  `close_try`) is populated — that day's price; OHLC fields are `0`. The bare
  Serbest Piyasa key is the only one with real `open`/`highest`/`lowest`.
- **Auth:** `Authorization: Bearer <token>` + `Origin`/`Referer: https://kur.doviz.com`
  (no cookies). The token is emitted by an obfuscated but **static, time-independent**
  function on every detail page and **rotates on redeploys**, so
  `scripts/doviz_token.py` derives it live (ported decoder) and caches it, refreshing
  on 401/403.

### Source of truth
- FX: https://kur.doviz.com/  ·  Gold: https://altin.doviz.com/
- Live feed: `wss://socket.doviz.com` (subprotocol `nokta-chat-json`), public
- Archive: `https://api.doviz.com/api/v12/assets/<key>/archive` (Bearer token)
- Catalog + schema last verified **2026-07-14**. Item lists / socket-key spelling can
  drift — re-scan the HTML `data-socket-key` set (`fetch_vendors.py --refresh-slugs`
  rewrites `scripts/slugs.json`).
