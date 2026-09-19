# Contributing

Real commands for this repository. `.github/workflows/ci.yml` is the source of
truth if this page and CI ever disagree.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
```

Three dependencies: `requests`, `beautifulsoup4`, `PyYAML`. Keep new ones out
unless there is no reasonable alternative.

## Before you write code

Open an issue first for anything beyond a fix — in particular anything that
would add a dependency or change what `products.yaml` is allowed to contain.

## The one rule that is not negotiable

A new check starts as a failing test. Add a `check("label", condition)` call
inside `selftest()` in `monitor.py`. Most existing checks test `parse_price`,
`extract`, or `diff_message` against inline HTML/strings — no network, no live
site. Confirm your new check fails first, then implement.

## Running the tests

```bash
python -m compileall -q .
python monitor.py --selftest
```

Same two steps CI runs, in that order.

## Commit messages

Match `git log --oneline` in this repository: a short, imperative summary, no
ticket prefixes, no emoji. Recent examples:

```
Add --selftest, and run it in CI
Read a price written with a space as a thousands separator
price-stock-monitor: config-driven price & stock change monitor with history and alerts
```

## License

Contributions are published under this repository's MIT license.
