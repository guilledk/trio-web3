#!/usr/bin/env python3


async def test_get_block(w3):

    block = await w3.get_block(
        'latest', full_transactions=True)

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
