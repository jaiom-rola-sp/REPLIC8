import argparse

parser = argparse.ArgumentParser()
parser.add_argument("customer")
args = parser.parse_args()
print("customer:", args.customer)
print("open_orders:", 3)
