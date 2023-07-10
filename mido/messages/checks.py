# SPDX-FileCopyrightText: 2016 Ole Martin Bjorndalen <ombdalen@gmail.com>
#
# SPDX-License-Identifier: MIT

from numbers import Integral, Real
from typing import Any, Sequence

from .specs import (
    SPEC_BY_TYPE, MIN_SONGPOS, MAX_SONGPOS,
    MIN_PITCHWHEEL, MAX_PITCHWHEEL
)


def check_type(type_: Any) -> None:
    if type_ not in SPEC_BY_TYPE:
        raise ValueError(f'invalid message type {type_!r}')


def check_channel(channel: Any) -> None:
    if not isinstance(channel, int):
        raise TypeError('channel must be int')
    if not 0 <= channel <= 15:
        raise ValueError('channel must be in range 0..15')


def check_pos(pos: Any) -> None:
    if not isinstance(pos, int):
        raise TypeError('song pos must be int')
    if not MIN_SONGPOS <= pos <= MAX_SONGPOS:
        raise ValueError('song pos must be in range {}..{}'.format(
                         MIN_SONGPOS, MAX_SONGPOS))


def check_pitch(pitch: Any) -> None:
    if not isinstance(pitch, int):
        raise TypeError('pichwheel value must be int')
    if not MIN_PITCHWHEEL <= pitch <= MAX_PITCHWHEEL:
        raise ValueError('pitchwheel value must be in range {}..{}'.format(
                         MIN_PITCHWHEEL, MAX_PITCHWHEEL))


def check_data(data_bytes: Sequence[Any]) -> None:
    for byte in data_bytes:
        check_data_byte(byte)


def check_frame_type(value: Any) -> None:
    if not isinstance(value, int):
        raise TypeError('frame_type must be int')
    if not 0 <= value <= 7:
        raise ValueError('frame_type must be in range 0..7')


def check_frame_value(value: Any) -> None:
    if not isinstance(value, int):
        raise TypeError('frame_value must be int')
    if not 0 <= value <= 15:
        raise ValueError('frame_value must be in range 0..15')


def check_data_byte(value: Any) -> None:
    if not isinstance(value, int):
        raise TypeError('data byte must be int')
    if not 0 <= value <= 127:
        raise ValueError('data byte must be in range 0..127')


def check_time(time: Any) -> None:
    if not isinstance(time, Real):
        raise TypeError('time must be int or float')


_CHECKS = {
    'type': check_type,
    'data': check_data,
    'channel': check_channel,
    'control': check_data_byte,
    'data': check_data,
    'frame_type': check_frame_type,
    'frame_value': check_frame_value,
    'note': check_data_byte,
    'pitch': check_pitch,
    'pos': check_pos,
    'program': check_data_byte,
    'song': check_data_byte,
    'value': check_data_byte,
    'velocity': check_data_byte,
    'time': check_time,
}


def check_value(name: str, value: Any) -> None:
    _CHECKS[name](value)


def check_msgdict(msgdict: dict) -> None:
    spec = SPEC_BY_TYPE.get(msgdict['type'])
    if spec is None:
        raise ValueError('unknown message type {!r}'.format(msgdict['type']))

    for name, value in msgdict.items():
        if name not in spec['attribute_names']:
            raise ValueError(
                '{} message has no attribute {}'.format(spec['type'], name))

        check_value(name, value)
