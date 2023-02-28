#!/usr/bin/env python3
import time


async def test_get_block(w3):

    block = await w3.get_block(
        'latest', full_transactions=True)

    assert time.time() - block.timestamp < 30
