#!/usr/bin/env python3
"""Generate Brightwell's orders, the dataset the series shares from post 04 on.

Usage: python3 scripts/make_orders.py agentcore/04-builtin-tools

Deterministic, seeded, so re-running it changes nothing. Writes two files:

  tool/orders.csv   the retailer's system of record, served by the tool Lambda
  payload.json      one customer's charges export, the input to the post 04 demo,
                    with the two discrepancies the post walks through baked in

Order ids are not dates. They are allocated in placement order but the dataset
spans January to August 2026, so a reader sorting by either column sees
something that looks like a shop rather than a loop.
"""

import csv
import json
import pathlib
import random
import sys
from datetime import date, datetime, timedelta

SEED = 20260821
ORDERS = 300
CUSTOMERS = 40
FIRST_ID = 1001
START = date(2026, 1, 5)
END = date(2026, 8, 20)

# Roughly what a small outdoor retailer sells, with price bands that make the
# totals plausible rather than uniform.
CATALOGUE = [
    ("wool socks", 12.00), ("dry bag 10L", 18.50), ("head torch", 24.99),
    ("trail map", 9.95), ("gas canister", 6.80), ("base layer", 34.00),
    ("waterproof jacket", 129.00), ("walking poles", 58.00), ("sleeping mat", 72.50),
    ("two-person tent", 189.00), ("stove", 44.10), ("water filter", 39.00),
]
CARRIERS = ["DPD", "DPD", "DPD", "Royal Mail", "Royal Mail"]  # DPD-weighted
# The demo's customer is the first one, by id, with enough history to make a
# reconciliation worth reading: six or more orders, two or more of them in
# March, so "charged twice in March" has somewhere to happen.
MIN_ORDERS, MIN_MARCH = 6, 2


def main():
    demo = pathlib.Path(sys.argv[1].rstrip("/"))
    rng = random.Random(SEED)
    span = (END - START).days

    customers = [f"c-{1000 + i}" for i in range(CUSTOMERS)]

    # Placement dates sorted so ids run in date order.
    placed = sorted(START + timedelta(days=rng.randint(0, span)) for _ in range(ORDERS))
    orders = []
    for i, day in enumerate(placed):
        items = rng.choices(CATALOGUE, k=rng.randint(1, 4))
        total = round(sum(price for _, price in items), 2)
        age = (END - day).days
        if age < 2:
            status, carrier, eta = "picking", "", (day + timedelta(days=3)).isoformat()
        elif age < 6:
            status, carrier, eta = "shipped", rng.choice(CARRIERS), (day + timedelta(days=4)).isoformat()
        else:
            status, carrier, eta = "delivered", rng.choice(CARRIERS), ""
        orders.append({
            "order_id": FIRST_ID + i,
            "customer_id": rng.choice(customers),
            "placed_at": day.isoformat(),
            "items": len(items),
            "total": f"{total:.2f}",
            "status": status,
            "carrier": carrier,
            "eta": eta,
        })

    def history(customer):
        mine = [o for o in orders if o["customer_id"] == customer]
        march = [o for o in mine if o["placed_at"].startswith("2026-03")]
        return mine, march

    demo_customer = next(
        (c for c in customers if len(history(c)[0]) >= MIN_ORDERS and len(history(c)[1]) >= MIN_MARCH),
        None,
    )
    if demo_customer is None:
        raise SystemExit("no customer has enough history under this seed, pick another")
    mine, march = history(demo_customer)

    tool = demo / "tool"
    tool.mkdir(exist_ok=True)
    with (tool / "orders.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(orders[0]))
        writer.writeheader()
        writer.writerows(orders)

    # The customer's export: one charge per order, taken the day it was placed,
    # except that the first March order was charged twice (a retried payment
    # that went through both times) and the last order was charged before a
    # discount code applied, so it is a few pounds over.
    charges = []
    twice = march[0]
    over = mine[-1]
    for o in mine:
        when = datetime.fromisoformat(o["placed_at"]).replace(hour=rng.randint(8, 21), minute=rng.randint(0, 59))
        amount = float(o["total"])
        if o is over:
            amount = round(amount + 5.00, 2)
        charges.append((o["order_id"], when.isoformat(timespec="minutes"), amount))
        if o is twice:
            retry = when + timedelta(minutes=rng.randint(2, 9))
            charges.append((o["order_id"], retry.isoformat(timespec="minutes"), amount))

    lines = ["order_id,charged_at,amount"] + [f"{oid},{when},{amt:.2f}" for oid, when, amt in charges]
    (demo / "payload.json").write_text(json.dumps({
        "actor": demo_customer,
        "session": "billing-query",
        "csv": "\n".join(lines) + "\n",
    }) + "\n")

    print(f"{len(orders)} orders, {len(customers)} customers, {START} to {END}")
    print(f"{demo_customer}: {len(mine)} orders, double charge on {twice['order_id']}, overcharge on {over['order_id']} (+5.00)")


if __name__ == "__main__":
    main()
