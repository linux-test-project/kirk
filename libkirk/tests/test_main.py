"""
Unittests for main module.
"""
import os
import sys
import pwd
import time
import json
import pytest
import libkirk.main


class TestMain:
    """
    The the main module entry point.
    """

    @pytest.fixture(autouse=True)
    def setup(self, dummy_framework):
        """
        Setup main before running tests.
        """
        libkirk.main.LOADED_FRAMEWORK.append(dummy_framework)

    def read_report(self, temp, tests_num) -> dict:
        """
        Check if report file contains the given number of tests.
        """
        name = pwd.getpwuid(os.getuid()).pw_name
        report = str(temp / f"kirk.{name}" / "latest" / "results.json")
        assert os.path.isfile(report)

        # read report and check if all suite's tests have been executed
        report_d = None
        with open(report, 'r') as report_f:
            report_d = json.loads(report_f.read())

        assert len(report_d["results"]) == tests_num

        return report_d

    def test_wrong_options(self):
        """
        Test wrong options.
        """
        cmd_args = [
            "--run-command1234", "ls"
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == 2

    def test_run_command(self, tmpdir):
        """
        Test --run-command option.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir", str(temp),
            "--run-command", "ls"
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

    @pytest.mark.skipif(sys.version_info < (3,8), reason="requires python3.8+")
    def test_run_command_timeout(self, tmpdir):
        """
        Test --run-command option with timeout.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir", str(temp),
            "--run-command", "ls",
            "--exec-timeout", "0"
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
            "--tmp-dir", str(temp),
            "--framework", "dummy",
            "--run-suite", "suite01"
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        self.read_report(temp, 2)

    def test_run_suite_timeout(self, tmpdir):
        """
        Test --run-suite option with timeout.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir", str(temp),
            "--framework", "dummy",
            "--run-suite", "suite01",
            "--suite-timeout", "0"
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        report_d = self.read_report(temp, 2)
        for param in report_d["results"]:
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
            "--tmp-dir", str(temp),
            "--framework", "dummy",
            "--run-suite", "suite01",
            "--verbose",
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        captured = capsys.readouterr()
        assert "ciao0\n" in captured.out

    @pytest.mark.xfail(reason="This test passes if run alone. capsys bug?")
    def test_run_suite_no_colors(self, tmpdir, capsys):
        """
        Test --run-suite option with --no-colors.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir", str(temp),
            "--framework", "dummy",
            "--run-suite", "suite01",
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
            "--tmp-dir", str(temp),
            "--framework", "dummy",
            "--run-suite", "suite01"
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        self.read_report(temp, 2)

        # restore session
        name = pwd.getpwuid(os.getuid()).pw_name
        cmd_args = [
            "--tmp-dir", str(temp),
            "--restore", f"{str(temp)}/kirk.{name}/latest",
            "--framework", "dummy",
            "--run-suite", "suite01", "environ"
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        self.read_report(temp, 1)

    def test_json_report(self, tmpdir):
        """
        Test --json-report option.
        """
        temp = tmpdir.mkdir("temp")
        report = str(tmpdir / "report.json")
        cmd_args = [
            "--tmp-dir", str(temp),
            "--framework", "dummy",
            "--run-suite", "suite01",
            "--json-report", report
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK
        assert os.path.isfile(report)

        report_a = self.read_report(temp, 2)
        report_b = None
        with open(report, 'r') as report_f:
            report_b = json.loads(report_f.read())

        assert report_a == report_b

    def test_skip_tests(self, tmpdir):
        """
        Test --skip-tests option.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir", str(temp),
            "--framework", "dummy",
            "--run-suite", "suite01",
            "--skip-tests", "test0[12]"
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        self.read_report(temp, 0)

    def test_skip_file(self, tmpdir):
        """
        Test --skip-file option.
        """
        skipfile = tmpdir / "skipfile"
        skipfile.write("test01\ntest02")

        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir", str(temp),
            "--framework", "dummy",
            "--run-suite", "suite01",
            "--skip-file", str(skipfile)
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        self.read_report(temp, 0)

    def test_skip_tests_and_file(self, tmpdir):
        """
        Test --skip-file option with --skip-tests.
        """
        skipfile = tmpdir / "skipfile"
        skipfile.write("test02")

        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir", str(temp),
            "--framework", "dummy",
            "--run-suite", "suite01",
            "--skip-tests", "test01",
            "--skip-file", str(skipfile)
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        self.read_report(temp, 0)

    def test_workers(self, tmpdir):
        """
        Test --workers option.
        """
        temp = tmpdir.mkdir("temp")

        # run on multiple workers
        cmd_args = [
            "--tmp-dir", str(temp),
            "--framework", "dummy",
            "--run-suite", "suite01",
            "--workers", str(os.cpu_count()),
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK
        self.read_report(temp, 2)

    def test_sut_help(self):
        """
        Test "--sut help" command and check if SUT class(es) are loaded.
        """
        cmd_args = [
            "--sut", "help"
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK
        assert len(libkirk.main.LOADED_SUT) > 0

    def test_framework_help(self):
        """
        Test "--framework help" command and check if Framework class(es)
        are loaded.
        """
        cmd_args = [
            "--framework", "help"
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK
        assert len(libkirk.main.LOADED_FRAMEWORK) > 0

    def test_env(self, tmpdir):
        """
        Test --env option.
        """
        temp = tmpdir.mkdir("temp")
        cmd_args = [
            "--tmp-dir", str(temp),
            "--framework", "dummy",
            "--run-suite", "environ",
            "--env", "hello=ciao"
        ]

        with pytest.raises(SystemExit) as excinfo:
            libkirk.main.run(cmd_args=cmd_args)

        assert excinfo.value.code == libkirk.main.RC_OK

        report_d = self.read_report(temp, 1)
        assert report_d["results"][0]["test"]["log"] == "ciao"
