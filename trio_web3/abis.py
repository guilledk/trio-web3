#!/usr/bin/env python3

import json

from pathlib import Path


ABI_DIR = Path(__file__).parent.parent / 'abis'

def standard_interfaces():
    abis = {}

    for p in ABI_DIR.glob('*.json'):
        with open(p, 'r') as abi_file:
            abis[p.stem] = json.loads(abi_file.read())

    return abis
