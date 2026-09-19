# Security policy

price-stock-monitor fetches product pages you configure, extracts price and
stock with CSS selectors, and stores history in SQLite. This file defines
what counts as a security issue in that specific tool.

## Reporting

Use GitHub's private vulnerability reporting on this repository: **Security →
Report a vulnerability**. It opens a private thread; nothing becomes public
until there is a fix.

If that is not available to you, email **hello@dkautomation.dev** with
`price-stock-monitor` in the subject line.

Include the commit or version you ran, the exact command, and what happened.
A proof of concept is welcome; a scanner's raw output usually is not.

**Do not open a public issue for a vulnerability.**

## Supported versions

No tagged releases yet — the `main` branch is the supported version. Report
against the commit you actually ran.

## What to expect

| | |
|---|---|
| First reply | within 3 working days |
| Assessment | within 7 working days of the first reply |
| Fix or a stated decision not to fix | within 30 days for anything reproducible |

Single-person commitments, not a company SLA.

## Scope

`products.yaml` is loaded with `yaml.safe_load`, and the product URLs and
`webhook_url` in it are your own configuration — trusted input. The page a
tracked URL serves back is not: it can be any site you chose to watch,
including one that changes its response once it notices it is being polled.

In scope:

- A tracked page's content reaching the SQLite history, the console, or the
  optional `webhook_url` in a way that does more than get parsed as a
  price/stock string — for example anything that breaks out of the
  parameterised SQL insert in `save_snapshot`, or a webhook payload that ends
  up carrying more than the documented `{"text": "..."}` line.
- Any way for `products.yaml` to make the YAML loader execute code instead of
  just returning data.

Out of scope:

- The product URL or `webhook_url` themselves — you put them in your own
  config file.
- A target page being slow, blocking the scraper, changing its markup so a
  selector stops matching, or rate-limiting the requests — maintenance
  issues, not vulnerabilities.
- Price or stock text being misread because a site's format is not one of
  the ones `parse_price` normalises.

## Credit

Named in the fix's release notes if you want that; say so if you would rather
not be.

There is no bug bounty.
