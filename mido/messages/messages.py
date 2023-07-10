# SPDX-FileCopyrightText: 2016 Ole Martin Bjorndalen <ombdalen@gmail.com>
# SPDX-FileCopyrightText: 2023 Raphaël Doursenaud <rdoursenaud@gmail.com>
#
# SPDX-License-Identifier: MIT
from __future__ import annotations
import re
from abc import ABC, abstractmethod
from typing import Dict, Iterator, Any, Iterable, Tuple
from typing_extensions import Self

from .checks import check_msgdict, check_value, check_data
from .decode import decode_message
from .encode import encode_message
from .specs import make_msgdict, SPEC_BY_TYPE, REALTIME_TYPES
from .strings import msg2str, str2msg


class BaseMessage(ABC):
    """Abstract base class for messages.
    """
    is_meta = False

    type: str
    control: int

    @abstractmethod
    def __init__(self, type: str, **args: Any):
        raise NotImplementedError

    @abstractmethod
    def copy(self) -> 'BaseMessage':
        raise NotImplementedError

    @abstractmethod
    def bytes(self) -> list[int]:
        raise NotImplementedError

    def bin(self) -> bytearray:
        """Encode message and return as a ``bytearray``.

        This can be used to write the message to a file.

        :return: the binary representation of the message.
        :rtype: bytearray
        """
        return bytearray(self.bytes())

    def hex(self, sep: str = ' ') -> str:
        """Encode message and return as a string of hexadecimal numbers.

        :param sep: specifies a separator to insert between hexadecimal numbers.
        :type sep: str, optional, defaults to a SPACE.

        :return: the hexadecimal representation of the message.
        :rtype: str
        """
        return sep.join(f'{byte:02X}' for byte in self.bytes())

    def dict(self) -> dict[str, Any]:
        """Returns a dictionary containing the attributes of the message.

        Sysex data will be returned as a ``list``.

        Example:
            {'type': 'sysex', 'data': [1, 2], 'time': 0}

        :return: the attributes of the message.
        :rtype: dict[str, Any]
        """
        data = vars(self).copy()
        if data['type'] == 'sysex':
            # Make sure we return a list instead of a SysexData object.
            data['data'] = list(data['data'])

        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Self:
        """Create a message from a dictionary.

        :param data:
            ``type`` is the only field required.
            The others will be set to default values.
        :type data: Dict[str, Any]

        :return: an object instance.
        :rtype: Self
        """
        return cls(**data)

    def _get_value_names(self) -> list[str]:
        # This is overridden by MetaMessage.
        return list(SPEC_BY_TYPE[self.type]['value_names']) + ['time']

    def __repr__(self) -> str:
        items = [repr(self.type)]
        for name in self._get_value_names():
            items.append(f'{name}={getattr(self, name)!r}')
        return '{}({})'.format(type(self).__name__, ', '.join(items))

    @property
    def is_realtime(self) -> bool:
        """True if the message is a system realtime message."""
        return self.type in REALTIME_TYPES

    def is_cc(self, control: int | None = None) -> bool:
        """Return ``True`` if the message is of type ``control_change``.

        :param control:
            Can be used to test for a specific control number, for example:

            .. code-block:: python

                if msg.is_cc(7):
                    # Message is control change 7 (channel volume).
        :type control: int, optional

        :return: Whether a message is of type ``control_change``.
        :rtype: bool
        """
        if self.type != 'control_change':
            return False
        elif control is None:
            return True
        else:
            return self.control == control

    def __delattr__(self, name: str) -> None:
        raise AttributeError('attribute cannot be deleted')

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError('message is immutable')

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BaseMessage):
            raise TypeError(f'can\'t compare message to {type(other)}')

        # This includes time in comparison.
        return vars(self) == vars(other)


class SysexData(tuple):  # type: ignore[type-arg]
    """Special kind of tuple accepts and converts any sequence in +=.
    """
    def __iadd__(self, other: tuple[Any, ...]) -> tuple:  # type: ignore[misc]
        super().__add__()
        check_data(other)
        return self + SysexData(other)


class Message(BaseMessage):
    """An object representing a MIDI message.
    """
    data: 'SysexData'

    def __init__(self, type: str, **args: Any) -> None:
        """Initialise a MIDI message.

        :param type: the message type keyword.
        :type type: str

        :param **args: supplementary data for initializing the message.
        :type **args: Any, optional
        """
        msgdict = make_msgdict(type, args)
        if type == 'sysex':
            msgdict['data'] = SysexData(msgdict['data'])
        check_msgdict(msgdict)
        vars(self).update(msgdict)

    def copy(self, **overrides: Any) -> 'Message':
        """Return a copy of the message.

        :param overrides:
            Attributes will be overridden by the passed keyword arguments.
            Only message specific attributes can be overridden.
        :type overrides: Any, optional

        .. warning:: The message type cannot be changed.

        :return: a copy of the message.
        :rtype: Message
        """
        if not overrides:
            # Bypass all checks.
            msg = self.__class__.__new__(self.__class__)
            vars(msg).update(vars(self))
            return msg

        if 'type' in overrides and overrides['type'] != self.type:
            raise ValueError('copy must be same message type')

        if 'data' in overrides:
            overrides['data'] = SysexData(overrides['data'])

        msgdict = vars(self).copy()
        msgdict.update(overrides)
        check_msgdict(msgdict)
        return self.__class__(**msgdict)

    @classmethod
    def from_bytes(cls, data: Iterable[int], time: int = 0) -> 'Message':
        """Parse a byte encoded message.

        This is the reverse of :meth:`bytes()` or :meth:`bin()`.

        :param data: from which the ``Message`` is created.
        :type data: Iterable[int]

        :param time: sets the ``Message`` time.
        :type time: int, optional, defaults to 0

        :return: a MIDI message object instance.
        :rtype: Message
        """
        msg = cls.__new__(cls)
        msgdict = decode_message(data, time=time)
        if 'data' in msgdict:
            msgdict['data'] = SysexData(msgdict['data'])
        vars(msg).update(msgdict)
        return msg

    @classmethod
    def from_hex(cls, text: str, time: int = 0,
                 sep: str | None = None) -> 'Message':
        """Parse a hex encoded message.

        This is the reverse of :meth:`hex()`.

        :param text: the hex encoded text to build the ``Message`` from.
        :type text: str

        :param time: sets the ``Message`` time.
        :type time: int, optional, defaults to 0

        :param sep: the separator used between hexadecimal numbers, if any.
        :type sep: str, optional, defaults to None

        :return: a MIDI message object instance.
        :rtype: Message
        """
        # bytearray.fromhex() is a bit picky about its input
        # so we need to replace all whitespace characters with spaces.
        text = re.sub(r'\s', ' ', text)

        if sep is not None:
            # We also replace the separator with spaces making sure
            # the string length remains the same so char positions will
            # be correct in bytearray.fromhex() error messages.
            text = text.replace(sep, ' ' * len(sep))

        return cls.from_bytes(bytearray.fromhex(text), time=time)

    @classmethod
    def from_str(cls, text: str) -> 'Message':
        """Parse a string encoded message.

        This is the reverse of ``str(msg)``.

        :param text: the text encoded message to build the ``Message`` from.
        :type text: str

        :return: a MIDI message object instance.
        :rtype: Message
        """
        return cls(**str2msg(text))

    def __len__(self) -> int | float:
        if self.type == 'sysex':
            return 2 + len(self.data)
        else:
            return SPEC_BY_TYPE[self.type]['length']

    def __str__(self) -> str:
        return msg2str(vars(self))

    def _setattr(self, name: str, value: Any) -> None:
        if name == 'type':
            raise AttributeError('type attribute is read only')
        elif name not in vars(self):
            raise AttributeError('{} message has no '
                                 'attribute {}'.format(self.type,
                                                       name))
        else:
            check_value(name, value)
            if name == 'data':
                vars(self)['data'] = SysexData(value)
            else:
                vars(self)[name] = value

    __setattr__ = _setattr

    def bytes(self) -> list[int]:
        """Encode message and return as a list of integers.

        :return: the MIDI message encoded as bytes.
        :rtype: list[int]
        """
        return encode_message(vars(self))


def parse_string(text: str) -> 'Message':
    """Parse a string of text and return a message.

    The string can span multiple lines, but must contain one full message.

    :param text: the text to parse.
    :type text: str

    :raises ValueError: if the string could not be parsed.

    :return: a MIDI message object instance.
    :rtype: Message
    """
    return Message.from_str(text)


def parse_string_stream(
    stream: Iterable[str]
) -> Iterator[Tuple[Message | None, str | None]]:
    """Parse a stream of messages and yield ``(message, error_message)``.

    stream can be any iterable that generates text strings, where each
    string is a string encoded message.

    If a string can be parsed, ``(message, None)`` is returned. If it
    can't be parsed, ``(None, error_message)`` is returned. The error
    message contains the line number where the error occurred.

    :param stream: the stream to parse.
    :type stream: Iterable[str]

    :return: A MIDI message object instance or an error.
    :rtype: Iterator[Tuple[Message | None, str | None]]
    """
    line_number = 1
    for line in stream:
        try:
            line = line.split('#')[0].strip()
            if line:
                yield parse_string(line), None
        except ValueError as exception:
            error_message = 'line {line_number}: {msg}'.format(
                line_number=line_number, msg=exception.args[0]
            )
            yield None, error_message
        line_number += 1


def format_as_string(msg: 'Message', include_time: bool = True) -> str:
    """Format a message and return as a string.

    This is equivalent to ``str(msg)``.

    :param msg: the message to format as a string.
    :type msg: Message

    :param include_time: includes or leaves out the ``time`` attribute
    :type include_time: bool, optional, defaults to True

    :return: the message formatted as a string.
    :rtype: str
    """
    return msg2str(vars(msg), include_time=include_time)
