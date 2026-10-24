#!/usr/bin/env python3
"""Prepare the ASR cache online once, then validate entirely offline."""
import argparse
from pathlib import Path
from gateway.asr_cache import ensure
parser=argparse.ArgumentParser();parser.add_argument('--offline',action='store_true');args=parser.parse_args()
print('SenseVoice ready:',ensure(Path(__file__).resolve().parents[1],offline=args.offline))
