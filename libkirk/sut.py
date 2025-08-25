"""
.. module:: sut
    :platform: Linux
    :synopsis: sut definition

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

import asyncio
import re
from typing import Any, Dict, List, Optional, Tuple

from libkirk.errors import KirkException, SUTError
from libkirk.plugin import Plugin


class IOBuffer:
    """
    IO stdout buffer. The API is similar to ``IO`` types.
    """

    async def write(self, data: str) -> None:
        """
        Write data.
        """
        raise NotImplementedError()


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


class SUT(Plugin):
    """
    SUT abstraction class. It could be a remote host, a local host, a virtual
    machine instance, etc.
    """

    FAULT_INJECTION_FILES = [
        "fail_io_timeout",
        "fail_make_request",
        "fail_page_alloc",
        "failslab",
    ]

    @property
    def parallel_execution(self) -> bool:
        """
        If True, SUT supports commands parallel execution.
        """
        raise NotImplementedError()

    @property
    async def is_running(self) -> bool:
        """
        Return True if SUT is running.
        """
        raise NotImplementedError()

    async def ping(self) -> float:
        """
        If SUT is replying and it's available, ping will return time needed to
        wait for SUT reply.
        :returns: float
        """
        raise NotImplementedError()

    async def communicate(self, iobuffer: Optional[IOBuffer] = None) -> None:
        """
        Start communicating with the SUT.
        :param iobuffer: buffer used to write SUT stdout
        :type iobuffer: IOBuffer
        """
        raise NotImplementedError()

    async def stop(self, iobuffer: Optional[IOBuffer] = None) -> None:
        """
        Stop the current SUT session.
        :param iobuffer: buffer used to write SUT stdout
        :type iobuffer: IOBuffer
        """
        raise NotImplementedError()

    async def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        iobuffer: Optional[IOBuffer] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Coroutine to run command on target.
        :param command: command to execute
        :type command: str
        :param cwd: current working directory
        :type cwd: str
        :param env: environment variables
        :type env: dict
        :param iobuffer: buffer used to write SUT stdout
        :type iobuffer: IOBuffer
        :returns: dictionary containing command execution information

            {
                "command": <str>,
                "returncode": <int>,
                "stdout": <str>,
                "exec_time": <float>,
            }

            If None is returned, then callback failed.
        """
        raise NotImplementedError()

    async def fetch_file(self, target_path: str) -> bytes:
        """
        Fetch file from target path and return data from target path.
        :param target_path: path of the file to download from target
        :type target_path: str
        :returns: bytes contained in target_path
        """
        raise NotImplementedError()

    async def ensure_communicate(
        self, iobuffer: Optional[IOBuffer], retries: int = 10
    ) -> None:
        """
        Ensure that `communicate` is completed, retrying as many times we
        want in case of `KirkException` error. After each `communicate` error
        the SUT is stopped and a new communication is tried.
        :param iobuffer: buffer used to write SUT stdout
        :type iobuffer: IOBuffer
        :param retries: number of times we retry communicating with SUT
        :type retries: int
        """
        retries = max(retries, 1)

        for retry in range(retries):
            try:
                await self.communicate(iobuffer=iobuffer)
                break
            except KirkException as err:
                if retry >= retries - 1:
                    raise err

                await self.stop(iobuffer=iobuffer)

    async def get_info(self) -> Dict[str, str]:
        """
        Return SUT information.
        :returns: dict

            {
                "distro": str,
                "distro_ver": str,
                "kernel": str,
                "arch": str,
                "cpu" : str,
                "swap" : str,
                "ram" : str,
            }

        """

        # create suite results
        async def _run_cmd(cmd: str) -> str:
            """
            Run command, check for returncode and return command's stdout.
            """
            stdout = "unknown"
            try:
                ret = await asyncio.wait_for(self.run_command(cmd), 1.5)
                if ret and ret["returncode"] == 0:
                    stdout = ret["stdout"].rstrip()
            except asyncio.TimeoutError:
                pass

            return stdout

        # pyrefly: ignore[bad-unpacking]
        distro, distro_ver, kernel, arch, cpu, meminfo = await asyncio.gather(
            *[
                _run_cmd('. /etc/os-release && echo "$ID"'),
                _run_cmd('. /etc/os-release && echo "$VERSION_ID"'),
                _run_cmd("uname -s -r -v"),
                _run_cmd("uname -m"),
                _run_cmd("uname -p"),
                _run_cmd("cat /proc/meminfo"),
            ]
        )

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
            "arch": arch,
            "cpu": cpu,
            "ram": memory,
            "swap": swap,
        }

        return ret

    _tainted_lock = asyncio.Lock()
    _tainted_status = asyncio.Queue(maxsize=1)

    async def get_tainted_info(self) -> Tuple[int, List[str]]:
        """
        Return information about kernel if tainted.
        :returns: (int, list[str])
        """
        if self._tainted_lock.locked() and self._tainted_status.qsize() > 0:
            status = await self._tainted_status.get()
            return status

        async with self._tainted_lock:
            ret = await self.run_command("cat /proc/sys/kernel/tainted")
            if not ret or ret["returncode"] != 0:
                raise SUTError("Can't read tainted kernel information")

            tainted_num = len(TAINTED_MSG)
            code = ret["stdout"].strip()

            # output is likely message in stderr
            if not code.isdigit():
                raise SUTError(code)

            code = int(code)
            bits = format(code, f"0{tainted_num}b")[::-1]

            messages = []
            for i in range(0, tainted_num):
                if bits[i] == "1":
                    msg = TAINTED_MSG[i]
                    messages.append(msg)

            if self._tainted_status.qsize() > 0:
                await self._tainted_status.get()

            await self._tainted_status.put((code, messages))

            return code, messages

    async def logged_as_root(self) -> bool:
        """
        Return True if we are logged as root inside the SUT. False otherwise.
        """
        ret = await self.run_command("id -u")
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
        Return True if fault injection is enabled in the kernel.
        False otherwise.
        """
        for ftype in self.FAULT_INJECTION_FILES:
            ret = await self.run_command(f"test -d /sys/kernel/debug/{ftype}")
            if ret and ret["returncode"] != 0:
                return False

        return True

    async def setup_fault_injection(self, prob) -> None:
        """
        Configure kernel fault injection. When `prob` is zero, the fault
        injection is set to default values.
        :param prob: Fault probabilty in between 0-100
        """
        interval = 1 if prob == 0 else 100
        times = 1 if prob == 0 else -1

        async def _set_value(value, path):
            """
            Set the value to the path
            """
            ret = await self.run_command(f"echo {value} > {path}")
            if ret and ret["returncode"] != 0:
                raise SUTError(f"Can't setup {path}. {ret['stdout']}")

        for ftype in self.FAULT_INJECTION_FILES:
            path = f"/sys/kernel/debug/{ftype}"

            await _set_value(0, f"{path}/space")
            await _set_value(times, f"{path}/times")
            await _set_value(interval, f"{path}/interval")
            await _set_value(prob, f"{path}/probability")
