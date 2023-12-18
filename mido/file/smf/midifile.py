# SPDX-FileCopyrightText: 2016 Ole Martin Bjorndalen <ombdalen@gmail.com>
# SPDX-FileCopyrightText: 2023 Raphaël Doursenaud <rdoursenaud@gmail.com>
#
# SPDX-License-Identifier: MIT

"""
Standard MIDI file reading and playback.

References:
https://www.midi.org/specifications/file-format-specifications/standard-midi-files
"""

import string
import struct
import time
from numbers import Integral

from mido.protocol.version1.message.specs import SPEC_BY_STATUS

from .event.meta import (
    MetaEvent,
    build_meta_event,
    encode_variable_int,
    meta_charset,
)
from .event.midi import MidiEvent
from .event.sysex import SysExEvent
from .track import MidiTrack, fix_end_of_track, merge_tracks
from .units import tick2second

# The default tempo is 120 BPM.
# (500000 microseconds per beat (quarter note).)
DEFAULT_TEMPO = 500000
DEFAULT_TICKS_PER_BEAT = 480

# Maximum event length to attempt to read.
MAX_EVENT_LENGTH = 1000000


def print_byte(byte, pos=0):
    char = chr(byte)
    if char.isspace() or char not in string.printable:
        char = '.'

    print(f'  {pos:06x}: {byte:02x}  {char}')  # noqa: T201


class DebugFileWrapper:
    def __init__(self, file):
        self.file = file

    def read(self, size):
        data = self.file.read(size)

        for byte in data:
            print_byte(byte, self.file.tell())

        return data

    def tell(self):
        return self.file.tell()


def read_byte(self):
    byte = self.read(1)
    if byte == b'':
        raise EOFError
    else:
        return ord(byte)


def read_bytes(infile, size):
    if size > MAX_EVENT_LENGTH:
        raise OSError('Event length {} exceeds maximum length {}'.format(
            size, MAX_EVENT_LENGTH))
    return [read_byte(infile) for _ in range(size)]


def _dbg(text=''):
    print(text)  # noqa: T201


# We can't use the chunk module for two reasons:
#
# 1. we may have mixed big and little endian chunk sizes. (RIFF is
# little endian while MTrk is big endian.)
#
# 2. the chunk module assumes that chunks are padded to the nearest
# multiple of 2. This is not true of MIDI files.

def read_chunk_header(infile):
    header = infile.read(8)
    if len(header) < 8:
        raise EOFError

    # TODO: check for b'RIFF' and switch endian?

    return struct.unpack('>4sL', header)


def read_file_header(infile):
    name, size = read_chunk_header(infile)

    if name != b'MThd':
        raise OSError('MThd not found. Probably not a MIDI file')
    else:
        data = infile.read(size)

        if len(data) < 6:
            raise EOFError

        return struct.unpack('>hhh', data[:6])


def read_message_event(infile, status_byte, peek_data, delta_time, clip=False):
    try:
        spec = SPEC_BY_STATUS[status_byte]
    except LookupError as le:
        raise OSError(f'undefined status byte 0x{status_byte:02x}') from le

    # Subtract 1 for status byte.
    size = spec['length'] - 1 - len(peek_data)
    data_bytes = peek_data + read_bytes(infile, size)

    if clip:
        data_bytes = [byte if byte < 127 else 127 for byte in data_bytes]
    else:
        for byte in data_bytes:
            if byte > 127:
                raise OSError('data byte must be in range 0..127')

    return MidiEvent.from_bytes(
        [status_byte] + data_bytes, delta_time=delta_time)


def read_sysex_event(infile, delta_time, clip=False):
    length = read_variable_int(infile)
    data = read_bytes(infile, length)

    # Strip start and end bytes.
    # TODO: is this necessary?
    if data and data[0] == 0xf0:
        data = data[1:]
    if data and data[-1] == 0xf7:
        data = data[:-1]

    if clip:
        data = [byte if byte < 127 else 127 for byte in data]

    return SysExEvent(delta_time=delta_time, data=data)


def read_variable_int(infile):
    delta = 0

    while True:
        byte = read_byte(infile)
        delta = (delta << 7) | (byte & 0x7f)
        if byte < 0x80:
            return delta


def read_meta_event(infile, delta):
    meta_type = read_byte(infile)
    length = read_variable_int(infile)
    data = read_bytes(infile, length)
    return build_meta_event(meta_type, data, delta)


def read_track(infile, debug=False, clip=False):
    track = MidiTrack()

    name, size = read_chunk_header(infile)

    if name != b'MTrk':
        raise OSError('no MTrk header at start of track')

    if debug:
        _dbg(f'-> size={size}')
        _dbg()

    start = infile.tell()
    last_status = None

    while True:
        # End of track reached.
        if infile.tell() - start == size:
            break

        if debug:
            _dbg('Event:')

        delta_time = read_variable_int(infile)

        if debug:
            _dbg(f'-> delta_time={delta_time}')

        status_byte = read_byte(infile)

        if status_byte < 0x80:
            if last_status is None:
                raise OSError('running status without last_status')
            peek_data = [status_byte]
            status_byte = last_status
        else:
            if status_byte != 0xff:
                # Meta events don't set running status.
                last_status = status_byte
            peek_data = []

        if status_byte == 0xff:
            event = read_meta_event(infile, delta_time)
        elif status_byte in [0xf0, 0xf7]:
            # TODO: I'm not quite clear on the difference between
            # f0 and f7 events.
            event = read_sysex_event(infile, delta_time, clip)
        else:
            event = read_message_event(
                infile, status_byte, peek_data, delta_time, clip)

        track.append(event)

        if debug:
            _dbg(f'-> {event!r}')
            _dbg()

    return track


def write_chunk(outfile, name, data):
    """Write an IFF chunk to the file.

    `name` must be a bytestring."""
    outfile.write(name)
    outfile.write(struct.pack('>L', len(data)))
    outfile.write(data)


def write_track(outfile, track):
    data = bytearray()

    running_status_byte = None
    for event in fix_end_of_track(track):
        if not isinstance(event.delta_time, Integral):
            raise ValueError('event delta time must be int in MIDI file')
        if event.delta_time < 0:
            raise ValueError('event delta time must be non-negative in MIDI '
                             'file')

        if event.is_realtime:
            raise ValueError('realtime messages are not allowed in MIDI files')

        data.extend(encode_variable_int(event.delta_time))

        if event.is_meta:
            data.extend(event.bytes())
            running_status_byte = None
        elif event.type == 'sysex':
            data.append(0xf0)
            # length (+ 1 for end byte (0xf7))
            data.extend(encode_variable_int(len(event.data) + 1))
            data.extend(event.data)
            data.append(0xf7)
            running_status_byte = None
        else:
            event_bytes = event.bytes()
            status_byte = event_bytes[0]

            if status_byte == running_status_byte:
                data.extend(event_bytes[1:])
            else:
                data.extend(event_bytes)

            if status_byte < 0xf0:
                running_status_byte = status_byte
            else:
                running_status_byte = None

    write_chunk(outfile, b'MTrk', data)


def get_seconds_per_tick(tempo, ticks_per_beat):
    # Tempo is given in microseconds per beat (default 500000).
    # At this tempo there are (500000 / 1000000) == 0.5 seconds
    # per beat. At the default resolution of 480 ticks per beat
    # this is:
    #
    #    (500000 / 1000000) / 480 == 0.5 / 480 == 0.0010417
    #
    return (tempo / 1000000.0) / ticks_per_beat


class MidiFile:
    def __init__(self, filename=None, file=None,
                 type=1, ticks_per_beat=DEFAULT_TICKS_PER_BEAT,
                 charset='latin1',
                 debug=False,
                 clip=False,
                 tracks=None
                 ):

        self.filename = filename
        self.type = type
        self.ticks_per_beat = ticks_per_beat
        self.charset = charset
        self.debug = debug
        self.clip = clip

        self.tracks = []
        self._merged_track = None

        if type not in range(3):
            raise ValueError(
                f'invalid format {format} (must be 0, 1 or 2)')

        if tracks is not None:
            self.tracks = tracks
        elif file is not None:
            self._load(file)
        elif self.filename is not None:
            with open(filename, 'rb') as file:
                self._load(file)

    @property
    def merged_track(self):
        # The tracks of type 2 files are not in sync, so they can
        # not be played back like this.
        if self.type == 2:
            raise TypeError("can't merge tracks in type 2 (asynchronous) file")

        if self._merged_track is None:
            self._merged_track = merge_tracks(self.tracks, skip_checks=True)
        return self._merged_track

    @merged_track.deleter
    def merged_track(self):
        self._merged_track = None

    def add_track(self, name=None):
        """Add a new track to the file.

        This will create a new MidiTrack object and append it to the
        track list.
        """
        track = MidiTrack()
        if name is not None:
            track.name = name
        self.tracks.append(track)
        del self.merged_track  # uncache merged track
        return track

    def _load(self, infile):
        if self.debug:
            infile = DebugFileWrapper(infile)

        with meta_charset(self.charset):
            if self.debug:
                _dbg('Header:')

            (self.type,
             num_tracks,
             self.ticks_per_beat) = read_file_header(infile)

            if self.debug:
                _dbg('-> type={}, tracks={}, ticks_per_beat={}'.format(
                    self.type, num_tracks, self.ticks_per_beat))
                _dbg()

            for i in range(num_tracks):
                if self.debug:
                    _dbg(f'Track {i}:')

                self.tracks.append(read_track(infile,
                                              debug=self.debug,
                                              clip=self.clip))
                # TODO: used to ignore EOFError. I hope things still work.

    @property
    def length(self):
        """Playback time in seconds.

        This will be computed by going through every event in every
        track and adding up delta times.
        """
        if self.type == 2:
            raise ValueError('impossible to compute length'
                             ' for type 2 (asynchronous) file')

        return sum(event.delta_time for event in self)

    def __iter__(self):
        # The tracks of type 2 files are not in sync, so they can
        # not be played back like this.
        if self.type == 2:
            raise TypeError("can't merge tracks in type 2 (asynchronous) file")

        tempo = DEFAULT_TEMPO
        for event in self.merged_track:
            # Convert event time from absolute time
            # in ticks to relative time in seconds.
            # FIXME: delta_time should not contain time in seconds!
            if event.delta_time > 0:
                delta_time = tick2second(event.delta_time, self.ticks_per_beat,
                                         tempo)
            else:
                delta_time = 0

            yield event.copy(delta_time=delta_time, skip_checks=True)

            if event.type == 'set_tempo':
                tempo = event.tempo

    def play(self, meta_events=False, now=time.time):
        """Play back all tracks.

        The generator will sleep between each event by
        default. Events are yielded with correct timing. The time
        attribute is set to the number of seconds slept since the
        previous event.

        By default, you will only get normal MIDI message events. Pass
        meta_events=True if you also want meta events.

        You will receive copies of the original events, so you can
        safely modify them without ruining the tracks.

        By default, the system clock is used for the timing of yielded
        MIDI events. To use a different clock (e.g. to synchronize to
        an audio stream), pass now=time_fn where time_fn is a zero
        argument function that yields the current time in seconds.
        """
        start_time = now()
        input_time = 0.0

        for event in self:
            input_time += event.delta_time

            playback_time = now() - start_time
            duration_to_next_event = input_time - playback_time

            if duration_to_next_event > 0.0:
                # FIXME: this can be unreliable
                time.sleep(duration_to_next_event)
                # TODO: set the time attribute per the docstring

            if isinstance(event, MetaEvent) and not meta_events:
                continue
            else:
                yield event

    def save(self, filename=None, file=None):
        """Save to a file.

        If file is passed the data will be saved to that file. This is
        typically an in-memory file or and already open file like sys.stdout.

        If filename is passed the data will be saved to that file.

        Raises ValueError if both file and filename are None,
        or if a type 0 file has != one track.
        """
        if self.type == 0 and len(self.tracks) != 1:
            raise ValueError('type 0 file must have exactly 1 track')

        if file is not None:
            self._save(file)
        elif filename is not None:
            with open(filename, 'wb') as file:
                self._save(file)
        else:
            raise ValueError('requires filename or file')

    def _save(self, outfile):
        with meta_charset(self.charset):
            header = struct.pack('>hhh', self.type,
                                 len(self.tracks),
                                 self.ticks_per_beat)

            write_chunk(outfile, b'MThd', header)

            for track in self.tracks:
                write_track(outfile, track)

    def print_tracks(self, meta_only=False):
        """Prints out all events in a .midi file.

        May take argument meta_only to show only meta events.

        Use:
        print_tracks() -> will print all events
        print_tracks(meta_only=True) -> will print only MetaEvent
        """
        for i, track in enumerate(self.tracks):
            print(f'=== Track {i}')  # noqa: T201
            for event in track:
                if not isinstance(event, MetaEvent) and meta_only:
                    pass
                else:
                    print(f'{event!r}')  # noqa: T201

    def __repr__(self):
        if self.tracks:
            tracks_str = ',\n'.join(repr(track) for track in self.tracks)
            tracks_str = '  ' + tracks_str.replace('\n', '\n  ')
            tracks_str = f', tracks=[\n{tracks_str}\n]'
        else:
            tracks_str = ''

        return '{}(type={}, ticks_per_beat={}{})'.format(
            self.__class__.__name__,
            self.type,
            self.ticks_per_beat,
            tracks_str,
        )

    # The context manager has no purpose but is kept around since it was
    # used in examples in the past.
    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        return False
