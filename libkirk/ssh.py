"""
.. module:: ssh
    :platform: Linux
    :synopsis: module defining SSH SUT

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import time
import asyncio
import logging
import importlib
import contextlib
from libkirk.sut import SUT
from libkirk.sut import SUTError
from libkirk.sut import IOBuffer
from libkirk.sut import KernelPanicError

try:
    import asyncssh
    import asyncssh.misc

    class MySSHClientSession(asyncssh.SSHClientSession):
        """
        Custom SSHClientSession used to store stdout during execution of commands
        and to check if Kernel Panic has occured in the system.
        """

        def __init__(self, iobuffer: IOBuffer):
            self._output = []
            self._iobuffer = iobuffer
            self._panic = False

        def data_received(self, data, _) -> None:
            """
            Override default data_received callback, storing stdout/stderr inside
            a buffer and checking for kernel panic.
            """
            self._output.append(data)

            if self._iobuffer:
                asyncio.ensure_future(self._iobuffer.write(data))

            if "Kernel panic" in data:
                self._panic = True

        def kernel_panic(self) -> bool:
            """
            True if command triggered a kernel panic during its execution.
            """
            return self._panic

        def get_output(self) -> list:
            """
            Return the list containing stored stdout/stderr messages.
            """
            return self._output
except ModuleNotFoundError:
    pass


# pylint: disable=too-many-instance-attributes
class SSHSUT(SUT):
    """
    A SUT that is using SSH protocol con communicate and transfer data.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("kirk.ssh")
        self._tmpdir = None
        self._host = None
        self._port = None
        self._reset_cmd = None
        self._user = None
        self._password = None
        self._key_file = None
        self._sudo = False
        self._known_hosts = None
        self._session_sem = None
        self._stop = False
        self._conn = None
        self._downloader = None
        self._channels = []

    @property
    def name(self) -> str:
        return "ssh"

    @property
    def config_help(self) -> dict:
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

    async def _reset(self, iobuffer: IOBuffer = None) -> None:
        """
        Run the reset command on host.
        """
        if not self._reset_cmd:
            return

        self._logger.info("Executing reset command: %s", repr(self._reset_cmd))

        proc = await asyncio.create_subprocess_shell(
            self._reset_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE)

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

    def _create_command(self, cmd: str, cwd: str, env: dict) -> str:
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

        script = ''.join(args)
        if self._sudo:
            script = f"sudo /bin/sh -c '{script}'"

        return script

    def setup(self, **kwargs: dict) -> None:
        if not importlib.util.find_spec('asyncssh'):
            raise SUTError("'asyncssh' library is not available")

        self._logger.info("Initialize SUT")

        self._tmpdir = kwargs.get("tmpdir", None)
        self._host = kwargs.get("host", "localhost")
        self._port = kwargs.get("port", 22)
        self._reset_cmd = kwargs.get("reset_cmd", None)
        self._user = kwargs.get("user", "root")
        self._password = kwargs.get("password", None)
        self._key_file = kwargs.get("key_file", None)
        self._known_hosts = kwargs.get("known_hosts", None)

        try:
            self._port = int(kwargs.get("port", "22"))

            if 1 > self._port > 65535:
                raise ValueError()
        except ValueError:
            raise SUTError("'port' must be an integer between 1-65535")

        try:
            self._sudo = int(kwargs.get("sudo", 0)) == 1
        except ValueError:
            raise SUTError("'sudo' must be 0 or 1")

    @property
    def parallel_execution(self) -> bool:
        return True

    @property
    async def is_running(self) -> bool:
        return self._conn is not None

    async def communicate(self, iobuffer: IOBuffer = None) -> None:
        if await self.is_running:
            raise SUTError("SUT is already running")

        try:
            self._conn = None
            if self._key_file:
                priv_key = asyncssh.read_private_key(self._key_file)

                self._conn = await asyncssh.connect(
                    host=self._host,
                    port=self._port,
                    username=self._user,
                    client_keys=[priv_key],
                    known_hosts=self._known_hosts)
            else:
                self._conn = await asyncssh.connect(
                    host=self._host,
                    port=self._port,
                    username=self._user,
                    password=self._password,
                    known_hosts=self._known_hosts)

            # read maximum number of sessions and limit `run_command`
            # concurrent calls to that by using a semaphore
            ret = await self._conn.run(
                r'sed -n "s/^MaxSessions\s*\([[:digit:]]*\)/\1/p" '
                '/etc/ssh/sshd_config')

            max_sessions = ret.stdout or 10

            self._logger.info("Maximum SSH sessions: %d", max_sessions)
            self._session_sem = asyncio.Semaphore(max_sessions)
        except asyncssh.misc.ChannelOpenError as err:
            if not self._stop:
                raise SUTError(err)

    async def stop(self, iobuffer: IOBuffer = None) -> None:
        if not await self.is_running:
            return

        self._stop = True
        try:
            if self._channels:
                self._logger.info("Killing %d process(es)",
                                  len(self._channels))

                for proc in self._channels:
                    proc.kill()
                    await proc.wait_closed()

                self._channels.clear()

            if self._downloader:
                await self._downloader.close()

            self._logger.info("Closing connection")
            self._conn.close()
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
            await self._conn.run("test .", check=True)
        except asyncssh.Error as err:
            raise SUTError(err)

        end_t = time.time() - start_t

        self._logger.info("SUT replied after %.3f seconds", end_t)

        return end_t

    async def run_command(
            self,
            command: str,
            cwd: str = None,
            env: dict = None,
            iobuffer: IOBuffer = None) -> dict:
        if not command:
            raise ValueError("command is empty")

        if not await self.is_running:
            raise SUTError("SSH connection is not present")

        async with self._session_sem:
            cmd = self._create_command(command, cwd, env)
            ret = None
            start_t = 0
            stdout = []
            panic = False
            channel = None
            session = None

            try:
                self._logger.info("Running command: %s", repr(command))

                channel, session = await self._conn.create_session(
                    lambda: MySSHClientSession(iobuffer),
                    cmd
                )

                self._channels.append(channel)
                start_t = time.time()

                await channel.wait_closed()

                panic = session.kernel_panic()
                stdout = session.get_output()
            finally:
                if channel:
                    self._channels.remove(channel)

                    ret = {
                        "command": command,
                        "returncode": channel.get_returncode(),
                        "exec_time": time.time() - start_t,
                        "stdout": "".join(stdout)
                    }

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

        data = None
        try:
            ret = await self._conn.run(
                f"cat {target_path}",
                check=True,
                encoding=None)

            data = ret.stdout
        except asyncssh.Error as err:
            if not self._stop:
                raise SUTError(err)

        return data
