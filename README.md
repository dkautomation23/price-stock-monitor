# price-stock-monitor

Watch product pages for **price changes and stock changes**, keep a full history,
and get alerted the moment something moves — a single, dependency-light Python CLI.

Built for e-commerce operators who track competitor prices or restocks by hand
in a spreadsheet. Point it at any product URL, give it a CSS selector for the
price (and optionally the stock label), and it does the rest on a schedule.

## What it does

- **Price + stock tracking** from any product page via CSS selectors — works with
  Shopify, WooCommerce, marketplaces, or plain HTML stores.
- **Change detection**: price drops/rises (with % delta), out-of-stock and
  back-in-stock transitions. Silent when nothing changes.
- **Full history** in a local SQLite file — every check is a timestamped row you
  can query or chart later.
- **Alerts** to the console or any webhook (Slack, Discord, or a generic
  `{"text": ...}` endpoint).
- **Polite by default**: request timeout, retries with exponential backoff,
  rotating User-Agent, and a configurable delay between products.

## Quick start

```bash
pip install -r requirements.txt
cp products.example.yaml products.yaml   # edit for your pages (defaults just work)
python monitor.py --config products.yaml --once
```

The example config points at [books.toscrape.com](https://books.toscrape.com), a
public scraping sandbox, so the first run works with zero setup.

Run it on a schedule:

```bash
# built-in loop
python monitor.py --config products.yaml --watch --interval 3600

# or a cron entry (hourly)
0 * * * * cd /path/to/price-stock-monitor && python monitor.py --once
```

## Sample output

```
[2026-08-17 06:12:03 UTC] checking 2 product(s)...
  * tracking started — A Light in the Attic: 51.77, in stock
  * tracking started — Tipping the Velvet: 53.74, in stock

[2026-08-17 07:12:05 UTC] checking 2 product(s)...
  * A Light in the Attic: price dropped 51.77 -> 45.17 (-12.7%)
    Tipping the Velvet: 53.74 (no change)
```

## Config

```yaml
settings:
  timeout: 20          # seconds per request
  retries: 2           # extra attempts on failure
  backoff: 1.0         # base backoff seconds (doubles each retry)
  request_delay: 1.0   # pause between products
  webhook_url: "..."   # optional; posts {"text": "<change>"} on each change

products:
  - name: "My product"
    url: "https://store.example.com/products/thing"
    price_selector: ".price__current"   # any CSS selector
    stock_selector: ".product__stock"   # optional
    in_stock_text: "in stock"           # substring that means available
```

Prices are normalised across formats (`$1,234.56`, `1.234,56 €`, `£45`), so the
`%` deltas stay correct regardless of the store's locale.

## Notes

- Scrape only public pages you're allowed to, and keep `request_delay` sane — the
  defaults are already gentle.
- History lives in `history.db` (git-ignored). Delete it to reset tracking.

## License

MIT — see [LICENSE](LICENSE).
