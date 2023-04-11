#!/usr/bin/env python3

import itertools

from typing import (
    Any,
    Tuple,
    Callable,
    Coroutine,
    Optional,
)

from eth_typing import (
    ChecksumAddress
)


from web3.types import (
    ABI,
    ABIFunction,
    FunctionIdentifier,
    TxParams,
)
from web3._utils.abi import (
    get_abi_output_types
)
from web3._utils.contracts import (
    encode_abi,
    find_matching_event_abi,
    find_matching_fn_abi,
    get_function_info,
    prepare_transaction,
    map_abi_data,
)

from web3._utils.normalizers import (
    BASE_RETURN_NORMALIZERS,
)

from web3.contract.contract import (
    Contract,
    ContractFunctions,
    # ContractCaller,
    ContractEvents,
)

from eth_abi.codec import (
    ABICodec,
)
from eth_abi.registry import (
    registry as default_registry,
)
from eth_abi.exceptions import (
    DecodingError,
)


class DummyEth:
    def __init__(self):
        self.is_async = False

class DummyW3:
    def __init__(self):
        self.codec = ABICodec(default_registry)
        self.eth = DummyEth()


class W3Contract(Contract):

    def __init__(
        self,
        w3: DummyW3,
        address: ChecksumAddress,
        abi: ABI
    ):
        self.web3 = w3
        self.abi = abi
        self.address = address
        self.bytecode = b''

        self.functions = ContractFunctions(self.abi, self.web3, self.address)
        # self.caller = ContractCaller(self.abi, self.web3, self.address)
        self.events = ContractEvents(self.abi, self.web3, self.address)
        self.fallback = Contract.get_fallback_function(self.abi, self.web3, self.address)
        self.receive = Contract.get_receive_function(self.abi, self.web3, self.address)


async def call_contract_function(
    web3: DummyW3,
    address: ChecksumAddress,
    normalizers: Tuple[Callable[..., Any], ...],
    function_identifier: FunctionIdentifier,
    transaction: TxParams,
    rpc_fn: Coroutine,
    fn_args: Any,
    fn_kwargs: Any,
    contract_abi: Optional[ABI] = None,
    fn_abi: Optional[ABIFunction] = None,
) -> Any:
    """
    Helper function for interacting with a contract function using the
    `eth_call` API.
    """
    tx = prepare_transaction(
        address,
        web3,
        fn_identifier=function_identifier,
        contract_abi=contract_abi,
        fn_abi=fn_abi,
        transaction=transaction,
        fn_args=fn_args,
        fn_kwargs=fn_kwargs,
    )

    return_data = await rpc_fn(
        'eth_call', [tx], decode=True
    )

    if fn_abi is None:
        fn_abi = find_matching_fn_abi(contract_abi, web3.codec, function_identifier, fn_args, fn_kwargs)

    output_types = get_abi_output_types(fn_abi)
    output_data = web3.codec.decode(output_types, return_data)

    _normalizers = itertools.chain(
        BASE_RETURN_NORMALIZERS,
        normalizers,
    )
    normalized_data = map_abi_data(_normalizers, output_types, output_data)

    if len(normalized_data) == 1:
        return normalized_data[0]
    else:
        return None
