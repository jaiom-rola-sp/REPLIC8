"""A pricing helper that is both a library and a command-line tool."""
import sys


def price(sku):
    return {"sku": sku, "price": 4.5}


if __name__ == "__main__":
    print("sku:", sys.argv[1])
