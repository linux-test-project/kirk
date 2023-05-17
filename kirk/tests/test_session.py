"""
Unittests for the session module.
"""
import os
import json
import stat
import asyncio
import pytest
from kirk.host import HostSUT
from kirk.session import Session


pytestmark = pytest.mark.asyncio

# number of tests created inside temporary folder
TESTS_NUM = 9


@pytest.fixture(autouse=True)
def prepare_tmpdir(tmpdir):
    """
    Prepare the temporary directory adding runtest folder.
    """
    content = ""
    for i in range(TESTS_NUM):
        content += f"test0{i} echo ciao\n"

    tmpdir.mkdir("testcases").mkdir("bin")
    runtest = tmpdir.mkdir("runtest")

    for i in range(3):
        suite = runtest / f"suite{i}"
        suite.write(content)


@pytest.fixture
async def sut_config():
    """
    SUT Configuration.
    """
    yield {}


@pytest.fixture
async def sut(sut_config):
    """
    SUT communication object.
    """
    obj = HostSUT()
    obj.setup(*sut_config)
    await obj.communicate()
    yield obj
    await obj.stop()


class TestSession:
    """
    Test for Session class.
    """

    @pytest.fixture
    async def session(self, tmpdir, sut):
        """
        Session communication object.
        """
        session = Session(
            tmpdir=str(tmpdir),
            ltpdir=str(tmpdir),
            sut=sut)

        yield session

        await asyncio.wait_for(session.stop(), timeout=30)

    async def test_run(self, tmpdir, session):
        """
        Test run method when executing suites.
        """
        await session.run(suites=["suite0", "suite1", "suite2"])

        for i in range(3):
            assert os.path.isfile(str(tmpdir / "runtest" / f"suite{i}"))

    async def test_run_skip_tests(self, tmpdir, sut):
        """
        Test run method when executing suites.
        """
        report = str(tmpdir / "report.json")
        session = Session(
            tmpdir=str(tmpdir),
            ltpdir=str(tmpdir),
            sut=sut,
            skip_tests="test0[01]|test0[45]"
        )

        try:
            await session.run(suites=["suite0"], report_path=report)
        finally:
            await asyncio.wait_for(session.stop(), timeout=30)

        assert os.path.isfile(report)

        report_data = None
        with open(report, "r") as report_file:
            report_data = json.loads(report_file.read())

        assert len(report_data["results"]) == TESTS_NUM - 4

    async def test_run_with_report(self, tmpdir, session):
        """
        Test run method when generating report file.
        """
        report = str(tmpdir / "report.json")
        await session.run(suites=["suite0"], report_path=report)

        assert os.path.isfile(report)

        report_data = None
        with open(report, "r") as report_file:
            report_data = json.loads(report_file.read())

        assert len(report_data["results"]) == TESTS_NUM

    async def test_run_stop(self, tmpdir, session):
        """
        Test stop method during run.
        """
        suite = tmpdir / "runtest" / "suite0"

        content = "test0 echo ciao\n"
        content += "test1 echo ciao\n"
        content += "test2 sleep 1; echo ciao\n"
        suite.write(content)

        async def stop():
            await asyncio.sleep(0.2)
            await session.stop()

        report = str(tmpdir / "report.json")
        await asyncio.gather(*[
            session.run(suites=["suite0"], report_path=report),
            stop(),
        ])

        assert os.path.isfile(report)

        report_data = None
        with open(report, "r") as report_file:
            report_data = json.loads(report_file.read())

        assert len(report_data["results"]) == 2

    async def test_run_command(self, sut, session):
        """
        Test run method when running a single command.
        """
        temp_file = "/tmp/file"

        await session.run(command=f"touch {temp_file}")

        await sut.ensure_communicate()
        ret = await sut.run_command(f"test {temp_file}")

        assert ret["returncode"] == 0

    async def test_run_command_stop(self, tmpdir, sut):
        """
        Test stop when runnig a command.
        """
        session = Session(
            tmpdir=str(tmpdir),
            ltpdir=str(tmpdir),
            sut=sut)

        async def stop():
            await asyncio.sleep(0.2)
            await asyncio.wait_for(session.stop(), timeout=30)

        await asyncio.gather(*[
            session.run(command="sleep 1"),
            stop()
        ])

    async def test_env(self, tmpdir, sut):
        """
        Test environment variables injected in the SUT by session object.
        """
        # create runtest file
        suite = tmpdir / "runtest" / "envsuite"
        suite.write("test script.sh")

        # create test script
        script_sh = tmpdir / "testcases" / "bin" / "script.sh"
        script_sh.write("#!/bin/sh\necho -n $VAR0:$VAR1")

        st = os.stat(str(script_sh))
        os.chmod(str(script_sh), st.st_mode | stat.S_IEXEC)

        # run session with environment variables and save report
        report_path = tmpdir / "report.json"
        session = Session(
            tmpdir=str(tmpdir),
            ltpdir=str(tmpdir),
            sut=sut,
            env=dict(VAR0="0", VAR1="1")
        )

        try:
            await session.run(
                report_path=report_path,
                suites=["envsuite"])
        finally:
            await asyncio.wait_for(session.stop(), timeout=30)

        assert os.path.isfile(report_path)

        # read report and check if all tests have been executed
        report_d = None
        with open(report_path, 'r') as report_f:
            report_d = json.loads(report_f.read())

        assert len(report_d["results"]) == 1
        assert report_d["results"][0]["test"]["log"] == "0:1"
