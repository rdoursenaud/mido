# SPDX-FileCopyrightText: 2013 Ole Martin Bjorndalen <ombdalen@gmail.com>
# SPDX-FileCopyrightText: 2023 Raphaël Doursenaud <rdoursenaud@gmail.com>
#
# SPDX-License-Identifier: MIT

"""MIDI Parser

There is no need to use this module directly. All you need is
available in the top level module.
"""
from __future__ import annotations

from collections import deque

from typing import Sequence, Iterator

from typing_extensions import Deque

from .messages import Message
from .tokenizer import Tokenizer


class Parser:
    """MIDI byte stream parser.

    Parses a stream of MIDI bytes and produces messages.

    Data can be put into the parser in the form of
    integers, byte arrays or byte strings.
    """
    def __init__(self, data: Sequence[int] | None = None) -> None:
        """Initializes the MIDI parser.

        :param data: initial MIDI data to feed the parser with.
        :type data: Sequence[int], optional, defaults to ``None``
        """
        # For historical reasons self.messages is public and must be a
        # deque(). (It is referenced directly inside ports.)
        self.messages: Deque[Message] = deque()
        self._tok = Tokenizer()
        if data:
            self.feed(data)

    def _decode(self) -> None:
        for midi_bytes in self._tok:
            self.messages.append(Message.from_bytes(midi_bytes))

    def feed(self, data: Sequence[int]) -> None:
        """Feeds MIDI data to the parser.

        Accepts any object that produces a sequence of integers in
        range 0..255, such as:

            .. code-block:: python

                [0, 1, 2]
                (0, 1, 2)
                [for i in range(256)]
                (for i in range(256)]
                bytearray()

        :param data: MIDI data to feed the parser with.
        :type data: Sequence[int]
        """
        self._tok.feed(data)
        self._decode()

    def feed_byte(self, byte: int) -> None:
        """Feeds one MIDI byte into the parser.

        The byte must be an integer in range 0..255.

        :param byte: a single MIDI ``byte`` to feed the parser with
        :type byte: int
        """
        self._tok.feed_byte(byte)
        self._decode()

    def get_message(self) -> Message | None:
        """Gets the first parsed message.

        :return: ``None`` if there is no message yet. If you don't want to
            deal with ``None``, you can use :meth:`pending()` to see how many
            messages you can get before you get ``None``, or just iterate
            over the parser.
        :rtype: Message | None
        """
        for msg in self:
            return msg
        else:
            return None

    def pending(self) -> int:
        """Checks if there are pending messages in the parser.

        :return: the number of pending messages.
        :rtype: int
        """
        return len(self.messages)

    __len__ = pending

    def __iter__(self) -> Iterator[Message]:
        """Yields messages that have been parsed so far.

        :return: Iterates over :class:`Message` objects.
        :rtype: Iterator[Message]
        """
        while len(self.messages) > 0:
            yield self.messages.popleft()


def parse_all(data: Sequence[int]) -> list[Message]:
    """Parses MIDI data into a list of all messages found.

    This is typically used to parse a little bit of data with a few
    messages in it. It's best to use a :class:`Parser` object for larger
    amounts of data. Also, it's often easier to use :func:`parse()` if you
    know there's only one message in the data.

    :param data: MIDI data to be parsed.
    :type data: Sequence[int]

    :return: parsed MIDI data into ``Message(s)``.
    :rtype: list[Message]
    """
    return list(Parser(data))


def parse(data: Sequence[int]) -> Message | None:
    """Parses MIDI data and returns the first message found.

    .. warning::

        Data after the first message is ignored. Use :func:`parse_all()`
        to parse more than one message.

    :param data: MIDI data to be parsed.
    :type data: Sequence[int]

    :return: the first message found
    :rtype: Message | None
    """
    return Parser(data).get_message()
