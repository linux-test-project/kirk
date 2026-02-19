"""
.. module:: sut
    :platform: Linux
    :synopsis: module implementing SUT

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

import asyncio
import re
from typing import (
    Dict,
    List,
    Optional,
    Tuple,
)

import libkirk.plugin
from libkirk.com import (
    ComChannel,
    IOBuffer,
)
from libkirk.errors import SUTError
from libkirk.plugin import Plugin

# discovered SUT implementations
_SUT = []


class SUT(Plugin):
    """
    SUT abstraction class. It could be a remote host, a local host, a virtual
    machine instance, or any complex system we want to test.
    """

    TAINTED_MSG = [
        "proprietary module was loaded",
        "module was force loaded",
        "kernel running on an out of specification system",
        "module was force unloaded",
        "processor reported a Machine Check Exception (MCE)",
        "bad page referenced or some unexpected page flags",
        "taint requested by userspace application",
        "kernel died recently, i.e. there was an OOPS or BUG",
        "ACPI table overridden by user",
        "kernel issued warning",
        "staging driver was loaded",
        "workaround for bug in platform firmware applied",
        "externally-built (“out-of-tree”) module was loaded",
        "unsigned module was loaded",
        "soft lockup occurred",
        "kernel has been live patched",
        "auxiliary taint, defined for and used by distros",
        "kernel was built with the struct randomization plugin",
    ]

    FAULT_INJECTION_FILES = [
        "fail_io_timeout",
        "fail_make_request",
        "fail_page_alloc",
        "failslab",
    ]

    _optimize = False

    def get_channel(self) -> ComChannel:
        """
        :return: Main channel to communicated with SUT.
        :rtype: ComChannel
        """
        raise NotImplementedError()

    async def start(self, iobuffer: Optional[IOBuffer] = None) -> None:
        """
        Start the SUT.

        :param iobuffer: IO channel where to write stdout.
        :type iobuffer: IOBuffer
        """
        raise NotImplementedError()

    async def stop(self, iobuffer: Optional[IOBuffer] = None) -> None:
        """
        Stop the SUT.

        :param iobuffer: IO channel where to write stdout.
        :type iobuffer: IOBuffer
        """
        raise NotImplementedError()

    async def restart(self, iobuffer: Optional[IOBuffer] = None) -> None:
        """
        Restart the SUT.

        :param iobuffer: IO channel where to write stdout.
        :type iobuffer: IOBuffer
        """
        raise NotImplementedError()

    @property
    async def is_running(self) -> bool:
        """
        :return: True if system under test is up and running. False otherwise.
        :rtype: bool
        """
        raise NotImplementedError()

    @property
    def optimize(self) -> bool:
        """
        Optimize the commands execution by applying parallelization
        when it's available.

        :return: True if SUT will optimize commands execution on SUT.
        """
        return self._optimize

    @optimize.setter
    def optimize(self, value: bool) -> None:
        """
        Set commands execution optimization.
        """
        self._optimize = value

    async def _run_cmd(self, cmd: str) -> str:
        """
        Run command, check for returncode and return command's stdout.
        """
        stdout = "unknown"
        try:
            channel = self.get_channel()
            ret = await asyncio.wait_for(channel.run_command(cmd), 1.5)
            if ret and ret["returncode"] == 0:
                stdout = ret["stdout"].rstrip()
        except asyncio.TimeoutError:
            pass

        return stdout

    async def _get_distro(self) -> str:
        """
        Return the distro name.
        """
        return await self._run_cmd('. /etc/os-release && echo "$ID"')

    async def _get_distro_ver(self) -> str:
        """
        Return the distro version.
        """
        return await self._run_cmd('. /etc/os-release && echo "$VERSION_ID"')

    async def _get_kernel(self) -> str:
        """
        Return the kernel name.
        """
        return await self._run_cmd("uname -s -r -v")

    async def _get_cmdline(self) -> str:
        """
        Return /proc/cmdline content.
        """
        return await self._run_cmd("cat /proc/cmdline")

    async def _get_arch(self) -> str:
        """
        Return the architecture name.
        """
        return await self._run_cmd("uname -m")

    async def _get_cpu(self) -> str:
        """
        Return the CPU name.
        """
        return await self._run_cmd("uname -p")

    async def _get_meminfo(self) -> str:
        """
        Return the memory information.
        """
        return await self._run_cmd("cat /proc/meminfo")

    async def get_info(self) -> Dict[str, str]:
        """
        Return SUT information.

        :return: Dictionary containing the SUT information in the form of:

            .. code-block:: python

                {
                    "distro": str,
                    "distro_ver": str,
                    "kernel": str,
                    "cmdline": str,
                    "arch": str,
                    "cpu" : str,
                    "swap" : str,
                    "ram" : str,
                }

        :rtype: dict
        """
        if not await self.is_running:
            raise SUTError("SUT is not running")

        distro = ""
        distro_ver = ""
        kernel = ""
        cmdline = ""
        arch = ""
        cpu = ""
        meminfo = ""

        if self.optimize:
            # pyrefly: ignore[bad-unpacking]
            distro, distro_ver, kernel, cmdline, arch, cpu, meminfo = await asyncio.gather(
                *[
                    self._get_distro(),
                    self._get_distro_ver(),
                    self._get_kernel(),
                    self._get_cmdline(),
                    self._get_arch(),
                    self._get_cpu(),
                    self._get_meminfo(),
                ]
            )
        else:
            distro = await self._get_distro()
            distro_ver = await self._get_distro_ver()
            kernel = await self._get_kernel()
            cmdline = await self._get_cmdline()
            arch = await self._get_arch()
            cpu = await self._get_cpu()
            meminfo = await self._get_meminfo()

        memory = "unknown"
        swap = "unknown"

        if meminfo:
            mem_m = re.search(r"MemTotal:\s+(?P<memory>\d+\s+kB)", meminfo)
            if mem_m:
                memory = mem_m.group("memory")

            swap_m = re.search(r"SwapTotal:\s+(?P<swap>\d+\s+kB)", meminfo)
            if swap_m:
                swap = swap_m.group("swap")

        ret = {
            "distro": distro,
            "distro_ver": distro_ver,
            "kernel": kernel,
            "cmdline": cmdline,
            "arch": arch,
            "cpu": cpu,
            "ram": memory,
            "swap": swap,
        }

        return ret

    # Lazily initialised inside get_tainted_info() so that the
    # asyncio primitives are always created on the *running* loop.
    # Class-level assignment would bind them to the loop that was
    # current at import time, which breaks on Python 3.7-3.9 when
    # tests run on a different loop than the session loop.
    _tainted_lock: Optional[asyncio.Lock] = None
    _tainted_status: Optional[asyncio.Queue] = None

    async def get_tainted_info(self) -> Tuple[int, List[str]]:
        """
        Return information about kernel if tainted.

        :return: A tuple containing tainted information. First element is the
            tainted code and the second element is the tainted message.
        :rtype: (int, list[str])
        """
        if not await self.is_running:
            raise SUTError("SUT is not running")

        # Initialise on first use, always inside a running loop.
        if self._tainted_lock is None:
            self._tainted_lock = asyncio.Lock()
        if self._tainted_status is None:
            self._tainted_status = asyncio.Queue(maxsize=1)

        if self._tainted_lock.locked() and self._tainted_status.qsize() > 0:
            status = await self._tainted_status.get()
            return status

        async with self._tainted_lock:
            channel = self.get_channel()
            ret = await channel.run_command("cat /proc/sys/kernel/tainted")
            if not ret or ret["returncode"] != 0:
                raise SUTError("Can't read tainted kernel information")

            tainted_num = len(self.TAINTED_MSG)
            code = ret["stdout"].strip()

            # output is likely message in stderr
            if not code.isdigit():
                raise SUTError(code)

            code = int(code)
            bits = format(code, f"0{tainted_num}b")[::-1]

            messages = []
            for i in range(0, tainted_num):
                if bits[i] == "1":
                    msg = self.TAINTED_MSG[i]
                    messages.append(msg)

            if self._tainted_status.qsize() > 0:
                await self._tainted_status.get()

            await self._tainted_status.put((code, messages))

            return code, messages

    async def logged_as_root(self) -> bool:
        """
        :return: True if we are logged as root inside the SUT. False otherwise.
        :rtype: bool
        """
        if not await self.is_running:
            raise SUTError("SUT is not running")

        channel = self.get_channel()
        ret = await channel.run_command("id -u")
        if not ret or ret["returncode"] != 0:
            raise SUTError("Can't determine if we are running as root")

        val = ret["stdout"].rstrip()
        user_id = 100
        try:
            user_id = int(val)
        except ValueError as err:
            raise SUTError(f"'id -u' returned {val}") from err

        return user_id == 0

    async def is_fault_injection_enabled(self) -> bool:
        """
        :return: True if fault injection is enabled in the kernel. False
            otherwise.
        :rtype: bool
        """
        if not await self.is_running:
            raise SUTError("SUT is not running")

        channel = self.get_channel()

        for ftype in self.FAULT_INJECTION_FILES:
            ret = await channel.run_command(f"test -d /sys/kernel/debug/{ftype}")
            if ret and ret["returncode"] != 0:
                return False

        return True

    async def setup_fault_injection(self, prob: int) -> None:
        """
        Configure kernel fault injection. When prob is zero, the fault
        injection is set to default values.

        :param prob: Fault probabilty in between 0-100.
        :type prob: int
        """
        if not await self.is_running:
            raise SUTError("SUT is not running")

        interval = 1 if prob == 0 else 100
        times = 1 if prob == 0 else -1

        async def _set_value(value: int, path: str) -> None:
            """
            Set the value to the path
            """
            channel = self.get_channel()
            ret = await channel.run_command(f"echo {value} > {path}")
            if ret and ret["returncode"] != 0:
                raise SUTError(f"Can't setup {path}. {ret['stdout']}")

        for ftype in self.FAULT_INJECTION_FILES:
            path = f"/sys/kernel/debug/{ftype}"

            await _set_value(0, f"{path}/space")
            await _set_value(times, f"{path}/times")
            await _set_value(interval, f"{path}/interval")
            await _set_value(prob, f"{path}/probability")


def discover(path: str, extend: bool = True) -> None:
    """
    Discover all SUT implementations inside path.

    :param path: Directory where searching for SUT implementations.
    :type path: str
    :param extend: If True, it will add new discovered SUT on top of the
        ones already found. If False, previous discovered SUT will be
        cleared.
    :type param: bool
    """
    global _SUT

    obj = libkirk.plugin.discover(SUT, path)
    if not extend:
        _SUT.clear()

    _SUT.extend(obj)


def get_suts() -> List[ComChannel]:
    """
    :return: List of loaded SUT implementations.
    :rtype: list(ComChannel)
    """
    global _SUT
    # pyrefly: ignore[bad-return]
    return _SUT
