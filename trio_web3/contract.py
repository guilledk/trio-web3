#!/usr/bin/env python3

from functools import partial

import trio

from web3 import Web3


class AsyncContract:

    def __init__(self, contract):
        self._contract = contract

    async def call(self, fn_name, *args, **kwargs):
        fn = getattr(self._contract.functions, fn_name)
        return await trio.to_thread.run_sync(
            partial(fn().call, *args, **kwargs))


