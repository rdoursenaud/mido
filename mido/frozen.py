# SPDX-FileCopyrightText: 2016 Ole Martin Bjorndalen <ombdalen@gmail.com>
# SPDX-FileCopyrightText: 2023 Raphaël Doursenaud <rdoursenaud@gmail.com>
#
# SPDX-License-Identifier: MIT
from __future__ import annotations

from abc import ABC
from typing import Type

from .messages import BaseMessage, Message
from .midifiles import MetaMessage, UnknownMetaMessage


class Frozen(ABC):
    """Abstract base class for a frozen (immutable) representation of an object.
    """
    def __setattr__(self, *_):
        raise ValueError('frozen message is immutable')

    def __hash__(self):
        return hash(tuple(sorted(vars(self).items())))


class FrozenMessage(Frozen, Message):
    """A frozen (immutable) representation of a :class:`Message`.
    """
    pass


class FrozenMetaMessage(Frozen, MetaMessage):
    """A frozen (immutable) representation of a :class:`MetaMessage`.
    """
    pass


class FrozenUnknownMetaMessage(Frozen, UnknownMetaMessage):
    """A frozen (immutable) representation of an :class:`UnknownMetaMessage`.
    """
    def __repr__(self):
        return 'Frozen' + UnknownMetaMessage.__repr__(self)


def is_frozen(msg: Type[BaseMessage] | Type[Frozen]) -> bool:
    """Checks if a :class:`Message` is frozen.

    :param msg: The message to check.
    :type msg: :class:`BaseMessage` or :class:`Frozen`

    :raises ValueError: if ``msg`` is not a supported type.

    :return: the MIDI message instance frozen status.
    :rtype: bool
    """
    if not isinstance(msg, BaseMessage) and not isinstance(msg, Frozen):
        raise ValueError('Expected a Message-like object.')

    return isinstance(msg, Frozen)


# TODO: these two functions are almost the same except inverted. There
# should be a way to refactor them to lessen code duplication.

def freeze_message(
        msg: Message | MetaMessage | UnknownMetaMessage | None
) -> (Frozen | FrozenMessage | FrozenMetaMessage | FrozenUnknownMetaMessage |
      None):
    """Freezes a :class:`Message`.

    :param msg: The message to freeze.
    :type msg: :class:`BaseMessage` | None

    :raises ValueError: if ``msg`` is not a supported type.

    :return: a frozen version of the message. Frozen messages are immutable,
        hashable and can be used as dictionary keys.

        Will return ``None`` if called with ``None``.
        This allows you to do things like:

            .. code-block:: python

            msg = freeze_message(port.poll())
    :rtype: :class:`Frozen` | None
    """
    if msg is None:
        return None
    if isinstance(msg, Frozen):
        # Already frozen.
        return msg
    class_: Type[Frozen]
    if isinstance(msg, Message):
        class_ = FrozenMessage
    elif isinstance(msg, UnknownMetaMessage):
        class_ = FrozenUnknownMetaMessage
    elif isinstance(msg, MetaMessage):
        class_ = FrozenMetaMessage
    else:
        raise ValueError('first argument must be a message or None')

    frozen = class_.__new__(class_)
    vars(frozen).update(vars(msg))
    return frozen


def thaw_message(
        msg: Frozen | FrozenMessage | FrozenMetaMessage |
        FrozenUnknownMetaMessage | BaseMessage | None
) -> BaseMessage | Message | MetaMessage | UnknownMetaMessage | None:
    """Thaw message.

    Returns a mutable version of a frozen message.

    Will return ``None`` if called with ``None``.

    :param msg: The message to thaw.
    :type msg: Frozen | FrozenMessage | FrozenMetaMessage |
        FrozenUnknownMetaMessage | BaseMessage | None

    :raises ValueError: if ``msg`` is not a supported type.

    :return: A mutable version of a frozen message.
    :rtype: BaseMessage
    """
    if msg is None:
        return None
    if not isinstance(msg, Frozen):
        # Already thawed, just return a copy.
        return msg.copy()
    class_: Type[BaseMessage]
    if isinstance(msg, FrozenMessage):
        class_ = Message
    elif isinstance(msg, FrozenUnknownMetaMessage):
        class_ = UnknownMetaMessage
    elif isinstance(msg, FrozenMetaMessage):
        class_ = MetaMessage
    else:
        raise ValueError('first argument must be a message or None')

    thawed = class_.__new__(class_)
    vars(thawed).update(vars(msg))
    return thawed
