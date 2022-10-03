#!/usr/bin/env python3

import logging

from typing import Optional
from functools import partial
from contextlib import aclosing, asynccontextmanager

import web3
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

    async def chain_id(self):
        return await trio.to_thread.run_sync(
            self._w3.eth._chain_id)

    async def block_number(self):
        return await trio.to_thread.run_sync(
            self._w3.eth.get_block_number)

    async def get_block(self, *args, **kwargs):
        return await trio.to_thread.run_sync(
            partial(self._w3.eth.get_block, *args, **kwargs))

    async def _stream_blocks(
        self,
        # can be 'latest', 'earliest', 'pending', a block number or a hash
        start_block: str | int = 'latest',
        end_block: Optional[str | int] = None,
        full: bool = True,
        max_tasks: int = 10
    ):
        if start_block == 'latest':
            start_block = await self.block_number()

        start_block = await self.get_block(start_block, full_transactions=full)

        yield start_block

        start_block = start_block.number.real

        if end_block:
            end_block = (await self.get_block(end_block, full_transactions=full)).number.real
        else:
            end_block = 2 ** 64

        head_block = await self.block_number()
        need_head_updates = end_block > head_block

        async def head_block_updater():
            while need_head_updates:
                await trio.sleep(2)
                head_block = await self.block_number()

        send_channel, receive_channel = trio.open_memory_channel(max_tasks)
        async def block_task(block_number, event):
            for i in range(5):
                try:
                    block = await self.get_block(block_number, full_transactions=full)

                    if block.timestamp == 0:
                        raise web3.exceptions.BlockNotFound('timestamp == 0 in block')

                except web3.exceptions.BlockNotFound:
                    await trio.sleep(.5)

            await send_channel.send(block)
            event.set()

        current_block = start_block
        async with trio.open_nursery() as n:

            n.start_soon(head_block_updater)

            async def block_task_spawner():
                nonlocal max_tasks
                nonlocal current_block
                tasks = []
                async with send_channel:
                    while current_block != end_block:

                        if head_block - current_block <= 3:
                            need_head_updates = False
                            max_tasks = 3

                        next_block_num = current_block + 1

                        if len(tasks) > max_tasks:
                            await tasks[0].wait()
                            tasks.pop(0)

                        event = trio.Event()
                        tasks.append(event)
                        n.start_soon(block_task, next_block_num, event)

                        current_block = next_block_num

                    for task in tasks:
                        await task.wait()


            n.start_soon(block_task_spawner)

            looking_for = start_block + 1
            pending = {}
            async with receive_channel:
                async for block in receive_channel:
                    pending[block.number.real] = block

                    while looking_for in pending:
                        yield pending.pop(looking_for)
                        if looking_for == end_block:
                            break
                        looking_for += 1

            # just to be sure
            need_head_updates = False

    @asynccontextmanager
    async def stream_blocks(self, *args, **kwargs):
        async with aclosing(
            self._stream_blocks(*args, **kwargs)
        ) as wrapped_stream:
            yield wrapped_stream
