#!/usr/bin/env python3

import logging

import trio


async def test_stream_old_range(w3):
    last_block = None
    start_block = 180698860
    async with w3.stream_blocks(
        start_block,
        end_block=start_block + 100
    ) as stream:
        async for block in stream:
            assert 'mixHash' in block
            assert 'size' in block
            assert 'totalDifficulty' in block
            assert 'uncles' in block
            assert 'difficulty' in block
            assert 'extraData' in block
            assert 'gasLimit' in block
            assert 'miner' in block
            assert 'nonce' in block
            assert 'parentHash' in block
            assert 'receiptsRoot' in block
            assert 'sha3Uncles' in block
            assert 'stateRoot' in block
            assert 'transactionsRoot' in block
            assert 'gasUsed' in block
            assert 'hash' in block
            assert 'logsBloom' in block
            assert 'number' in block
            assert 'timestamp' in block
            assert 'transactions' in block

            logging.info(f'got block {block.number.real}')

            # ensure order
            if last_block:
                assert block.number.real - last_block.number.real <= 1
                assert block.timestamp - last_block.timestamp <= 1

            last_block = block


async def test_stream_catch_up(w3):
    last_block = None
    head_block = await w3.block_number()
    start_block = head_block - 49
    end_block = head_block + 50
    async with w3.stream_blocks(
        start_block,
        end_block=end_block
    ) as stream:
        async for block in stream:
            assert 'mixHash' in block
            assert 'size' in block
            assert 'totalDifficulty' in block
            assert 'uncles' in block
            assert 'difficulty' in block
            assert 'extraData' in block
            assert 'gasLimit' in block
            assert 'miner' in block
            assert 'nonce' in block
            assert 'parentHash' in block
            assert 'receiptsRoot' in block
            assert 'sha3Uncles' in block
            assert 'stateRoot' in block
            assert 'transactionsRoot' in block
            assert 'gasUsed' in block
            assert 'hash' in block
            assert 'logsBloom' in block
            assert 'number' in block
            assert 'timestamp' in block
            assert 'transactions' in block

            logging.info(f'got block {block.number.real}')

            # ensure order
            if last_block:
                assert block.number.real - last_block.number.real <= 1
                assert block.timestamp - last_block.timestamp <= 1

            last_block = block

async def test_stream_latest_blocks(w3):
    i = 0
    last_block = None
    start_num = None

    async with w3.stream_blocks('latest') as stream:
        async for block in stream:
            assert 'mixHash' in block
            assert 'size' in block
            assert 'totalDifficulty' in block
            assert 'uncles' in block
            assert 'difficulty' in block
            assert 'extraData' in block
            assert 'gasLimit' in block
            assert 'miner' in block
            assert 'nonce' in block
            assert 'parentHash' in block
            assert 'receiptsRoot' in block
            assert 'sha3Uncles' in block
            assert 'stateRoot' in block
            assert 'transactionsRoot' in block
            assert 'gasUsed' in block
            assert 'hash' in block
            assert 'logsBloom' in block
            assert 'number' in block
            assert 'timestamp' in block
            assert 'transactions' in block

            if not start_num:
                start_num = block.number.real

            logging.info(f'got block {block.number.real}')

            # ensure order
            if last_block:
                assert block.number.real - last_block.number.real <= 1
                assert block.timestamp - last_block.timestamp <= 1

            if block.number.real >= start_num + 100:
                break

            last_block = block
