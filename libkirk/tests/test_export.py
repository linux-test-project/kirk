"""
Unit tests for Exporter implementations.
"""
import json
import asyncio
import pytest
from libkirk.data import Test
from libkirk.data import Suite
from libkirk.results import SuiteResults, TestResults, ResultStatus
from libkirk.export import JSONExporter


pytestmark = pytest.mark.asyncio


class TestJSONExporter:
    """
    Test JSONExporter class implementation.
    """

    async def test_save_file_bad_args(self):
        """
        Test save_file method with bad arguments.
        """
        exporter = JSONExporter()

        with pytest.raises(ValueError):
            await exporter.save_file(list(), "")

        with pytest.raises(ValueError):
            await exporter.save_file(None, "")

        with pytest.raises(ValueError):
            await exporter.save_file([0, 1], None)

    async def test_save_file(self, tmpdir):
        """
        Test save_file method.
        """
        # create suite/test metadata objects
        tests = [
            Test(name="ls0", cmd="ls"),
            Test(name="ls1", cmd="ls", args=["-l"]),
            Test(name="ls2", cmd="ls", args=["--error"])
        ]
        suite0 = Suite("ls_suite0", tests)

        # create results objects
        tests_res = [
            TestResults(
                test=tests[0],
                failed=0,
                passed=1,
                broken=0,
                skipped=0,
                warnings=0,
                exec_time=1,
                retcode=0,
                stdout="folder\nfile.txt",
                status=0,
            ),
            TestResults(
                test=tests[1],
                failed=0,
                passed=1,
                broken=0,
                skipped=0,
                warnings=0,
                exec_time=1,
                retcode=0,
                stdout="folder\nfile.txt",
                status=0,
            ),
            TestResults(
                test=tests[2],
                failed=1,
                passed=0,
                broken=0,
                skipped=0,
                warnings=0,
                exec_time=1,
                retcode=1,
                stdout="",
                status=ResultStatus.FAIL,
            ),
        ]

        suite_res = [
            SuiteResults(
                suite=suite0,
                tests=tests_res,
                distro="openSUSE-Leap",
                distro_ver="15.3",
                kernel="5.17",
                arch="x86_64",
                cpu="x86_64",
                swap="10 kB",
                ram="1000 kB",
                exec_time=3),
        ]

        exporter = JSONExporter()
        tasks = []

        for i in range(100):
            output = tmpdir / f"output{i}.json"
            tasks.append(exporter.save_file(suite_res, str(output)))

        await asyncio.gather(*tasks, return_exceptions=True)

        for i in range(100):
            data = None

            output = tmpdir / f"output{i}.json"
            with open(str(output), 'r') as json_data:
                data = json.load(json_data)

            assert len(data["results"]) == 3
            assert data["results"][0] == {
                "test": {
                    "command": "ls",
                    "arguments": [],
                    "failed": 0,
                    "passed": 1,
                    "broken": 0,
                    "skipped": 0,
                    "warnings": 0,
                    "duration": 1,
                    "result": "pass",
                    "log": "folder\nfile.txt",
                    "retval": [
                        "0"
                    ],
                },
                "status": "pass",
                "test_fqn": "ls0",
            }
            assert data["results"][1] == {
                "test": {
                    "command": "ls",
                    "arguments": ["-l"],
                    "failed": 0,
                    "passed": 1,
                    "broken": 0,
                    "skipped": 0,
                    "warnings": 0,
                    "duration": 1,
                    "result": "pass",
                    "log": "folder\nfile.txt",
                    "retval": [
                        "0"
                    ],
                },
                "status": "pass",
                "test_fqn": "ls1",
            }
            assert data["results"][2] == {
                "test": {
                    "command": "ls",
                    "arguments": ["--error"],
                    "failed": 1,
                    "passed": 0,
                    "broken": 0,
                    "skipped": 0,
                    "warnings": 0,
                    "duration": 1,
                    "result": "fail",
                    "log": "",
                    "retval": [
                        "1"
                    ],
                },
                "status": "fail",
                "test_fqn": "ls2",
            }

            assert data["environment"] == {
                "distribution_version": "15.3",
                "distribution": "openSUSE-Leap",
                "kernel": "5.17",
                "arch": "x86_64",
                "cpu": "x86_64",
                "swap": "10 kB",
                "RAM": "1000 kB",
            }
            assert data["stats"] == {
                "runtime": 3,
                "passed": 2,
                "failed": 1,
                "broken": 0,
                "skipped": 0,
                "warnings": 0,
            }
