"""
.. module:: main
    :platform: Linux
    :synopsis: main script

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""

import argparse
import asyncio
import os
import re
from typing import Dict, List, Optional, Union

import libkirk
import libkirk.com
import libkirk.data
import libkirk.plugin
import libkirk.sut
from libkirk import __version__
from libkirk.com import ComChannel
from libkirk.errors import CommunicationError, FrameworkError, KirkException, SUTError
from libkirk.framework import Framework
from libkirk.monitor import JSONFileMonitor
from libkirk.session import Session
from libkirk.sut import SUT
from libkirk.tempfile import TempDir
from libkirk.ui import ParallelUserInterface, SimpleUserInterface, VerboseUserInterface

# Maximum number of COM instances
MAX_COM_INSTANCES = 128

# runtime loaded Framework(s)
LOADED_FRAMEWORK = []

# return codes of the application
RC_OK = 0
RC_ERROR = 1
RC_INTERRUPT = 130


def _from_params_to_config(params: List[str]) -> Dict[str, str]:
    """
    Return a configuration as dictionary according with input parameters
    given to the commandline option.
    """
    config = {}
    for param in params:
        if "=" not in param:
            raise argparse.ArgumentTypeError(
                f"Missing '=' assignment in '{param}' parameter"
            )

        data = param.split("=", 1)
        key = data[0]
        value = data[1]

        if not key:
            raise argparse.ArgumentTypeError(f"Empty key for '{param}' parameter")

        if not key:
            raise argparse.ArgumentTypeError(f"Empty value for '{param}' parameter")

        config[key] = value

    return config


def _dict_config(
    opt_name: str,
    plugins: Union[List[ComChannel], List[SUT]],
    value: str,
) -> Dict[str, str]:
    """
    Generic dictionary option configuration.
    """
    if value == "help":
        return {"help": ""}

    if not value:
        raise argparse.ArgumentTypeError("Parameters list can't be empty")

    params = value.split(":")

    config = _from_params_to_config(params[1:])
    config["name"] = params[0]

    return config


def _com_config(value: str) -> Optional[Dict[str, str]]:
    """
    Return the list of channels configurations.
    """
    plugins = libkirk.com.get_channels()
    config = _dict_config("com", plugins, value)

    if "help" in config:
        return config

    name = config["name"]

    if name not in [p.name for p in plugins]:
        raise argparse.ArgumentTypeError(
            f"Can't find communication handler with name '{name}'"
        )

    return config


def _print_plugin_help(
    opt_name: str,
    plugins: Union[List[ComChannel], List[SUT]],
) -> None:
    """
    Print the ``plugins`` help for ``opt_name`` option.
    """
    msg = f"{opt_name} option supports the following syntax:\n"
    msg += "\n\t<name>:<param1>=<value1>:<param2>=<value2>:..\n"
    msg += "\nSupported plugins: | "

    for plugin in plugins:
        msg += f"{plugin.name} | "

    msg += "\n"

    for plugin in plugins:
        if not plugin.config_help:
            msg += f"\n{plugin.name} has not configuration\n"
        else:
            msg += f"\n{plugin.name} configuration:\n"
            for opt, desc in plugin.config_help.items():
                msg += f"\t{opt}: {desc}\n"

    print(msg)


def _env_config(value: str) -> Optional[Dict[str, str]]:
    """
    Return an environment configuration dictionary, parsing strings such as
    "key=value:key=value:key=value".
    """
    if not value:
        return None

    params = value.split(":")
    config = _from_params_to_config(params)

    return config


def _iterate_config(value: str) -> int:
    """
    Return the iterate value.
    """
    if not value:
        return 1

    ret = 1
    try:
        ret = int(value)
    except TypeError as err:
        raise argparse.ArgumentTypeError("Invalid number") from err

    if ret <= 1:
        return 1

    return ret


def _time_config(data: str) -> int:
    """
    Return the time in seconds from '30s', '4m', '5h', '20d' format.
    If no suffix is specified, value is considered in seconds.
    """
    indata = data.strip()

    match = re.search(r"^(?P<value>\d+)\s*(?P<suffix>[smhd]?)$", indata)
    if not match:
        raise argparse.ArgumentTypeError(f"Incorrect time format '{indata}'")

    value = int(match.group("value"))
    suffix = match.group("suffix")

    if not suffix or suffix == "s":
        return value

    if suffix == "m":
        value *= 60
    elif suffix == "h":
        value *= 3600
    elif suffix == "d":
        value *= 3600 * 24

    return value


def _finjection_config(value: str) -> int:
    """
    Return probability of fault injection.
    """
    if not value:
        return 0

    ret = 0
    try:
        ret = int(value)
    except TypeError as err:
        raise argparse.ArgumentTypeError("Invalid number") from err

    if ret < 0:
        return 0

    if ret > 100:
        return 100

    return ret


def _discover_frameworks(path: str) -> None:
    """
    Discover new Framework implementations.
    """
    objs = libkirk.plugin.discover(Framework, path)
    LOADED_FRAMEWORK.extend(objs)


def _get_skip_tests(skip_tests: str, skip_file: str) -> str:
    """
    Return the skipped tests regexp.
    """
    skip = ""

    if skip_file:
        lines = None
        with open(skip_file, "r", encoding="utf-8") as skip_file_data:
            lines = skip_file_data.readlines()

        toskip = [line.rstrip() for line in lines if not re.search(r"^\s+#.*", line)]
        skip = "|".join(toskip)

    if skip_tests:
        if skip_file:
            skip += "|"

        skip += skip_tests

    return skip


def _init_channels(
    args: argparse.Namespace, parser: argparse.ArgumentParser, tmpdir: TempDir
) -> None:
    """
    Initialize channels according to configuration.
    """
    for config in args.com:
        plugin = None

        if "id" in config:
            plugin = libkirk.com.clone_channel(config["name"], config["id"])
        else:
            name = config["name"]
            plugin = next(
                (c for c in libkirk.com.get_channels() if c.name == name),
                None,
            )

            assert plugin

        com_config = config.copy()
        com_config["tmpdir"] = tmpdir.abspath

        try:
            # pyrefly: ignore[bad-argument-type]
            plugin.setup(**com_config)
        except CommunicationError as err:
            parser.error(str(err))


def _get_sut(
    args: argparse.Namespace, parser: argparse.ArgumentParser, tmpdir: TempDir
) -> SUT:
    """
    Create and return SUT object.
    """
    sut_config = args.sut.copy()
    sut_config["tmpdir"] = tmpdir.abspath

    sut_name = args.sut["name"]
    sut = next((s for s in libkirk.sut.get_suts() if s.name == sut_name), None)
    if not sut:
        parser.error(f"'{sut_name}' SUT is not available")

    try:
        # pyrefly: ignore[missing-attribute]
        sut.setup(**sut_config)
    except SUTError as err:
        parser.error(str(err))

    # pyrefly: ignore[bad-return]
    return sut


def _get_framework(
    args: argparse.Namespace, parser: argparse.ArgumentParser
) -> Framework:
    """
    Create and framework object.
    """
    fw_config = args.framework.copy()
    if args.env:
        fw_config["env"] = args.env.copy()

    if args.exec_timeout:
        fw_config["test_timeout"] = args.exec_timeout

    if args.suite_timeout:
        fw_config["suite_timeout"] = args.suite_timeout

    fw_name = args.framework["name"]
    fw = next((f for f in LOADED_FRAMEWORK if f.name == fw_name), None)
    if not fw:
        parser.error(f"'{fw_name}' framework is not available")

    try:
        # pyrefly: ignore[missing-attribute]
        fw.setup(**fw_config)
    except FrameworkError as err:
        parser.error(str(err))

    # pyrefly: ignore[bad-return]
    return fw


def _start_session(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    """
    Start the LTP session.
    """
    skip_tests = _get_skip_tests(args.skip_tests, args.skip_file)
    if skip_tests:
        try:
            re.compile(skip_tests)
        except re.error:
            parser.error(f"'{skip_tests}' is not a valid regular expression")

    # check if session can be restored
    restore_dir = args.restore
    if restore_dir and os.path.islink(args.restore):
        restore_dir = os.readlink(args.restore)

    if restore_dir and not os.path.isdir(restore_dir):
        parser.error(f"Can't restore '{args.restore}'. Folder doesn't exist")

    # create temporary directory
    tmpdir = None
    if args.tmp_dir == "":
        tmpdir = TempDir(None)
    elif args.tmp_dir:
        tmpdir = TempDir(args.tmp_dir)
    else:
        tmpdir = TempDir("/tmp")

    # initialize channels
    if args.com:
        _init_channels(args, parser, tmpdir)

    # create SUT and Framework objects
    sut = _get_sut(args, parser, tmpdir)
    framework = _get_framework(args, parser)

    # start session
    session = Session(
        sut=sut,
        framework=framework,
        tmpdir=tmpdir,
        exec_timeout=args.exec_timeout,
        suite_timeout=args.suite_timeout,
        workers=args.workers,
        force_parallel=args.force_parallel,
    )

    # initialize monitor file
    monitor = None
    if args.monitor:
        monitor = JSONFileMonitor(args.monitor)

    # initialize user interface
    if args.workers > 1:
        ParallelUserInterface(args.no_colors)
    else:
        if args.verbose:
            VerboseUserInterface(args.no_colors)
        else:
            SimpleUserInterface(args.no_colors)

    # start event loop
    exit_code = RC_OK

    # read tests regex filter
    run_pattern = args.run_pattern
    if run_pattern:
        try:
            re.compile(run_pattern)
        except re.error:
            parser.error(f"'{run_pattern}' is not a valid regular expression")

    async def session_run() -> None:
        """
        Run session then stop events handler.
        """
        try:
            if monitor:
                await monitor.start()

            await session.run(
                command=args.run_command,
                suites=args.run_suite,
                pattern=run_pattern,
                report_path=args.json_report,
                restore_path=restore_dir,
                suite_iterate=args.suite_iterate,
                skip_tests=skip_tests,
                randomize=args.randomize,
                runtime=args.runtime,
                fault_prob=args.fault_injection,
            )
        except asyncio.CancelledError:
            await session.stop()
        finally:
            await libkirk.events.stop()
            if monitor:
                await monitor.stop()

    loop = libkirk.get_event_loop()
    exit_code = RC_OK

    try:
        loop.run_until_complete(
            # pyrefly: ignore[bad-argument-type]
            asyncio.gather(*[libkirk.events.start(), session_run()])
        )
    except KeyboardInterrupt:
        exit_code = RC_INTERRUPT
    except KirkException:
        exit_code = RC_ERROR
    finally:
        try:
            # at this point loop has been closed, so we can collect all
            # tasks and cancel them
            loop.run_until_complete(
                # pyrefly: ignore[bad-argument-type]
                asyncio.gather(
                    *[
                        session.stop(),
                        libkirk.events.stop(),
                    ]
                )
            )
            libkirk.cancel_tasks(loop)
        except KeyboardInterrupt:
            pass

    parser.exit(exit_code)


def run(cmd_args: Optional[List[str]] = None) -> None:
    """
    Entry point of the application.
    """
    currdir = os.path.dirname(os.path.realpath(__file__))

    libkirk.com.discover(os.path.join(currdir, "channels"))
    libkirk.sut.discover(currdir)

    _discover_frameworks(currdir)

    parser = argparse.ArgumentParser(
        description="Kirk - All-in-one Linux Testing Framework"
    )

    generic_opts = parser.add_argument_group("General options")
    generic_opts.add_argument(
        "--version", "-V", action="version", version=f"%(prog)s, {__version__}"
    )
    generic_opts.add_argument(
        "--verbose", "-v", action="store_true", help="Verbose mode"
    )
    generic_opts.add_argument(
        "--no-colors", "-n", action="store_true", help="If defined, no colors are shown"
    )
    generic_opts.add_argument(
        "--tmp-dir", "-d", type=str, default="/tmp", help="Temporary directory"
    )
    generic_opts.add_argument(
        "--restore", "-r", type=str, help="Restore a specific session"
    )
    generic_opts.add_argument(
        "--json-report", "-o", type=str, help="JSON output report"
    )
    generic_opts.add_argument(
        "--monitor", "-m", type=str, help="Location of the monitor file"
    )
    generic_opts.add_argument(
        "--plugins", "-P", type=str, help="Location of custom plugins"
    )

    conf_opts = parser.add_argument_group("Configuration options")
    conf_opts.add_argument(
        "--com",
        "-C",
        type=_com_config,
        action="append",
        help="Communication channel parameters. For help please use '--com help'",
    )
    conf_opts.add_argument(
        "--sut",
        "-u",
        default="default",
        type=lambda x: _dict_config("sut", libkirk.sut.get_suts(), x),
        help="System Under Test parameters. For help please use '--sut help'",
    )
    conf_opts.add_argument(
        "--framework",
        "-U",
        default="ltp",
        type=lambda x: _dict_config("framework", LOADED_FRAMEWORK, x),
        help="Framework parameters. For help please use '--framework help'",
    )
    conf_opts.add_argument(
        "--env",
        "-e",
        type=_env_config,
        help="List of key=value environment values separated by ':'",
    )
    conf_opts.add_argument("--skip-tests", "-s", type=str, help="Skip specific tests")
    conf_opts.add_argument(
        "--skip-file",
        "-S",
        type=str,
        help="Skip specific tests using a skip file (newline separated item)",
    )

    exec_opts = parser.add_argument_group("Execution options")
    exec_opts.add_argument("--run-suite", "-f", nargs="*", help="List of suites to run")
    exec_opts.add_argument(
        "--run-pattern", "-p", help="Run all tests matching the regex pattern"
    )
    exec_opts.add_argument("--run-command", "-c", help="Command to run")
    exec_opts.add_argument(
        "--suite-timeout",
        "-T",
        type=_time_config,
        default="1h",
        help="Timeout before stopping the suite (default: 1h)",
    )
    exec_opts.add_argument(
        "--exec-timeout",
        "-t",
        type=_time_config,
        default="1h",
        help="Timeout before stopping a single execution (default: 1h)",
    )
    exec_opts.add_argument(
        "--randomize",
        "-R",
        action="store_true",
        help="Force parallelization execution of all tests",
    )
    exec_opts.add_argument(
        "--runtime",
        "-I",
        type=_time_config,
        default="0",
        help="Set for how long we want to run the session in seconds",
    )
    exec_opts.add_argument(
        "--suite-iterate",
        "-i",
        type=_iterate_config,
        default=1,
        help="Number of times to repeat testing suites",
    )
    exec_opts.add_argument(
        "--workers",
        "-w",
        type=int,
        default=1,
        help="Number of workers to execute tests in parallel",
    )
    exec_opts.add_argument(
        "--force-parallel",
        "-W",
        action="store_true",
        help="Force parallelization execution of all tests",
    )
    exec_opts.add_argument(
        "--fault-injection",
        "-F",
        type=_finjection_config,
        default=0,
        help="Probability of failure (0-100)",
    )

    # output arguments
    # parse comand line
    args = parser.parse_args(cmd_args)

    if args.plugins:
        if not os.path.isdir(args.plugins):
            parser.error(f"'{args.plugins}' plugins directory doesn't exist")

        libkirk.com.discover(args.plugins)
        libkirk.sut.discover(args.plugins)

    if args.com and [obj for obj in args.com if "help" in obj]:
        _print_plugin_help("--com", libkirk.com.get_channels())
        parser.exit(RC_OK)

    if args.com and len(args.com) >= MAX_COM_INSTANCES:
        parser.error(f"Maximum number of communication objects is {MAX_COM_INSTANCES}")

    if args.sut and "help" in args.sut:
        _print_plugin_help("--sut", libkirk.sut.get_suts())
        parser.exit(RC_OK)

    if args.framework and "help" in args.framework:
        _print_plugin_help("--framework", LOADED_FRAMEWORK)
        parser.exit(RC_OK)

    if args.json_report and os.path.exists(args.json_report):
        parser.error(f"JSON report file already exists: {args.json_report}")

    if args.run_pattern and not args.run_suite:
        parser.error("--run-pattern must be used with --run-suite")

    if not args.run_suite and not args.run_command:
        parser.error("--run-suite/--run-command are required")

    if args.skip_file and not os.path.isfile(args.skip_file):
        parser.error(f"'{args.skip_file}' skip file doesn't exist")

    if args.tmp_dir and not os.path.isdir(args.tmp_dir):
        parser.error(f"'{args.tmp_dir}' temporary folder doesn't exist")

    _start_session(args, parser)


if __name__ == "__main__":
    run()
