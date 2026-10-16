"""Reload DEV UI in place, or stop DEV after removing its notification icon."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop_dev_control import send_command


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('reload', 'stop'))
    parser.add_argument('--pid', type=int, required=True)
    args = parser.parse_args()
    sent = send_command(args.action, args.pid)
    print(json.dumps({'sent':sent, 'action':args.action, 'pid':args.pid}))
    raise SystemExit(0 if sent else 1)
