"""
.. module:: qemu
    :platform: Linux
    :synopsis: module containing qemu SUT implementation

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import re
import time
import signal
import string
import shutil
import secrets
import logging
import asyncio
import contextlib
from libkirk.sut import SUT
from libkirk.sut import IOBuffer
from libkirk.sut import SUTError
from libkirk.sut import KernelPanicError


# pylint: disable=too-many-instance-attributes
class QemuSUT(SUT):
    """
    Qemu SUT spawn a new VM using qemu and execute commands inside it.
    This SUT implementation can be used to run commands inside
    a protected, virtualized environment.
    """

    def __init__(self) -> None:
        self._logger = logging.getLogger("kirk.qemu")
        self._comm_lock = asyncio.Lock()
        self._cmd_lock = asyncio.Lock()
        self._fetch_lock = asyncio.Lock()
        self._tmpdir = None
        self._proc = None
        self._stop = False
        self._logged_in = False
        self._last_pos = 0
        self._user = None
        self._password = None
        self._prompt = None
        self._ram = None
        self._smp = None
        self._virtfs = None
        self._serial_type = None
        self._qemu_cmd = None
        self._opts = None
        self._image = None
        self._kernel = None
        self._initrd = None
        self._last_read = ""
        self._panic = False

    @staticmethod
    def _generate_string(length: int = 10) -> str:
        """
        Generate a random string of the given length.
        """
        out = ''.join(secrets.choice(string.ascii_letters + string.digits)
                      for _ in range(length))
        return out

    def _get_transport(self) -> str:
        """
        Return a couple of transport_dev and transport_file used by
        qemu instance for transport configuration.
        """
        pid = os.getpid()
        transport_file = os.path.join(self._tmpdir, f"transport-{pid}")
        transport_dev = ""

        if self._serial_type == "isa":
            transport_dev = "/dev/ttyS1"
        elif self._serial_type == "virtio":
            transport_dev = "/dev/vport1p1"

        return transport_dev, transport_file

    def _get_command(self) -> str:
        """
        Return the full qemu command to execute.
        """
        pid = os.getpid()
        tty_log = os.path.join(self._tmpdir, f"ttyS0-{pid}.log")

        params = []
        params.append("-enable-kvm")
        params.append("-display none")
        params.append(f"-m {self._ram}")
        params.append(f"-smp {self._smp}")
        params.append("-device virtio-rng-pci")
        params.append(f"-chardev stdio,id=tty,logfile={tty_log}")

        if self._serial_type == "isa":
            params.append("-serial chardev:tty")
            params.append("-serial chardev:transport")
        elif self._serial_type == "virtio":
            params.append("-device virtio-serial")
            params.append("-device virtconsole,chardev=tty")
            params.append("-device virtserialport,chardev=transport")
        else:
            raise NotImplementedError(
                f"Unsupported serial device type {self._serial_type}")

        _, transport_file = self._get_transport()
        params.append(f"-chardev file,id=transport,path={transport_file}")

        if self._virtfs:
            params.append(
                "-virtfs local,"
                f"path={self._virtfs},"
                "mount_tag=host0,"
                "security_model=mapped-xattr,"
                "readonly=on")

        if self._image:
            params.append(f"-drive if=virtio,cache=unsafe,file={self._image}")

        if self._initrd:
            params.append(f"-initrd {self._initrd}")

        if self._kernel:
            console = "ttyS0"
            if self._serial_type == "virtio":
                console = "hvc0"

            params.append(f"-append 'console={console} ignore_loglevel'")
            params.append(f"-kernel {self._kernel}")

        if self._opts:
            params.append(self._opts)

        cmd = f"{self._qemu_cmd} {' '.join(params)}"

        return cmd

    def setup(self, **kwargs: dict) -> None:
        self._logger.info("Initialize SUT")

        self._tmpdir = kwargs.get("tmpdir", None)
        self._user = kwargs.get("user", None)
        self._password = kwargs.get("password", None)
        self._prompt = kwargs.get("prompt", "#")
        self._image = kwargs.get("image", None)
        self._initrd = kwargs.get("initrd", None)
        self._kernel = kwargs.get("kernel", None)
        self._ram = kwargs.get("ram", "2G")
        self._smp = kwargs.get("smp", "2")
        self._virtfs = kwargs.get("virtfs", None)
        self._serial_type = kwargs.get("serial", "isa")
        self._opts = kwargs.get("options", None)

        system = kwargs.get("system", "x86_64")
        self._qemu_cmd = f"qemu-system-{system}"

        if not self._tmpdir or not os.path.isdir(self._tmpdir):
            raise SUTError(
                f"Temporary directory doesn't exist: {self._tmpdir}")

        if self._image and not os.path.isfile(self._image):
            raise SUTError(
                f"Image location doesn't exist: {self._image}")

        if self._kernel and not os.path.isfile(self._kernel):
            raise SUTError(
                f"Kernel location doesn't exist: {self._kernel}")

        if self._initrd and not os.path.isfile(self._initrd):
            raise SUTError(
                f"initrd location doesn't exist: {self._initrd}")

        if not self._ram:
            raise SUTError("RAM is not defined")

        if not self._smp:
            raise SUTError("CPU is not defined")

        if self._virtfs and not os.path.isdir(self._virtfs):
            raise SUTError(
                f"Virtual FS directory doesn't exist: {self._virtfs}")

        if self._serial_type not in ["isa", "virtio"]:
            raise SUTError("Serial protocol must be isa or virtio")

    @property
    def config_help(self) -> dict:
        return {
            "image": "qemu image location",
            "kernel": "kernel image location",
            "initrd": "initrd image location",
            "user": "user name (default: '')",
            "password": "user password (default: '')",
            "prompt": "prompt string (default: '#')",
            "system": "system architecture (default: x86_64)",
            "ram": "RAM of the VM (default: 2G)",
            "smp": "number of CPUs (default: 2)",
            "serial": "type of serial protocol. isa|virtio (default: isa)",
            "virtfs": "directory to mount inside VM",
            "options": "user defined options",
        }

    @property
    def name(self) -> str:
        return "qemu"

    @property
    def parallel_execution(self) -> bool:
        return False

    @property
    async def is_running(self) -> bool:
        if self._proc is None:
            return False

        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(self._proc.wait(), 1e-6)

        return self._proc.returncode is None

    async def ping(self) -> float:
        if not await self.is_running:
            raise SUTError("SUT is not running")

        _, _, exec_time = await self._exec("test .", None)

        return exec_time

    async def _read_stdout(self, size: int, iobuffer: IOBuffer) -> str:
        """
        Read data from stdout.
        """
        data = await self._proc.stdout.read(size)
        rdata = data.decode(encoding="utf-8", errors="replace")

        # write on stdout buffers
        if iobuffer:
            await iobuffer.write(rdata)

        return rdata

    async def _write_stdin(self, data: str) -> None:
        """
        Write data on stdin.
        """
        if not await self.is_running:
            return

        wdata = data.encode(encoding="utf-8")
        try:
            self._proc.stdin.write(wdata)
        except BrokenPipeError as err:
            if not self._stop:
                raise SUTError(err)

    async def _wait_for(self, message: str, iobuffer: IOBuffer) -> str:
        """
        Wait a string from stdout.
        """
        if not await self.is_running:
            return None

        self._logger.info("Waiting for message: %s", repr(message))

        stdout = self._last_read
        self._panic = False

        while True:
            if self._stop or self._panic:
                break

            if not await self.is_running:
                break

            message_pos = stdout.find(message)
            if message_pos != -1:
                self._last_read = stdout[message_pos + len(message):]
                break

            data = await self._read_stdout(1024, iobuffer)
            if data:
                stdout += data

            if "Kernel panic" in stdout:
                # give time to panic message coming out from serial
                await asyncio.sleep(2)

                # read as much data as possible from stdout
                data = await self._read_stdout(1024 * 1024, iobuffer)
                stdout += data

                self._panic = True

        if self._panic:
            # if we ended before raising Kernel panic, we raise the exception
            raise KernelPanicError()

        return stdout

    async def _wait_lockers(self) -> None:
        """
        Wait for SUT lockers to be released.
        """
        async with self._comm_lock:
            pass

        async with self._cmd_lock:
            pass

        async with self._fetch_lock:
            pass

    async def _exec(self, command: str, iobuffer: IOBuffer) -> set:
        """
        Execute a command and return set(stdout, retcode, exec_time).
        """
        self._logger.debug("Execute command: %s", repr(command))

        code = self._generate_string()

        msg = f"echo $?-{code}\n"
        if command and command.rstrip():
            msg = f"{command};" + msg

        self._logger.info("Sending %s", repr(msg))

        t_start = time.time()

        await self._write_stdin(f"{command}; echo $?-{code}\n")
        stdout = await self._wait_for(code, iobuffer)

        exec_time = time.time() - t_start

        retcode = -1

        if not self._stop:
            if stdout and stdout.rstrip():
                match = re.search(f"(?P<retcode>\\d+)-{code}", stdout)
                if not match and not self._stop:
                    raise SUTError(
                        f"Can't read return code from reply {repr(stdout)}")

                # first character is '\n'
                stdout = stdout[1:match.start()]

                try:
                    retcode = int(match.group("retcode"))
                except TypeError:
                    pass

        self._logger.debug(
            "stdout=%s, retcode=%d, exec_time=%d",
            repr(stdout),
            retcode,
            exec_time)

        return stdout, retcode, exec_time

    async def stop(self, iobuffer: IOBuffer = None) -> None:
        if not await self.is_running:
            return

        self._logger.info("Shutting down virtual machine")
        self._stop = True

        try:
            if not self._panic:
                # stop command first
                if self._cmd_lock.locked() or self._fetch_lock.locked():
                    self._logger.info("Stop running command")

                    # send interrupt character (equivalent of CTRL+C)
                    await self._write_stdin('\x03')
                    await self._wait_lockers()

                # logged in -> poweroff
                if self._logged_in:
                    self._logger.info("Poweroff virtual machine")

                    await self._write_stdin("poweroff; poweroff -f\n")

                    while await self.is_running:
                        await self._read_stdout(1024, iobuffer)

                    await self._proc.wait()
        except asyncio.TimeoutError:
            pass
        finally:
            # still running -> stop process
            if await self.is_running:
                self._logger.info("Killing virtual machine")

                self._proc.kill()

                await self._wait_lockers()
                await self._proc.wait()

            self._stop = False

        self._logger.info("Qemu process ended")

    async def communicate(self, iobuffer: IOBuffer = None) -> None:
        if not shutil.which(self._qemu_cmd):
            raise SUTError(f"Command not found: {self._qemu_cmd}")

        if await self.is_running:
            raise SUTError("Virtual machine is already running")

        error = None

        async with self._comm_lock:
            self._logged_in = False

            cmd = self._get_command()

            self._logger.info("Starting virtual machine")
            self._logger.debug(cmd)

            # pylint: disable=consider-using-with
            self._proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT)

            try:
                if self._user:
                    await self._wait_for("login:", iobuffer)
                    await self._write_stdin(f"{self._user}\n")

                    if self._password:
                        await self._wait_for("Password:", iobuffer)
                        await self._write_stdin(f"{self._password}\n")

                    await asyncio.sleep(0.2)

                await self._wait_for(self._prompt, iobuffer)
                await asyncio.sleep(0.2)

                await self._write_stdin("stty -echo; stty cols 1024\n")
                await self._wait_for(self._prompt, None)

                await self._write_stdin("dmesg -D\n")
                await self._wait_for(self._prompt, None)

                _, retcode, _ = await self._exec("export PS1=''", None)
                if retcode != 0:
                    raise SUTError("Can't setup prompt string")

                if self._virtfs:
                    _, retcode, _ = await self._exec(
                        "mount -t 9p -o trans=virtio host0 /mnt", None)
                    if retcode != 0:
                        raise SUTError("Failed to mount virtfs")

                self._logged_in = True

                self._logger.info("Virtual machine started")
            except SUTError as err:
                error = err

        if not self._stop and error:
            # this can happen when shell is available but
            # something happened during commands execution
            await self.stop(iobuffer=iobuffer)

            raise SUTError(error)

    async def run_command(
            self,
            command: str,
            cwd: str = None,
            env: dict = None,
            iobuffer: IOBuffer = None) -> dict:
        if not command:
            raise ValueError("command is empty")

        if not await self.is_running:
            raise SUTError("Virtual machine is not running")

        async with self._cmd_lock:
            self._logger.info("Running command: %s", command)

            if cwd:
                stdout, retcode, _ = await self._exec(f"cd {cwd}", None)
                if retcode != 0:
                    raise SUTError(
                        f"Can't setup current working directory: {stdout}")

            if env:
                for key, value in env.items():
                    stdout, retcode, _ = await self._exec(
                        f"export {key}={value}", None)
                    if retcode != 0:
                        raise SUTError(
                            f"Can't setup env {key}={value}: {stdout}")

            stdout, retcode, exec_time = await self._exec(
                f"{command}",
                iobuffer)

            ret = {
                "command": command,
                "returncode": retcode,
                "stdout": stdout,
                "exec_time": exec_time,
            }

            self._logger.debug(ret)

            return ret

    async def fetch_file(self, target_path: str) -> bytes:
        if not target_path:
            raise ValueError("target path is empty")

        if not await self.is_running:
            raise SUTError("Virtual machine is not running")

        async with self._fetch_lock:
            self._logger.info("Downloading %s", target_path)

            _, retcode, _ = await self._exec(f'test -f {target_path}', None)
            if retcode != 0:
                raise SUTError(f"'{target_path}' doesn't exist")

            transport_dev, transport_path = self._get_transport()

            stdout, retcode, _ = await self._exec(
                f"cat {target_path} > {transport_dev}", None)

            if self._stop:
                return bytes()

            if retcode not in [0, signal.SIGHUP, signal.SIGKILL]:
                raise SUTError(
                    f"Can't send file to {transport_dev}: {stdout}")

            # read back data and send it to the local file path
            file_size = os.path.getsize(transport_path)

            retdata = bytes()

            with open(transport_path, "rb") as transport:
                while not self._stop and self._last_pos < file_size:
                    transport.seek(self._last_pos)
                    data = transport.read(4096)
                    retdata += data

                    self._last_pos = transport.tell()

            self._logger.info("File downloaded")

            return retdata
