# SPDX-FileCopyrightText: 2014 Ole Martin Bjorndalen <ombdalen@gmail.com>
# SPDX-FileCopyrightText: 2023 Raphaël Doursenaud <rdoursenaud@gmail.com>
#
# SPDX-License-Identifier: MIT


from __future__ import annotations

import importlib
import os
from types import ModuleType
from typing import Any, Callable, Dict, Optional, Type

from typing_extensions import Final

from .. import ports

DEFAULT_BACKEND: Final = 'mido.backends.rtmidi'


class Backend:
    """A wrapper for the backend module.

    A backend module implements classes for input and output ports for
    a specific MIDI library. The Backend object wraps around the
    object and provides convenient ``open_*()`` and ``get_*_names()``
    functions.
    """
    def __init__(
            self,
            name: str | None = None,
            api: str | None = None,
            load: bool = False,
            use_environ: bool = True,
    ):
        """Initializes a new backend.

        :param name: of the backend.
        :type name: str | None, optional, defaults to None

        :param api: of the backend.
        :type api: str | None, optional, defaults to None

        :param load: load the backend immediately or defer to first use.
        :type load: bool, optional, defaults to False

        :param use_environ: allow or block getting default backend information
            from the environment variables.
        :type use_environ: bool, optional, defaults to True
        """
        self.name = name or os.environ.get('MIDO_BACKEND', DEFAULT_BACKEND)
        self.api = api
        self.use_environ = use_environ
        self._module: ModuleType | None = None

        # Split out api (if present).
        if api:
            self.api = api
        elif self.name and '/' in self.name:
            self.name, self.api = self.name.split('/', 1)
        else:
            self.api = None

        if load:
            self.load()

    @property
    def module(self) -> ModuleType:
        """A reference module implementing the backend.

        This will always be a valid reference to a module. Accessing
        this property will load the module. Use :attr:`.loaded` to check if
        the module is loaded.
        """
        self.load()
        return self._module

    @property
    def loaded(self) -> bool:
        """Returns ``True`` if the module is loaded.
        """
        return self._module is not None

    def load(self) -> None:
        """Loads the module.

        Does nothing if the module is already loaded.

        This function will be called if you access the :attr:`module` property.
        """
        if not self.loaded:
            self._module = importlib.import_module(self.name)

    def _env(self, name: str) -> str | None:
        if self.use_environ:
            return os.environ.get(name)
        else:
            return None

    def _add_api(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        if self.api and 'api' not in kwargs:
            kwargs['api'] = self.api
        return kwargs

    def open_input(
            self,
            name: str | None = None,
            virtual: bool = False,
            callback: Optional[Callable] = None,
            **kwargs,
    ) -> 'Type[ports.BaseInput]':
        """Opens an input port.

        If the environment variable ``MIDO_DEFAULT_INPUT`` is set,
        it will override the default port.

        :param name: of the input port to open. Omit to use the default port.
        :type name: str, optional

        :param virtual: Passing True opens a new port that other
            applications can connect to.
        :type virtual: bool, optional, defaults to False

        :param callback: A callback function to be called
            when a new message arrives.
            The function should take one argument: the message.
        :type callback: callable, optional, defaults to None

        :raises: IOError if ``virtual`` and/or ``callback`` is
            set and not supported by the backend.

        :return: the opened input port.
        :rtype: BaseInput
        """
        kwargs.update(dict(virtual=virtual, callback=callback))

        if name is None:
            name = self._env('MIDO_DEFAULT_INPUT')

        return self.module.Input(name, **self._add_api(kwargs))

    def open_output(
            self,
            name: str | None = None,
            virtual: bool = False,
            autoreset: bool = False,
            **kwargs,
    ) -> 'Type[ports.BaseOutput]':
        """Opens an output port.

        If the environment variable ``MIDO_DEFAULT_OUTPUT`` is set,
        it will override the default port.

        :param name: of the output port to open. Omit to use the default port.
        :type name: str, optional

        :param virtual: Passing True opens a new port that other
            applications can connect to.
        :type virtual: bool, optional, defaults to False

        :param autoreset: Automatically send ``all_notes_off`` and
            ``reset_all_controllers`` on all channels.
            This is the same as calling :func:`reset` on the port.
        :type autoreset: bool, optional, defaults to False

        :raises: IOError if ``virtual`` is
            set and not supported by the backend.
        """
        kwargs.update(dict(virtual=virtual, autoreset=autoreset))

        if name is None:
            name = self._env('MIDO_DEFAULT_OUTPUT')

        return self.module.Output(name, **self._add_api(kwargs))

    def open_ioport(
            self,
            name: str | None = None,
            virtual: bool = False,
            callback: Optional[Callable] = None,
            autoreset: bool = False,
            **kwargs,
    ) -> 'ports.IOPort':
        """Open a port for input and output.

        If the environment variable ``MIDO_DEFAULT_IOPORT`` is set,
        it will override the default port.

        :param name: of the input/output port to open.
            Omit to use the default port.
        :type name: str, optional

        :param virtual: Passing True opens a new port that other
            applications can connect to.
        :type virtual: bool, optional, defaults to False

        :param callback: A callback function to be called
            when a new message arrives.
            The function should take one argument: the message.
        :type callback: callable, optional, defaults to None

        :param autoreset: Automatically send ``all_notes_off`` and
            ``reset_all_controllers`` on all channels. This is the same as
            calling :func:`reset` on the port.
        :type autoreset: bool, optional, defaults to False

        :raises: IOError if ``virtual`` and/or ``callback`` is
            set and not supported by the backend.
        """
        kwargs.update(dict(virtual=virtual, callback=callback,
                           autoreset=autoreset))

        if name is None:
            name = self._env('MIDO_DEFAULT_IOPORT') or None

        if hasattr(self.module, 'IOPort'):
            # Backend has a native IOPort. Use it.
            return self.module.IOPort(name, **self._add_api(kwargs))
        else:
            # Backend has no native IOPort. Use the IOPort wrapper
            # in midi.ports.
            #
            # We need an input and an output name.

            # MIDO_DEFAULT_IOPORT overrides the other two variables.
            if name:
                input_name = output_name = name
            else:
                input_name = self._env('MIDO_DEFAULT_INPUT')
                output_name = self._env('MIDO_DEFAULT_OUTPUT')

            kwargs = self._add_api(kwargs)

            return ports.IOPort(self.module.Input(input_name, **kwargs),
                                self.module.Output(output_name, **kwargs))

    def _get_devices(self, **kwargs):
        if hasattr(self.module, 'get_devices'):
            return self.module.get_devices(**self._add_api(kwargs))
        else:
            return []

    def get_input_names(self, **kwargs) -> list[str]:
        """Lists all input ports names.

        :return: all input ports names.
        :rtype: list[str]
        """
        devices = self._get_devices(**self._add_api(kwargs))
        names = [device['name'] for device in devices if device['is_input']]
        return names

    def get_output_names(self, **kwargs) -> list[str]:
        """lists all output ports names.

        :return: all output ports names.
        :rtype: list[str]
        """
        devices = self._get_devices(**self._add_api(kwargs))
        names = [device['name'] for device in devices if device['is_output']]
        return names

    def get_ioport_names(self, **kwargs) -> list[str]:
        """Lists all I/O ports names.

        :return: all I/O ports names.
        :rtype: list[str]
        """
        devices = self._get_devices(**self._add_api(kwargs))
        inputs = [device['name'] for device in devices if device['is_input']]
        outputs = {
            device['name'] for device in devices if device['is_output']}
        return [name for name in inputs if name in outputs]

    def __repr__(self):
        if self.loaded:
            status = 'loaded'
        else:
            status = 'not loaded'

        if self.api:
            name = f'{self.name}/{self.api}'
        else:
            name = self.name

        return f'<backend {name} ({status})>'
