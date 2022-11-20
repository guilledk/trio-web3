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

    w3.add_contract(addr, abi)

    result = (await w3.eth_call(
        addr,
        fn_id,
        '0x249767c5ad21de5ba684adf79907bc3ee9ff3197',
        1
    )).result

    output = decode_function_output(
        fn_id, result, abi, w3._codec)

    assert 'Tether USD' in output
