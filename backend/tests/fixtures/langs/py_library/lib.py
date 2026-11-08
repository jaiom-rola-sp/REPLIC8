"""A small billing library, written the way old Python 3 code usually is."""
import datetime
import os
import sys
from decimal import Decimal

print("module loaded")  # runs on import; must never reach the caller


def invoice_total(quantity, unit_price, tax_rate=0.1):
    return {"total": round(quantity * unit_price * (1 + tax_rate), 2)}


def typed(a: int, b: str = "x", *rest, **extra):
    return {"a": a, "b": b}


def keyword_only(a, *, mode="fast"):
    return {"a": a, "mode": mode}


def list_items(customer):
    return [{"sku": "A1", "qty": 2}, {"sku": "B7", "qty": 1}]


def customer_name(customer_id):
    return "ACME Corp"


def noisy(x):
    print("debug output")
    os.write(1, b"raw write\n")
    return {"x": x}


def broken(x):
    raise ValueError("secret detail")


def exits(x):
    sys.exit(3)


def reads_stdin():
    return {"line": input()}


def fancy(x):
    return {"when": datetime.date(2026, 11, 7), "amount": Decimal("12.50"), "tags": {"b", "a"}}


def not_json(x):
    return {"value": float("nan")}


def _private():
    return 1
