#!/usr/bin/env python3

import logging

from typing import Any, Sequence
from itertools import count
from contextlib import asynccontextmanager as acm, aclosing

import asks
import trio

from web3.types import (
    ABI
)
from eth_utils import (
    decode_hex,
    is_hexstr
)
from eth_typing import (
    HexStr,
    TypeStr,
    ChecksumAddress
)

from trio_web3.types import (
    JSONRPCResult, Block, ChainOptions,
)

from .contract import (
    DummyW3,
    W3Contract,
    call_contract_function
)


class AsyncWeb3:

    def __init__(self, endpoint: str, options: ChainOptions):
        self.endpoint = endpoint
        self.options = options

        self._rpc_id: Iterable = count(0)
        self._session = asks.Session(connections=200)

        # contracts impl
        self._web3 = DummyW3()
        self._contracts = {}

    async def json_rpc(
        self,
        method: str,
        params: list = [],
        decode: bool = False
    ) -> dict:

        resp = await self._session.post(
            self.endpoint,
            json={
                'jsonrpc': '2.0',
                'method': method,
                'params': params,
                'id': next(self._rpc_id)
            },
            retries=3
        )

        resp = JSONRPCResult(**resp.json())
        if resp.error:
            raise ValueError(resp)

        if decode and is_hexstr(resp.result):
            return decode_hex(resp.result)

        else:
            return resp

    async def chain_id(self):
        return (await self.json_rpc('eth_chainId')).result

    async def block_number(self):
        return int((await self.json_rpc('eth_blockNumber')).result, 0)

    async def get_block(
        self,
        block_num: int | str = 'latest',
        full_transactions: bool = True
    ):
        resp = await self.json_rpc(
            'eth_getBlockByNumber',
            [block_num, full_transactions])

        if resp.result:
            return Block.from_json(resp.result)

        else:
            return None

    async def _stream_blocks(
        self,
        # can be 'latest', 'earliest', 'pending', a block number or a hash
        start_block: str | int = 'latest',
        end_block: str | int | None = None,
        full: bool = True,
        max_tasks: int = 10
    ):
        start_block = await self.get_block(start_block, full_transactions=full)

        if not start_block:
            raise ValueError('Couldn\t find start block')

        yield start_block

        start_block = start_block.number

        if not end_block:
            end_block = 2 ** 64

        head_block = await self.block_number()
        need_head_updates = end_block > head_block

        async def head_block_updater():
            while need_head_updates:
                await trio.sleep(2)
                head_block = await self.block_number()

        send_channel, receive_channel = trio.open_memory_channel(max_tasks)
        async def block_task(block_number, event, retry=8):
            for i in range(retry):
                block = await self.get_block(block_number, full_transactions=full)

                if block == None or block.timestamp == 0:
                    continue

                break

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
                    pending[block.number] = block

                    while looking_for in pending:
                        yield pending.pop(looking_for)
                        if looking_for == end_block:
                            break
                        looking_for += 1

            # just to be sure
            need_head_updates = False

    @acm
    async def stream_blocks(self, *args, **kwargs):
        async with aclosing(
            self._stream_blocks(*args, **kwargs)
        ) as wrapped_stream:
            yield wrapped_stream

    def add_contract(
        self,
        address: ChecksumAddress,
        abi: ABI
    ):
        self._contracts[address] = W3Contract(
            self._web3,
            address,
            abi
        )

    def decode_fn_input(
        self,
        contract_address: ChecksumAddress,
        data: HexStr
    ):
        return self._contracts[contract_address].decode_function_input(data)

    async def eth_call(
        self,
        contract_address: ChecksumAddress,
        fn_id: str,
        from_address: ChecksumAddress,
        nonce: int,
        gas: int = 21000,
        gas_price: int = 2000000,
        value: int = 0,
        fn_args=(),
        fn_kwargs=()
    ):
        return await call_contract_function(
            self._web3,
            contract_address,
            [],
            fn_id,
            {
                'chain_id': self.options['chain_id'],
                'from': from_address,
                'gas': 21000,
                'gas_price': 2000000,
                'nonce': nonce,
                'type': 0,
                'value': value
            },
            self.json_rpc,
            fn_args, fn_kwargs,
            contract_abi=self._contracts[contract_address].abi,
        )
