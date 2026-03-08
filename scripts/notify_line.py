#!/usr/bin/env python3
"""LINE通知スクリプト（LINE Notify終了のためスキップ）"""
import argparse
import sys

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--type', default='info')
    parser.add_argument('--message', default='')
    parser.add_argument('--poem', default='')
    parser.add_argument('--filter', default='')
    args = parser.parse_args()
    print(f"通知スキップ（LINE Notify終了）: type={args.type}")

if __name__ == "__main__":
    main()
