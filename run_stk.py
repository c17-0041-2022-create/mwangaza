#!/usr/bin/env python
"""One-off STK Push runner for local testing.

Usage:
  python run_stk.py <phone> <amount>

Examples:
  python run_stk.py 254712345678 1
"""
import argparse
import json
import sys

from daraja import initiate_stk_push


def main():
    parser = argparse.ArgumentParser(description='Run a single Daraja STK Push')
    parser.add_argument('phone', help='Phone number in format 2547XXXXXXXX')
    parser.add_argument('amount', type=int, help='Amount in KES')
    parser.add_argument('--account', default='TestPayment', help='Account reference')
    parser.add_argument('--desc', default='Test transaction', help='Transaction description')
    args = parser.parse_args()

    print(f"Sending STK Push to {args.phone} for KES {args.amount}...")
    try:
        resp = initiate_stk_push(args.phone, args.amount, args.account, args.desc)
        print('--- Daraja STK Push response ---')
        print(json.dumps(resp, indent=2, ensure_ascii=False))
        return 0
    except Exception as e:
        print('STK Push Exception:', str(e))
        # for debugging include full stack trace
        import traceback
        traceback.print_exc()
        return 2


if __name__ == '__main__':
    sys.exit(main())
