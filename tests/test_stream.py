#!/usr/bin/env python3

import logging

import trio


async def test_stream_old_range(w3):
    last_block = None
    start_block = 180698860
    async with w3.stream_blocks(
        start_block,
        end_block=start_block + 100,
        max_tasks=50
    ) as stream:
        async for block in stream:

            logging.info(f'got block {block.number}')

            # ensure order
            if last_block:
                assert block.number - last_block.number <= 1
                assert block.timestamp - last_block.timestamp <= 1

            last_block = block


async def test_stream_catch_up(w3):
    amount = 50
    last_block = None
    head_block = await w3.block_number()
    start_block = head_block - amount
    end_block = head_block + amount
    async with w3.stream_blocks(
        start_block,
        end_block=end_block
    ) as stream:
        async for block in stream:

            logging.info(f'got block {block.number}')

            # ensure order
            if last_block:
                assert block.number - last_block.number <= 1
                assert block.timestamp - last_block.timestamp <= 1

            last_block = block

async def test_stream_latest_blocks(w3):
    i = 0
    last_block = None
    start_num = None

    async with w3.stream_blocks('latest') as stream:
        async for block in stream:
            if not start_num:
                start_num = block.number

            logging.info(f'got block {block.number}')

            # ensure order
            if last_block:
                assert block.number - last_block.number <= 1
                assert block.timestamp - last_block.timestamp <= 1

            if block.number >= start_num + 20:
                break

            last_block = block
