#!/usr/bin/env python3
"""price-stock-monitor — watch product pages for price and stock changes.

Polite, config-driven monitor: fetches each product page with retries and a
rotating User-Agent, extracts price and availability with CSS selectors,
stores a timestamped history in SQLite, and reports changes (price drop/rise,
back-in-stock, out-of-stock) to the console or a webhook.

Usage:
    python monitor.py --config products.yaml --once
    python monitor.py --config products.yaml --watch --interval 3600
"""
from __future__ import annotations

import argparse
import random
import re
import sqlite3
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

PRICE_RE = re.compile(r"\d[\d.,]*")
# European shops write 1299 as "1 299" with a (non-breaking) space. Left alone,
# the price regex stops at the space and reports a price of 1 - which then looks
# like a 99.9% price drop. Only a space sitting between a digit and exactly three
# digits is closed up, so "5 each" and "2 x 10" are untouched.
THOUSANDS_SPACE_RE = re.compile(r"(\d)[\s  ](\d{3})(?!\d)")


@dataclass
class Product:
    name: str
    url: str
    price_selector: str
    stock_selector: str | None = None
    in_stock_text: str = "in stock"


@dataclass
class Snapshot:
    price: float | None
    in_stock: bool | None
    raw_price: str
    raw_stock: str


def load_config(path: str):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    products = [
        Product(
            name=item["name"],
            url=item["url"],
            price_selector=item["price_selector"],
            stock_selector=item.get("stock_selector"),
            in_stock_text=item.get("in_stock_text", "in stock"),
        )
        for item in data.get("products", [])
    ]
    return products, data.get("settings", {})


def parse_price(text: str) -> float | None:
    """Pull a number out of messy price text and normalise separators."""
    if not text:
        return None
    m = PRICE_RE.search(THOUSANDS_SPACE_RE.sub(r"\1\2", text))
    if not m:
        return None
    num = m.group(0).replace(" ", "")
    if "," in num and "." in num:
        # last separator is the decimal point
        if num.rfind(",") > num.rfind("."):
            num = num.replace(".", "").replace(",", ".")
        else:
            num = num.replace(",", "")
    elif "," in num:
        # 1,234 -> thousands ; 1,99 -> decimal
        num = num.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", num) else num.replace(",", ".")
    try:
        return float(num)
    except ValueError:
        return None


def fetch(url: str, timeout: int, retries: int, backoff: float) -> str:
    last_err: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = requests.get(
                url,
                headers={
                    "User-Agent": random.choice(USER_AGENTS),
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
    raise RuntimeError(f"failed to fetch {url}: {last_err}")


def extract(html: str, product: Product) -> Snapshot:
    soup = BeautifulSoup(html, "html.parser")
    price_el = soup.select_one(product.price_selector)
    raw_price = price_el.get_text(strip=True) if price_el else ""
    price = parse_price(raw_price)

    in_stock: bool | None = None
    raw_stock = ""
    if product.stock_selector:
        stock_el = soup.select_one(product.stock_selector)
        raw_stock = stock_el.get_text(" ", strip=True) if stock_el else ""
        if raw_stock:
            in_stock = product.in_stock_text.lower() in raw_stock.lower()
    return Snapshot(price=price, in_stock=in_stock, raw_price=raw_price, raw_stock=raw_stock)


DB_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    ts TEXT NOT NULL,
    price REAL,
    in_stock INTEGER,
    raw_price TEXT,
    raw_stock TEXT
);
"""


def db_connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(DB_SCHEMA)
    return conn


def last_snapshot(conn: sqlite3.Connection, name: str):
    row = conn.execute(
        "SELECT price, in_stock FROM snapshots WHERE name=? ORDER BY id DESC LIMIT 1",
        (name,),
    ).fetchone()
    if not row:
        return None
    price, in_stock = row
    return price, (None if in_stock is None else bool(in_stock))


def save_snapshot(conn: sqlite3.Connection, product: Product, snap: Snapshot) -> None:
    conn.execute(
        "INSERT INTO snapshots(name, url, ts, price, in_stock, raw_price, raw_stock) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            product.name,
            product.url,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            snap.price,
            None if snap.in_stock is None else int(snap.in_stock),
            snap.raw_price,
            snap.raw_stock,
        ),
    )
    conn.commit()


def diff_message(product: Product, prev, snap: Snapshot) -> str | None:
    if prev is None:
        base = f"tracking started — {product.name}: {snap.price if snap.price is not None else '?'}"
        if snap.in_stock is not None:
            base += f", {'in stock' if snap.in_stock else 'out of stock'}"
        return base
    prev_price, prev_stock = prev
    msgs: list[str] = []
    if snap.price is not None and prev_price is not None and snap.price != prev_price:
        arrow = "dropped" if snap.price < prev_price else "rose"
        pct = (snap.price - prev_price) / prev_price * 100 if prev_price else 0
        msgs.append(f"price {arrow} {prev_price} -> {snap.price} ({pct:+.1f}%)")
    if snap.in_stock is not None and prev_stock is not None and snap.in_stock != prev_stock:
        msgs.append("back in stock" if snap.in_stock else "went out of stock")
    return f"{product.name}: " + "; ".join(msgs) if msgs else None


def notify_webhook(url: str, text: str) -> None:
    try:
        requests.post(url, json={"text": text}, timeout=10)
    except requests.RequestException as e:
        print(f"  ! webhook failed: {e}", file=sys.stderr)


def run_once(products: list[Product], settings: dict, conn: sqlite3.Connection) -> list[str]:
    changes: list[str] = []
    webhook = settings.get("webhook_url")
    delay = settings.get("request_delay", 1.0)
    for product in products:
        try:
            html = fetch(
                product.url,
                settings.get("timeout", 20),
                settings.get("retries", 2),
                settings.get("backoff", 1.0),
            )
            snap = extract(html, product)
        except RuntimeError as e:
            print(f"  ! {product.name}: {e}", file=sys.stderr)
            continue
        prev = last_snapshot(conn, product.name)
        msg = diff_message(product, prev, snap)
        save_snapshot(conn, product, snap)
        if msg:
            print(f"  * {msg}")
            changes.append(msg)
            if webhook and prev is not None:
                notify_webhook(webhook, msg)
        else:
            price = snap.price if snap.price is not None else "?"
            print(f"    {product.name}: {price} (no change)")
        time.sleep(delay)
    return changes


def selftest() -> int:
    """Price parsing, extraction and change detection are tested offline; fetching is not."""
    checks, failures = 0, []

    def check(label, condition):
        nonlocal checks
        checks += 1
        if not condition:
            failures.append(label)

    check("plain price", parse_price("$19.99") == 19.99)
    check("thousands separator", parse_price("$1,299.00") == 1299.0)
    check("european decimal comma", parse_price("1.299,50 €") == 1299.50)
    check("bare decimal comma", parse_price("19,99 €") == 19.99)
    check("thousands comma without decimals", parse_price("1,299") == 1299.0)
    check("non-breaking space survives", parse_price("1\xa0299.00") == 1299.0)
    check("no digits means no price", parse_price("Call for price") is None)
    check("empty means no price", parse_price("") is None)

    page = """
        <div class="price">  $1,299.00  </div>
        <span id="avail">In Stock — ships today</span>
    """
    product = Product(name="Widget", url="https://example.invalid/w",
                      price_selector=".price", stock_selector="#avail")
    snap = extract(page, product)
    check("price read through the selector", snap.price == 1299.0)
    check("raw price kept for auditing", "1,299.00" in snap.raw_price)
    check("stock text matched case-insensitively", snap.in_stock is True)

    out = extract('<div class="price">$5</div><span id="avail">Sold out</span>', product)
    check("absent stock wording reads as out of stock", out.in_stock is False)

    missing = extract("<div>nothing here</div>", product)
    check("a missing selector is not a crash", missing.price is None)
    check("unknown stock stays unknown, not False", missing.in_stock is None)

    first = diff_message(product, None, snap)
    check("first sighting announces tracking", "tracking started" in first)

    check("no change stays silent", diff_message(product, (1299.0, True), snap) is None)

    drop = diff_message(product, (1499.0, True), snap)
    check("a drop is named a drop", "dropped" in drop)
    check("the move is shown as a percentage", "-13.3%" in drop)
    rise = diff_message(product, (1000.0, True), snap)
    check("a rise is named a rise", "rose" in rise and "+29.9%" in rise)

    back = diff_message(product, (1299.0, False), snap)
    check("restock is reported", "back in stock" in back)
    gone = diff_message(product, (5.0, True), out)
    check("going out of stock is reported", "went out of stock" in gone)

    conn = db_connect(":memory:")
    check("empty history has no previous snapshot", last_snapshot(conn, "Widget") is None)
    save_snapshot(conn, product, snap)
    check("history round-trips price and stock", last_snapshot(conn, "Widget") == (1299.0, True))
    save_snapshot(conn, product, missing)
    check("unknown stock round-trips as None", last_snapshot(conn, "Widget") == (None, None))
    check("history is per product", last_snapshot(conn, "Other") is None)

    print(f"selftest: {checks - len(failures)}/{checks} passed")
    for failure in failures:
        print("  FAILED:", failure)
    return 1 if failures else 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Watch product pages for price and stock changes.")
    ap.add_argument("--config", default="products.yaml", help="YAML config file")
    ap.add_argument("--db", default="history.db", help="SQLite history file")
    ap.add_argument("--once", action="store_true", help="run a single check and exit (default)")
    ap.add_argument("--watch", action="store_true", help="loop forever")
    ap.add_argument("--interval", type=int, default=3600, help="seconds between checks in --watch mode")
    ap.add_argument("--selftest", action="store_true", help="run offline checks and exit")
    args = ap.parse_args()

    if args.selftest:
        raise SystemExit(selftest())

    products, settings = load_config(args.config)
    if not products:
        sys.exit("No products in config.")
    conn = db_connect(args.db)

    def cycle() -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"[{stamp}] checking {len(products)} product(s)...")
        run_once(products, settings, conn)

    cycle()
    if args.watch:
        try:
            while True:
                time.sleep(args.interval)
                cycle()
        except KeyboardInterrupt:
            print("\nstopped.")


if __name__ == "__main__":
    main()
