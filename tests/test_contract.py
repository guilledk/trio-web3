#!/usr/bin/env python3


async def test_contract_async_call(w3, erc20_info):
    addr, abi = erc20_info

    contract = w3.contract(address=addr, abi=abi)

    sync_resp = contract._contract.functions.totalSupply().call()

    assert sync_resp == (await contract.call('totalSupply'))
