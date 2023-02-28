#!/usr/bin/env python3

import json

from typing import NewType, TypedDict

import msgspec

from datetime import datetime

from msgspec import Struct
from eth_utils import to_int, is_hex
from eth_typing import (
    Address,
    ChecksumAddress,
    HexStr,
)


TxParams = TypedDict(
    "TxParams",
    {
        "chain_id": int,
        "data": bytes | HexStr,
        # addr or ens
        "from": Address| ChecksumAddress | str,
        "gas": int,
        # legacy pricing
        "gas_price": int,
        "nonce": int,
        # addr or ens
        "to": Address | ChecksumAddress | str,
        "type": int | HexStr,
        "value": int,
    },
    total=False,
)


class ChainOptions(TypedDict):
    chain_id: int


class JSONRPCResult(Struct):
    id: int
    jsonrpc: str = '2.0'
    result: dict | None = None
    error: dict | None = None


class Transaction(Struct):
    block_hash: HexStr
    block_number: int
    sender: ChecksumAddress
    gas: int
    gas_price: int
    hash: HexStr
    input: HexStr
    nonce: int
    to: ChecksumAddress
    transaction_index: int
    value: HexStr
    v: int
    r: HexStr
    s: HexStr

    @staticmethod
    def from_json(obj):
        return Transaction(
            block_hash=obj['blockHash'],
            block_number=to_int(hexstr=obj['blockNumber']),
            sender=obj['from'],
            gas=to_int(hexstr=obj['gas']),
            gas_price=to_int(hexstr=obj['gasPrice']),
            hash=obj['hash'],
            input=obj['input'],
            nonce=to_int(hexstr=obj['nonce']),
            to=obj['to'],
            transaction_index=to_int(hexstr=obj['transactionIndex']),
            value=obj['value'],
            v=to_int(hexstr=obj['v']),
            r=obj['r'],
            s=obj['s']
        )

    def to_dict(self):
        return json.loads(msgspec.json.encode(self))


class Block(Struct):
    mix_hash: str
    size: int
    total_difficulty: int
    uncles: list
    difficulty: int
    extra_data: str
    gas_limit: int
    miner: str
    nonce: int
    parent_hash: str
    receipts_root: str
    sha_3_uncles: str
    state_root: str
    transactions_root: str
    gas_used: int
    hash: str
    logs_bloom: str
    number: int
    timestamp: float
    transactions: list[Transaction]

    @staticmethod
    def from_json(obj):

        timestamp = obj['timestamp']
        if isinstance(timestamp, str):
            if is_hex(timestamp):
                timestamp = to_int(hexstr=timestamp)

            else:
                timestamp = datetime.fromisoformat(timestamp)

        elif not isinstance(timestamp, int) and not isinstance(timestamp, float):
            raise ValueError(f'Unsupported timestamp type: {timestamp}')


        return Block(
            mix_hash=obj['mixHash'],
            size=to_int(hexstr=obj['size']),
            total_difficulty=to_int(hexstr=obj['totalDifficulty']),
            uncles=obj['uncles'],
            difficulty=to_int(hexstr=obj['difficulty']),
            extra_data=obj['extraData'],
            gas_limit=to_int(hexstr=obj['gasLimit']),
            miner=obj['miner'],
            nonce=to_int(hexstr=obj['nonce']),
            parent_hash=obj['parentHash'],
            receipts_root=obj['receiptsRoot'],
            sha_3_uncles=obj['sha3Uncles'],
            state_root=obj['stateRoot'],
            transactions_root=obj['transactionsRoot'],
            gas_used=to_int(hexstr=obj['gasUsed']),
            hash=obj['hash'],
            logs_bloom=obj['logsBloom'],
            number=to_int(hexstr=obj['number']),
            timestamp=to_int(hexstr=obj['timestamp']),
            transactions=[Transaction.from_json(tx) for tx in obj['transactions']]
        )

    def to_dict(self):
        return json.loads(msgspec.json.encode(self))
