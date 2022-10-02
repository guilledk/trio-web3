#!/usr/bin/env python3

from functools import partial

import trio

from .contract import AsyncContract


class AsyncWeb3:

    def __init__(self, w3):
        self._w3 = w3

    def contract(self, *args, **kwargs):
        return AsyncContract(
            self._w3.eth.contract(*args, **kwargs))

    async def is_connected(self):
        return await trio.to_thread.run_sync(
            self._w3.isConnected)

    async def get_block(self, *args, **kwargs):
        return await trio.to_thread.run_sync(
            partial(self._w3.eth.get_block, *args, **kwargs))
