"""
Unittests for main module.
"""

import json
import os
import pwd
import sys

import pytest

import libkirk.sut
import libkirk.com
import libkirk.main


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

    @pytest.mark.xfail(reason="This test passes if run alone. capsys bug?")
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
        assert "test00: pass" in out

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
