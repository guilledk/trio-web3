#!/usr/bin/env python3

ZERO_ADDR = '0x0000000000000000000000000000000000000000'


async def test_contract_async_call(w3, erc20_info):
    addr, abi = erc20_info
    w3.add_contract(addr, abi)

    result = await w3.eth_call(
        addr,
        'name',
        ZERO_ADDR,
        1
    )

    assert 'Tether USD' in result


async def test_contract_async_call_with_param(w3, erc20_info):
    addr, abi = erc20_info
    w3.add_contract(addr, abi)

    result = await w3.eth_call(
        addr,
        'balanceOf',
        ZERO_ADDR,
        1,
        fn_args=('0x51DFB88958df54E357fBAcC8516194944E389Ce2',)
    )

    assert result != 0
