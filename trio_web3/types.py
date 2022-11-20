#!/usr/bin/env python3

from typing import NewType, TypedDict

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
