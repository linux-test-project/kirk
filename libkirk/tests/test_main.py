"""
Unittests for main module.
"""

import argparse
import asyncio
import json
import os
import pwd
import sys

import pytest

import libkirk
import libkirk.com
import libkirk.main
import libkirk.sut
from libkirk.evt import EventsHandler


@pytest.fixture(autouse=True)
def isolated_loop(monkeypatch):
    """
    Give every TestMain test its own event loop so that
    libkirk.main.run() cannot cancel tasks belonging to
    other (async) tests, and cannot leave the shared
    session loop in a dirty state.
    """
    # Remember which loop the session is using so we can restore it.
    session_loop = libkirk.get_event_loop()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Re-discover plugins now that the isolated loop is current, so that
    # every asyncio.Lock() inside plugin __init__ methods binds to this loop.
    currdir = os.path.dirname(os.path.realpath(libkirk.com.__file__))
    libkirk.com.discover(os.path.join(currdir, "channels"), extend=False)
    libkirk.sut.discover(currdir, extend=False)

    fresh_events = EventsHandler()
    monkeypatch.setattr(libkirk, "get_event_loop", lambda: loop)
    monkeypatch.setattr(libkirk, "events", fresh_events)

    yield loop

    # Drain and close the isolated loop.
    try:
        libkirk.cancel_tasks(loop)
        if not loop.is_closed():
            loop.run_until_complete(fresh_events.stop())
    finally:
        if not loop.is_closed():
            loop.close()
        # Restore the session loop so subsequent async tests still work.
        asyncio.set_event_loop(session_loop)


class TestHelpers:
    """
    Test helper functions in the main module.
    """

    def test_from_params_missing_equals(self):
        with pytest.raises(argparse.ArgumentTypeError, match="Missing '='"):
            libkirk.main._from_params_to_config(["noequalssign"])

    def test_from_params_empty_key(self):
        with pytest.raises(argparse.ArgumentTypeError, match="Empty key"):
            libkirk.main._from_params_to_config(["=value"])

    def test_from_params_empty_value(self):
        with pytest.raises(argparse.ArgumentTypeError, match="Empty value"):
            libkirk.main._from_params_to_config(["key="])

    def test_dict_config_empty(self):
        with pytest.raises(argparse.ArgumentTypeError, match="can't be empty"):
            libkirk.main._dict_config("")

    def test_time_config_invalid(self):
        with pytest.raises(argparse.ArgumentTypeError, match="Incorrect time"):
            libkirk.main._time_config("abc")

    def test_time_config_minutes(self):
        assert libkirk.main._time_config("5m") == 300

    def test_time_config_hours(self):
        assert libkirk.main._time_config("2h") == 7200

    def test_time_config_days(self):
        assert libkirk.main._time_config("1d") == 86400

    def test_time_config_seconds_suffix(self):
        assert libkirk.main._time_config("30s") == 30

    def test_time_config_no_suffix(self):
        assert libkirk.main._time_config("60") == 60

    def test_iterate_config_empty(self):
        assert libkirk.main._iterate_config("") == 1

    def test_iterate_config_zero(self):
        assert libkirk.main._iterate_config("0") == 1

    def test_finjection_config_empty(self):
        assert libkirk.main._finjection_config("") == 0

    def test_finjection_config_over_100(self):
        assert libkirk.main._finjection_config("200") == 100

    def test_finjection_config_negative(self):
        assert libkirk.main._finjection_config("-5") == 0

    def test_get_skip_tests_empty(self):
        assert libkirk.main._get_skip_tests("", "") == ""

    def test_get_skip_tests_with_file(self, tmpdir):
        skipfile = tmpdir / "skip"
        skipfile.write("test01\n# comment\ntest02\n\n")
        result = libkirk.main._get_skip_tests("", str(skipfile))
        assert result == "test01|test02"

    def test_get_skip_tests_combined(self, tmpdir):
        skipfile = tmpdir / "skip"
        skipfile.write("test01\n")
        result = libkirk.main._get_skip_tests("test02", str(skipfile))
        assert result == "test01|test02"


class TestMainErrors:
    """
    Test error paths in argument validation.
    """

    def test_no_run_option(self):
        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=["--sut", "default"])
        assert excinfo.value.code == 2

    def test_run_pattern_without_suite(self):
        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=["--run-pattern", "test.*"])
        assert excinfo.value.code == 2

    def test_invalid_plugins_dir(self):
        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(
                cmd_args=["--plugins", "/nonexistent", "--sut", "help"]
            )
        assert excinfo.value.code == 2

    def test_invalid_tmp_dir(self):
        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(
                cmd_args=[
                    "--tmp-dir", "/nonexistent_dir",
                    "--run-command", "ls",
                ]
            )
        assert excinfo.value.code == 2

    def test_invalid_skip_file(self):
        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(
                cmd_args=[
                    "--skip-file", "/nonexistent",
                    "--run-suite", "suite01",
                ]
            )
        assert excinfo.value.code == 2

    def test_json_report_exists(self, tmpdir):
        report = tmpdir / "report.json"
        report.write("{}")

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(
                cmd_args=[
                    "--tmp-dir", str(tmpdir),
                    "--json-report", str(report),
                    "--run-suite", "suite01",
                ]
            )
        assert excinfo.value.code == 2

    def test_com_help(self):
        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=["--com", "help"])
        assert excinfo.value.code == libkirk.main.RC_OK

    def test_com_invalid_name(self):
        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(
                cmd_args=[
                    "--com", "nonexistent",
                    "--run-command", "ls",
                ]
            )
        assert excinfo.value.code == 2


class TestMain:
    """
    The the main module entry point.
    """

    @pytest.fixture(autouse=True)
    def setup(self, ltpdir):
        """
        Create and initialize LTP root directory.
        """
        pass

    def read_report(self, temp) -> dict:
        """
        Check if report file contains the given number of tests.
        """
        name = pwd.getpwuid(os.getuid()).pw_name
        report = str(temp / f"kirk.{name}" / "latest" / "results.json")
        assert os.path.isfile(report)

        # read report and check if all suite's tests have been executed
        report_d = None
        with open(report, "r", encoding="utf-8") as report_f:
            report_d = json.loads(report_f.read())

        return report_d

    def test_wrong_options(self):
        """
        Test wrong options.
        """
        cmd_args = ["--run-command1234", "ls"]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == 2

    def test_run_command(self, tmpdir):
        """
        Test --run-command option.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = ["--tmp-dir", str(temp), "--run-command", "ls"]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

    @pytest.mark.skipif(sys.version_info < (3, 8), reason="requires python3.8+")
    def test_run_command_timeout(self, tmpdir):
        """
        Test --run-command option with timeout.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir",
            str(temp),
            "--run-command",
            "ls",
            "--exec-timeout",
            "0",
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_ERROR

    def test_run_suite(self, tmpdir):
        """
        Test --run-suite option.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir",
            str(temp),
            "--run-suite",
            "suite01",
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        report = self.read_report(temp)
        assert len(report["results"]) == 2

    def test_run_suite_timeout(self, tmpdir):
        """
        Test --run-suite option with timeout.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir",
            str(temp),
            "--run-suite",
            "suite01",
            "--suite-timeout",
            "0",
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        report = self.read_report(temp)
        assert len(report["results"]) == 2

        for param in report["results"]:
            assert param["test"]["passed"] == 0
            assert param["test"]["failed"] == 0
            assert param["test"]["broken"] == 0
            assert param["test"]["warnings"] == 0
            assert param["test"]["skipped"] == 1

    def test_run_suite_verbose(self, tmpdir, capsys):
        """
        Test --run-suite option with --verbose.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir",
            str(temp),
            "--run-suite",
            "suite01",
            "--verbose",
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        captured = capsys.readouterr()
        assert "echo -n ciao\n" in captured.out

    def test_run_suite_no_colors(self, tmpdir, capsys):
        """
        Test --run-suite option with --no-colors.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir",
            str(temp),
            "--run-suite",
            "suite01",
            "--no-colors",
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        out, _ = capsys.readouterr()
        assert "Passed:   2" in out

    def test_restore_suite(self, tmpdir):
        """
        Test --restore option.
        """
        temp = tmpdir.mkdir("temp")

        # run a normal session
        cmd_args = [
            "--tmp-dir",
            str(temp),
            "--run-suite",
            "suite01",
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        report = self.read_report(temp)
        assert len(report["results"]) == 2

        # restore session
        name = pwd.getpwuid(os.getuid()).pw_name
        cmd_args = [
            "--tmp-dir",
            str(temp),
            "--restore",
            f"{str(temp)}/kirk.{name}/latest",
            "--run-suite",
            "suite01",
            "environ",
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        report = self.read_report(temp)
        assert len(report["results"]) == 1

    def test_json_report(self, tmpdir):
        """
        Test --json-report option.
        """
        temp = tmpdir.mkdir("temp")
        report = str(tmpdir / "report.json")
        cmd_args = [
            "--tmp-dir",
            str(temp),
            "--run-suite",
            "suite01",
            "--json-report",
            report,
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK
        assert os.path.isfile(report)

        report_a = self.read_report(temp)
        assert len(report_a["results"]) == 2

        report_b = None
        with open(report, "r", encoding="utf-8") as report_f:
            report_b = json.loads(report_f.read())

        assert report_a == report_b

    def test_skip_tests(self, tmpdir):
        """
        Test --skip-tests option.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir",
            str(temp),
            "--run-suite",
            "suite01",
            "--skip-tests",
            "test0[23]",
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        report = self.read_report(temp)
        assert len(report["results"]) == 1

    def test_skip_file(self, tmpdir):
        """
        Test --skip-file option.
        """
        skipfile = tmpdir / "skipfile"
        skipfile.write("test02\ntest03")

        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir",
            str(temp),
            "--run-suite",
            "suite01",
            "--skip-file",
            str(skipfile),
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        report = self.read_report(temp)
        assert len(report["results"]) == 1

    def test_skip_tests_and_file(self, tmpdir):
        """
        Test --skip-file option with --skip-tests.
        """
        skipfile = tmpdir / "skipfile"
        skipfile.write("test03")

        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir",
            str(temp),
            "--run-suite",
            "suite01",
            "--skip-tests",
            "test01",
            "--skip-file",
            str(skipfile),
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        report = self.read_report(temp)
        assert len(report["results"]) == 1

    def test_workers(self, tmpdir):
        """
        Test --workers option.
        """
        temp = tmpdir.mkdir("temp")

        # run on multiple workers
        cmd_args = [
            "--tmp-dir",
            str(temp),
            "--run-suite",
            "suite01",
            "--workers",
            str(os.cpu_count()),
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        report = self.read_report(temp)
        assert len(report["results"]) == 2

    def test_sut_help(self):
        """
        Test "--sut help" command and check if SUT class(es) are loaded.
        """
        cmd_args = ["--sut", "help"]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK
        assert len(libkirk.sut.get_suts()) > 0

    def test_suite_iterate(self, tmpdir):
        """
        Test --suite-iterate option.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir",
            str(temp),
            "--run-suite",
            "suite01",
            "--suite-iterate",
            "4",
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        report = self.read_report(temp)
        assert len(report["results"]) == 8

    def test_randomize(self, tmpdir):
        """
        Test --randomize option.
        """
        num_of_suites = 10

        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir",
            str(temp),
            "--run-suite",
        ]
        cmd_args.extend(["suite01"] * num_of_suites)
        cmd_args.append("--randomize")

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        report = self.read_report(temp)
        assert len(report["results"]) == 2 * num_of_suites

        tests_names = []
        for test in report["results"]:
            tests_names.append(test["test_fqn"])

        assert ["test01", "test02"] * num_of_suites != tests_names

    def test_runtime(self, tmpdir):
        """
        Test --runtime option.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir",
            str(temp),
            "--run-suite",
            "suite01",
            "--runtime",
            "1",
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        report = self.read_report(temp)
        assert len(report["results"]) >= 2

    def test_plugins_channels(self, tmpdir):
        """
        Test --plugins discovery option with ComChannel.
        """
        impl = tmpdir / "chan.py"
        impl.write(
            "from libkirk.com import ComChannel\n\n"
            "class MyChannel(ComChannel):\n"
            "    @property\n"
            "    def name(self) -> str:\n"
            "        return 'mychan'"
        )

        cmd_args = [
            "--plugins",
            str(tmpdir),
            "--sut",
            "help"
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        channels = libkirk.com.get_channels()

        assert len(channels) > 0
        assert [item for item in channels if item.name == "mychan"]

    def test_plugins_suts(self, tmpdir):
        """
        Test --plugins discovery option with SUT.
        """
        impl = tmpdir / "sut.py"
        impl.write(
            "from libkirk.sut_base import GenericSUT\n\n"
            "class MySUT(GenericSUT):\n"
            "    @property\n"
            "    def name(self) -> str:\n"
            "        return 'mysut'"
        )

        cmd_args = [
            "--plugins",
            str(tmpdir),
            "--sut",
            "help"
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        suts = libkirk.sut.get_suts()

        assert len(suts) > 0
        assert [item for item in suts if item.name == "mysut"]

    def test_com(self, tmpdir):
        """
        Test --com option.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir",
            str(temp),
            "--com",
            "shell:id=myshell",
            "--sut",
            "default:com=myshell",
            "--run-suite",
            "suite01",
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        names = [com.name for com in libkirk.com.get_channels()]
        assert "myshell" in names
