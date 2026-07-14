# hermes-skills

A [Hermes agent](https://hermes-agent.nousresearch.com) **skills tap** — a GitHub
repository of installable skills for the Hermes agent. Each skill lives in its own
directory under [`skills/`](skills/) and is installed by directory name.

## Install

Add this repo as a tap once, then install any skill from it:

```bash
hermes skills tap add ElvisTR/hermes-skills
hermes skills install ElvisTR/hermes-skills/doviz-com
```

Or install a single skill directly, without adding the tap:

```bash
hermes skills install ElvisTR/hermes-skills/doviz-com
```

Preview before installing:

```bash
hermes skills inspect ElvisTR/hermes-skills/doviz-com
```

## Skills in this tap

| Skill | Category | What it does |
|-------|----------|--------------|
| [`doviz-com`](skills/doviz-com/) | research | Live, per-vendor & historical FX and gold prices from doviz.com |

---

## doviz-com

Turkish-market foreign-exchange and gold prices from
[doviz.com](https://kur.doviz.com), exposed as small Python CLIs. doviz.com has no
clean public price API, so this skill wraps its HTML tables, live WebSocket, and
semi‑private archive API for you and returns clean JSON.

### What you can ask for

- **Live / current price** of any currency (USD, EUR, GBP, … 63 total) or gold
  product (Gram Altın, Çeyrek, Ons, Has, Bilezik, … 19 total) against the Turkish Lira.
- **Per-vendor prices** — every bank / exchange office (Akbank, Kapalıçarşı, Harem,
  Denizbank, Merkez Bankası, …) with its own Alış (bid) / Satış (ask) / Makas (spread).
- **Historical daily prices** for an item + vendor — a single day or a date range.
- A **whole-market snapshot** of every item at once.

### Scripts

| Script | Purpose | Deps |
|--------|---------|------|
| `scripts/fetch_vendors.py` | Per-vendor bid/ask for one item (all vendors, one vendor, or cheapest) | stdlib (snapshot); `websocket-client` for `--live` |
| `scripts/fetch_history.py` | Historical daily close for an item + vendor (single day or range) | stdlib |
| `scripts/fetch_all.py` | One-shot snapshot of every currency + gold item | `websocket-client` |
| `scripts/doviz_token.py` | Shared helper — derives the archive API's Bearer token | stdlib |

### Quick start

The default snapshot paths use only the Python standard library. The live-socket
paths (`fetch_all.py`, `fetch_vendors.py --live`) need `websocket-client`:

```bash
# From the installed skill directory:
uv pip install -r requirements.txt          # NOT `pip` — the Hermes venv has no pip
```

Always **quote the script path and use forward slashes** — the Hermes terminal is a
POSIX shell even on Windows, so unquoted backslashes get eaten. Each script resolves
its own bundled data via `__file__`, so it runs from any working directory:

```bash
# Current per-vendor prices
python "…/skills/doviz-com/scripts/fetch_vendors.py" CAD                  # all vendors, CAD/TRY
python "…/skills/doviz-com/scripts/fetch_vendors.py" CAD --vendor Akbank  # one vendor
python "…/skills/doviz-com/scripts/fetch_vendors.py" CAD --best           # lowest ask
python "…/skills/doviz-com/scripts/fetch_vendors.py" gram-altin --gold    # gold vendor table

# Historical daily prices (item + vendor)
python "…/skills/doviz-com/scripts/fetch_history.py" USD --vendor Akbank --date 2020-03-16
python "…/skills/doviz-com/scripts/fetch_history.py" USD --vendor Akbank --start 2026-07-07 --end 2026-07-13

# Whole-market snapshot (needs websocket-client)
python "…/skills/doviz-com/scripts/fetch_all.py" --currencies
```

Items are ISO codes (`USD`, `CAD`) or gold product keys (`gram-altin`); vendors are a
name (`--vendor Akbank`, case-insensitive) or an id (`--vendor-id 1`). All scripts
print JSON and exit non-zero with an actionable message on bad input. Full field
reference, the currency/gold catalogs, and the WebSocket protocol are documented in
[`skills/doviz-com/SKILL.md`](skills/doviz-com/SKILL.md).

### Data sources

- HTML price tables on `kur.doviz.com` (FX) and `altin.doviz.com` (gold)
- Live ticks via `wss://socket.doviz.com` (subprotocol `nokta-chat-json`)
- Historical archive: `https://api.doviz.com/api/v12/assets/<vendorId>-<CODE>/archive`
  (Bearer token auto-derived by `doviz_token.py`)

## Requirements

- Python 3.8+
- [`uv`](https://docs.astral.sh/uv/) (Hermes ships it; used to install deps)
- `websocket-client` — only for the live/socket paths (`fetch_all.py`,
  `fetch_vendors.py --live`); every other path is standard-library only.

## License

MIT — see each skill's `SKILL.md` frontmatter. You are free to use, modify, and
redistribute.

## Disclaimer

Unofficial and **not affiliated with, endorsed by, or supported by doviz.com**. It
reads publicly displayed prices for informational purposes only — it is not financial
advice, and prices may be delayed or inaccurate. Use responsibly and respect
doviz.com's Terms of Service and rate limits.
