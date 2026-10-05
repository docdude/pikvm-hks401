import asyncio
import json

from typing import Any
from typing import Callable
from typing import Final

from ... import aiotools
from ... import tools

from ...logging import get_logger

from ...yamlconf import Option
from ...yamlconf import Section

from ...validators.basic import valid_float_f01
from ...validators.basic import valid_number
from ...validators.os import valid_abs_path

from . import BaseUserGpioDriver
from . import GpioDriverOfflineError


class Plugin(BaseUserGpioDriver):

    def __init__(
        self,
        instance_name: str,
        notifier: aiotools.AioNotifier,
        c: Section,
    ) -> None:

        super().__init__(instance_name, notifier, c)

        self.__socket_path: Final[str] = c.socket
        self.__timeout: Final[float] = c.timeout
        self.__state_poll: Final[float] = c.state_poll

        self.__active: int = -1
        self.__online: bool = False
        self.__update_notifier = aiotools.AioNotifier()

    @classmethod
    def get_plugin_options(cls) -> dict:
        return {
            "socket": Option(
                "/run/hks401d.sock",
                type=valid_abs_path,
            ),
            "timeout": Option(
                1.0,
                type=valid_float_f01,
            ),
            "state_poll": Option(
                0.25,
                type=valid_float_f01,
            ),
        }

    @classmethod
    def get_pin_validator(cls) -> Callable[[Any], Any]:
        return valid_number.mk(
            min=1,
            max=4,
            name="HKS401 channel",
        )

    async def run(self) -> None:
        prev_active = -2
        prev_online = False

        while True:
            try:
                response = await self.__command("state")
                state = response["state"]

                active = state.get("active_pc")
                if active in (1, 2, 3, 4):
                    self.__active = int(active)
                else:
                    self.__active = -1

                self.__online = True

            except Exception as ex:
                if self.__online:
                    get_logger(0).error(
                        "Lost connection to HKS401 daemon: %s",
                        tools.efmt(ex),
                    )

                self.__online = False
                self.__active = -1

            if (
                self.__active != prev_active
                or self.__online != prev_online
            ):
                self._notifier.notify()
                prev_active = self.__active
                prev_online = self.__online

            await self.__update_notifier.wait(self.__state_poll)

    async def cleanup(self) -> None:
        self.__online = False
        self.__active = -1

    async def read(self, pin: str) -> bool:
        if not self.__online:
            raise GpioDriverOfflineError(self)

        return self.__active == int(pin)

    async def write(self, pin: str, state: bool) -> None:
        # PiKVM output channels are switches.  We only need the ON
        # transition: selecting an inactive PC makes that channel active.
        # An OFF request for the currently active PC is intentionally ignored.
        if not state:
            return

        channel = int(pin)
        assert 1 <= channel <= 4

        try:
            response = await self.__command(f"select {channel}")

            if not response.get("ok"):
                raise RuntimeError(
                    response.get("error", "HKS401 selection failed")
                )

            # Wake the polling loop immediately instead of waiting for the
            # normal state_poll interval.
            self.__update_notifier.notify()

        except Exception as ex:
            get_logger(0).error(
                "Can't switch HKS401 to PC%d: %s",
                channel,
                tools.efmt(ex),
            )
            self.__online = False
            self.__active = -1
            self._notifier.notify()
            raise GpioDriverOfflineError(self)

    async def __command(self, command: str) -> dict:
        writer = None

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(self.__socket_path),
                timeout=self.__timeout,
            )

            writer.write((command + "\n").encode())
            await asyncio.wait_for(
                writer.drain(),
                timeout=self.__timeout,
            )

            raw = await asyncio.wait_for(
                reader.readline(),
                timeout=self.__timeout,
            )

            if not raw:
                raise RuntimeError("Empty response from hks401d")

            response = json.loads(raw.decode())

            if not response.get("ok"):
                raise RuntimeError(
                    response.get("error", "hks401d command failed")
                )

            return response

        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

    def __str__(self) -> str:
        return f"HKS401({self._instance_name})"

    __repr__ = __str__
