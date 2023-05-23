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
        self._session_sem = None
        self._stop = False
        self._conn = None
        self._downloader = None
        self._procs = []

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
            "timeout": "connection timeout in seconds (default: 10)",
            "key_file": "private key location",
            "reset_command": "command to reset the remote SUT",
            "sudo": "use sudo to access to root shell (default: 0)",
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
                    client_keys=[priv_key])
            else:
                self._conn = await asyncssh.connect(
                    host=self._host,
                    port=self._port,
                    username=self._user,
                    password=self._password)

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
            if self._procs:
                self._logger.info("Killing %d process(es)", len(self._procs))

                for proc in self._procs:
                    proc.kill()
                    await proc.wait()

                self._procs.clear()

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
            proc = None
            start_t = 0

            try:
                self._logger.info("Running command: %s", repr(command))

                proc = await self._conn.create_process(cmd)
                self._procs.append(proc)

                start_t = time.time()
                panic = False
                stdout = ""

                async for data in proc.stdout:
                    stdout += data

                    if iobuffer:
                        await iobuffer.write(data)

                    if "Kernel panic" in data:
                        panic = True
            finally:
                if proc:
                    self._procs.remove(proc)

                    if proc.returncode is None:
                        proc.kill()

                    ret = {
                        "command": command,
                        "returncode": proc.returncode,
                        "exec_time": time.time() - start_t,
                        "stdout": stdout
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
