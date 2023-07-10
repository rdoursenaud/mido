# SPDX-FileCopyrightText: 2013 Ole Martin Bjorndalen <ombdalen@gmail.com>
# SPDX-FileCopyrightText: 2023 Raphaël Doursenaud <rdoursenaud@gmail.com>
#
# SPDX-License-Identifier: MIT

"""
Useful tools for working with ports
"""
from __future__ import annotations

import abc
import random
import threading
import time
from abc import ABC
from types import TracebackType
from typing import Iterator, Optional, Sequence, Tuple

from typing_extensions import Final, Literal

from .messages import Message
from .parser import Parser

# How many seconds to sleep before polling again.
_DEFAULT_SLEEP_TIME: Final = 0.001
_sleep_time = _DEFAULT_SLEEP_TIME


# TODO: document this more.
def sleep() -> None:
    """Sleeps for N seconds.

    This is used in ports when polling and waiting for messages. N can
    be set with set_sleep_time().
    """
    time.sleep(_sleep_time)


def set_sleep_time(seconds: float = _DEFAULT_SLEEP_TIME) -> None:
    """Sets the number of seconds sleep() will sleep.
    """
    global _sleep_time
    _sleep_time = seconds


def get_sleep_time() -> float:
    """Gets the number of seconds sleep() will sleep.

    :return: The number of seconds sleep() will sleep.
    :rtype: float
    """
    return _sleep_time


def reset_messages() -> Iterator[Message]:
    """Yields ``All Notes Off`` and ``Reset All Controllers`` for all channels.
    """
    ALL_NOTES_OFF: Final = 123
    RESET_ALL_CONTROLLERS: Final = 121
    for channel in range(16):
        for control in [ALL_NOTES_OFF, RESET_ALL_CONTROLLERS]:
            yield Message('control_change', channel=channel, control=control)


def panic_messages() -> Iterator[Message]:
    """Yields ``All Sounds Off`` for all channels.

    This will mute all sounding notes regardless of
    envelopes. Useful when notes are hanging and nothing else
    helps.
    """
    ALL_SOUNDS_OFF: Final = 120
    for channel in range(16):
        yield Message('control_change', channel=channel,
                      control=ALL_SOUNDS_OFF)


class DummyLock:
    def __enter__(self) -> DummyLock:
        return self

    def __exit__(self, *_) -> Literal[False]:
        return False


class BasePort(ABC):
    """Abstract base class for Input and Output ports.
    """
    is_input = False
    is_output = False
    _locking = True

    def __init__(self, name: str | None = None, **kwargs) -> None:
        if hasattr(self, 'closed'):
            # __init__() called twice (from BaseInput and BaseOutput).
            # This stops _open() from being called twice.
            return

        self.name = name
        if self._locking:
            self._lock = threading.RLock()
        else:
            self._lock = DummyLock()
        self.closed = True
        self._open(**kwargs)
        self.closed = False

    def _open(self, **kwargs):
        pass

    def _close(self):
        pass

    def close(self) -> None:
        """Closes the port.

        If the port is already closed, nothing will happen.  The port
        is automatically closed when the object goes out of scope or
        is garbage collected.
        """
        with self._lock:
            if not self.closed:
                if hasattr(self, 'autoreset') and self.autoreset:
                    try:
                        self.reset()
                    except OSError:
                        pass

                self._close()
                self.closed = True

    def __del__(self) -> None:
        self.close()

    def __enter__(self) -> BasePort:
        return self

    def __exit__(self,
                 exc_type: type[BaseException],
                 exc_value: BaseException,
                 traceback: TracebackType) -> Literal[False]:
        self.close()
        return False

    def __repr__(self) -> str:
        if self.closed:
            state = 'closed'
        else:
            state = 'open'

        capabilities = self.is_input, self.is_output
        port_type = {(True, False): 'input',
                     (False, True): 'output',
                     (True, True): 'I/O port',
                     (False, False): 'mute port',
                     }[capabilities]

        name = self.name or ''

        try:
            device_type = self._device_type
        except AttributeError:
            device_type = self.__class__.__name__

        return '<{} {} {!r} ({})>'.format(
            state, port_type, name, device_type)


class BaseInput(BasePort):
    """Base class for input port.

    Subclass and override _receive() to create a new input port type.
    (See portmidi.py for an example of how to do this.)
    """
    is_input = True

    def __init__(self, name: str = '', **kwargs) -> None:
        """Create an input port.

        name is the port name, as returned by input_names(). If
        name is not passed, the default input is used instead.
        """
        BasePort.__init__(self, name, **kwargs)
        self._parser = Parser()
        self._messages = self._parser.messages  # Shortcut.

    def _check_callback(self) -> None:
        if hasattr(self, 'callback') and self.callback is not None:
            raise ValueError('a callback is set for this port')

    def _receive(self, block=True):
        pass

    def iter_pending(self) -> Iterator[Message] | None:
        """Iterate through pending messages.
        """
        while True:
            msg = self.poll()
            if msg is None:
                return None
            else:
                yield msg

    def receive(self, block: bool = True) -> Message | None:
        """Return the next message.

        This will block until a message arrives.

        If you pass block=False it will not block and instead return
        None if there is no available message.

        If the port is closed and there are no pending messages IOError
        will be raised. If the port closes while waiting inside receive(),
        IOError will be raised. TODO: this seems a bit inconsistent. Should
        different errors be raised? What's most useful here?
        """
        if not self.is_input:
            raise ValueError('Not an input port')

        self._check_callback()

        # If there is a message pending, return it right away.
        with self._lock:
            if self._messages:
                return self._messages.popleft()

        if self.closed:
            if block:
                raise ValueError('receive() called on closed port')
            else:
                return None

        while True:
            with self._lock:
                msg = self._receive(block=block)
                if msg:
                    return msg

                if self._messages:
                    return self._messages.popleft()
                elif not block:
                    return None
                elif self.closed:
                    raise OSError('port closed during receive()')

            sleep()

    def poll(self) -> Message | None:
        """Receive the next pending message or None

        This is the same as calling `receive(block=False)`.
        """
        return self.receive(block=False)

    def __iter__(self) -> Iterator[Optional[Message]]:
        """Iterate through messages until the port closes.
        """
        # This could have simply called receive() in a loop, but that
        # could result in a "port closed during receive()" error which
        # is hard to catch here.
        self._check_callback()
        while True:
            try:
                yield self.receive()
            except OSError:
                if self.closed:
                    # The port closed before or inside receive().
                    # (This makes the assumption that this is the reason,
                    # at the risk of masking other errors.)
                    return
                else:
                    raise


class BaseOutput(BasePort):
    """Base class for output port.

    Subclass and override _send() to create a new port type.  (See
    portmidi.py for how to do this.)
    """
    is_output = True

    def __init__(self, name: str = '', autoreset: bool = False,
                 **kwargs) -> None:
        """Create an output port

        name is the port name, as returned by output_names(). If
        name is not passed, the default output is used instead.
        """
        BasePort.__init__(self, name, **kwargs)
        self.autoreset = autoreset

    def _send(self, msg):
        pass

    def send(self, msg: Message) -> None:
        """Send a message on the port.

        A copy of the message will be sent, so you can safely modify
        the original message without any unexpected consequences.
        """
        if not self.is_output:
            raise ValueError('Not an output port')
        elif not isinstance(msg, Message):
            raise TypeError('argument to send() must be a Message')
        elif self.closed:
            raise ValueError('send() called on closed port')

        with self._lock:
            self._send(msg.copy())

    def reset(self) -> None:
        """Send "All Notes Off" and "Reset All Controllers" on all channels
        """
        if self.closed:
            return

        for msg in reset_messages():
            self.send(msg)

    def panic(self) -> None:
        """Send "All Sounds Off" on all channels.

        This will mute all sounding notes regardless of
        envelopes. Useful when notes are hanging and nothing else
        helps.
        """
        if self.closed:
            return

        for msg in panic_messages():
            self.send(msg)


class BaseIOPort(BaseInput, BaseOutput):
    def __init__(self, name: str = '', **kwargs) -> None:
        """Create an IO port.

        name is the port name, as returned by ioport_names().
        """
        BaseInput.__init__(self, name, **kwargs)
        BaseOutput.__init__(self, name, **kwargs)


class IOPort(BaseIOPort):
    """Input / output port.

    This is a convenient wrapper around an input port and an output
    port which provides the functionality of both. Every method call
    is forwarded to the appropriate port.
    """

    _locking = False

    def __init__(self, input: BaseInput, output: BaseOutput) -> None:
        self.input = input
        self.output = output

        # We use str() here in case name is None.
        self.name = f'{str(input.name)} + {str(output.name)}'
        self._messages = self.input._messages
        self.closed = False
        self._lock = DummyLock()

    def _close(self) -> None:
        self.input.close()
        self.output.close()

    def _send(self, message: Message) -> None:
        self.output.send(message)

    def _receive(self, block: bool = True) -> Message | None:
        return self.input.receive(block=block)


class EchoPort(BaseIOPort):
    def _send(self, message: Message) -> None:
        self._messages.append(message)

    __iter__ = BaseIOPort.iter_pending


class MultiPort(BaseIOPort):
    def __init__(self,
                 ports: Sequence[BasePort],
                 yield_ports: bool = False) -> None:
        BaseIOPort.__init__(self, 'multi')
        self.ports = list(ports)
        self.yield_ports = yield_ports

    def _send(self, message: Message) -> None:
        for port in self.ports:
            if not port.closed:
                # TODO: what if a SocketPort connection closes in-between here?
                port.send(message)

    def _receive(self, block: bool = True) -> None:
        self._messages.extend(multi_receive(self.ports,
                                            yield_ports=self.yield_ports,
                                            block=block))


def multi_receive(
    ports: Sequence[BaseInput],
    yield_ports: bool = False,
    block: bool = True
) -> (Iterator[Message] | Iterator[Tuple[BasePort, Message]]):
    """Receive messages from multiple ports.

    Generates messages from ever input port. The ports are polled in
    random order for fairness, and all messages from each port are
    yielded before moving on to the next port.

    If yield_ports=True, (port, message) is yielded instead of just
    the message.

    If block=False only pending messages will be yielded.
    """
    ports = list(ports)
    while True:
        # Make a shuffled copy of the port list.
        random.shuffle(ports)

        for port in ports:
            if not port.closed:
                for message in port.iter_pending():
                    if yield_ports:
                        yield port, message
                    else:
                        yield message

        if block:
            sleep()
        else:
            break


def multi_iter_pending(
    ports: list[BaseInput],
    yield_ports: bool = False
) -> (Iterator[Message] | Iterator[Tuple[BasePort, Message]]):
    """Iterate through all pending messages in ports.

    This is the same as calling multi_receive(ports, block=False).
    The function is kept around for backwards compatability.
    """
    return multi_receive(ports, yield_ports=yield_ports, block=False)


def multi_send(ports: Sequence[BaseOutput], msg: Message) -> None:
    """Send message on all ports.
    """
    for port in ports:
        port.send(msg)
