#!/usr/bin/env python3

import logging

from typing import Any, Sequence
from itertools import count
from contextlib import asynccontextmanager as acm, aclosing

import trio
import httpx

from eth_abi.codec import (
    ABICodec,
)
from eth_typing import (
    HexStr,
    TypeStr,
    ChecksumAddress
)

from trio_web3.types import (
    JSONRPCResult, Block, ChainOptions,
)
from trio_web3.contract.abi import (
    ABI, prepare_transaction, build_default_registry, decode_function_input
)


class AsyncWeb3:

    def __init__(self, endpoint: str, options: ChainOptions):
        self.endpoint = endpoint
        self.options = options

        self._client = httpx.AsyncClient()
        self._rpc_id: Iterable = count(0)

        # contracts impl
        self._registry = build_default_registry()
        self._codec = ABICodec(self._registry)
        self._contracts = {}

    async def __aenter__(self):
        self._client = self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._client.__aexit__(exc_type, exc, tb)

    async def json_rpc(self, method: str, params: list = []) -> dict:
        resp = (await self._client.post(
            self.endpoint,
            json={
                'jsonrpc': '2.0',
                'method': method,
                'params': params,
                'id': next(self._rpc_id)
            }
        )).json()

        resp = JSONRPCResult(**resp)
        if resp.error:
            raise ValueError(resp)

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
        async def block_task(block_number, event):
            for i in range(8):
                try:
                    block = await self.get_block(block_number, full_transactions=full)

                    if block == None:
                        raise ValueError('Block not found')

                    if block.timestamp == 0:
                        raise ValueError('timestamp == 0 in block')

                    break

                except ValueError:
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
        self._contracts[address] = {
            'abi': abi
        }

    def _prepare_fn_call(
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
            self._codec,
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

    def decode_fn_input(
        self,
        contract_address: ChecksumAddress,
        data: HexStr
    ):
        return decode_function_input(
            self._contracts[contract_address]['abi'],
            contract_address,
            data,
            self._codec
        )

    async def eth_call(self, *args, **kwargs):
        resp = (await self._client.post(
            self.endpoint,
            json={
                'jsonrpc': '2.0',
                'method': 'eth_call',
                'params': [self._prepare_fn_call(*args, **kwargs)],
                'id': 1
            })).json()

        return JSONRPCResult(**resp)

