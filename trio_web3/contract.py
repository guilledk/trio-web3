#!/usr/bin/env python3

import trio

from web3 import Web3


class AsyncContract:

    def __init__(self, contract):
        self._contract = contract
        self.address = contract.address

    async def call(self, fn_name, *args, **kwargs):
        fn = getattr(self._contract.functions, fn_name)
        return await trio.to_thread.run_sync(
            fn(*args, **kwargs).call)


