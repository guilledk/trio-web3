#!/usr/bin/env python3

import httpx

from eth_abi.codec import (
    ABICodec,
)

from trio_web3.contract import Contracts
from trio_web3.contract.abi import build_default_registry, decode_function_output


async def test_contract_async_call(w3, erc20_info):
    addr, abi = erc20_info
    fn_id = 'name'
    codec = ABICodec(build_default_registry())

    contracts = Contracts(codec, options={'chain_id': 40})
    contracts.add_contract(addr, abi)

    tx = contracts.prepare_fn_call(
        addr,
        fn_id,
        '0x249767c5ad21de5ba684adf79907bc3ee9ff3197',
        1
    )

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            'https://mainnet.telos.net/evm',
            json={
                'jsonrpc': '2.0',
                'method': 'eth_call',
                'params': [tx],
                'id': 1
            })

    assert resp.status_code == 200

    resp = resp.json()
    result = resp['result']

    output = decode_function_output(
        fn_id, result, abi, codec)

    assert 'Tether USD' in output
