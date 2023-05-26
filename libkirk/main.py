"""
.. module:: main
    :platform: Linux
    :synopsis: main script

.. moduleauthor:: Andrea Cervesato <andrea.cervesato@suse.com>
"""
import os
import re
import asyncio
import argparse
import libkirk
import libkirk.sut
import libkirk.data
import libkirk.events
import libkirk.plugin
from libkirk import KirkException
from libkirk.sut import SUT
from libkirk.sut import SUTError
from libkirk.framework import Framework
from libkirk.framework import FrameworkError
from libkirk.ui import SimpleUserInterface
from libkirk.ui import VerboseUserInterface
from libkirk.ui import ParallelUserInterface
from libkirk.session import Session
from libkirk.tempfile import TempDir

# runtime loaded SUT(s)
LOADED_SUT = []

# runtime loaded Framework(s)
LOADED_FRAMEWORK = []

# return codes of the application
RC_OK = 0
RC_ERROR = 1
RC_INTERRUPT = 130


def _from_params_to_config(params: list) -> dict:
    """
    Return a configuration as dictionary according with input parameters
    given to the commandline option.
    """
    config = {}
    for param in params:
        if '=' not in param:
            raise argparse.ArgumentTypeError(
                f"Missing '=' assignment in '{param}' parameter")

        data = param.split('=', 1)
        key = data[0]
        value = data[1]

        if not key:
            raise argparse.ArgumentTypeError(
                f"Empty key for '{param}' parameter")

        if not key:
            raise argparse.ArgumentTypeError(
                f"Empty value for '{param}' parameter")

        config[key] = value

    return config


def _dict_config(opt_name: str, plugins: list, value: str) -> dict:
    """
    Generic dictionary option configuration.
    """
    if value == "help":
        msg = f"--{opt_name} option supports the following syntax:\n"
        msg += "\n\t<name>:<param1>=<value1>:<param2>=<value2>:..\n"
        msg += "\nSupported plugins: | "

        for plugin in plugins:
            msg += f"{plugin.name} | "

        msg += '\n'

        for plugin in plugins:
            if not plugin.config_help:
                msg += f"\n{plugin.name} has not configuration\n"
            else:
                msg += f"\n{plugin.name} configuration:\n"
                for opt, desc in plugin.config_help.items():
                    msg += f"\t{opt}: {desc}\n"

        return {"help": msg}

    if not value:
        raise argparse.ArgumentTypeError("Parameters list can't be empty")

    params = value.split(':')
    name = params[0]

    config = _from_params_to_config(params[1:])
    config['name'] = name

    return config


def _sut_config(value: str) -> dict:
    """
    Return a SUT configuration according with input string.
    """
    return _dict_config("sut", LOADED_SUT, value)


def _framework_config(value: str) -> dict:
    """
    Return a Framework configuration according with input string.
    """
    return _dict_config("framework", LOADED_FRAMEWORK, value)


def _env_config(value: str) -> dict:
    """
    Return an environment configuration dictionary, parsing strings such as
    "key=value:key=value:key=value".
    """
    if not value:
        return None

    params = value.split(':')
    config = _from_params_to_config(params)

    return config


def _discover_sut(path: str) -> None:
    """
    Discover new SUT implementations.
    """
    objs = libkirk.plugin.discover(SUT, path)
    LOADED_SUT.extend(objs)


def _discover_frameworks(path: str) -> None:
    """
    Discover new Framework implementations.
    """
    objs = libkirk.plugin.discover(Framework, path)
    LOADED_FRAMEWORK.extend(objs)


def _get_plugin(plugins: list, name: str) -> object:
    """
    Return the Plugin object with given name.
    """
    obj = None
    for obj_comp in plugins:
        if obj_comp.name == name:
            obj = obj_comp
            break

    return obj


def _get_skip_tests(skip_tests: str, skip_file: str) -> str:
    """
    Return the skipped tests regexp.
    """
    skip = ""

    if skip_file:
        lines = None
        with open(skip_file, 'r', encoding="utf-8") as skip_file_data:
            lines = skip_file_data.readlines()

        toskip = [
            line.rstrip()
            for line in lines
            if not re.search(r'^\s+#.*', line)
        ]
        skip = '|'.join(toskip)

    if skip_tests:
        if skip_file:
            skip += "|"

        skip += skip_tests

    return skip


# pylint: disable=too-many-statements
def _start_session(
        args: argparse.Namespace,
        parser: argparse.ArgumentParser) -> None:
    """
    Start the LTP session.
    """
    skip_tests = _get_skip_tests(args.skip_tests, args.skip_file)
    if skip_tests:
        try:
            re.compile(skip_tests)
        except re.error:
            parser.error(f"'{skip_tests}' is not a valid regular expression")

    # create session object
    tmpdir = None
    if args.tmp_dir == '':
        tmpdir = TempDir(None)
    elif args.tmp_dir:
        tmpdir = TempDir(args.tmp_dir)
    else:
        tmpdir = TempDir("/tmp")

    # get the current SUT
    sut_name = args.sut["name"]
    sut = _get_plugin(LOADED_SUT, sut_name)
    if not sut:
        parser.error(f"'{sut_name}' SUT is not available")

    sut_config = args.sut.copy()
    sut_config["tmpdir"] = tmpdir.abspath
    try:
        sut.setup(**sut_config)
    except SUTError as err:
        parser.error(str(err))

    # get the current Framework
    fw_name = args.framework["name"]
    framework = _get_plugin(LOADED_FRAMEWORK, fw_name)
    if not framework:
        parser.error(f"'{fw_name}' framework is not available")

    fw_config = args.framework.copy()
    if args.env:
        fw_config['env'] = args.env.copy()
    try:
        framework.setup(**fw_config)
    except FrameworkError as err:
        parser.error(str(err))

    # start session
    session = Session(
        sut=sut,
        framework=framework,
        tmpdir=tmpdir,
        exec_timeout=args.exec_timeout,
        suite_timeout=args.suite_timeout,
        workers=args.workers,
        force_parallel=args.force_parallel,
        skip_tests=skip_tests)

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

    async def session_run() -> None:
        """
        Run session then stop events handler.
        """
        await session.run(
            command=args.run_command,
            suites=args.run_suite,
            report_path=args.json_report
        )
        await libkirk.events.stop()

    try:
        libkirk.run(asyncio.gather(*[
            libkirk.create_task(libkirk.events.start()),
            session_run()
        ]))
    except KeyboardInterrupt:
        exit_code = RC_INTERRUPT
    except KirkException:
        exit_code = RC_ERROR

    parser.exit(exit_code)


def run(cmd_args: list = None) -> None:
    """
    Entry point of the application.
    """
    currdir = os.path.dirname(os.path.realpath(__file__))
    _discover_sut(currdir)
    _discover_frameworks(currdir)

    parser = argparse.ArgumentParser(
        description='Kirk - All-in-one Linux Testing Framework')

    # user interface arguments
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Verbose mode")
    parser.add_argument(
        "--no-colors",
        "-n",
        action="store_true",
        help="If defined, no colors are shown")

    # generic directories arguments
    parser.add_argument(
        "--tmp-dir",
        "-d",
        type=str,
        default="/tmp",
        help="Temporary directory")

    # tests setup arguments
    parser.add_argument(
        "--env",
        "-e",
        type=_env_config,
        help="List of key=value environment values separated by ':'")
    parser.add_argument(
        "--skip-tests",
        "-i",
        type=str,
        help="Skip specific tests")
    parser.add_argument(
        "--skip-file",
        "-I",
        type=str,
        help="Skip specific tests using a skip file (newline separated item)")
    parser.add_argument(
        "--suite-timeout",
        "-T",
        type=int,
        default=3600,
        help="Timeout before stopping the suite")
    parser.add_argument(
        "--exec-timeout",
        "-t",
        type=int,
        default=3600,
        help="Timeout before stopping a single execution")

    # tests execution arguments
    parser.add_argument(
        "--run-suite",
        "-r",
        nargs="*",
        help="List of suites to run")
    parser.add_argument(
        "--run-command",
        "-c",
        help="Command to run")
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=1,
        help="Number of workers to execute tests in parallel")
    parser.add_argument(
        "--force-parallel",
        "-p",
        action="store_true",
        help="Force parallelization execution of all tests")

    # session arguments
    parser.add_argument(
        "--sut",
        "-s",
        default="host",
        type=_sut_config,
        help="System Under Test parameters. For help please use '-s help'")
    parser.add_argument(
        "--framework",
        "-f",
        default="ltp",
        type=_framework_config,
        help="Framework parameters. For help please use '-f help'")

    # output arguments
    parser.add_argument(
        "--json-report",
        "-j",
        type=str,
        help="JSON output report")

    # parse comand line
    args = parser.parse_args(cmd_args)

    if args.sut and "help" in args.sut:
        print(args.sut["help"])
        parser.exit(RC_OK)

    if args.framework and "help" in args.framework:
        print(args.framework["help"])
        parser.exit(RC_OK)

    if args.json_report and os.path.exists(args.json_report):
        parser.error(f"JSON report file already exists: {args.json_report}")

    if not args.run_suite and not args.run_command:
        parser.error("--run-suite/--run-cmd are required")

    if args.skip_file and not os.path.isfile(args.skip_file):
        parser.error(f"'{args.skip_file}' skip file doesn't exist")

    if args.tmp_dir and not os.path.isdir(args.tmp_dir):
        parser.error(f"'{args.tmp_dir}' temporary folder doesn't exist")

    _start_session(args, parser)


if __name__ == "__main__":
    run()
