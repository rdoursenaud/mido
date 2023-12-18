# SPDX-FileCopyrightText: 2017 Ole Martin Bjorndalen <ombdalen@gmail.com>
#
# SPDX-License-Identifier: MIT

import pytest

from mido.file.smf.event.meta import (
    KeySignatureError,
    MetaEvent,
    MetaSpec_key_signature,
    UnknownMetaEvent,
)


def test_copy_invalid_argument():
    with pytest.raises(ValueError):
        MetaEvent(delta_time=0, type='track_name').copy(a=1)


def test_copy_cant_override_type():
    with pytest.raises(ValueError):
        MetaEvent(delta_time=0, type='track_name').copy(type='end_of_track')


class TestKeySignature:
    @pytest.mark.parametrize('bad_key_sig', [[8, 0], [8, 1], [0, 2],
                                             [9, 1], [255 - 7, 0]])
    def test_bad_key_sig_throws_key_signature_error(self, bad_key_sig):
        with pytest.raises(KeySignatureError):
            MetaSpec_key_signature().decode(
                MetaEvent(delta_time=0, type='key_signature'),
                bad_key_sig)

    @pytest.mark.parametrize('input_bytes,expect_sig', [([0, 0], 'C'),
                                                        ([0, 1], 'Am'),
                                                        ([255 - 6, 0], 'Cb'),
                                                        ([255 - 6, 1], 'Abm'),
                                                        ([7, 1], 'A#m')
                                                        ])
    def test_key_signature(self, input_bytes, expect_sig):
        msg = MetaEvent(delta_time=0, type='key_signature')
        MetaSpec_key_signature().decode(msg, input_bytes)
        assert msg.key == expect_sig


def test_meta_event_repr():
    msg = MetaEvent(delta_time=10, type='end_of_track')
    msg_eval = eval(repr(msg))  # noqa: S307
    assert msg == msg_eval


def test_unknown_meta_event_repr():
    msg = UnknownMetaEvent(delta_time=10, type_byte=99, data=[1, 2])
    msg_eval = eval(repr(msg))  # noqa: S307
    assert msg == msg_eval


def test_meta_from_bytes_invalid():
    test_bytes = [
        0xC0,  # Not a meta event (Program Change channel 1)
        0x05   # Program #5
    ]
    with pytest.raises(ValueError):
        MetaEvent.from_bytes(test_bytes)


def test_meta_from_bytes_data_too_short():
    test_bytes = [
        0xFF,  # Meta event
        0x01,  # Event Type: Text
        0x04,  # Length
        ord('T'), ord('E'), ord('S'),  # Text: TES
    ]
    with pytest.raises(ValueError):
        MetaEvent.from_bytes(test_bytes)


def test_meta_from_bytes_data_too_long():
    test_bytes = [
        0xFF,  # Meta event
        0x01,  # Event Type: Text
        0x04,  # Length
        ord('T'), ord('E'), ord('S'), ord('T'), ord('S')  # Text: TESTS
    ]
    with pytest.raises(ValueError):
        MetaEvent.from_bytes(test_bytes)


def test_meta_from_bytes_text():
    test_bytes = [
        0xFF,  # Meta event
        0x01,  # Event Type: Text
        0x04,  # Length
        ord('T'), ord('E'), ord('S'), ord('T')  # Text: TEST
    ]
    msg = MetaEvent.from_bytes(test_bytes)
    assert msg.type == 'text'
    assert msg.text == 'TEST'
