#!/usr/bin/env python3

from typing import Any, Sequence

from eth_abi.codec import (
    ABICodec,
)

from eth_typing import (
    HexStr,
    TypeStr,
    ChecksumAddress
)

from trio_web3.types import ChainOptions
from trio_web3.contract.abi import ABI, prepare_transaction


class Contracts:

    def __init__(
        self,
        codec: ABICodec,
        options: ChainOptions
    ):
        self.codec = codec
        self.options = options

        self._contracts = {}

    def add_contract(
        self,
        address: ChecksumAddress,
        abi: ABI
    ):
        self._contracts[address] = {
            'abi': abi
        }

    def prepare_fn_call(
        self,
        contract_address: ChecksumAddress,
        fn_id: str,
        from_address: ChecksumAddress,
        nonce: int,
        gas: int = 21000,
        gas_price: int = 2000000,
        value: int = 0,
        fn_args: Sequence[Any] | None = None,
        fn_kwargs: Sequence[Any] | None = None,
    ):
        return prepare_transaction(
            contract_address,
            fn_id,
            self._contracts[contract_address]['abi'],
            self.codec,
            transaction={
                'chain_id': self.options['chain_id'],
                'from': from_address,
                'gas': 21000,
                'gas_price': 2000000,
                'nonce': nonce,
                'type': 0,
                'value': value
            },
            fn_args=fn_args,
            fn_kwargs=fn_kwargs
        )
