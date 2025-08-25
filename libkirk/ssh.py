"""
.. module:: ssh
    :platform: Linux
    :synopsis: module defining SSH SUT

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

import asyncio
import contextlib
import importlib.util
import logging
import time
from typing import Any, Dict, List, Optional

import libkirk.types
from libkirk.errors import KernelPanicError, SUTError
from libkirk.sut import SUT, IOBuffer

try:
    import asyncssh
    import asyncssh.misc

    class MySSHClientSession(asyncssh.SSHClientSession):
        """
        Custom SSHClientSession used to store stdout during execution of commands
        and to check if Kernel Panic has occured in the system.
        """

        def __init__(self, iobuffer: Optional[IOBuffer] = None):
            self._output = []
            self._iobuffer = iobuffer
            self._panic = False

        # pyrefly: ignore[bad-override]
        def data_received(self, data, _) -> None:
            """
            Override default data_received callback, storing stdout/stderr inside
            a buffer and checking for kernel panic.
            """
            self._output.append(data)

            if self._iobuffer:
                # pyrefly: ignore[unused-coroutine]
                asyncio.ensure_future(self._iobuffer.write(data))

            if "Kernel panic" in data:
                self._panic = True

        def kernel_panic(self) -> bool:
            """
            True if command triggered a kernel panic during its execution.
            """
            return self._panic

        def get_output(self) -> List[str]:
            """
            Return the list containing stored stdout/stderr messages.
            """
            return self._output
except ModuleNotFoundError:
    pass


class SSHSUT(SUT):
    """
    A SUT that is using SSH protocol con communicate and transfer data.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("kirk.ssh")
        self._host = ""
        self._port = 22
        self._reset_cmd = ""
        self._user = ""
        self._password = ""
        self._key_file = ""
        self._sudo = False
        self._known_hosts: Optional[str] = None
        self._session_sem = asyncio.Semaphore()
        self._stop = False
        self._conn = None
        self._channels = []

    @property
    def name(self) -> str:
        return "ssh"

    @property
    def config_help(self) -> Dict[str, str]:
        return {
            "host": "IP address of the SUT (default: localhost)",
            "port": "TCP port of the service (default: 22)",
            "user": "name of the user (default: root)",
            "password": "root password",
            "key_file": "private key location",
            "reset_cmd": "command to reset the remote SUT",
            "sudo": "use sudo to access to root shell (default: 0)",
            "known_hosts": "path to custom known_hosts file (optional)",
        }

    async def _reset(self, iobuffer: Optional[IOBuffer] = None) -> None:
        """
        Run the reset command on host.
        """
        if not self._reset_cmd:
            return

        self._logger.info("Executing reset command: %s", repr(self._reset_cmd))

        proc = await asyncio.create_subprocess_shell(
            self._reset_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        if not proc or not proc.stdout:
            raise SUTError("Can't communicate with the host shell")

        while True:
            line = await proc.stdout.read(1024)
            if line:
                sline = line.decode(encoding="utf-8", errors="ignore")

                if iobuffer:
                    await iobuffer.write(sline)

            with contextlib.suppress(asyncio.TimeoutError):
                returncode = await asyncio.wait_for(proc.wait(), 1e-6)
                if returncode is not None:
                    break

        await proc.wait()

        self._logger.info("Reset command has been executed")

    def _create_command(
        self, cmd: str, cwd: Optional[str], env: Optional[Dict[str, Any]]
    ) -> str:
        """
        Create command to send to SSH client.
        """
        args = []

        if cwd:
            args.append(f"cd {cwd} && ")

        if env:
            for key, value in env.items():
                args.append(f"export {key}={value} && ")

        args.append(cmd)

        script = "".join(args)
        if self._sudo:
            script = f"sudo /bin/sh -c '{script}'"

        return script

    def setup(self, **kwargs: Dict[str, Any]) -> None:
        if not importlib.util.find_spec("asyncssh"):
            raise SUTError("'asyncssh' library is not available")

        self._logger.info("Initialize SUT")

        self._host = libkirk.types.dict_item(kwargs, "host", str, default="localhost")
        self._reset_cmd = libkirk.types.dict_item(
            kwargs, "reset_cmd", str, default=None
        )
        self._user = libkirk.types.dict_item(kwargs, "user", str, default="root")
        self._password = libkirk.types.dict_item(kwargs, "password", str, default=None)
        self._key_file = libkirk.types.dict_item(kwargs, "key_file", str, default=None)
        self._known_hosts = libkirk.types.dict_item(
            kwargs, "known_hosts", str, default="~/.ssh/known_hosts"
        )

        if self._known_hosts == "/dev/null":
            self._known_hosts = None

        try:
            self._port = int(libkirk.types.dict_item(kwargs, "port", str, default="22"))

            if 1 > self._port > 65535:
                raise ValueError()
        except ValueError as err:
            raise SUTError("'port' must be an integer between 1-65535") from err

        try:
            self._sudo = (
                int(libkirk.types.dict_item(kwargs, "sudo", str, default="0")) == 1
            )
        except ValueError as err:
            raise SUTError("'sudo' must be 0 or 1") from err

    @property
    def parallel_execution(self) -> bool:
        return True

    @property
    async def is_running(self) -> bool:
        return self._conn is not None

    async def communicate(self, iobuffer: Optional[IOBuffer] = None) -> None:
        if await self.is_running:
            raise SUTError("SUT is already running")

        try:
            if self._key_file:
                priv_key = asyncssh.read_private_key(self._key_file)

                # pyrefly: ignore[bad-assignment]
                self._conn = await asyncssh.connect(
                    host=self._host,
                    port=self._port,
                    username=self._user,
                    client_keys=[priv_key],
                    known_hosts=self._known_hosts,
                )
            else:
                # pyrefly: ignore[bad-assignment]
                self._conn = await asyncssh.connect(
                    host=self._host,
                    port=self._port,
                    username=self._user,
                    password=self._password,
                    known_hosts=self._known_hosts,
                )

            # pyrefly: ignore[missing-attribute]
            # read maximum number of sessions and limit `run_command`
            # concurrent calls to that by using a semaphore
            ret = await self._conn.run(
                r'sed -n "s/^MaxSessions\s*\([[:digit:]]*\)/\1/p" '
                "/etc/ssh/sshd_config"
            )

            max_sessions = ret.stdout or 10

            self._logger.info("Maximum SSH sessions: %d", max_sessions)
            self._session_sem = asyncio.Semaphore(max_sessions)
        except asyncssh.misc.Error as err:
            if not self._stop:
                raise SUTError(err) from err

    async def stop(self, iobuffer: Optional[IOBuffer] = None) -> None:
        if not await self.is_running:
            return

        self._stop = True
        try:
            if self._channels:
                self._logger.info("Killing %d process(es)", len(self._channels))

                for proc in self._channels:
                    proc.kill()
                    await proc.wait_closed()

                self._channels.clear()

            self._logger.info("Closing connection")
            # pyrefly: ignore[missing-attribute]
            self._conn.close()
            # pyrefly: ignore[missing-attribute]
            await self._conn.wait_closed()
            self._logger.info("Connection closed")

            await self._reset(iobuffer=iobuffer)
        finally:
            self._stop = False
            self._conn = None

    async def ping(self) -> float:
        if not await self.is_running:
            raise SUTError("SUT is not running")

        start_t = time.time()

        self._logger.info("Ping %s:%d", self._host, self._port)

        try:
            # pyrefly: ignore[missing-attribute]
            await self._conn.run("test .", check=True)
        except asyncssh.Error as err:
            raise SUTError(err) from err

        end_t = time.time() - start_t

        self._logger.info("SUT replied after %.3f seconds", end_t)

        return end_t

    async def run_command(
        self,
        command: str,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        iobuffer: Optional[IOBuffer] = None,
    ) -> Optional[Dict[str, Any]]:
        if not command:
            raise ValueError("command is empty")

        if not await self.is_running:
            raise SUTError("SSH connection is not present")

        async with self._session_sem:
            cmd = self._create_command(command, cwd, env)
            start_t = 0
            stdout = []
            panic = False
            channel = None
            session = None
            ret = {
                "command": command,
                "returncode": 1,
                "exec_time": 0.0,
                "stdout": "",
            }

            try:
                self._logger.info("Running command: %s", repr(command))

                # pyrefly: ignore[missing-attribute]
                channel, session = await self._conn.create_session(
                    lambda: MySSHClientSession(iobuffer), cmd
                )

                self._channels.append(channel)
                start_t = time.time()

                await channel.wait_closed()

                panic = session.kernel_panic()
                stdout = session.get_output()
            except asyncssh.misc.ChannelOpenError as err:
                if not self._stop:
                    raise SUTError(err)
            finally:
                if channel:
                    self._channels.remove(channel)
                    ret["returncode"] = channel.get_returncode()
                    ret["stdout"] = "".join(stdout)

                ret["exec_time"] = time.time() - start_t

            if panic:
                raise KernelPanicError()

            self._logger.info("Command executed")
            self._logger.debug(ret)

            return ret

    async def fetch_file(self, target_path: str) -> bytes:
        if not target_path:
            raise ValueError("target path is empty")

        if not await self.is_running:
            raise SUTError("SSH connection is not present")

        data = bytes()
        try:
            # pyrefly: ignore[missing-attribute]
            ret = await self._conn.run(f"cat {target_path}", check=True, encoding=None)

            data = bytes(ret.stdout)
        except asyncssh.Error as err:
            if not self._stop:
                raise SUTError(err) from err

        return data
