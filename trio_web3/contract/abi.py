#!/usr/bin/env python3

import threading
import itertools
import functools

from typing import (
    Any,
    Callable,
    Collection,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Type,
    Union,
    Literal,
    TypedDict,
    TypeVar,
    cast
)
from collections import (
    abc,
    namedtuple,
)

from eth_abi import (
    codec,
    decoding,
    encoding,
)
from eth_abi.base import (
    parse_type_str
)
from eth_abi.codec import (
    ABICodec,
)
from eth_abi.grammar import (
    ABIType,
    BasicType,
    TupleType,
    parse,
)
from eth_abi.registry import (
    ABIRegistry,
    BaseEquals,
    registry as default_registry,
)
from hexbytes import (
    HexBytes,
)
from eth_utils import (
    add_0x_prefix,
    combomethod,
    encode_hex,
    function_abi_to_4byte_selector,
    is_list_like,
    is_text,
    to_tuple,
    remove_0x_prefix,
    to_bytes,
    to_hex,
)
from eth_utils.abi import (
    collapse_if_tuple,
)
from eth_utils.toolz import (
    curry,
    partial,
    pipe,
)
from eth_utils.curried import (
    apply_formatter_at_index,
    apply_formatter_if,
    apply_formatter_to_array,
    apply_formatters_to_dict,
    apply_formatters_to_sequence,
    apply_one_of_formatters,
    is_0x_prefixed,
    is_address,
    is_bytes,
    is_dict,
    is_integer,
    is_null,
    is_string,
    remove_0x_prefix,
    text_if_str,
    to_checksum_address,
    to_list,
    to_tuple,
)
from eth_typing import (
    HexStr,
    TypeStr,
    ChecksumAddress
)

from .normal import (
    abi_address_to_hex,
    abi_bytes_to_bytes,
    abi_ens_resolver,
    abi_string_to_text,
)
from ..types import TxParams


def hex_to_integer(value: HexStr) -> int:
    return int(value, 16)

def bytes_to_ascii(value: bytes) -> str:
    return codecs.decode(value, "ascii")

integer_to_hex = hex

to_ascii_if_bytes = apply_formatter_if(is_bytes, bytes_to_ascii)
to_integer_if_hex = apply_formatter_if(is_string, hex_to_integer)
to_hex_if_integer = apply_formatter_if(is_integer, integer_to_hex)

class ABIEventParams(TypedDict, total=False):
    indexed: bool
    name: str
    type: str


class ABIEvent(TypedDict, total=False):
    anonymous: bool
    inputs: Sequence["ABIEventParams"]
    name: str
    type: Literal["event"]


class ABIFunctionComponents(TypedDict, total=False):
    # better typed as Sequence['ABIFunctionComponents'], but recursion isnt possible yet
    # https://github.com/python/mypy/issues/731
    components: Sequence[Any]
    name: str
    type: str


class ABIFunctionParams(TypedDict, total=False):
    components: Sequence["ABIFunctionComponents"]
    name: str
    type: str


class ABIFunction(TypedDict, total=False):
    constant: bool
    inputs: Sequence["ABIFunctionParams"]
    name: str
    outputs: Sequence["ABIFunctionParams"]
    payable: bool
    stateMutability: Literal["pure", "view", "nonpayable", "payable"]
    type: Literal["function", "constructor", "fallback", "receive"]

class ABITypedData(namedtuple("ABITypedData", "abi_type, data")):
    """
    This class marks data as having a certain ABI-type.
    >>> a1 = ABITypedData(['address', addr1])
    >>> a2 = ABITypedData(['address', addr2])
    >>> addrs = ABITypedData(['address[]', [a1, a2]])
    You can access the fields using tuple() interface, or with
    attributes:
    >>> assert a1.abi_type == a1[0]
    >>> assert a1.data == a1[1]
    Unlike a typical `namedtuple`, you initialize with a single
    positional argument that is iterable, to match the init
    interface of all other relevant collections.
    """

    def __new__(cls, iterable: Iterable[Any]) -> "ABITypedData":
        return super().__new__(cls, *iterable)

ABIElement = Union[ABIFunction, ABIEvent]
ABI = Sequence[Union[ABIFunction, ABIEvent]]

def strip_abi_type(elements: Any) -> Any:
    if isinstance(elements, ABITypedData):
        return elements.data
    else:
        return elements

@to_tuple
def normalize_event_input_types(
    abi_args: Collection[Union[ABIFunction, ABIEvent]]
) -> Iterable[Union[ABIFunction, ABIEvent, Dict[TypeStr, Any]]]:
    for arg in abi_args:
        if is_recognized_type(arg["type"]):
            yield arg
        elif is_probably_enum(arg["type"]):
            yield {k: "uint8" if k == "type" else v for k, v in arg.items()}
        else:
            yield arg

def abi_to_signature(abi: Union[ABIFunction, ABIEvent]) -> str:
    function_signature = "{fn_name}({fn_input_types})".format(
        fn_name=abi["name"],
        fn_input_types=",".join(
            collapse_if_tuple(dict(arg))
            for arg in normalize_event_input_types(abi.get("inputs", []))
        ),
    )
    return function_signature

def get_abi_input_types(abi: ABIFunction) -> List[str]:
    if "inputs" not in abi and (abi["type"] == "fallback" or abi["type"] == "receive"):
        return []
    else:
        return [collapse_if_tuple(cast(Dict[str, Any], arg)) for arg in abi["inputs"]]


def get_abi_output_types(abi: ABIFunction) -> List[str]:
    if abi["type"] == "fallback":
        return []
    else:
        return [collapse_if_tuple(cast(Dict[str, Any], arg)) for arg in abi["outputs"]]

def _align_abi_input(arg_abi: ABIFunctionParams, arg: Any) -> Tuple[Any, ...]:
    """
    Aligns the values of any mapping at any level of nesting in ``arg``
    according to the layout of the corresponding abi spec.
    """
    tuple_parts = get_tuple_type_str_parts(arg_abi["type"])

    if tuple_parts is None:
        # Arg is non-tuple.  Just return value.
        return arg

    tuple_prefix, tuple_dims = tuple_parts
    if tuple_dims is None:
        # Arg is non-list tuple.  Each sub arg in `arg` will be aligned
        # according to its corresponding abi.
        sub_abis = arg_abi["components"]
    else:
        # Arg is list tuple.  A non-list version of its abi will be used to
        # align each element in `arg`.
        new_abi = copy.copy(arg_abi)
        new_abi["type"] = tuple_prefix

        sub_abis = itertools.repeat(new_abi)  # type: ignore

    if isinstance(arg, abc.Mapping):
        # Arg is mapping.  Align values according to abi order.
        aligned_arg = tuple(arg[abi["name"]] for abi in sub_abis)
    else:
        aligned_arg = arg

    if not is_list_like(aligned_arg):
        raise TypeError(
            f'Expected non-string sequence for "{arg_abi.get("type")}" '
            f"component type: got {aligned_arg}"
        )

    # convert NamedTuple to regular tuple
    typing = tuple if isinstance(aligned_arg, tuple) else type(aligned_arg)

    return typing(
        _align_abi_input(sub_abi, sub_arg)
        for sub_abi, sub_arg in zip(sub_abis, aligned_arg)
    )


def get_aligned_abi_inputs(
    abi: ABIFunction, args: Union[Tuple[Any, ...], Mapping[Any, Any]]
) -> Tuple[Tuple[Any, ...], Tuple[Any, ...]]:
    """
    Takes a function ABI (``abi``) and a sequence or mapping of args (``args``).
    Returns a list of type strings for the function's inputs and a list of
    arguments which have been aligned to the layout of those types.  The args
    contained in ``args`` may contain nested mappings or sequences corresponding
    to tuple-encoded values in ``abi``.
    """
    input_abis = abi.get("inputs", [])

    if isinstance(args, abc.Mapping):
        # `args` is mapping.  Align values according to abi order.
        args = tuple(args[abi["name"]] for abi in input_abis)

    return (
        # typed dict cannot be used w/ a normal Dict
        # https://github.com/python/mypy/issues/4976
        tuple(collapse_if_tuple(abi) for abi in input_abis),  # type: ignore
        type(args)(_align_abi_input(abi, arg) for abi, arg in zip(input_abis, args)),
    )

def merge_args_and_kwargs(
    function_abi: ABIFunction, args: Sequence[Any], kwargs: Dict[str, Any]
) -> Tuple[Any, ...]:
    """
    Takes a list of positional args (``args``) and a dict of keyword args
    (``kwargs``) defining values to be passed to a call to the contract function
    described by ``function_abi``.  Checks to ensure that the correct number of
    args were given, no duplicate args were given, and no unknown args were
    given.  Returns a list of argument values aligned to the order of inputs
    defined in ``function_abi``.
    """
    # Ensure the function is being applied to the correct number of args
    if len(args) + len(kwargs) != len(function_abi.get("inputs", [])):
        raise TypeError(
            f"Incorrect argument count. Expected '{len(function_abi['inputs'])}"
            f". Got '{len(args) + len(kwargs)}'"
        )

    # If no keyword args were given, we don't need to align them
    if not kwargs:
        return cast(Tuple[Any, ...], args)

    kwarg_names = set(kwargs.keys())
    sorted_arg_names = tuple(arg_abi["name"] for arg_abi in function_abi["inputs"])
    args_as_kwargs = dict(zip(sorted_arg_names, args))

    # Check for duplicate args
    duplicate_args = kwarg_names.intersection(args_as_kwargs.keys())
    if duplicate_args:
        raise TypeError(
            f"{function_abi.get('name')}() got multiple values for argument(s) "
            f"'{', '.join(duplicate_args)}'"
        )

    # Check for unknown args
    unknown_args = kwarg_names.difference(sorted_arg_names)
    if unknown_args:
        if function_abi.get("name"):
            raise TypeError(
                f"{function_abi.get('name')}() got unexpected keyword argument(s)"
                f" '{', '.join(unknown_args)}'"
            )
        raise TypeError(
            f"Type: '{function_abi.get('type')}' got unexpected keyword argument(s)"
            f" '{', '.join(unknown_args)}'"
        )

    # Sort args according to their position in the ABI and unzip them from their
    # names
    sorted_args = tuple(
        zip(
            *sorted(
                itertools.chain(kwargs.items(), args_as_kwargs.items()),
                key=lambda kv: sorted_arg_names.index(kv[0]),
            )
        )
    )

    if sorted_args:
        return sorted_args[1]
    else:
        return tuple()

def check_if_arguments_can_be_encoded(
    function_abi: ABIFunction,
    abi_codec: codec.ABIEncoder,
    args: Sequence[Any],
    kwargs: Dict[str, Any],
) -> bool:
    try:
        arguments = merge_args_and_kwargs(function_abi, args, kwargs)
    except TypeError:
        return False

    if len(function_abi.get("inputs", [])) != len(arguments):
        return False

    try:
        types, aligned_args = get_aligned_abi_inputs(function_abi, arguments)
    except TypeError:
        return False

    return all(
        abi_codec.is_encodable(_type, arg) for _type, arg in zip(types, aligned_args)
    )

class AddressEncoder(encoding.AddressEncoder):
    @classmethod
    def validate_value(cls, value: Any) -> None:
        if is_ens_name(value):
            return

        super().validate_value(value)


class AcceptsHexStrEncoder(encoding.BaseEncoder):
    subencoder_cls: Type[encoding.BaseEncoder] = None
    is_strict: bool = None

    def __init__(self, subencoder: encoding.BaseEncoder) -> None:
        self.subencoder = subencoder

    # type ignored b/c conflict w/ defined BaseEncoder.is_dynamic = False
    @property
    def is_dynamic(self) -> bool:  # type: ignore
        return self.subencoder.is_dynamic

    @classmethod
    def from_type_str(
        cls, abi_type: TypeStr, registry: ABIRegistry
    ) -> "AcceptsHexStrEncoder":
        subencoder_cls = cls.get_subencoder_class()
        # cast b/c expects BaseCoder but `from_type_string`
        # restricted to BaseEncoder subclasses
        subencoder = cast(
            encoding.BaseEncoder, subencoder_cls.from_type_str(abi_type, registry)
        )
        return cls(subencoder)

    @classmethod
    def get_subencoder_class(cls) -> Type[encoding.BaseEncoder]:
        if cls.subencoder_cls is None:
            raise AttributeError(f"No subencoder class is set. {cls.__name__}")
        return cls.subencoder_cls

    # type ignored b/c combomethod makes signature conflict
    # w/ defined BaseEncoder.validate_value()
    @combomethod
    def validate_value(self, value: Any) -> None:  # type: ignore
        normalized_value = self.validate_and_normalize(value)
        return self.subencoder.validate_value(normalized_value)

    def encode(self, value: Any) -> bytes:
        normalized_value = self.validate_and_normalize(value)
        return self.subencoder.encode(normalized_value)

    def validate_and_normalize(self, value: Any) -> HexStr:
        raw_value = value
        if is_text(value):
            try:
                value = decode_hex(value)
            except binascii.Error:
                self.invalidate_value(
                    value,
                    msg=f"{value} is an invalid hex string",
                )
            else:
                if raw_value[:2] != "0x":
                    if self.is_strict:
                        self.invalidate_value(
                            raw_value, msg="hex string must be prefixed with 0x"
                        )
                    elif raw_value[:2] != "0x":
                        warnings.warn(
                            "in v6 it will be invalid to pass a hex "
                            'string without the "0x" prefix',
                            category=DeprecationWarning,
                        )
        return value


class BytesEncoder(AcceptsHexStrEncoder):
    subencoder_cls = encoding.BytesEncoder
    is_strict = False


class ByteStringEncoder(AcceptsHexStrEncoder):
    subencoder_cls = encoding.ByteStringEncoder
    is_strict = False


class StrictByteStringEncoder(AcceptsHexStrEncoder):
    subencoder_cls = encoding.ByteStringEncoder
    is_strict = True


class ExactLengthBytesEncoder(encoding.BaseEncoder):
    # TODO: move this to eth-abi once the api is stabilized
    is_big_endian = False
    value_bit_size = None
    data_byte_size = None

    def validate(self) -> None:
        super().validate()

        if self.value_bit_size is None:
            raise ValueError("`value_bit_size` may not be none")
        if self.data_byte_size is None:
            raise ValueError("`data_byte_size` may not be none")
        if self.encode_fn is None:
            raise ValueError("`encode_fn` may not be none")
        if self.is_big_endian is None:
            raise ValueError("`is_big_endian` may not be none")

        if self.value_bit_size % 8 != 0:
            raise ValueError(
                f"Invalid value bit size: {self.value_bit_size}. "
                "Must be a multiple of 8"
            )

        if self.value_bit_size > self.data_byte_size * 8:
            raise ValueError("Value byte size exceeds data size")

    def encode(self, value: Any) -> bytes:
        normalized_value = self.validate_value(value)
        return self.encode_fn(normalized_value)

    # type ignored b/c conflict with defined BaseEncoder.validate_value() -> None
    def validate_value(self, value: Any) -> bytes:  # type: ignore
        if not is_bytes(value) and not is_text(value):
            self.invalidate_value(value)

        raw_value = value
        if is_text(value):
            try:
                value = decode_hex(value)
            except binascii.Error:
                self.invalidate_value(
                    value,
                    msg=f"{value} is not a valid hex string",
                )
            else:
                if raw_value[:2] != "0x":
                    self.invalidate_value(
                        raw_value, msg="hex string must be prefixed with 0x"
                    )

        byte_size = self.value_bit_size // 8
        if len(value) > byte_size:
            self.invalidate_value(
                value,
                exc=ValueOutOfBounds,
                msg=f"exceeds total byte size for bytes{byte_size} encoding",
            )
        elif len(value) < byte_size:
            self.invalidate_value(
                value,
                exc=ValueOutOfBounds,
                msg=f"less than total byte size for bytes{byte_size} encoding",
            )
        return value

    @staticmethod
    def encode_fn(value: Any) -> bytes:
        return value

    @parse_type_str("bytes")
    def from_type_str(cls, abi_type: BasicType, registry: ABIRegistry) -> bytes:
        # type ignored b/c kwargs are set in superclass init
        # Unexpected keyword argument "value_bit_size" for "__call__" of "BaseEncoder"
        return cls(  # type: ignore
            value_bit_size=abi_type.sub * 8,
            data_byte_size=abi_type.sub,
        )


class BytesDecoder(decoding.FixedByteSizeDecoder):
    # FixedByteSizeDecoder.is_big_endian is defined as None
    is_big_endian = False  # type: ignore

    # FixedByteSizeDecoder.decoder_fn is defined as None
    @staticmethod
    def decoder_fn(data: bytes) -> bytes:  # type: ignore
        return data

    @parse_type_str("bytes")
    def from_type_str(cls, abi_type: BasicType, registry: ABIRegistry) -> bytes:
        # type ignored b/c kwargs are set in superclass init
        # Unexpected keyword argument "value_bit_size" for "__call__" of "BaseDecoder"
        return cls(  # type: ignore
            value_bit_size=abi_type.sub * 8,
            data_byte_size=abi_type.sub,
        )


class TextStringEncoder(encoding.TextStringEncoder):
    @classmethod
    def validate_value(cls, value: Any) -> None:
        if is_bytes(value):
            try:
                value = to_text(value)
            except UnicodeDecodeError:
                cls.invalidate_value(
                    value,
                    msg="not decodable as unicode string",
                )

        super().validate_value(value)

def build_default_registry() -> ABIRegistry:
    # We make a copy here just to make sure that eth-abi's default registry is not
    # affected by our custom encoder subclasses
    registry = default_registry.copy()

    registry.unregister("address")
    registry.unregister("bytes<M>")
    registry.unregister("bytes")
    registry.unregister("string")

    registry.register(
        BaseEquals("address"),
        AddressEncoder,
        decoding.AddressDecoder,
        label="address",
    )
    registry.register(
        BaseEquals("bytes", with_sub=True),
        BytesEncoder,
        decoding.BytesDecoder,
        label="bytes<M>",
    )
    registry.register(
        BaseEquals("bytes", with_sub=False),
        ByteStringEncoder,
        decoding.ByteStringDecoder,
        label="bytes",
    )
    registry.register(
        BaseEquals("string"),
        TextStringEncoder,
        decoding.StringDecoder,
        label="string",
    )
    return registry

TReturn = TypeVar("TReturn")
TValue = TypeVar("TValue")

def map_collection(func: Callable[..., TReturn], collection: Any) -> Any:
    """
    Apply func to each element of a collection, or value of a dictionary.
    If the value is not a collection, return it unmodified
    """
    datatype = type(collection)
    if isinstance(collection, Mapping):
        return datatype((key, func(val)) for key, val in collection.items())
    if is_string(collection):
        return collection
    elif isinstance(collection, Iterable):
        return datatype(map(func, collection))
    else:
        return collection

def reject_recursive_repeats(to_wrap: Callable[..., Any]) -> Callable[..., Any]:
    """
    Prevent simple cycles by returning None when called recursively with same instance
    """
    # types ignored b/c dynamically set attribute
    to_wrap.__already_called = {}  # type: ignore

    @functools.wraps(to_wrap)
    def wrapped(*args: Any) -> Any:
        arg_instances = tuple(map(id, args))
        thread_id = threading.get_ident()
        thread_local_args = (thread_id,) + arg_instances
        if thread_local_args in to_wrap.__already_called:  # type: ignore
            raise ValueError(f"Recursively called {to_wrap} with {args!r}")
        to_wrap.__already_called[thread_local_args] = True  # type: ignore
        try:
            wrapped_val = to_wrap(*args)
        finally:
            del to_wrap.__already_called[thread_local_args]  # type: ignore
        return wrapped_val

    return wrapped

@reject_recursive_repeats
def recursive_map(func: Callable[..., TReturn], data: Any) -> TReturn:
    """
    Apply func to data, and any collection items inside data (using map_collection).
    Define func so that it only applies to the type of value that you
    want it to apply to.
    """

    def recurse(item: Any) -> TReturn:
        return recursive_map(func, item)

    items_mapped = map_collection(recurse, data)
    return func(items_mapped)

@curry
def data_tree_map(
    func: Callable[[TypeStr, Any], Tuple[TypeStr, Any]], data_tree: Any
) -> "ABITypedData":
    """
    Map func to every ABITypedData element in the tree. func will
    receive two args: abi_type, and data
    """

    def map_to_typed_data(elements: Any) -> "ABITypedData":
        if isinstance(elements, ABITypedData) and elements.abi_type is not None:
            return ABITypedData(func(*elements))
        else:
            return elements

    return recursive_map(map_to_typed_data, data_tree)

@curry
def abi_data_tree(types: Sequence[TypeStr], data: Sequence[Any]) -> List[Any]:
    """
    Decorate the data tree with pairs of (type, data). The pair tuple is actually an
    ABITypedData, but can be accessed as a tuple.
    As an example:
    >>> abi_data_tree(types=["bool[2]", "uint"], data=[[True, False], 0])
    [("bool[2]", [("bool", True), ("bool", False)]), ("uint256", 0)]
    """
    return [
        abi_sub_tree(data_type, data_value)
        for data_type, data_value in zip(types, data)
    ]

def map_abi_data(
    normalizers: Sequence[Callable[[TypeStr, Any], Tuple[TypeStr, Any]]],
    types: Sequence[TypeStr],
    data: Sequence[Any],
) -> Any:
    """
    This function will apply normalizers to your data, in the
    context of the relevant types. Each normalizer is in the format:
    def normalizer(datatype, data):
        # Conditionally modify data
        return (datatype, data)
    Where datatype is a valid ABI type string, like "uint".
    In case of an array, like "bool[2]", normalizer will receive `data`
    as an iterable of typed data, like `[("bool", True), ("bool", False)]`.
    Internals
    ---
    This is accomplished by:
    1. Decorating the data tree with types
    2. Recursively mapping each of the normalizers to the data
    3. Stripping the types back out of the tree
    """
    pipeline = itertools.chain(
        [abi_data_tree(types)],
        map(data_tree_map, normalizers),
        [partial(recursive_map, strip_abi_type)],
    )

    return pipe(data, *pipeline)

def encode_abi(
    abi_codec: ABICodec,
    abi: ABIFunction,
    arguments: Sequence[Any],
    data: Optional[HexStr] = None,
) -> HexStr:
    argument_types = get_abi_input_types(abi)

    if not check_if_arguments_can_be_encoded(abi, abi_codec, arguments, {}):
        raise TypeError(
            "One or more arguments could not be encoded to the necessary "
            f"ABI type.  Expected types are: {', '.join(argument_types)}"
        )

    normalizers = [
        abi_address_to_hex,
        abi_bytes_to_bytes,
        abi_string_to_text,
    ]
    normalized_arguments = map_abi_data(
        normalizers,
        argument_types,
        arguments,
    )
    encoded_arguments = abi_codec.encode(
        argument_types,
        normalized_arguments,
    )

    if data:
        return to_hex(HexBytes(data) + encoded_arguments)
    else:
        return encode_hex(encoded_arguments)

def filter_by_encodability(
    abi_codec: codec.ABIEncoder,
    args: Sequence[Any],
    kwargs: Dict[str, Any],
    contract_abi: ABI,
) -> List[ABIFunction]:
    return [
        cast(ABIFunction, function_abi)
        for function_abi in contract_abi
        if check_if_arguments_can_be_encoded(
            cast(ABIFunction, function_abi), abi_codec, args, kwargs
        )
    ]

def filter_by_argument_count(
    num_arguments: int, contract_abi: ABI
) -> List[Union[ABIFunction, ABIEvent]]:
    return [abi for abi in contract_abi if len(abi["inputs"]) == num_arguments]

def filter_by_name(name: str, contract_abi: ABI) -> List[Union[ABIFunction, ABIEvent]]:
    return [
        abi
        for abi in contract_abi
        if (
            abi["type"] not in ("fallback", "constructor", "receive")
            and abi["name"] == name
        )
    ]


def find_matching_fn_abi(
    abi: ABI,
    abi_codec: ABICodec,
    fn_identifier: str = None,
    args: Optional[Sequence[Any]] = None,
    kwargs: Optional[Any] = None,
) -> ABIFunction:
    args = args or tuple()
    kwargs = kwargs or dict()
    num_arguments = len(args) + len(kwargs)

    if not is_text(fn_identifier):
        raise TypeError("Unsupported function identifier")

    name_filter = functools.partial(filter_by_name, fn_identifier)
    arg_count_filter = functools.partial(filter_by_argument_count, num_arguments)
    encoding_filter = functools.partial(filter_by_encodability, abi_codec, args, kwargs)

    function_candidates = pipe(abi, name_filter, arg_count_filter, encoding_filter)

    if len(function_candidates) == 1:
        return function_candidates[0]
    else:
        matching_identifiers = name_filter(abi)
        matching_function_signatures = [
            abi_to_signature(func) for func in matching_identifiers
        ]

        arg_count_matches = len(arg_count_filter(matching_identifiers))
        encoding_matches = len(encoding_filter(matching_identifiers))

        if arg_count_matches == 0:
            diagnosis = (
                "\nFunction invocation failed due to improper number of arguments."
            )
        elif encoding_matches == 0:
            diagnosis = (
                "\nFunction invocation failed due to no matching argument types."
            )
        elif encoding_matches > 1:
            diagnosis = (
                "\nAmbiguous argument encoding. "
                "Provided arguments can be encoded to multiple functions "
                "matching this call."
            )

        collapsed_args = extract_argument_types(args)
        collapsed_kwargs = dict(
            {(k, extract_argument_types([v])) for k, v in kwargs.items()}
        )
        message = (
            f"\nCould not identify the intended function with name `{fn_identifier}`, "
            f"positional arguments with type(s) `{collapsed_args}` and "
            f"keyword arguments with type(s) `{collapsed_kwargs}`."
            f"\nFound {len(matching_identifiers)} function(s) with "
            f"the name `{fn_identifier}`: {matching_function_signatures}{diagnosis}"
        )

        raise ValidationError(message)


def get_function_info(
    fn_name: str,
    abi_codec: ABICodec,
    contract_abi: Optional[ABI] = None,
    fn_abi: Optional[ABIFunction] = None,
    args: Optional[Sequence[Any]] = None,
    kwargs: Optional[Any] = None,
) -> Tuple[ABIFunction, HexStr, Tuple[Any, ...]]:
    if args is None:
        args = tuple()
    if kwargs is None:
        kwargs = {}

    if fn_abi is None:
        fn_abi = find_matching_fn_abi(contract_abi, abi_codec, fn_name, args, kwargs)

    # typed dict cannot be used w/ a normal Dict
    # https://github.com/python/mypy/issues/4976
    fn_selector = encode_hex(function_abi_to_4byte_selector(fn_abi))  # type: ignore

    fn_arguments = merge_args_and_kwargs(fn_abi, args, kwargs)

    _, aligned_fn_arguments = get_aligned_abi_inputs(fn_abi, fn_arguments)

    return fn_abi, fn_selector, aligned_fn_arguments

def encode_transaction_data(
    fn_identifier: str,
    abi_codec: ABICodec,
    contract_abi: Optional[ABI] = None,
    fn_abi: Optional[ABIFunction] = None,
    args: Optional[Sequence[Any]] = None,
    kwargs: Optional[Any] = None,
) -> HexStr:
    fn_abi, fn_selector, fn_arguments = get_function_info(
        # type ignored b/c fn_id here is always str b/c FallbackFn is handled above
        fn_identifier,  # type: ignore
        abi_codec,
        contract_abi,
        fn_abi,
        args,
        kwargs,
    )

    return add_0x_prefix(encode_abi(abi_codec, fn_abi, fn_arguments, fn_selector))

def validate_payable(transaction: TxParams, abi: ABIFunction) -> None:
    """Raise ValidationError if non-zero ether
    is sent to a non-payable function.
    """
    if "value" in transaction:
        if to_integer_if_hex(transaction["value"]) != 0:
            if "payable" in abi and not abi["payable"]:
                raise ValidationError(
                    "Sending non-zero ether to a contract function "
                    "with payable=False. Please ensure that "
                    "transaction's value is 0."
                )


def prepare_transaction(
    address: ChecksumAddress,
    fn_identifier: str,
    contract_abi: ABI,
    abi_codec: ABICodec,
    transaction: Optional[TxParams] = None,
    fn_args: Optional[Sequence[Any]] = None,
    fn_kwargs: Optional[Any] = None,
) -> TxParams:
    """
    :parameter `is_function_abi` is used to distinguish  function abi from contract abi
    Returns a dictionary of the transaction that could be used to call this
    TODO: make this a public API
    TODO: add new prepare_deploy_transaction API
    """
    fn_abi = find_matching_fn_abi(
        contract_abi, abi_codec, fn_identifier, fn_args, fn_kwargs
    )

    validate_payable(transaction, fn_abi)

    prepared_transaction = cast(TxParams, dict(**transaction))

    if "data" in prepared_transaction:
        raise ValueError("Transaction parameter may not contain a 'data' key")

    if address:
        prepared_transaction.setdefault("to", address)

    prepared_transaction["data"] = encode_transaction_data(
        fn_identifier,
        abi_codec,
        contract_abi,
        fn_abi,
        fn_args,
        fn_kwargs,
    )
    return prepared_transaction

def decode_function_output(
    fn_id: str,
    data: HexStr,
    abi: ABI,
    abi_codec: ABICodec,
    fn_args=None,
    fn_kwargs=None
):
    data = bytes.fromhex(data[2:])
    fn_abi = find_matching_fn_abi(
        abi, abi_codec, fn_id,
        args=fn_args, kwargs=fn_kwargs)

    output_types = get_abi_output_types(fn_abi)
    return abi_codec.decode(output_types, data)

